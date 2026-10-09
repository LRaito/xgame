from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.deps import CurrentUser, GameStatsServiceDep
from backend.errors import NotFoundError, ValidationError
from backend.http import json_err, json_ok

router = APIRouter(prefix="/api/games/stats", tags=["game-stats"])

logger = logging.getLogger(__name__)


class PlaytimeAddBody(BaseModel):
    game_id: int
    # 收 float 再由 service 取整：声明成 int 会让 30.5 这类上报直接 422，
    # 绕开统一错误信封（与 list_recent 越界值在 service 收敛是同一个理由）
    seconds: float = 0


class PlaytimeSetBody(BaseModel):
    hours: float = 0


class ProgressSetBody(BaseModel):
    progress: str = ""


@router.post("/playtime")
def stats_add_playtime(
    body: PlaytimeAddBody,
    _user: CurrentUser,
    service: GameStatsServiceDep,
):
    """播放页累计一段游玩时长（best-effort 心跳上报）。"""
    try:
        total = service.add_playtime(_user.id, body.game_id, body.seconds)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok({"play_seconds": total})


@router.put("/{game_id}/playtime")
def stats_set_playtime(
    game_id: int,
    body: PlaytimeSetBody,
    _user: CurrentUser,
    service: GameStatsServiceDep,
):
    """手动把总时长改写成指定小时数（游戏中心右键菜单）。"""
    try:
        total = service.set_playtime(_user.id, game_id, body.hours)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    logger.info("已设置游戏总时长 user_id=%s game_id=%s", _user.id, game_id)
    return json_ok({"play_seconds": total})


@router.put("/{game_id}/progress")
def stats_set_progress(
    game_id: int,
    body: ProgressSetBody,
    _user: CurrentUser,
    service: GameStatsServiceDep,
):
    """手动设置游戏进度：未开始 / 进行中 / 已通关。"""
    try:
        progress = service.set_progress(_user.id, game_id, body.progress)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    logger.info("已设置游戏进度 user_id=%s game_id=%s", _user.id, game_id)
    return json_ok({"progress": progress})
