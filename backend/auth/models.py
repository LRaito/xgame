from datetime import datetime, timezone

from sqlmodel import Field, SQLModel
from werkzeug.security import check_password_hash, generate_password_hash

# 用户名规则：数字、字母、中划线、下划线。刻意收窄字符集，因为它会被直接当成
# 存档目录名（save/{用户名}/…），不允许空格、点、中文等需要额外转义的字符。
USERNAME_PATTERN = r"^[0-9A-Za-z_-]+$"
USERNAME_MIN_LENGTH = 2
USERNAME_MAX_LENGTH = 32


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    """账号：只用于隔离各人的模拟器配置与存档，不做邮箱/找回密码等安全机制。"""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(max_length=USERNAME_MAX_LENGTH, unique=True, index=True)
    password_hash: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=_utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class LoginAttempt(SQLModel, table=True):
    """登录失败计数与锁定：同一用户名连续失败到阈值就锁一段时间。"""

    __tablename__ = "login_attempts"

    username: str = Field(primary_key=True, max_length=USERNAME_MAX_LENGTH)
    failed_count: int = Field(default=0)
    locked_until: datetime | None = Field(default=None)
