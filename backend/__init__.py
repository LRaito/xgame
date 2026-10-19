import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from backend.auth.router import router as auth_router
from backend.backup import backup_database, start_backup_loop
from backend.config import LOG_FORMAT, SECRET_KEY, settings_from_overrides
from backend.csrf import CSRFMiddleware
from backend.database import ensure_data_dir, init_db, make_engine
from backend.games.gallery_router import router as game_gallery_router
from backend.games.ranking_router import router as game_ranking_router
from backend.games.router import router as games_router
from backend.games.save_router import router as game_saves_router
from backend.games.screenshot_router import router as game_screenshots_router
from backend.games.search_index import ensure_game_index
from backend.games.search_router import router as game_search_router
from backend.games.settings_router import router as game_settings_router
from backend.games.stats_router import router as game_stats_router
from backend.http import json_err
from backend.mount_guard import require_mounted
from backend.request_limit import RequestBodyLimitMiddleware
from backend.storage.local import LocalStorage
from backend.tools.router import router as tools_router

logger = logging.getLogger(__name__)


def create_app(test_config: dict | None = None) -> FastAPI:
    settings = settings_from_overrides(test_config)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    # 数据根目录里没有 .mounted 哨兵文件就不放行：打日志、等 5 秒、退出进程，由容器重启策略
    # 反复重试（见 backend/mount_guard.py）。必须在建目录、建库之前。
    require_mounted(settings)

    ensure_data_dir(settings)
    engine = make_engine(settings)
    init_db(engine)
    # 启动先备一次，之后由守护线程每小时再备一次（当月只有一份 <YYYY-MM>.db，每次都整份重写）
    backup_database(settings)
    start_backup_loop(settings)
    # 启动时检查一次游戏检索索引：没有就自动补建（已有则跳过；建不出来只记 warning，不拦启动）
    ensure_game_index(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = lambda: Session(engine)

    # 游戏素材与存档都按相对路径落在项目文件根目录下，根目录不存在时自动建出来
    app.state.storage = LocalStorage(settings.STORAGE_ROOT)

    app.add_middleware(CSRFMiddleware, settings=settings)
    app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        https_only=settings.SESSION_COOKIE_SECURE and not settings.TESTING,
        same_site=settings.SESSION_COOKIE_SAMESITE,
    )
    # 顶替 nginx 的 client_max_body_size（见 backend/request_limit.py）：Docker 路线上 nginx 先拦，
    # 这里只是兜底；「解压即用」的 Windows 包没有 nginx，就靠它当唯一的全局上传闸门。
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_BYTES)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return json_err(message, exc.status_code)

    app.include_router(tools_router)
    app.include_router(auth_router)
    app.include_router(games_router)
    # 紧跟 games_router。注意 `/api/games/search`、`/api/games/search/consoles` 与
    # `/api/games/search/ranking…` 之所以不会被 games_router 的 `/{game_id}/…` 抢走，是因为那些
    # 路由的第二段字面量只有 cover/play/h5/guide，且 `/api/games` 下没有单段 `/{game_id}`。
    # 以后若给 games_router 加一条单段动态路由，这里就会撞车。
    app.include_router(game_search_router)
    # 榜单与检索共用同一个只读库（game.db），只是读另一张表，所以也挂在这条前缀下
    app.include_router(game_ranking_router)
    app.include_router(game_saves_router)
    app.include_router(game_screenshots_router)
    app.include_router(game_gallery_router)
    app.include_router(game_settings_router)
    app.include_router(game_stats_router)

    # 「解压即用」的 Windows 包专用，靠环境变量开关，Docker 路线默认关闭：
    # 静态站（没有 nginx 时由后端托管 dist）。它是 catch-all 路由，必须注册在所有 API 路由之后。
    from backend.static_site import mount_static_site

    mount_static_site(app, settings)

    return app
