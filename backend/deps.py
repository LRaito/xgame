from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from backend.auth.models import User
from backend.auth.service import AuthService
from backend.config import Settings
from backend.games.gallery_service import GalleryService
from backend.games.save_service import CloudSaveService
from backend.games.screenshot_service import ScreenshotService
from backend.games.service import GameService
from backend.games.settings_service import EmulatorSettingsService
from backend.games.stats_service import GameStatsService

SESSION_USER_KEY = "user_id"


def get_db(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, session: DbSession) -> User:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录。")
    user = AuthService(session).get_by_id(int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录。")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_game_service(request: Request, session: DbSession) -> GameService:
    return GameService(session, request.app.state.storage)


GameServiceDep = Annotated[GameService, Depends(get_game_service)]


def get_cloud_save_service(
    request: Request, session: DbSession, user: CurrentUser
) -> CloudSaveService:
    # 存档落盘路径带用户名，所以服务里要拿到当前账号
    return CloudSaveService(session, request.app.state.storage, user.username)


SaveServiceDep = Annotated[CloudSaveService, Depends(get_cloud_save_service)]


def get_screenshot_service(
    request: Request, session: DbSession, user: CurrentUser
) -> ScreenshotService:
    # 截图落盘路径带用户名，所以服务里要拿到当前账号
    return ScreenshotService(session, request.app.state.storage, user.username)


ScreenshotServiceDep = Annotated[ScreenshotService, Depends(get_screenshot_service)]


def get_gallery_service(request: Request, session: DbSession) -> GalleryService:
    # 图集按游戏共享（不记上传者），落盘路径只跟游戏走，所以不需要当前账号
    return GalleryService(session, request.app.state.storage)


GalleryServiceDep = Annotated[GalleryService, Depends(get_gallery_service)]


def get_emulator_settings_service(session: DbSession) -> EmulatorSettingsService:
    return EmulatorSettingsService(session)


EmulatorSettingsServiceDep = Annotated[
    EmulatorSettingsService, Depends(get_emulator_settings_service)
]


def get_game_stats_service(session: DbSession) -> GameStatsService:
    return GameStatsService(session)


GameStatsServiceDep = Annotated[GameStatsService, Depends(get_game_stats_service)]


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
