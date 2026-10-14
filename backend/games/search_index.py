"""游戏检索索引的构建。

`make index` 与**服务启动时的自动补建**都走这里的 `build_index()`，它是
`<根路径>/db/game.db` 的**唯一写入方**；平台运行期的所有读都走
`search_service.GameSearchService`，它一律以 `mode=ro` 打开。所以这里可以放心用
「整库重建 + 原子替换」这种最简单也最不容易出错的做法，不需要增量更新。

数据源是 `backend/search/csv/` 下的一份份 `机种,中文,英文` 三列名录（UTF-8 带 BOM、CRLF、无表头）。
"""

import csv
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.config import SEARCH_CSV_DIR, Settings
from backend.games.search_text import index_text

logger = logging.getLogger(__name__)

# 索引结构的版本。改了表结构就加一，运行期读到不匹配的版本会直接报「请重新构建」，
# 而不是在旧库上跑出新代码的诡异结果。
SCHEMA_VERSION = "1"

# 建库语句。game_fts 是 contentless（content=''）表：只存倒排索引、不重复存正文，
# 正文永远从 game 表取——所以 snippet()/highlight() 在它上面恒返回 NULL，高亮必须在前端做。
_SCHEMA = """
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


class IndexBuildError(Exception):
    """构建失败。message 是给用户看的中文，`backend/cli.py` 直接打印。"""


@dataclass(frozen=True)
class BuildStats:
    rows: int
    consoles: int
    seconds: float
    size: int
    path: Path


def ensure_game_index(settings: Settings, *, csv_dir: Path | None = None) -> BuildStats | None:
    """启动时补一次索引：**没有才建**，已经存在就跳过。

    服务起来后自检一次，用户就不用为了第一次能用检索页去手工跑命令；`make index` 仍然是
    手动重建/更新索引的入口（换 CSV、改分词规则之后用它覆盖）。

    全程 best-effort，**绝不拦住启动**：建不出来最多是检索页提示「尚未构建索引」。
    容器里必然走 `csv_dir` 不存在那条分支——CSV 被 `.dockerignore` 排除、镜像里没有，
    索引应当在宿主机上构建（数据根是同一个宿主目录，所以构建完容器立刻能读到）。
    """
    if settings.TESTING:
        return None
    target = settings.game_index_path
    if target.is_file():
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
        return build_index(source, target)
    except Exception as exc:  # noqa: BLE001 - 建不出来不该拦住服务启动
        logger.warning("自动构建游戏检索索引失败（不影响启动）：%s", exc)
        return None


def build_index(csv_dir: Path, out_path: Path) -> BuildStats:
    """读 `csv_dir` 下所有 CSV，重建 `out_path`（`<根路径>/db/game.db`）。

    可重复执行：每次都从零重建，成功后整体替换旧文件。失败不会留下半成品——
    临时文件写在同目录、失败即删，旧库原封不动。
    """
    csv_files = sorted(Path(csv_dir).glob("*.csv"))
    if not csv_files:
        raise IndexBuildError(f"没有找到任何 CSV 名录：{csv_dir}")

    out_path = Path(out_path)
    temp_path = out_path.with_name(f"{out_path.name}.tmp")
    started = time.monotonic()

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.unlink(missing_ok=True)
        rows, consoles = _write_database(csv_files, temp_path)
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
    )
    logger.info("游戏检索索引已重建：%s（%d 行 / %d 机种）", out_path, rows, consoles)
    return stats


def _permission_error(out_path: Path) -> IndexBuildError:
    """写不进去时给一条能照做的中文提示（默认数据根被 Docker 以 root 建过就会撞上）。"""
    return IndexBuildError(
        f"没有写入权限：{out_path.parent}\n"
        f"（该目录多半是 Docker 容器以 root 建的）先执行一次：\n"
        f'    sudo chown -R "$USER" {out_path.parent.parent}\n'
        f"再重新运行 make index。"
    )


def _write_database(csv_files: list[Path], temp_path: Path) -> tuple[int, int]:
    """把名录写进临时库文件，返回 (行数, 机种数)。"""
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
    return row_id, len(console_ids)


def _read_csv(csv_file: Path):
    """逐行读一个源 CSV。带 BOM、CRLF，所以用 utf-8-sig + newline='' 交给 csv 模块处理引号。"""
    with csv_file.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.reader(handle)
