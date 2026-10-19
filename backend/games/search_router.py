"""游戏检索接口（只读）。

数据源是 `make index` 构建的独立只读库 `<根路径>/db/game.db`，与平台自己的 `games` 表无关。
两条路径都在 `/api/games/search` 下，都是 GET（自动免 CSRF），都要登录。
"""

from fastapi import APIRouter, Query

from backend.deps import CurrentUser, GameSearchServiceDep
from backend.errors import IndexUnavailableError
from backend.games.search_service import PAGE_SIZE_DEFAULT
from backend.http import json_err, json_ok

router = APIRouter(prefix="/api/games/search", tags=["games"])


@router.get("")
def game_search(
    _user: CurrentUser,
    service: GameSearchServiceDep,
    q: str = Query(""),
    console_id: int | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(PAGE_SIZE_DEFAULT),
):
    """在名录里检索一页。索引还没构建时返回 `indexed: false` + 空列表（不是错误）。"""
    try:
        result = service.search(q=q, console_id=console_id, page=page, page_size=page_size)
    except IndexUnavailableError as exc:
        return json_err(str(exc), 503)
    return json_ok(
        {
            "indexed": result.indexed,
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "items": [
                {
                    "id": item.id,
                    "console_id": item.console_id,
                    "console": item.console,
                    "zh": item.zh,
                    "en": item.en,
                }
                for item in result.items
            ],
        }
    )


@router.get("/consoles")
def game_search_consoles(_user: CurrentUser, service: GameSearchServiceDep):
    """机种下拉的候选项（按 id 排 = 词表顺序，同一厂商的机种相邻）。

    一行 = 一个统一机种（`任天堂GB` 与 `任天堂GBC` 是同一行「任天堂 GB/GBC」），
    `platform_id` 是 EmulatorJS 的 system key，未收录机种为 null。
    """
    try:
        consoles = service.list_consoles()
    except IndexUnavailableError as exc:
        return json_err(str(exc), 503)
    return json_ok(
        {
            "indexed": service.is_indexed(),
            "consoles": [
                {"id": item.id, "name": item.name, "platform_id": item.platform_id}
                for item in consoles
            ],
        }
    )
