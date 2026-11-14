from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.shortcuts.keys import normalize_binding, require_action_id
from backend.shortcuts.models import UserShortcut


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ShortcutOverride:
    action_id: str
    binding: str
    updated_at: datetime


class ShortcutService:
    """用户级快捷键覆盖配置：按 (用户, 动作) 一行，整行覆盖读写。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self, user_id: int) -> list[ShortcutOverride]:
        rows = self._session.exec(
            select(UserShortcut)
            .where(UserShortcut.user_id == user_id)
            .order_by(UserShortcut.action_id)
        ).all()
        return [
            ShortcutOverride(
                action_id=row.action_id,
                binding=row.binding,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    def set_binding(
        self, user_id: int, action_id: str, binding: str
    ) -> ShortcutOverride:
        """新建或覆盖一个动作的键位；`binding=""` 表示关闭。"""
        action_id = require_action_id(action_id)
        normalized = normalize_binding(binding)
        try:
            row = self._write(user_id, action_id, normalized)
        except IntegrityError:
            # 并发首写撞唯一约束（两个标签同时第一次保存）：回滚后按已有行重写
            self._session.rollback()
            row = self._write(user_id, action_id, normalized)
        return ShortcutOverride(
            action_id=row.action_id,
            binding=row.binding,
            updated_at=row.updated_at,
        )

    def reset(self, user_id: int, action_id: str) -> None:
        """删掉覆盖配置，回到前端默认键位；本来就没有时也成功。"""
        action_id = require_action_id(action_id)
        row = self._find(user_id, action_id)
        if row is not None:
            self._session.delete(row)
            self._session.commit()

    def _write(self, user_id: int, action_id: str, binding: str) -> UserShortcut:
        row = self._find(user_id, action_id)
        if row is None:
            row = UserShortcut(user_id=user_id, action_id=action_id, binding=binding)
        else:
            row.binding = binding
            row.updated_at = _utcnow()
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def _find(self, user_id: int, action_id: str) -> UserShortcut | None:
        return self._session.exec(
            select(UserShortcut).where(
                UserShortcut.user_id == user_id,
                UserShortcut.action_id == action_id,
            )
        ).first()
