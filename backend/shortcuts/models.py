from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserShortcut(SQLModel, table=True):
    """某个账号对一个快捷键动作的覆盖配置。

    没有这一行 = 使用前端默认键位；`binding=""` = 用户主动关闭了该快捷键。
    `action_id` 由前端动作注册表定义（如 `play.sync_cloud`），后端只校验字符集。
    """

    __tablename__ = "user_shortcuts"
    __table_args__ = (UniqueConstraint("user_id", "action_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    action_id: str = Field(max_length=64)
    binding: str = Field(default="", max_length=64)
    updated_at: datetime = Field(default_factory=_utcnow)
