"""游戏名录与游戏榜单的构建。

只在 `make index` 时构建数据；服务启动只用 `ensure_empty_game_db()` 建空的当前结构，
不重载、不重建已有 game.db。这个模块是
`<运行时根>/db/game.db` 的**构建者**；运行期读走 `search_service.GameSearchService`
与 `ranking_service.GameRankingService`，它们一律以 `mode=ro` 打开。运行期的
`ranking.in_library` 标记由 `ranking_flags.py` 用短事务更新，不做整库重建。
所以这里可以放心用「整库重建 + 原子替换」这种最简单也最不容易出错的做法。

数据源两份，都在 `backend/search/` 下：

- `catalog/` 下的一份份 `中文名,英文名` 两列名录（UTF-8 带 BOM、CRLF、首行表头），构成游戏名录索引；
  机种由文件名经 `platforms.SEARCH_CSV_CONSOLE_NAMES` 推导，不再写在行里；
- `rankings/` 下每个机种一个四列 CSV（`中文名,英文名,评分,卡带ID`），构成游戏榜单；
  机种由文件名（机种 id）决定。

榜单单独建表、单独一个版本号：它的表结构变化不影响游戏名录的 `schema_version`，补榜单失败也不会
把游戏名录一起变成「版本过旧」。

**机种归一**：游戏名录的机种来自文件名映射（`gb.csv` → `任天堂GB`、`gbc.csv` → `任天堂GBC`），
榜单机种直接来自文件名（`nes.csv` → 机种 id `nes`），两份数据都用 `backend/games/platforms.py`
的词表表达同一套机种。名录侧同一个机种的多个原始名（`任天堂GB` + `任天堂GBC`）**在库里就是同一行
console**，页面的机种下拉天然不会出现两个同名项；游戏名录里认不出的机种（Wii、3DS、CD-I…）
保留原文、`platform_id` 留空，自成一组，显示名仍按「公司名 + 空格 + 型号」补空格。
"""

import csv
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.games.cartridge import normalize_cartridge_id
from backend.games.platforms import (
    PLATFORM_BY_ID,
    PLATFORMS,
    SEARCH_CSV_CONSOLE_NAMES,
    display_console_name,
    normalize_name,
    resolve_platform,
)
from backend.games.search_text import index_text

logger = logging.getLogger(__name__)

# 索引结构的版本。改了游戏名录表结构就加一，运行期读到不匹配的版本会直接报「请重新构建」，
# 而不是在旧库上跑出新代码的诡异结果。**榜单表不在这个版本的管理范围内**（见 RANKING_SCHEMA_VERSION）：
# 往老库里加榜单表是纯新增，不该让已经能用的游戏名录库被判成过旧。
# 2：机种归一（console 表加 platform_id / raw_names，同一机种合并成一行）
SCHEMA_VERSION = "2"

# 榜单表结构的版本，独立于上面的游戏名录版本。
# 2：机种归一（ranking 表加 platform 列，主键从 (console, rank) 改成 (platform, rank)）
# 3：单列 title 拆成 zh / en 两列（与游戏名录的中文名、英文名对齐）
# 4：增加 score 列（MobyGames 原始 double）
# 5：增加评分索引（跨机种 score、机种+score）
# 6：去掉 rank，增加自增 id 与 (platform, en) 唯一索引
# 7：增加 in_library 标记与卡带 ID → ranking.id 映射表
RANKING_SCHEMA_VERSION = "7"

# 建库语句。game_fts 是 contentless（content=''）表：只存倒排索引、不重复存正文，
# 正文永远从 game 表取——所以 snippet()/highlight() 在它上面恒返回 NULL，高亮必须在前端做。
#
# console 一行 = 一个**统一机种**（不是 CSV 里的一个原始机种名）：`name` 是词表里的统一显示名、
# `platform_id` 是 EmulatorJS 的 system key、`raw_names` 记下被合并进来的原始写法（溯源用）。
# 认不出机种的保留原文当 name、`platform_id` 留空。`name` 上的 UNIQUE 因此等价于
# 「下拉里不会出现两个同名项」——别名索引把 `label` 也当别名收了，所以原文撞上统一名时
# 会被解析成那个机种，不会变成一个撞车的「未收录」行。
_SEARCH_SCHEMA = """
CREATE TABLE console(
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    platform_id TEXT,
    raw_names   TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX idx_console_platform ON console(platform_id);

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

# 榜单表。`id` 是主键，构建时按行序从 1 显式分配，只用于数据库身份与同分稳定排序；`platform` 是机种 key
# （来自榜单文件名，也就是 EmulatorJS 的 system key），`console` 留文件名 stem 供溯源，
# `score` 存 MobyGames 原始 double。`rank` 不再落库。
# `uq_ranking_platform_en` 保证同一机种内英文名唯一；评分排序走 `_RANKING_INDEXES`。
#
# 机种存文本而不是外键到 console 表：榜单的机种未必出现在游戏名录里，复用 console 表会污染
# 游戏名录的机种下拉（两个页面各自维护自己的机种清单，只是**用同一份词表**）。
# cartridge_ids 存 JSON 数组文本：每行 0~2 个，读取时 json.loads 即可，不需要子表与 join。
_RANKING_SCHEMA = """
CREATE TABLE IF NOT EXISTS ranking(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,
    console       TEXT NOT NULL,
    score         REAL NOT NULL,
    zh            TEXT NOT NULL,
    en            TEXT NOT NULL,
    cartridge_ids TEXT NOT NULL,
    in_library    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ranking_cartridges(
    cartridge_id TEXT PRIMARY KEY,
    ranking_id   INTEGER NOT NULL REFERENCES ranking(id)
);
"""

_SCHEMA = _SEARCH_SCHEMA + _RANKING_SCHEMA

# 榜单索引：
# - `(platform, en)` 唯一：数据契约要求同一机种内英文名唯一。
# - `(score DESC)`：跨机种 `ORDER BY score DESC, id`。`id` 是主键，二级索引自动附带 id。
# - `(platform, score DESC)`：单机种 `WHERE platform = ? ORDER BY score DESC, id`。
# - `(in_library, score DESC)` / `(platform, in_library, score DESC)`：库存三态筛选后的排序。
# - `ranking_id`：反向按榜单行查卡带 ID，供标记重算。
_RANKING_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_ranking_platform_en ON ranking(platform, en)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_score ON ranking(score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_platform_score ON ranking(platform, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_in_library_score ON ranking(in_library, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_platform_in_library_score "
    "ON ranking(platform, in_library, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_cartridges_ranking "
    "ON ranking_cartridges(ranking_id)",
)


def _create_ranking_indexes(conn: sqlite3.Connection) -> None:
    for statement in _RANKING_INDEXES:
        conn.execute(statement)


# 空 game.db 初始化与结构校验：结构只允许由启动初始化或 make upgrade 改变。
_GAME_DB_TABLES = {
    "console",
    "game",
    "game_fts",
    "meta",
    "ranking",
    "ranking_cartridges",
}
_GAME_DB_INDEXES = {
    "idx_console_platform",
    "idx_game_console",
    "uq_ranking_platform_en",
    "idx_ranking_score",
    "idx_ranking_platform_score",
    "idx_ranking_in_library_score",
    "idx_ranking_platform_in_library_score",
    "idx_ranking_cartridges_ranking",
}


def _game_db_table_names(path: Path) -> set[str] | None:
    """只读列出用户表；打不开返回 None。"""
    try:
        conn = sqlite3.connect(f"{Path(path).as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        conn.execute("PRAGMA query_only = 1")
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def ensure_empty_game_db(path: Path) -> bool:
    """game.db 不存在或没有任何表时，建一份最新的空结构（表/索引/版本，无数据）。

    已有表的库**一律不碰**：旧版本结构由 make upgrade 迁移，数据由 make index 重建。
    返回是否新建了文件。
    """
    path = Path(path)
    tables = _game_db_table_names(path) if path.is_file() else set()
    if tables:
        return False
    if tables is None:
        logger.warning("无法读取 game.db，跳过空结构初始化：%s", path)
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.init.tmp")
    temp.unlink(missing_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(temp)
        conn.executescript(_SCHEMA)
        _create_ranking_indexes(conn)
        _upsert_meta(
            conn,
            {
                "schema_version": SCHEMA_VERSION,
                "ranking_schema_version": RANKING_SCHEMA_VERSION,
                "ranking_rows": "0",
                "ranking_consoles": "0",
            },
        )
        conn.commit()
        conn.close()
        conn = None
        os.chmod(temp, 0o644)
        os.replace(temp, path)
        logger.info("已初始化空 game.db 结构：%s（版本 %s）", path, RANKING_SCHEMA_VERSION)
        return True
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    finally:
        if conn is not None:
            conn.close()


def game_db_is_current(path: Path) -> bool:
    """game.db 是否已经是当前结构（make index 只允许在此时更新数据）。"""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        conn.execute("PRAGMA query_only = 1")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if not _GAME_DB_TABLES <= tables:
            return False
        meta = dict(
            conn.execute("SELECT key, value FROM meta").fetchall()
        )
        if meta.get("schema_version") != SCHEMA_VERSION:
            return False
        if meta.get("ranking_schema_version") != RANKING_SCHEMA_VERSION:
            return False
        ranking_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(ranking)")
        }
        if "in_library" not in ranking_columns:
            return False
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        return _GAME_DB_INDEXES <= indexes
    except sqlite3.Error:
        return False
    finally:
        conn.close()


# 榜单里同一格最多两个卡带 ID（也可以一个都没有），用这些分隔符分开。**空格不是分隔符**：卡带 ID 里常有空格
# （如 `POKEMON FIRE RED`），按空格拆会把一个 ID 拆成好几个；连字符与下划线同样不分割。
_RANKING_ID_SPLIT = re.compile(r"[、,，/;；]+")
# 表头固定四列；首行内容恰好是这四格时跳过。
_RANKING_HEADER = ("中文名", "英文名", "评分", "卡带ID")
# 榜单 CSV 的列数（中文名,英文名,评分,卡带ID）；卡带 ID 为空时可省成 3 列。
_RANKING_COLUMNS = 4
# 旧版首格是序号/排名的榜单表头：明确拒绝，避免把序号当中文名静默解析。
_RANKING_OLD_INDEX_HEADERS = {"序号", "排名"}
# 评分只接受普通十进制写法，落库转 double；负号、科学计数法一律拒绝。
_RANKING_SCORE_RE = re.compile(r"^\d+(?:\.\d+)?$")
# 游戏名录的表头。真实目录里的 CSV 都带这一行；自定义 `--csv-dir` 可以不带，所以按可选处理：
# 只跳过**第一行**且内容恰好是这两格，避免把恰巧同名的游戏当表头。
_SEARCH_HEADER = ("中文名", "英文名")


# 进度回调：(阶段名, 已完成, 总数)。总数 <= 0 表示该阶段无法估计百分比。
ProgressCallback = Callable[[str, int, int], None]


def _notify(
    on_progress: ProgressCallback | None, label: str, current: int, total: int
) -> None:
    if on_progress is not None:
        on_progress(label, current, total)


class IndexBuildError(Exception):
    """构建失败。message 是给用户看的中文，`backend/cli.py` 直接打印。"""


class RankingCsvError(IndexBuildError):
    """榜单 CSV 内容不合法（列数、重复英文名、空字段、卡带 ID 数量等）。"""


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
    platform: str  # 机种键（文件名 stem，也就是 EmulatorJS 的 system key）
    console: str  # 文件名 stem，仅作溯源与展示兜底
    score: float
    zh: str
    en: str
    cartridge_ids: tuple[str, ...]


@dataclass(frozen=True)
class RankingData:
    rows: tuple[RankingRow, ...]
    platforms: tuple[str, ...]  # 机种键（去重，按首次出现顺序）
    fingerprint: str
    source: str


def build_index(
    csv_dir: Path,
    out_path: Path,
    *,
    ranking_dir: Path | None = None,
    strict_ranking: bool = False,
    on_progress: ProgressCallback | None = None,
) -> BuildStats:
    """读 `csv_dir` 下所有游戏名录 CSV，构建 `out_path`（`<运行时根>/db/game.db`）的数据。

    调用方必须先确认 `out_path` 已是当前结构（CLI 用 `game_db_is_current()` 校验）；
    这里只写数据、不做结构迁移。写入用同结构的临时库 + 原子替换，可重复执行，
    失败不会留下半成品。`ranking_dir` 给了就在同一次构建里把榜单也写进去；
    `strict_ranking=False` 时榜单目录坏了只记 warning（游戏名录照常建），
    `True`（`make index`）时直接抛错让人看到问题。`on_progress` 用来向调用方
    报告各阶段进度，回调里不能抛异常（CLI 传的是终端绘制函数）。
    """
    csv_files = sorted(Path(csv_dir).glob("*.csv"), key=_csv_sort_key)
    if not csv_files:
        raise IndexBuildError(f"没有找到任何 CSV 名录：{csv_dir}")

    ranking_data = None
    if ranking_dir is not None:
        ranking_path = Path(ranking_dir)
        if ranking_path.is_dir():
            try:
                ranking_data = _load_ranking_dir(ranking_path, on_progress=on_progress)
            except RankingCsvError:
                if strict_ranking:
                    raise
                logger.warning("游戏榜单 CSV 解析失败，本次只建游戏名录：%s", ranking_path)

    out_path = Path(out_path)
    temp_path = out_path.with_name(f"{out_path.name}.tmp")
    started = time.monotonic()

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.unlink(missing_ok=True)
        rows, consoles, ranking_rows, ranking_consoles = _write_database(
            csv_files, temp_path, ranking_data, on_progress=on_progress
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
        "游戏名录与游戏榜单已重建：%s（名录 %d 行 / %d 机种，榜单 %d 条 / %d 机种）",
        out_path,
        rows,
        consoles,
        ranking_rows,
        ranking_consoles,
    )
    return stats




def _permission_error(out_path: Path) -> IndexBuildError:
    """写不进去时给一条能照做的中文提示（默认数据根被 Docker 以 root 建过就会撞上）。"""
    return IndexBuildError(
        f"没有写入权限：{out_path.parent}\n"
        f"（该目录多半是 Docker 容器以 root 建的）先执行一次：\n"
        f'    sudo chown -R "$USER" {out_path.parent.parent}\n'
        f"再重新运行 make index。"
    )


def _write_database(
    csv_files: list[Path],
    temp_path: Path,
    ranking_data: RankingData | None,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[int, int, int, int]:
    """把名录（以及可选的榜单）写进临时库文件，返回 (行数, 机种数, 榜单条数, 榜单机种数)。"""
    # 不开 WAL：WAL 会留 -wal/-shm 伴随文件，而 os.replace 只换主文件，新库配旧 -wal 必坏。
    conn = sqlite3.connect(temp_path)
    try:
        conn.executescript(_SCHEMA)
        _create_ranking_indexes(conn)

        # 第一遍：读完名录（按 (机种原始名, 中文, 英文) 三元组去重）并按统一机种分组。
        # 机种原始名来自文件名映射，见 `_console_name_for()`。
        # 行数只有五万级，整份读进内存换「机种 id 可以按词表顺序分配」是划算的。
        rows: list[tuple[str, str, str, str]] = []  # (分组键, 中文, 英文, 来源 CSV)
        seen: set[tuple[str, str, str]] = set()
        groups: dict[str, list[str]] = {}  # 分组键 -> 该组的原始机种名（按首次出现顺序）

        _notify(on_progress, "读取游戏名录", 0, len(csv_files))
        for file_index, csv_file in enumerate(csv_files, start=1):
            console_name = _console_name_for(csv_file)
            for line_no, row in enumerate(_read_csv(csv_file), start=1):
                if line_no == 1 and _is_search_header(row):
                    continue
                if len(row) != 2:
                    raise IndexBuildError(
                        f"{csv_file.name} 第 {line_no} 行有 {len(row)} 列，"
                        f"应为 2 列（中文名,英文名）；机种由文件名决定。"
                    )
                zh, en = (cell.strip() for cell in row)

                # 去重只认三元组完全一致的（跨源文件也算）：同款游戏的不同地区版本
                # 中文或英文至少有一处不同，必须都留着。
                key = (console_name, zh, en)
                if key in seen:
                    continue
                seen.add(key)

                group = _console_group(console_name)
                rows.append((group, zh, en, csv_file.name))
                raw_names = groups.setdefault(group, [])
                if console_name not in raw_names:
                    raw_names.append(console_name)
            _notify(on_progress, "读取游戏名录", file_index, len(csv_files))

        if not rows:
            raise IndexBuildError(f"{csv_files[0].parent} 下的 CSV 一行数据都没有。")

        console_ids = _write_consoles(conn, groups)

        row_id = 0
        for group, zh, en, src in rows:
            row_id += 1
            conn.execute(
                "INSERT INTO game(id, console_id, zh, en, src) VALUES(?, ?, ?, ?, ?)",
                (row_id, console_ids[group], zh, en, src),
            )
            conn.execute(
                "INSERT INTO game_fts(rowid, zh_uni, en_uni) VALUES(?, ?, ?)",
                (row_id, index_text(zh), index_text(en)),
            )
            _notify(on_progress, "写入游戏名录", row_id, len(rows))

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
            ranking_rows, ranking_consoles = _write_ranking(
                conn, ranking_data, on_progress=on_progress
            )
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
        # FTS5 的 optimize 只合并倒排索引段，耗时通常很短，不单独报进度
        # optimize 会重建倒排索引块，必须落在自己的事务里（放进隐式事务一旦回滚就白做）
        conn.execute("INSERT INTO game_fts(game_fts) VALUES('optimize')")
        conn.commit()
    finally:
        conn.close()

    # 压缩必须在连接关闭之后做：Windows 上仍被打开的文件无法替换
    _vacuum_database(temp_path, on_progress=on_progress)

    # 收尾断言：临时文件旁边不该有 journal 系伴随文件（有的话 os.replace 出来的主库会与它不匹配）
    for suffix in ("-wal", "-shm", "-journal"):
        leftover = temp_path.with_name(temp_path.name + suffix)
        if leftover.exists():  # pragma: no cover - 正常路径不会走到
            leftover.unlink()
    return row_id, len(console_ids), ranking_rows, ranking_consoles


# 轮询 VACUUM INTO 目标文件大小的间隔（秒）。进度条只按整数百分比刷新，再密没有收益。
_VACUUM_POLL_INTERVAL = 0.1


def _vacuum_database(
    temp_path: Path, *, on_progress: ProgressCallback | None = None
) -> None:
    """把临时库压缩成新文件再原子替换回 ``temp_path``。

    ``VACUUM`` 是单条 SQLite 调用，报不出百分比；``VACUUM INTO`` 逐页顺序写新文件，
    用「新文件大小 / 预估产物大小」近似进度。产物等价，而且不建回滚日志，在慢盘上
    比 ``VACUUM`` 快得多。
    """
    vacuum_path = temp_path.with_name(temp_path.name + ".vacuum")
    vacuum_path.unlink(missing_ok=True)
    total = _compacted_size(temp_path)
    errors: list[Exception] = []

    def run() -> None:
        try:
            conn = sqlite3.connect(temp_path)
            try:
                conn.execute("VACUUM INTO ?", (str(vacuum_path),))
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 - 交给主线程重新抛出
            errors.append(exc)

    thread: threading.Thread | None = None
    try:
        if on_progress is None:
            run()
        else:
            _notify(on_progress, "正在优化索引", 0, total)
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            written = 0
            while thread.is_alive():
                written = max(written, _file_size(vacuum_path, total))
                _notify(on_progress, "正在优化索引", written, total)
                thread.join(_VACUUM_POLL_INTERVAL)
        if thread is not None:
            thread.join()
        if errors:
            raise errors[0]
        os.replace(vacuum_path, temp_path)
        _notify(on_progress, "正在优化索引", total, total)
    except BaseException:
        if thread is not None and thread.is_alive():
            thread.join()
        vacuum_path.unlink(missing_ok=True)
        raise


def _compacted_size(path: Path) -> int:
    """估算压缩后的库大小：去掉 freelist 页再乘页大小。

    VACUUM 只回收空闲页，所以这个估算与真实产物的偏差很小；收尾时进度直接补到 100%。
    """
    conn = None
    try:
        conn = sqlite3.connect(path)
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        return max((page_count - freelist) * page_size, 1)
    except sqlite3.Error:
        return max(path.stat().st_size, 1)
    finally:
        if conn is not None:
            conn.close()


def _file_size(path: Path, limit: int) -> int:
    try:
        return min(path.stat().st_size, limit)
    except OSError:
        return 0


# 认不出机种的原始名自成一组时的分组键前缀（加前缀是为了与机种 id 分得开）
_RAW_GROUP_PREFIX = "raw:"


def _console_group(console_name: str) -> str:
    """原始机种名 → 分组键：认得出机种就用机种 id，认不出就按原文归一后自成一组。

    归一是为了把大小写/空白的写法差异并到一起（`CD-I` 与 `cd-i` 是同一组），
    归一后仍不同的（`CD-I` 与 `CD I`）就当两个机种——总比把不相干的机器并了强。
    """
    platform = resolve_platform(console_name)
    if platform is not None:
        return platform.id
    return _RAW_GROUP_PREFIX + normalize_name(console_name)


def _write_consoles(conn: sqlite3.Connection, groups: dict[str, list[str]]) -> dict[str, int]:
    """写 console 表，返回「分组键 → console.id」。

    顺序：**已收录机种按词表顺序**（下拉因此按厂商分组，且不再随 CSV 文件名变化），
    未收录的按在 CSV 里首次出现的顺序跟在后面。id 从 1 起连续分配。
    """
    ordered: list[str] = [platform.id for platform in PLATFORMS if platform.id in groups]
    ordered += [group for group in groups if group.startswith(_RAW_GROUP_PREFIX)]

    console_ids: dict[str, int] = {}
    for index, group in enumerate(ordered, start=1):
        raw_names = groups[group]
        platform = resolve_platform(group) if not group.startswith(_RAW_GROUP_PREFIX) else None
        conn.execute(
            "INSERT INTO console(id, name, platform_id, raw_names) VALUES(?, ?, ?, ?)",
            (
                index,
                platform.label if platform else display_console_name(raw_names[0]),
                platform.id if platform else None,
                json.dumps(raw_names, ensure_ascii=False),
            ),
        )
        console_ids[group] = index
    return console_ids


def _console_name_for(csv_file: Path) -> str:
    """游戏名录 CSV 的机种身份：文件名 stem 经映射表还原；未登记时按 stem 兜底。

    兜底是为了让 `--csv-dir` 指向自定义目录时仍能用；真实 `backend/search/catalog/` 目录的
    文件名完整性由 `tests/test_platforms.py` 钉住。
    """
    return SEARCH_CSV_CONSOLE_NAMES.get(csv_file.stem, csv_file.stem)


def _csv_sort_key(csv_file: Path) -> tuple[str, str]:
    """按旧文件名口径排序，保持 raw_names 与未收录机种 id 的顺序不变。

    旧文件名就是「机种原始名 + .csv」；同一原始名的两个文件（ps2-jp / ps2-us）再按
    新文件名定序，仍与旧的「日版 / 美版」顺序一致。
    """
    return (f"{_console_name_for(csv_file)}.csv", csv_file.name)


def _read_csv(csv_file: Path):
    """逐行读一个源 CSV。带 BOM、CRLF，所以用 utf-8-sig + newline='' 交给 csv 模块处理引号。"""
    with csv_file.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.reader(handle)


def _is_search_header(row: list[str]) -> bool:
    """第一行是否是 `中文名,英文名` 表头（容忍单元格首尾空白）。"""
    return len(row) == len(_SEARCH_HEADER) and tuple(cell.strip() for cell in row) == _SEARCH_HEADER


def _load_ranking_dir(
    ranking_dir: Path, *, on_progress: ProgressCallback | None = None
) -> RankingData:
    """解析榜单目录，返回行、机种与多文件内容指纹。任何格式问题都抛带文件名与行号的中文错误。"""
    csv_files = sorted(Path(ranking_dir).glob("*.csv"))
    if not csv_files:
        raise RankingCsvError(f"{ranking_dir} 下没有任何榜单 CSV。")

    digest = hashlib.sha256()
    rows: list[RankingRow] = []
    platforms: list[str] = []
    seen_platforms: set[str] = set()
    first_seen: dict[tuple[str, str], tuple[str, int]] = {}
    duplicates: list[str] = []

    _notify(on_progress, "解析游戏榜单", 0, len(csv_files))
    for file_index, csv_path in enumerate(csv_files, start=1):
        raw = csv_path.read_bytes()
        # 指纹覆盖「文件名 + 原始字节」：改名、换内容、增删文件都会变；空文件也算一份。
        digest.update(csv_path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")

        platform = PLATFORM_BY_ID.get(csv_path.stem)
        if platform is None:
            raise RankingCsvError(
                f"{csv_path.name}：榜单文件名必须是机种 id（如 nes.csv、segaMD.csv）。"
            )
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RankingCsvError(
                f"{csv_path.name} 不是 UTF-8 编码，请另存为 UTF-8 后重试。"
            ) from exc

        first_row = True
        for line_no, raw_row in enumerate(csv.reader(io.StringIO(text, newline="")), start=1):
            row = list(raw_row)
            # Excel 常在行尾留一串空列，先裁掉再判列数；最多裁到 4 列。
            while len(row) > _RANKING_COLUMNS and not row[-1].strip():
                row.pop()
            if not row or all(not cell.strip() for cell in row):
                continue
            if first_row:
                first_row = False
                if tuple(cell.strip() for cell in row) == _RANKING_HEADER:
                    continue
                if row[0].strip() in _RANKING_OLD_INDEX_HEADERS:
                    raise RankingCsvError(
                        f"{csv_path.name} 第 {line_no} 行：榜单 CSV 应为"
                        f"「中文名,英文名,评分,卡带ID」四列，不再有「序号」。"
                    )
            # 第 4 列（卡带 ID）允许为空：写成空列会被上面的裁尾删掉，所以 3 列也算合法。
            if len(row) not in (3, _RANKING_COLUMNS):
                raise RankingCsvError(
                    f"{csv_path.name} 第 {line_no} 行有 {len(row)} 列，"
                    f"应为 4 列（中文名,英文名,评分,卡带ID），"
                    f"卡带 ID 为空时可省掉第 4 列。"
                )

            zh, en, score_text = (cell.strip() for cell in row[:3])
            ids_text = row[3].strip() if len(row) > 3 else ""
            if not en:
                raise RankingCsvError(f"{csv_path.name} 第 {line_no} 行缺少英文名。")
            if not _RANKING_SCORE_RE.match(score_text):
                raise RankingCsvError(
                    f"{csv_path.name} 第 {line_no} 行的评分「{score_text}」不是有效的数字。"
                )

            ids: list[str] = []
            for part in _RANKING_ID_SPLIT.split(ids_text):
                part = part.strip()
                if part and part not in ids:
                    ids.append(part)
            if len(ids) > 2:
                raise RankingCsvError(
                    f"{csv_path.name} 第 {line_no} 行有 {len(ids)} 个游戏卡带ID，最多 2 个。"
                )

            title_key = (platform.id, en)
            if title_key in first_seen:
                first_file, first_line = first_seen[title_key]
                duplicates.append(
                    f"  {csv_path.name} 第 {line_no} 行：{platform.id}「{en}」"
                    f"（首次出现于 {first_file} 第 {first_line} 行）"
                )
                continue
            first_seen[title_key] = (csv_path.name, line_no)

            if platform.id not in seen_platforms:
                seen_platforms.add(platform.id)
                platforms.append(platform.id)
            rows.append(
                RankingRow(
                    platform=platform.id,
                    console=csv_path.stem,
                    score=float(score_text),
                    zh=zh,
                    en=en,
                    cartridge_ids=tuple(ids),
                )
            )

        # 只有表头的机种文件合法（例如暂无评分的 c128/pcfx/pet），继续读下一份。
        _notify(on_progress, "解析游戏榜单", file_index, len(csv_files))

    if duplicates:
        raise RankingCsvError(
            "榜单 CSV 中同一机种内英文名重复（必须唯一，重复标题只保留评分最高的一条）：\n"
            + "\n".join(duplicates)
        )

    if not rows:
        raise RankingCsvError(
            f"{ranking_dir} 下的榜单 CSV 一行数据都没有（空文件，或只有表头）。"
        )

    return RankingData(
        rows=tuple(rows),
        platforms=tuple(platforms),
        fingerprint=digest.hexdigest(),
        source=ranking_dir.name,
    )


def _write_ranking(
    conn: sqlite3.Connection,
    data: RankingData,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[int, int]:
    """把榜单整份写进 `ranking` 表、重建卡带映射并更新 meta（调用方负责事务与建表）。"""
    # 逐行插入；id 显式按行序从 1 分配（整库重建，每次都是同一序列），与游戏名录一致。
    # 榜单是几千行级，事务内逐条插入可以接受。
    mapping: dict[str, int] = {}
    first_seen: dict[str, str] = {}
    conflicts: list[str] = []
    for ranking_id, row in enumerate(data.rows, start=1):
        conn.execute(
            "INSERT INTO ranking(id, platform, console, score, zh, en, cartridge_ids, in_library) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, 0)",
            (
                ranking_id,
                row.platform,
                row.console,
                row.score,
                row.zh,
                row.en,
                json.dumps(list(row.cartridge_ids), ensure_ascii=False),
            ),
        )
        seen_in_row: set[str] = set()
        for raw in row.cartridge_ids:
            normalized = normalize_cartridge_id(raw)
            if not normalized or normalized in seen_in_row:
                continue
            seen_in_row.add(normalized)
            previous = mapping.get(normalized)
            if previous is not None and previous != ranking_id:
                conflicts.append(
                    f"{normalized}（{first_seen[normalized]} ↔ "
                    f"{row.platform} / {row.zh or row.en or '未命名'}）"
                )
                continue
            mapping[normalized] = ranking_id
            first_seen.setdefault(
                normalized, f"{row.platform} / {row.zh or row.en or '未命名'}"
            )
        _notify(on_progress, "写入游戏榜单", ranking_id, len(data.rows))

    if conflicts:
        raise RankingCsvError(
            "榜单 CSV 中同一卡带 ID 出现在多行（卡带 ID 必须全局唯一）：\n  "
            + "\n  ".join(conflicts)
        )

    conn.executemany(
        "INSERT INTO ranking_cartridges(cartridge_id, ranking_id) VALUES(?, ?)",
        list(mapping.items()),
    )
    _upsert_meta(
        conn,
        {
            "ranking_schema_version": RANKING_SCHEMA_VERSION,
            "ranking_fingerprint": data.fingerprint,
            "ranking_source": data.source,
            "ranking_rows": str(len(data.rows)),
            "ranking_consoles": str(len(data.platforms)),
            "ranking_loaded_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return len(data.rows), len(data.platforms)


def _upsert_meta(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    conn.executemany(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        values.items(),
    )
