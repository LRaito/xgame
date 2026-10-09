import re

from sqlmodel import Session, select

from backend.auth.models import (
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    USERNAME_PATTERN,
    User,
)
from backend.errors import AuthError, ValidationError

PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 64

_USERNAME_RE = re.compile(USERNAME_PATTERN)


def validate_username(raw: str) -> str:
    """校验并返回用户名（去首尾空白）。不合规抛 ValidationError，消息里说清原因。"""
    username = (raw or "").strip()
    if not username:
        raise ValidationError("请填写用户名。")
    if not USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH:
        raise ValidationError(
            f"用户名长度需在 {USERNAME_MIN_LENGTH}–{USERNAME_MAX_LENGTH} 个字符之间。"
        )
    if not _USERNAME_RE.match(username):
        raise ValidationError("用户名只能包含数字、字母、中划线和下划线。")
    return username


def validate_password(raw: str) -> str:
    """校验并返回密码。刻意不 strip——前后空格也是密码的一部分。"""
    password = raw or ""
    if not password:
        raise ValidationError("请填写密码。")
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValidationError(
            f"密码长度需在 {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} 个字符之间。"
        )
    return password


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_user(self, username: str, password: str) -> User:
        """注册：用户名唯一，密码只做哈希入库。"""
        username = validate_username(username)
        password = validate_password(password)
        existing = self._session.exec(
            select(User).where(User.username == username)
        ).first()
        if existing is not None:
            raise AuthError(f"用户名 {username} 已被占用，换一个吧。")
        user = User(username=username)
        user.set_password(password)
        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)
        return user

    def authenticate(self, username: str, password: str) -> User:
        user = self._session.exec(
            select(User).where(User.username == (username or "").strip())
        ).first()
        if user is None or not user.check_password(password):
            raise AuthError("用户名或密码不正确。")
        return user

    def get_by_id(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)
