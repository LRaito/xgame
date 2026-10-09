import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from backend.auth.router import router as auth_router
from backend.backup import backup_database
from backend.config import (
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
    settings_from_overrides,
)
from backend.csrf import CSRFMiddleware
from backend.database import ensure_data_dir, init_db, make_engine
from backend.games.gallery_router import router as game_gallery_router
from backend.games.router import router as games_router
from backend.games.save_router import router as game_saves_router
from backend.games.screenshot_router import router as game_screenshots_router
from backend.games.settings_router import router as game_settings_router
from backend.games.stats_router import router as game_stats_router
from backend.http import json_err
from backend.mount_guard import ensure_mounted
from backend.storage.local import LocalStorage
from backend.tools.router import router as tools_router

logger = logging.getLogger(__name__)


def create_app(test_config: dict | None = None) -> FastAPI:
    settings = settings_from_overrides(test_config)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    # 数据根目录里缺 .mounted 哨兵文件就补一个（见 backend/mount_guard.py）
    ensure_mounted(settings)

    ensure_data_dir(settings)
    engine = make_engine(settings)
    init_db(engine)
    # 启动时检查一次月度备份：当月还没有就补一份，已有则跳过
    backup_database(settings)

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
        https_only=SESSION_COOKIE_SECURE and not settings.TESTING,
        same_site=settings.SESSION_COOKIE_SAMESITE,
    )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return json_err(message, exc.status_code)

    app.include_router(tools_router)
    app.include_router(auth_router)
    app.include_router(games_router)
    app.include_router(game_saves_router)
    app.include_router(game_screenshots_router)
    app.include_router(game_gallery_router)
    app.include_router(game_settings_router)
    app.include_router(game_stats_router)

    return app
