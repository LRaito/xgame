"""游戏检索索引与游戏榜单的构建。

`make index` 与**服务启动时的自动补建**都走这里的 `build_index()`；服务启动时还会走
`ensure_ranking_loaded()`，把榜单 CSV 就地补进一个已经存在的库。这个模块是
`<根路径>/db/game.db` 的**唯一写入方**；平台运行期的所有读都走
`search_service.GameSearchService` 与 `ranking_service.GameRankingService`，它们一律以
`mode=ro` 打开。所以这里可以放心用「整库重建 + 原子替换」这种最简单也最不容易出错的做法，
不需要增量更新。

数据源两份，都在 `backend/search/` 下：

- `csv/` 下的一份份 `机种,中文,英文` 三列名录（UTF-8 带 BOM、CRLF、无表头），构成检索索引；
- `ranking/ranking.csv` 的四列榜单（`序号,机种名称,游戏名称,游戏卡带ID`），构成游戏榜单。

榜单单独建表、单独一个版本号：它的表结构变化不影响检索的 `schema_version`，补榜单失败也不会
把检索一起变成「版本过旧」。
"""

import csv
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.config import RANKING_CSV_PATH, SEARCH_CSV_DIR, Settings
from backend.games.search_text import index_text

logger = logging.getLogger(__name__)

# 索引结构的版本。改了检索表结构就加一，运行期读到不匹配的版本会直接报「请重新构建」，
# 而不是在旧库上跑出新代码的诡异结果。**榜单表不在这个版本的管理范围内**（见 RANKING_SCHEMA_VERSION）：
# 往老库里加榜单表是纯新增，不该让已经能用的检索库被判成过旧。
SCHEMA_VERSION = "1"

# 榜单表结构的版本，独立于上面的检索版本。
RANKING_SCHEMA_VERSION = "1"

# 建库语句。game_fts 是 contentless（content=''）表：只存倒排索引、不重复存正文，
# 正文永远从 game 表取——所以 snippet()/highlight() 在它上面恒返回 NULL，高亮必须在前端做。
_SEARCH_SCHEMA = """
CREATE TABLE console(
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE game(
    id         INTEGER PRIMARY KEY,
    console_id INTEGER NOT NULL REFERENCES console(id),
    zh         TEXT NOT NULL DEFAULT '',
    en         TEXT NOT NULL DEFAULT '',
    src        TEXT NOT NULL
);

-- 无关键词时按机种分页/排序走这条，不用于搜索
CREATE INDEX idx_game_console ON game(console_id, en);

CREATE VIRTUAL TABLE game_fts USING fts5(
    zh_uni,
    en_uni,
    content='',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# 榜单表。`PRIMARY KEY (console, rank)` 同时满足两种查询：`SELECT DISTINCT console`（小表全扫）
# 与 `WHERE console = ? ORDER BY rank`（主键前缀有序，不必再建索引）。机种存名称而不是外键，
# 因为榜单的机种未必出现在检索名录里，复用 console 表会污染检索的机种下拉。
# cartridge_ids 存 JSON 数组文本：每行 0~2 个，读取时 json.loads 即可，不需要子表与 join。
_RANKING_SCHEMA = """
CREATE TABLE IF NOT EXISTS ranking(
    console       TEXT NOT NULL,
    rank          INTEGER NOT NULL CHECK (rank >= 1),
    title         TEXT NOT NULL,
    cartridge_ids TEXT NOT NULL,
    PRIMARY KEY (console, rank)
) WITHOUT ROWID;
"""

_SCHEMA = _SEARCH_SCHEMA + _RANKING_SCHEMA

# 榜单里同一格最多两个卡带 ID（也可以一个都没有），用这些分隔符分开。**空格不是分隔符**：卡带 ID 里常有空格
# （如 `POKEMON FIRE RED`），按空格拆会把一个 ID 拆成好几个；连字符与下划线同样不分割。
_RANKING_ID_SPLIT = re.compile(r"[、,，/;；]+")
# 允许出现的表头（第一条非空行第一格命中就跳过）。
_RANKING_HEADERS = {"序号", "排名"}
# 榜单 CSV 的列数。
_RANKING_COLUMNS = 4


class IndexBuildError(Exception):
    """构建失败。message 是给用户看的中文，`backend/cli.py` 直接打印。"""


class RankingCsvError(IndexBuildError):
    """榜单 CSV 内容不合法（列数、序号、空字段、卡带 ID 数量等）。"""


@dataclass(frozen=True)
class BuildStats:
    rows: int
    consoles: int
    seconds: float
    size: int
    path: Path
    ranking_rows: int = 0
    ranking_consoles: int = 0


@dataclass(frozen=True)
class RankingRow:
    console: str
    rank: int
    title: str
    cartridge_ids: tuple[str, ...]


@dataclass(frozen=True)
class RankingData:
    rows: tuple[RankingRow, ...]
    consoles: tuple[str, ...]
    fingerprint: str
    source: str


@dataclass(frozen=True)
class RankingLoadStats:
    rows: int
    consoles: int
    fingerprint: str


# `ensure_game_index(ranking_csv=...)` 的默认值：区分「没传，用 RANKING_CSV_PATH」与
# 「显式传 None，本次不处理榜单」——测试要能 monkeypatch 模块常量，也要能关掉榜单。
_DEFAULT_RANKING = object()


def ensure_game_index(
    settings: Settings,
    *,
    csv_dir: Path | None = None,
    ranking_csv: Path | None | object = _DEFAULT_RANKING,
) -> BuildStats | None:
    """启动时补一次索引：**没有才建**，已经存在就跳过；榜单另外就地补一次。

    服务起来后自检一次，用户就不用为了第一次能用检索页去手工跑命令；`make index` 仍然是
    手动重建/更新索引的入口（换 CSV、改分词规则之后用它覆盖）。

    全程 best-effort，**绝不拦住启动**：建不出来最多是检索页提示「尚未构建索引」、
    榜单页提示「榜单尚未加载」（例如数据根没有写权限、或 CSV 被人删掉了）。
    """
    if settings.TESTING:
        return None

    if ranking_csv is _DEFAULT_RANKING:
        ranking_path: Path | None = RANKING_CSV_PATH
    else:
        ranking_path = Path(ranking_csv) if ranking_csv else None

    target = settings.game_index_path
    if target.is_file():
        # 库已经在：只把榜单补进去（源 CSV 没变时这个调用一个字节都不写）
        _load_ranking_best_effort(target, ranking_path)
        return None

    source = Path(csv_dir) if csv_dir else SEARCH_CSV_DIR
    if not source.is_dir():
        logger.info(
            "没有找到游戏检索的 CSV 名录（%s），跳过自动构建；"
            "要在容器里用检索，请先在宿主机执行 make index。",
            source,
        )
        return None

    try:
        # build_index 自己会打一条 INFO（路径 + 行数 + 机种数），这里不重复
        return build_index(source, target, ranking_csv=ranking_path, strict_ranking=False)
    except Exception as exc:  # noqa: BLE001 - 建不出来不该拦住服务启动
        logger.warning("自动构建游戏检索索引失败（不影响启动）：%s", exc)
        return None


def build_index(
    csv_dir: Path,
    out_path: Path,
    *,
    ranking_csv: Path | None = None,
    strict_ranking: bool = False,
) -> BuildStats:
    """读 `csv_dir` 下所有检索 CSV，重建 `out_path`（`<根路径>/db/game.db`）。

    可重复执行：每次都从零重建，成功后整体替换旧文件。失败不会留下半成品——
    临时文件写在同目录、失败即删，旧库原封不动。

    `ranking_csv` 给了就在同一次构建里把榜单也写进去；`strict_ranking=False` 时榜单 CSV
    坏了只记 warning（检索照常建），`True`（`make index`）时直接抛错让人看到问题。
    """
    csv_files = sorted(Path(csv_dir).glob("*.csv"))
    if not csv_files:
        raise IndexBuildError(f"没有找到任何 CSV 名录：{csv_dir}")

    ranking_data = None
    if ranking_csv is not None:
        ranking_path = Path(ranking_csv)
        if ranking_path.is_file():
            try:
                ranking_data = _load_ranking_csv(ranking_path)
            except RankingCsvError:
                if strict_ranking:
                    raise
                logger.warning("游戏榜单 CSV 解析失败，本次只建检索索引：%s", ranking_path)

    out_path = Path(out_path)
    temp_path = out_path.with_name(f"{out_path.name}.tmp")
    started = time.monotonic()

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.unlink(missing_ok=True)
        rows, consoles, ranking_rows, ranking_consoles = _write_database(
            csv_files, temp_path, ranking_data
        )
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, out_path)
    except PermissionError as exc:
        temp_path.unlink(missing_ok=True)
        raise _permission_error(out_path) from exc
    except sqlite3.OperationalError as exc:
        # 目录存在但没有写权限时，报的是 sqlite3 的 "unable to open database file" 而不是
        # PermissionError —— 这条同样要给可操作的中文提示，不能甩一个 traceback 给用户。
        temp_path.unlink(missing_ok=True)
        if "unable to open database" in str(exc):
            raise _permission_error(out_path) from exc
        raise IndexBuildError(f"构建索引失败：{exc}") from exc
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise IndexBuildError(f"写入 {out_path} 失败：{exc}") from exc
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    seconds = time.monotonic() - started
    stats = BuildStats(
        rows=rows,
        consoles=consoles,
        seconds=seconds,
        size=out_path.stat().st_size,
        path=out_path,
        ranking_rows=ranking_rows,
        ranking_consoles=ranking_consoles,
    )
    logger.info(
        "游戏检索索引已重建：%s（%d 行 / %d 机种，榜单 %d 条 / %d 机种）",
        out_path,
        rows,
        consoles,
        ranking_rows,
        ranking_consoles,
    )
    return stats


def ensure_ranking_loaded(
    db_path: Path,
    csv_path: Path,
    *,
    strict: bool = False,
) -> RankingLoadStats | None:
    """把榜单 CSV 就地补进一个已经存在的 `game.db`（服务启动时调用）。

    幂等：源 CSV 的 SHA-256 与库里的指纹一致时**连读写连接都不打开**，一个字节都不写。
    指纹用原始字节算而不是 size+mtime：`touch`、`git checkout`、解压都会改 mtime 但内容没变，
    而 `cp -p` / 解压工具又会保留 mtime，两者都会误判。

    `strict=False`（启动路径）时任何失败都只记 warning 并返回 `None`，绝不拦住启动；
    `strict=True` 时抛出 `IndexBuildError`。
    """
    db_path = Path(db_path)
    csv_path = Path(csv_path)
    if not db_path.is_file() or not csv_path.is_file():
        return None

    try:
        data = _load_ranking_csv(csv_path)
    except RankingCsvError as exc:
        if strict:
            raise
        logger.warning("游戏榜单 CSV 解析失败，跳过加载（不影响启动）：%s", exc)
        return None

    stats = RankingLoadStats(
        rows=len(data.rows), consoles=len(data.consoles), fingerprint=data.fingerprint
    )

    # 第一步：只读预检。指纹一致就到此为止，绝不打开读写连接。
    conn = None
    try:
        conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = 1")
        if not _search_schema_matches(conn):
            logger.warning("游戏检索索引版本与当前代码不符，跳过榜单就地加载：%s", db_path)
            return None
        if _ranking_matches(conn, data.fingerprint):
            return stats
    except sqlite3.Error as exc:
        if strict:
            raise IndexBuildError(f"读取榜单索引失败：{exc}") from exc
        logger.warning("读取榜单索引失败，跳过加载（不影响启动）：%s", exc)
        return None
    finally:
        if conn is not None:
            conn.close()

    # 第二步：就地更新。显式事务 + 事务内二次指纹检查，失败回滚后旧榜单原封不动。
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        try:
            # 不开 WAL：WAL 会留 -wal/-shm 伴随文件，而整库重建那条路是 os.replace 主库，
            # 新库配旧 -wal 必坏。老库万一曾处于 WAL 模式，这里也顺手掰回来。
            conn.execute("PRAGMA journal_mode = DELETE")
        except sqlite3.Error:  # pragma: no cover - 只读库在这里失败，下面写入时再报
            pass
        conn.execute("BEGIN IMMEDIATE")
        if _ranking_matches(conn, data.fingerprint):
            conn.commit()
            return stats
        conn.execute("DROP TABLE IF EXISTS ranking")
        conn.execute(_RANKING_SCHEMA)
        _write_ranking(conn, data)
        conn.commit()
    except (sqlite3.Error, OSError) as exc:
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error:  # pragma: no cover - 回滚都失败就只能记日志
                pass
        if strict:
            raise _ranking_write_error(exc, db_path) from exc
        logger.warning("%s（不影响启动）", _ranking_write_error(exc, db_path))
        return None
    finally:
        if conn is not None:
            conn.close()

    logger.info("游戏榜单已加载：%s（%d 条 / %d 机种）", db_path, stats.rows, stats.consoles)
    return stats


def _load_ranking_best_effort(db_path: Path, csv_path: Path | None) -> None:
    """启动路径的包装：任何异常都只记日志，绝不冒泡到 `create_app()`。"""
    if csv_path is None:
        return
    if not Path(csv_path).is_file():
        logger.info("没有找到游戏榜单 CSV（%s），跳过加载。", csv_path)
        return
    try:
        ensure_ranking_loaded(db_path, csv_path, strict=False)
    except Exception as exc:  # noqa: BLE001 - 兜底，函数内部已经处理过常见错误
        logger.warning("加载游戏榜单失败（不影响启动）：%s", exc)


def _permission_error(out_path: Path) -> IndexBuildError:
    """写不进去时给一条能照做的中文提示（默认数据根被 Docker 以 root 建过就会撞上）。"""
    return IndexBuildError(
        f"没有写入权限：{out_path.parent}\n"
        f"（该目录多半是 Docker 容器以 root 建的）先执行一次：\n"
        f'    sudo chown -R "$USER" {out_path.parent.parent}\n'
        f"再重新运行 make index。"
    )


def _ranking_write_error(exc: Exception, db_path: Path) -> IndexBuildError:
    """榜单写库失败的统一中文提示：权限问题要给出可照做的命令。"""
    if isinstance(exc, sqlite3.OperationalError) and "unable to open database" in str(exc):
        return IndexBuildError(
            f"没有写入权限，无法把榜单写进 {db_path}\n"
            f'（该目录多半是 Docker 容器以 root 建的）先执行一次：\n'
            f'    sudo chown -R "$USER" {db_path.parent.parent}'
        )
    return IndexBuildError(f"加载游戏榜单失败：{exc}")


def _write_database(
    csv_files: list[Path],
    temp_path: Path,
    ranking_data: RankingData | None,
) -> tuple[int, int, int, int]:
    """把名录（以及可选的榜单）写进临时库文件，返回 (行数, 机种数, 榜单条数, 榜单机种数)。"""
    # 不开 WAL：WAL 会留 -wal/-shm 伴随文件，而 os.replace 只换主文件，新库配旧 -wal 必坏。
    conn = sqlite3.connect(temp_path)
    try:
        conn.executescript(_SCHEMA)
        console_ids: dict[str, int] = {}
        seen: set[tuple[str, str, str]] = set()
        row_id = 0

        for csv_file in csv_files:
            for line_no, row in enumerate(_read_csv(csv_file), start=1):
                if len(row) != 3:
                    raise IndexBuildError(
                        f"{csv_file.name} 第 {line_no} 行有 {len(row)} 列，"
                        f"应为 3 列（机种,中文,英文）。"
                    )
                console_name, zh, en = (cell.strip() for cell in row)

                # 去重只认三元组完全一致的（跨源文件也算）：同款游戏的不同地区版本
                # 中文或英文至少有一处不同，必须都留着。
                key = (console_name, zh, en)
                if key in seen:
                    continue
                seen.add(key)

                console_id = console_ids.get(console_name)
                if console_id is None:
                    console_id = len(console_ids) + 1
                    console_ids[console_name] = console_id
                    conn.execute(
                        "INSERT INTO console(id, name) VALUES(?, ?)",
                        (console_id, console_name),
                    )

                row_id += 1
                conn.execute(
                    "INSERT INTO game(id, console_id, zh, en, src) VALUES(?, ?, ?, ?, ?)",
                    (row_id, console_id, zh, en, csv_file.name),
                )
                conn.execute(
                    "INSERT INTO game_fts(rowid, zh_uni, en_uni) VALUES(?, ?, ?)",
                    (row_id, index_text(zh), index_text(en)),
                )

        if row_id == 0:
            raise IndexBuildError(f"{csv_files[0].parent} 下的 CSV 一行数据都没有。")

        now = datetime.now().isoformat(timespec="seconds")
        meta = {
            "schema_version": SCHEMA_VERSION,
            "built_at": now,
            "rows": str(row_id),
            "consoles": str(len(console_ids)),
        }
        conn.executemany("INSERT INTO meta(key, value) VALUES(?, ?)", meta.items())

        ranking_rows, ranking_consoles = 0, 0
        if ranking_data is not None:
            ranking_rows, ranking_consoles = _write_ranking(conn, ranking_data)
        else:
            # 没有榜单 CSV 也要留下版本号：榜单页据此区分「索引都没有」与「榜单还没加载」
            _upsert_meta(
                conn,
                {
                    "ranking_schema_version": RANKING_SCHEMA_VERSION,
                    "ranking_rows": "0",
                    "ranking_consoles": "0",
                },
            )
        conn.commit()
        # optimize 会重建倒排索引块，必须落在自己的事务里（放进隐式事务一旦回滚就白做）
        conn.execute("INSERT INTO game_fts(game_fts) VALUES('optimize')")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()

    # 收尾断言：临时文件旁边不该有 journal 系伴随文件（有的话 os.replace 出来的主库会与它不匹配）
    for suffix in ("-wal", "-shm", "-journal"):
        leftover = temp_path.with_name(temp_path.name + suffix)
        if leftover.exists():  # pragma: no cover - 正常路径不会走到
            leftover.unlink()
    return row_id, len(console_ids), ranking_rows, ranking_consoles


def _read_csv(csv_file: Path):
    """逐行读一个源 CSV。带 BOM、CRLF，所以用 utf-8-sig + newline='' 交给 csv 模块处理引号。"""
    with csv_file.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.reader(handle)


def _load_ranking_csv(csv_path: Path) -> RankingData:
    """解析榜单 CSV，返回行、机种与内容指纹。任何格式问题都抛带行号的中文错误。"""
    raw = csv_path.read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RankingCsvError(f"{csv_path.name} 不是 UTF-8 编码，请另存为 UTF-8 后重试。") from exc

    rows: list[RankingRow] = []
    consoles: dict[str, str] = {}  # casefold 后的机种 -> 首次出现的写法
    seen_ranks: set[tuple[str, int]] = set()
    first_row = True

    for line_no, raw_row in enumerate(csv.reader(io.StringIO(text, newline="")), start=1):
        row = list(raw_row)
        # Excel 常在行尾留一串空列，先裁掉再判列数
        while row and not row[-1].strip():
            row.pop()
        if not row or all(not cell.strip() for cell in row):
            continue
        if first_row:
            first_row = False
            if row[0].strip() in _RANKING_HEADERS:
                continue
        # 第 4 列（卡带 ID）允许为空：写成空列会被上面的裁尾删掉，所以 3 列也算合法。
        if len(row) not in (3, _RANKING_COLUMNS):
            raise RankingCsvError(
                f"{csv_path.name} 第 {line_no} 行有 {len(row)} 列，"
                f"应为 4 列（序号,机种名称,游戏名称,游戏卡带ID），"
                f"卡带 ID 为空时可省掉第 4 列。"
            )

        seq_text, console, title = (cell.strip() for cell in row[:3])
        ids_text = row[3].strip() if len(row) > 3 else ""
        try:
            rank = int(seq_text)
        except ValueError as exc:
            raise RankingCsvError(
                f"{csv_path.name} 第 {line_no} 行的序号「{seq_text}」不是整数。"
            ) from exc
        if rank < 1:
            raise RankingCsvError(f"{csv_path.name} 第 {line_no} 行的序号必须是正整数。")
        if not console:
            raise RankingCsvError(f"{csv_path.name} 第 {line_no} 行缺少机种名称。")
        if not title:
            raise RankingCsvError(f"{csv_path.name} 第 {line_no} 行缺少游戏名称。")

        ids: list[str] = []
        for part in _RANKING_ID_SPLIT.split(ids_text):
            part = part.strip()
            if part and part not in ids:
                ids.append(part)
        if len(ids) > 2:
            raise RankingCsvError(
                f"{csv_path.name} 第 {line_no} 行有 {len(ids)} 个游戏卡带ID，最多 2 个。"
            )

        key = console.casefold()
        stored = consoles.get(key)
        if stored is None:
            stored = console
            consoles[key] = stored
        if (key, rank) in seen_ranks:
            raise RankingCsvError(
                f"{csv_path.name} 第 {line_no} 行：机种「{stored}」的序号 {rank} 重复。"
            )
        seen_ranks.add((key, rank))
        rows.append(RankingRow(console=stored, rank=rank, title=title, cartridge_ids=tuple(ids)))

    if not rows:
        raise RankingCsvError(f"{csv_path.name} 一行榜单数据都没有（空文件，或只有表头）。")

    return RankingData(
        rows=tuple(rows),
        consoles=tuple(consoles.values()),
        fingerprint=fingerprint,
        source=csv_path.name,
    )


def _write_ranking(conn: sqlite3.Connection, data: RankingData) -> tuple[int, int]:
    """把榜单整份写进 `ranking` 表并更新 meta（调用方负责事务与建表）。"""
    conn.executemany(
        "INSERT INTO ranking(console, rank, title, cartridge_ids) VALUES(?, ?, ?, ?)",
        [
            (row.console, row.rank, row.title, json.dumps(list(row.cartridge_ids), ensure_ascii=False))
            for row in data.rows
        ],
    )
    _upsert_meta(
        conn,
        {
            "ranking_schema_version": RANKING_SCHEMA_VERSION,
            "ranking_fingerprint": data.fingerprint,
            "ranking_source": data.source,
            "ranking_rows": str(len(data.rows)),
            "ranking_consoles": str(len(data.consoles)),
            "ranking_loaded_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return len(data.rows), len(data.consoles)


def _upsert_meta(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    conn.executemany(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        values.items(),
    )


def _search_schema_matches(conn: sqlite3.Connection) -> bool:
    """检索版本与代码一致才允许就地写榜单：不往看不懂的库里写东西。"""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row[0] == SCHEMA_VERSION)


def _ranking_matches(conn: sqlite3.Connection, fingerprint: str) -> bool:
    """库里已经装的就是这份 CSV：版本一致、指纹一致、表也在。"""
    try:
        version = conn.execute(
            "SELECT value FROM meta WHERE key = 'ranking_schema_version'"
        ).fetchone()
        stored = conn.execute("SELECT value FROM meta WHERE key = 'ranking_fingerprint'").fetchone()
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ranking'"
        ).fetchone()
    except sqlite3.Error:
        return False
    return bool(
        version
        and version[0] == RANKING_SCHEMA_VERSION
        and stored
        and stored[0] == fingerprint
        and table
    )
