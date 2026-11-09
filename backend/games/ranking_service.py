"""游戏榜单的只读查询。

数据是 `backend/games/search_index.py` 写进 `<根路径>/db/game.db` 的 `ranking` 表
（`make index` 构建、服务启动时就地补载）。**这里只读**：每个请求开一条 `mode=ro` 的短连接，
从不建文件、从不写。榜单没加载（老库、或 CSV 还没到位）是正常状态，返回
`has_ranking: false` 而不是报错。
"""

import json
import logging
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from backend.errors import IndexUnavailableError
from backend.games.platforms import PLATFORM_BY_ID, platform_label, platform_order
from backend.games.search_index import RANKING_SCHEMA_VERSION
from backend.games.service import GameLink

logger = logging.getLogger(__name__)

# 榜单页默认选中的机种（统一机种键，也就是 EmulatorJS 的 system key）：FC。
_DEFAULT_PLATFORM = "nes"

# 「按卡带ID 找库存游戏」的能力，由构造函数注入（实现见 `GameService.map_for_cartridge_ids`）：
# 传一批**原始**卡带ID 文本，回一批命中的 `{原始ID: GameLink}`。榜单服务自己不碰 `games` 表，
# 也不 import 平台库存那边的 service，只认这个窄接口。
CartridgeLookup = Callable[[Sequence[str]], Mapping[str, GameLink]]


@dataclass(frozen=True)
class RankingItem:
    rank: int
    zh: str
    en: str
    platform: str
    cartridge_ids: tuple[str, ...]
    # 该行是否关联到平台库存里的游戏（关联在**请求期**做，见 GameRankingService._attach_links）。
    # 命中的是哪一个卡带ID 由关联规则决定，这里只留结果：游戏 id、播放页路径与是否有本体。
    game_id: int | None = None
    path: str | None = None
    # 无本体的关联行仍显示为链接样式，但前端点击时提示先上传本体（不进播放页）
    has_body: bool = False


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


# 一次库存关联查询最多带多少个卡带 ID。单个机种最多 100 行 × 2 个 ID = 200；
# 跨机种（全部机种）会有 6000+ 个，必须分批，避开 SQLite 的宿主参数上限（老版本是 999）。
_CARTRIDGE_LOOKUP_CHUNK = 500


class GameRankingService:
    def __init__(
        self, db_path: Path, cartridge_lookup: CartridgeLookup | None = None
    ) -> None:
        self._db_path = Path(db_path)
        # None = 不关联平台库存（榜单照样返回，只是没有 game_id / path）
        self._cartridge_lookup = cartridge_lookup

    def is_indexed(self) -> bool:
        """索引是否已构建。只 stat，不建目录、不建文件。"""
        return self._db_path.is_file()

    def list_consoles(self) -> RankingConsoles:
        """机种清单（去重、按词表顺序）与默认机种。

        `MIN(console)` 取的是该机种在 CSV 里出现过的写法中最小的一条，只用于「认不出机种」
        的那些当兜底；认得出的用词表统一显示名，未收录但登记了显示名的（`3DS`、`CD-I`）也统一。
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
        """取榜单（不分页）。给了机种就只取该机种；为空时取全部机种（跨机种）。

        `console` 为空**不再回落到默认机种**：榜单页默认选中 FC 是前端拿
        `/consoles` 的 `default_console` 自己填的；用户把下拉清空时，这里返回整份榜单。
        """
        if not self.is_indexed():
            return RankingPage(False, False, None, [])
        requested = (console or "").strip()
        with self._connect() as conn:
            if not _ranking_ready(conn):
                return RankingPage(True, False, None, [])
            try:
                if not requested:
                    # 跨机种：platform 一起取出来，按词表顺序再按序号排（raw: 机种排最后）。
                    rows = conn.execute(
                        "SELECT platform, rank, zh, en, cartridge_ids FROM ranking"
                    ).fetchall()
                    rows.sort(
                        key=lambda row: (platform_order(row[0]), row[0], int(row[1]))
                    )
                    items = [_to_item(row[1:], platform=row[0]) for row in rows]
                    chosen = None
                else:
                    rows = conn.execute("SELECT DISTINCT platform FROM ranking").fetchall()
                    platforms = [row[0] for row in rows]
                    if not platforms:
                        return RankingPage(True, True, None, [])
                    chosen = _match_platform(platforms, requested)
                    if chosen is None:
                        # 机种不在榜单里：回显请求值 + 空列表，与检索页的过滤语义一致
                        return RankingPage(True, True, requested, [])
                    items = [
                        _to_item(row, platform=chosen)
                        for row in conn.execute(
                            "SELECT rank, zh, en, cartridge_ids FROM ranking "
                            "WHERE platform = ? ORDER BY rank",
                            (chosen,),
                        ).fetchall()
                    ]
            except sqlite3.Error as exc:
                raise _broken(exc) from exc
        # 关联放在 with 之外：先关掉只读库的连接，再去查平台库存的 app.db
        page_items = self._attach_links(items)
        return RankingPage(True, True, chosen, page_items)

    def _attach_links(self, items: list[RankingItem]) -> list[RankingItem]:
        """把榜单行关联到平台库存的游戏（命中才有 `game_id` / `path`）。

        **关联只能在请求期做**：榜单所在的 `game.db` 是外部名录的派生只读库，刻意不与 `games` 表
        联动（构建索引时也不能把库存信息写进 `ranking` 表），所以每次请求现查一次，增删游戏立刻生效。

        规则：一行最多两个卡带ID，**任意一个**命中就算关联，命中多个时取**该行第一个命中的那个**
        （按 CSV 里的先后，结果确定）；比对是「去首尾空白 + 转大写」（`normalize_cartridge_id`）。
        **不区分有无本体**：无本体的游戏也关联，`has_body=False` 由前端决定是否拦下跳转。
        按 `_CARTRIDGE_LOOKUP_CHUNK` 分批查库存，不是逐行查。
        """
        if self._cartridge_lookup is None or not items:
            return items
        raw_ids = [cartridge_id for item in items for cartridge_id in item.cartridge_ids]
        links: dict[str, GameLink] = {}
        for start in range(0, len(raw_ids), _CARTRIDGE_LOOKUP_CHUNK):
            links.update(
                self._cartridge_lookup(raw_ids[start : start + _CARTRIDGE_LOOKUP_CHUNK])
                or {}
            )
        if not links:
            return items
        linked: list[RankingItem] = []
        for item in items:
            link = next(
                (links[cid] for cid in item.cartridge_ids if cid in links), None
            )
            if link is None:
                linked.append(item)
            else:
                linked.append(
                    replace(
                        item,
                        game_id=link.game_id,
                        path=link.path,
                        has_body=link.has_body,
                    )
                )
        return linked

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


def _to_item(row: tuple, platform: str) -> RankingItem:
    rank, zh, en, ids_text = row
    try:
        ids = json.loads(ids_text)
    except (TypeError, ValueError) as exc:
        raise _broken(exc) from exc
    if not isinstance(ids, list):
        raise _broken(ValueError(f"cartridge_ids 不是数组：{ids_text!r}"))
    return RankingItem(
        rank=int(rank),
        zh=str(zh),
        en=str(en),
        platform=platform,
        cartridge_ids=tuple(str(item) for item in ids),
    )


def _broken(exc: Exception) -> IndexUnavailableError:
    logger.warning("读取游戏榜单索引失败：%s", exc)
    return IndexUnavailableError("游戏榜单索引已损坏，请重新执行 make index 构建。")
