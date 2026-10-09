from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.errors import ValidationError
from backend.games.models import GameEmulatorSettings

# 只有主机模拟器有这套设置：flash 走 Ruffle、h5 是沙箱 iframe，都没有 EmulatorJS 设置
_EMULATOR_TYPES = frozenset({"nes", "snes", "gb", "gba", "segaMD", "segaGG", "segaMS"})
# 引擎那块设置（键位 + 选项 + 金手指）实测几 KB，留足余量即可
_MAX_PAYLOAD_BYTES = 64 * 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EmulatorSettings:
    game_type: str
    settings: dict
    updated_at: datetime


class EmulatorSettingsService:
    """模拟器设置按(用户, 平台)一份：内容就是引擎 localStorage 值的 JSON 文本。

    数据量小（几 KB），整体覆盖读写，元数据与内容都放 SQLite，不落文件。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: int, game_type: str) -> EmulatorSettings | None:
        self._require_emulator_type(game_type)
        row = self._find(user_id, game_type)
        return None if row is None else self._to_result(row)

    def save(self, user_id: int, game_type: str, settings: dict) -> EmulatorSettings:
        """整块覆盖：没有则新建，已有则替换 payload。"""
        self._require_emulator_type(game_type)
        payload = _dump_payload(settings)
        try:
            row = self._write(user_id, game_type, payload)
        except IntegrityError:
            # 并发首写撞唯一约束（多标签同时第一次保存）：回滚后按已有行重写
            self._session.rollback()
            row = self._write(user_id, game_type, payload)
        return self._to_result(row)

    def _write(self, user_id: int, game_type: str, payload: str) -> GameEmulatorSettings:
        row = self._find(user_id, game_type)
        if row is None:
            row = GameEmulatorSettings(user_id=user_id, game_type=game_type, payload=payload)
        else:
            row.payload = payload
            row.updated_at = _utcnow()
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def _find(self, user_id: int, game_type: str) -> GameEmulatorSettings | None:
        return self._session.exec(
            select(GameEmulatorSettings).where(
                GameEmulatorSettings.user_id == user_id,
                GameEmulatorSettings.game_type == game_type,
            )
        ).first()

    @staticmethod
    def _require_emulator_type(game_type: str) -> None:
        if game_type not in _EMULATOR_TYPES:
            raise ValidationError("该游戏类型不支持保存模拟器设置。")

    @staticmethod
    def _to_result(row: GameEmulatorSettings) -> EmulatorSettings:
        try:
            settings = json.loads(row.payload or "{}")
        except ValueError:
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        return EmulatorSettings(
            game_type=row.game_type,
            settings=settings,
            updated_at=row.updated_at,
        )


def _dump_payload(settings) -> str:
    """校验并序列化引擎设置块。

    EmulatorJS 读回时会校验 `controlSettings`/`settings` 是对象、`cheats` 是数组，
    任一不合规就整块丢弃，所以在入口就把结构卡住，避免存进一份永远不会被加载的数据。
    """
    if not isinstance(settings, dict):
        raise ValidationError("设置内容格式错误。")
    if not isinstance(settings.get("controlSettings"), dict) or not isinstance(
        settings.get("settings"), dict
    ):
        raise ValidationError("设置内容缺少必要字段。")
    if not isinstance(settings.get("cheats"), list):
        raise ValidationError("设置内容缺少必要字段。")
    try:
        payload = json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("设置内容无法保存。") from exc
    if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise ValidationError("设置内容过大。")
    return payload
