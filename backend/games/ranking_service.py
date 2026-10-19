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
from backend.games.platforms import PLATFORM_BY_ID, platform_label, platform_order
from backend.games.search_index import RANKING_SCHEMA_VERSION

logger = logging.getLogger(__name__)

# 榜单页默认选中的机种（统一机种键，也就是 EmulatorJS 的 system key）：FC。
_DEFAULT_PLATFORM = "nes"


@dataclass(frozen=True)
class RankingItem:
    rank: int
    title: str
    cartridge_ids: tuple[str, ...]


@dataclass(frozen=True)
class RankingConsole:
    """榜单里的一个机种：统一机种键 + 统一显示名 + 本机种在平台上能不能玩。"""

    platform: str
    label: str
    playable: bool


@dataclass(frozen=True)
class RankingPage:
    indexed: bool
    has_ranking: bool
    console: str | None  # 回显的是统一机种键
    items: list[RankingItem]


@dataclass(frozen=True)
class RankingConsoles:
    indexed: bool
    has_ranking: bool
    consoles: list[RankingConsole]
    default_console: str | None


class GameRankingService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    def is_indexed(self) -> bool:
        """索引是否已构建。只 stat，不建目录、不建文件。"""
        return self._db_path.is_file()

    def list_consoles(self) -> RankingConsoles:
        """机种清单（去重、按词表顺序）与默认机种。

        `MIN(console)` 取的是该机种在 CSV 里出现过的写法中最小的一条，只用于「认不出机种」
        的那些（`3DS`、`CD-I`）当显示名；认得出的用词表里的统一显示名。
        """
        if not self.is_indexed():
            return RankingConsoles(False, False, [], None)
        with self._connect() as conn:
            if not _ranking_ready(conn):
                return RankingConsoles(True, False, [], None)
            try:
                rows = conn.execute(
                    "SELECT platform, MIN(console) FROM ranking GROUP BY platform"
                ).fetchall()
            except sqlite3.Error as exc:
                raise _broken(exc) from exc
        consoles = sorted(
            (_to_console(row[0], row[1]) for row in rows),
            key=lambda item: (platform_order(item.platform), item.platform),
        )
        return RankingConsoles(
            True, True, consoles, _pick_default([item.platform for item in consoles])
        )

    def get(self, console: str | None = None) -> RankingPage:
        """取某个机种的整份榜单（不分页）。机种为空时用默认机种。"""
        if not self.is_indexed():
            return RankingPage(False, False, None, [])
        requested = (console or "").strip()
        with self._connect() as conn:
            if not _ranking_ready(conn):
                return RankingPage(True, False, None, [])
            try:
                rows = conn.execute("SELECT DISTINCT platform FROM ranking").fetchall()
                platforms = [row[0] for row in rows]
                if not platforms:
                    return RankingPage(True, True, None, [])
                chosen = (
                    _pick_default(platforms)
                    if not requested
                    else _match_platform(platforms, requested)
                )
                if chosen is None:
                    # 机种不在榜单里：回显请求值 + 空列表，与检索页的过滤语义一致
                    return RankingPage(True, True, requested, [])
                items = conn.execute(
                    "SELECT rank, title, cartridge_ids FROM ranking "
                    "WHERE platform = ? ORDER BY rank",
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


def _pick_default(platforms: list[str]) -> str | None:
    """默认机种：FC → 词表里最靠前的那个（认不出机种的排在词表之后，不会抢到默认位）。"""
    if not platforms:
        return None
    if _DEFAULT_PLATFORM in platforms:
        return _DEFAULT_PLATFORM
    return min(platforms, key=lambda item: (platform_order(item), item))


def _match_platform(platforms: list[str], requested: str) -> str | None:
    """把请求里的机种键对回库里的写法：先精确，再大小写不敏感（`raw:` 那些是归一后的原文）。"""
    if requested in platforms:
        return requested
    folded = requested.casefold()
    for platform in platforms:
        if platform.casefold() == folded:
            return platform
    return None


def _to_console(platform: str, raw_console: str) -> RankingConsole:
    """库里的一行机种 → 展示用的机种项。认得出机种就用统一显示名，认不出用 CSV 原文。"""
    return RankingConsole(
        platform=platform,
        label=platform_label(platform, raw_console),
        playable=platform in PLATFORM_BY_ID and bool(PLATFORM_BY_ID[platform].extensions),
    )


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
