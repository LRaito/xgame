"""游戏榜单的只读查询。

数据是 `backend/games/search_index.py` 写进 `<根路径>/db/game.db` 的 `ranking` 表
（`make index` 构建、服务启动时就地补载）。**这里只读**：每个请求开一条 `mode=ro` 的短连接，
从不建文件、从不写。榜单没加载（老库、或 CSV 还没到位）是正常状态，返回
`has_ranking: false` 而不是报错。
"""

import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from backend.errors import IndexUnavailableError
from backend.games.search_index import RANKING_SCHEMA_VERSION

logger = logging.getLogger(__name__)

# 榜单页默认选中的机种：先精确匹配 GBA，再退到名称里含 GBA 的（兼容「任天堂GBA」）。
_DEFAULT_CONSOLE = "GBA"


@dataclass(frozen=True)
class RankingItem:
    rank: int
    title: str
    cartridge_ids: tuple[str, ...]


@dataclass(frozen=True)
class RankingPage:
    indexed: bool
    has_ranking: bool
    console: str | None
    items: list[RankingItem]


@dataclass(frozen=True)
class RankingConsoles:
    indexed: bool
    has_ranking: bool
    consoles: list[str]
    default_console: str | None


class GameRankingService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    def is_indexed(self) -> bool:
        """索引是否已构建。只 stat，不建目录、不建文件。"""
        return self._db_path.is_file()

    def list_consoles(self) -> RankingConsoles:
        """机种清单（去重、按名称排序）与默认机种。"""
        if not self.is_indexed():
            return RankingConsoles(False, False, [], None)
        with self._connect() as conn:
            if not _ranking_ready(conn):
                return RankingConsoles(True, False, [], None)
            try:
                rows = conn.execute(
                    "SELECT DISTINCT console FROM ranking ORDER BY console"
                ).fetchall()
            except sqlite3.Error as exc:
                raise _broken(exc) from exc
        consoles = [row[0] for row in rows]
        return RankingConsoles(True, True, consoles, _pick_default(consoles))

    def get(self, console: str | None = None) -> RankingPage:
        """取某个机种的整份榜单（不分页）。机种为空时用默认机种。"""
        if not self.is_indexed():
            return RankingPage(False, False, None, [])
        requested = (console or "").strip()
        with self._connect() as conn:
            if not _ranking_ready(conn):
                return RankingPage(True, False, None, [])
            try:
                rows = conn.execute(
                    "SELECT DISTINCT console FROM ranking ORDER BY console"
                ).fetchall()
                consoles = [row[0] for row in rows]
                if not consoles:
                    return RankingPage(True, True, None, [])
                chosen = _pick_default(consoles) if not requested else _match_console(consoles, requested)
                if chosen is None:
                    # 机种不在榜单里：回显请求值 + 空列表，与检索页的过滤语义一致
                    return RankingPage(True, True, requested, [])
                items = conn.execute(
                    "SELECT rank, title, cartridge_ids FROM ranking "
                    "WHERE console = ? ORDER BY rank",
                    (chosen,),
                ).fetchall()
            except sqlite3.Error as exc:
                raise _broken(exc) from exc
        return RankingPage(True, True, chosen, [_to_item(row) for row in items])

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """开一条只读连接，用完即关（与 `GameSearchService._connect` 同一套写法）。

        URI 用 `Path.as_uri()` 拼而不是手写 `f"file:{path}?mode=ro"`：数据根是用户配的，
        路径里可能有空格、`?`、`#`、`%`，裸拼会被 URI 解析吃掉。`query_only` 是第二道保险。
        """
        try:
            conn = sqlite3.connect(f"{self._db_path.as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            logger.warning("打开游戏榜单索引失败：%s", exc)
            raise IndexUnavailableError("游戏检索索引无法打开，请重新执行 make index 构建。") from exc
        try:
            conn.execute("PRAGMA query_only = 1")
            yield conn
        finally:
            conn.close()


def _ranking_ready(conn: sqlite3.Connection) -> bool:
    """库里确实装过榜单：表在、版本对、指纹在。没装过是正常状态，不是错误。

    只有「版本在但不匹配」才报 503——那是代码与库对不上，得重建。
    """
    try:
        version = conn.execute(
            "SELECT value FROM meta WHERE key = 'ranking_schema_version'"
        ).fetchone()
        fingerprint = conn.execute(
            "SELECT value FROM meta WHERE key = 'ranking_fingerprint'"
        ).fetchone()
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ranking'"
        ).fetchone()
    except sqlite3.Error as exc:
        raise _broken(exc) from exc
    if version and version[0] != RANKING_SCHEMA_VERSION:
        raise IndexUnavailableError("游戏榜单索引版本过旧，请重新执行 make index 构建。")
    return bool(version and fingerprint and table)


def _pick_default(consoles: list[str]) -> str | None:
    """默认机种：GBA（不区分大小写）→ 名称里含 GBA 的 → 排序后的第一个。"""
    if not consoles:
        return None
    for name in consoles:
        if name.casefold() == _DEFAULT_CONSOLE.casefold():
            return name
    for name in consoles:
        if _DEFAULT_CONSOLE.casefold() in name.casefold():
            return name
    return consoles[0]


def _match_console(consoles: list[str], requested: str) -> str | None:
    """把请求里的机种名对回库里的写法：先精确，再大小写不敏感。"""
    if requested in consoles:
        return requested
    folded = requested.casefold()
    for name in consoles:
        if name.casefold() == folded:
            return name
    return None


def _to_item(row: tuple) -> RankingItem:
    rank, title, ids_text = row
    try:
        ids = json.loads(ids_text)
    except (TypeError, ValueError) as exc:
        raise _broken(exc) from exc
    if not isinstance(ids, list):
        raise _broken(ValueError(f"cartridge_ids 不是数组：{ids_text!r}"))
    return RankingItem(rank=int(rank), title=title, cartridge_ids=tuple(str(item) for item in ids))


def _broken(exc: Exception) -> IndexUnavailableError:
    logger.warning("读取游戏榜单索引失败：%s", exc)
    return IndexUnavailableError("游戏榜单索引已损坏，请重新执行 make index 构建。")
