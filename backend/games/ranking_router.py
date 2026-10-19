"""游戏榜单接口（只读）。

数据源与游戏检索是同一个独立只读库 `<根路径>/db/game.db`（`make index` 构建、服务启动时
就地补载），所以路径挂在 `/api/games/search/ranking` 下——既和检索同源，也避免在
`/api/games` 下新增单段路径与 `games_router` 的 `/{game_id}/…` 撞车。
两条都是 GET（自动免 CSRF），都要登录。
"""

from fastapi import APIRouter, Query

from backend.deps import CurrentUser, GameRankingServiceDep
from backend.errors import IndexUnavailableError
from backend.http import json_err, json_ok

router = APIRouter(prefix="/api/games/search/ranking", tags=["games"])


@router.get("")
def game_ranking(
    _user: CurrentUser,
    service: GameRankingServiceDep,
    console: str = Query(""),
):
    """取某个机种的整份榜单（`console` 是统一机种键，取自 `/consoles`）。

    榜单没加载时返回 `has_ranking: false` + 空列表（不是错误）。
    """
    try:
        page = service.get(console=console or None)
    except IndexUnavailableError as exc:
        return json_err(str(exc), 503)
    return json_ok(
        {
            "indexed": page.indexed,
            "has_ranking": page.has_ranking,
            "console": page.console,
            "items": [
                {
                    "rank": item.rank,
                    "title": item.title,
                    "cartridge_ids": list(item.cartridge_ids),
                }
                for item in page.items
            ],
        }
    )


@router.get("/consoles")
def game_ranking_consoles(_user: CurrentUser, service: GameRankingServiceDep):
    """机种下拉的候选项（只列榜单 CSV 里出现过的机种）与默认机种。

    每项 `{platform, label, playable}`：`platform` 是统一机种键（请求榜单时原样回传），
    `label` 是与游戏管理/检索共用的统一显示名，`playable` 表示本平台是否已收录该机种。
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
            "default_console": result.default_console,
        }
    )
