"""游戏检索的只读查询。

数据是 `backend/games/search_index.py` 用 `make index` 或**服务启动时的自动补建**从 CSV 名录
构建出来的独立 SQLite 库（`<根路径>/db/game.db`）。**这里只读**：每个请求开一条 `mode=ro` 的
短连接，从不建文件、从不写。库不存在是正常状态（服务启动时没能补建成功，例如数据根没有写权限、
或名录 CSV 被删了），返回「未构建」而不是报错。
"""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from backend.errors import IndexUnavailableError
from backend.games.search_index import SCHEMA_VERSION
from backend.games.search_text import fts_query

logger = logging.getLogger(__name__)

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100

# 主查询。几条硬约束（都实测过，别改）：
#   1. **不能给 game_fts 起别名**：`FROM game_fts f ... WHERE f MATCH ?` 会报 `no such column: f`，
#      `bm25(f, …)` 同样报错——MATCH 与 bm25() 只认真表名。
#   2. bm25 的列权重顺序 = FTS 表的列顺序（8.0 给 zh_uni、1.0 给 en_uni），改 schema 就得跟着改。
#   3. `ORDER BY bm25(...)` 是升序（bm25 返回负值，越小越相关）。
#   4. 末尾的 `g.id` 是必须的 tiebreaker：去重后仍有 427 组「同机种 + 同英文名」的行，
#      少了它翻页会重复/丢行。
_SEARCH_SQL = """
SELECT c.id, c.name, g.id, g.zh, g.en
FROM game_fts
JOIN game    g ON g.id = game_fts.rowid
JOIN console c ON c.id = g.console_id
WHERE game_fts MATCH :q{console_filter}
ORDER BY bm25(game_fts, 8.0, 1.0), g.id
LIMIT :limit OFFSET :offset
"""

# 无关键词时的全量列表：走 idx_game_console 的顺序扫描分页。同样必须有 g.id 兜排序。
_LIST_SQL = """
SELECT c.id, c.name, g.id, g.zh, g.en
FROM game g
JOIN console c ON c.id = g.console_id
{where}
ORDER BY g.console_id, g.en, g.id
LIMIT :limit OFFSET :offset
"""

# 总数单独查。**不能**用 `COUNT(*) OVER ()` 和 bm25 排序合成一条：实测报
# `unable to use function bm25 in the requested context`。
_SEARCH_COUNT_SQL = """
SELECT count(*)
FROM game_fts
JOIN game g ON g.id = game_fts.rowid
WHERE game_fts MATCH :q{console_filter}
"""

_LIST_COUNT_SQL = "SELECT count(*) FROM game g{where}"


@dataclass(frozen=True)
class ConsoleItem:
    id: int
    name: str


@dataclass(frozen=True)
class SearchItem:
    id: int
    console_id: int
    console: str
    zh: str
    en: str


@dataclass(frozen=True)
class SearchPage:
    indexed: bool
    total: int
    page: int
    page_size: int
    items: list[SearchItem]


class GameSearchService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    def is_indexed(self) -> bool:
        """索引是否已构建。只 stat，不建目录、不建文件。"""
        return self._db_path.is_file()

    def list_consoles(self) -> list[ConsoleItem]:
        """机种清单。按 id 排（= 源文件的读取顺序，同一厂商的机种相邻）。"""
        if not self.is_indexed():
            return []
        with self._connect() as conn:
            _check_schema(conn)
            try:
                rows = conn.execute("SELECT id, name FROM console ORDER BY id").fetchall()
            except sqlite3.Error as exc:
                raise _broken(exc) from exc
        return [ConsoleItem(id=row[0], name=row[1]) for row in rows]

    def search(
        self,
        *,
        q: str | None = None,
        console_id: int | None = None,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
    ) -> SearchPage:
        """检索一页。参数越界在这里收敛（别放到 Query(ge=,le=) 上，那会返回 422 绕开错误信封）。"""
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or PAGE_SIZE_DEFAULT), PAGE_SIZE_MAX))
        if not self.is_indexed():
            return SearchPage(False, 0, page, page_size, [])

        query = fts_query(q)
        with self._connect() as conn:
            _check_schema(conn)
            # 机种过滤不写成 `:cid IS NULL OR …`：OR 会让 SQLite 放弃 idx_game_console。
            # 这里的片段是代码里的常量，不含任何用户输入。
            console_filter = " AND g.console_id = :cid" if console_id else ""
            params = {"limit": page_size, "offset": (page - 1) * page_size}
            if console_id:
                params["cid"] = int(console_id)

            if query:
                params["q"] = query
                try:
                    total = conn.execute(
                        _SEARCH_COUNT_SQL.format(console_filter=console_filter), params
                    ).fetchone()[0]
                    rows = conn.execute(
                        _SEARCH_SQL.format(console_filter=console_filter), params
                    ).fetchall()
                except sqlite3.Error as exc:
                    raise _broken(exc) from exc
            else:
                # 前导空格是必须的：模板里紧跟着 `game`，少了它就成了 `gameWHERE`
                where = " WHERE g.console_id = :cid" if console_id else ""
                try:
                    total = conn.execute(_LIST_COUNT_SQL.format(where=where), params).fetchone()[0]
                    rows = conn.execute(_LIST_SQL.format(where=where), params).fetchall()
                except sqlite3.Error as exc:
                    raise _broken(exc) from exc

        items = [
            SearchItem(id=row[2], console_id=row[0], console=row[1], zh=row[3], en=row[4])
            for row in rows
        ]
        return SearchPage(True, total, page, page_size, items)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """开一条只读连接，用完即关（`with sqlite3.connect(...)` 只管事务、不会关连接）。

        URI 用 `Path.as_uri()` 拼而不是手写 `f"file:{path}?mode=ro"`：数据根是用户配的，
        路径里可能有空格、`?`、`#`、`%`，裸拼会被 URI 解析吃掉。`query_only` 是第二道保险，
        拦住以后误加进来的写语句。
        """
        try:
            conn = sqlite3.connect(f"{self._db_path.as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            logger.warning("打开游戏检索索引失败：%s", exc)
            raise IndexUnavailableError("游戏检索索引无法打开，请重新执行 make index 构建。") from exc
        try:
            conn.execute("PRAGMA query_only = 1")
            yield conn
        finally:
            conn.close()


def _broken(exc: sqlite3.Error) -> IndexUnavailableError:
    logger.warning("读取游戏检索索引失败：%s", exc)
    return IndexUnavailableError("游戏检索索引已损坏，请重新执行 make index 构建。")


def _check_schema(conn: sqlite3.Connection) -> None:
    """校验索引版本：老库配新代码要明确报错，而不是给出莫名其妙的结果。"""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.Error as exc:
        raise _broken(exc) from exc
    if row is None or row[0] != SCHEMA_VERSION:
        raise IndexUnavailableError("游戏检索索引版本过旧，请重新执行 make index 构建。")
