"""游戏榜单接口（只读）。

数据源与游戏名录是同一个独立只读库 `<运行时根>/db/game.db`（`make index` 构建、启动只建空结构），
所以路径挂在 `/api/games/search/ranking` 下——既和游戏名录同源，也避免在
`/api/games` 下新增单段路径与 `games_router` 的 `/{game_id}/…` 撞车。
两条都是 GET（自动免 CSRF），都要登录。
"""

from fastapi import APIRouter, Query

from backend.deps import CurrentUser, GameRankingServiceDep
from backend.errors import IndexUnavailableError
from backend.games.search_service import PAGE_SIZE_DEFAULT
from backend.http import json_err, json_ok

router = APIRouter(prefix="/api/games/search/ranking", tags=["games"])


@router.get("")
def game_ranking(
    _user: CurrentUser,
    service: GameRankingServiceDep,
    console: str = Query(""),
    keyword: str = Query(""),
    in_library: bool | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(PAGE_SIZE_DEFAULT),
):
    """取榜单的一页（`console` 是统一机种键，取自 `/consoles`；不传则跨机种）。

    关键词与库存三态（全部/之内/之外）都由服务端过滤。`page` / `page_size` 越界在 service 收敛。
    榜单没加载时返回 `has_ranking: false` + 空列表（不是错误）。
    与平台库存关联上的行会多三个字段（`game_id` / `path` / `has_body`）。
    """
    try:
        result = service.get(
            console=console or None,
            page=page,
            page_size=page_size,
            keyword=keyword,
            in_library=in_library,
        )
    except IndexUnavailableError as exc:
        return json_err(str(exc), 503)
    return json_ok(
        {
            "indexed": result.indexed,
            "has_ranking": result.has_ranking,
            "console": result.console,
            "page": result.page,
            "page_size": result.page_size,
            "total": result.total,
            "matched_total": result.matched_total,
            "items": [
                {
                    "score": item.score,
                    "zh": item.zh,
                    "en": item.en,
                    "platform": item.platform,
                    "cartridge_ids": list(item.cartridge_ids),
                    "in_library": item.in_library,
                    "game_id": item.game_id,
                    "path": item.path,
                    "has_body": item.has_body,
                }
                for item in result.items
            ],
        }
    )


@router.get("/consoles")
def game_ranking_consoles(_user: CurrentUser, service: GameRankingServiceDep):
    """机种下拉的候选项（只列榜单 CSV 里出现过的机种）。

    每项 `{platform, label, playable}`：`platform` 是统一机种键（请求榜单时原样回传），
    `label` 是与游戏管理/游戏名录共用的统一显示名，`playable` 表示本平台是否已收录该机种。
    页面默认不选中任何类型。
    """
    try:
        result = service.list_consoles()
    except IndexUnavailableError as exc:
        return json_err(str(exc), 503)
    return json_ok(
        {
            "indexed": result.indexed,
            "has_ranking": result.has_ranking,
            "consoles": [
                {
                    "platform": item.platform,
                    "label": item.label,
                    "playable": item.playable,
                }
                for item in result.consoles
            ],
        }
    )
