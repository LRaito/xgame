from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.deps import CurrentUser, EmulatorSettingsServiceDep
from backend.errors import ValidationError
from backend.http import iso, json_err, json_ok

router = APIRouter(prefix="/api/games/emulator-settings", tags=["game-emulator-settings"])

logger = logging.getLogger(__name__)


class EmulatorSettingsBody(BaseModel):
    game_type: str
    # 引擎设置块原样透传，结构校验交给 service（Pydantic 直接 422 会绕开统一错误信封）
    settings: Any


def _payload(item) -> dict:
    return {
        "game_type": item.game_type,
        "settings": item.settings,
        "updated_at": iso(item.updated_at),
    }


@router.get("")
def emulator_settings_get(
    _user: CurrentUser,
    service: EmulatorSettingsServiceDep,
    game_type: str = Query(...),
):
    """取当前用户某平台（gba/nes/…）的模拟器设置；还没存过时 settings 为 null。"""
    try:
        item = service.get(user_id=_user.id, game_type=game_type)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    if item is None:
        return json_ok({"game_type": game_type, "settings": None, "updated_at": None})
    return json_ok(_payload(item))


@router.put("")
def emulator_settings_save(
    body: EmulatorSettingsBody,
    _user: CurrentUser,
    service: EmulatorSettingsServiceDep,
):
    """整块覆盖保存当前用户某平台的模拟器设置。"""
    try:
        item = service.save(
            user_id=_user.id, game_type=body.game_type, settings=body.settings
        )
    except ValidationError as exc:
        return json_err(str(exc), 400)
    logger.info("已保存模拟器设置 user_id=%s game_type=%s", _user.id, body.game_type)
    return json_ok(_payload(item))
