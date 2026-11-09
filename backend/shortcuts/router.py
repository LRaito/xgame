from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.deps import CurrentUser, ShortcutServiceDep
from backend.errors import ValidationError
from backend.http import json_err, json_ok

router = APIRouter(prefix="/api/user-shortcuts", tags=["user-shortcuts"])

logger = logging.getLogger(__name__)


class ShortcutBody(BaseModel):
    # 空串 = 关闭该快捷键
    binding: str


def _payload(item) -> dict:
    return {"action_id": item.action_id, "binding": item.binding}


@router.get("")
def list_shortcuts(_user: CurrentUser, service: ShortcutServiceDep):
    """当前账号的全部覆盖配置；没有出现过的动作使用前端默认键位。"""
    return json_ok(
        {"overrides": [_payload(item) for item in service.list(_user.id)]}
    )


@router.put("/{action_id}")
def set_shortcut(
    action_id: str,
    body: ShortcutBody,
    _user: CurrentUser,
    service: ShortcutServiceDep,
):
    """设置一个快捷键动作的键位；传空串表示关闭。"""
    try:
        item = service.set_binding(_user.id, action_id, body.binding)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    logger.info("已保存快捷键 user_id=%s action_id=%s", _user.id, action_id)
    return json_ok(_payload(item))


@router.delete("/{action_id}")
def reset_shortcut(
    action_id: str,
    _user: CurrentUser,
    service: ShortcutServiceDep,
):
    """删除覆盖配置，恢复到前端默认键位；幂等。"""
    try:
        service.reset(_user.id, action_id)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    logger.info("已重置快捷键 user_id=%s action_id=%s", _user.id, action_id)
    return json_ok({"action_id": action_id})
