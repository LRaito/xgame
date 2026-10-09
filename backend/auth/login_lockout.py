from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from backend.auth.models import LoginAttempt
from backend.errors import LoginLockedError

SHORT_LOCK_THRESHOLD = 3
DAY_LOCK_THRESHOLD = 6
SHORT_LOCK_MINUTES = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _end_of_utc_day(now: datetime) -> datetime:
    next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return next_day


class LoginLockoutService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def check_allowed(self, username: str) -> None:
        username = (username or "").strip()
        if not username:
            return
        attempt = self._get(username)
        if attempt is None or attempt.locked_until is None:
            return

        now = _utcnow()
        locked_until = _ensure_aware(attempt.locked_until)
        if now >= locked_until:
            attempt.locked_until = None
            self._session.add(attempt)
            self._session.commit()
            return

        if attempt.failed_count >= DAY_LOCK_THRESHOLD:
            raise LoginLockedError("登录失败次数过多，今日已禁止登录，请明天再试。")
        raise LoginLockedError("登录失败次数过多，请 5 分钟后再试。")

    def record_failure(self, username: str) -> None:
        username = (username or "").strip()
        if not username:
            return

        attempt = self._get_or_create(username)
        attempt.failed_count += 1
        now = _utcnow()
        if attempt.failed_count >= DAY_LOCK_THRESHOLD:
            attempt.locked_until = _end_of_utc_day(now)
        elif attempt.failed_count >= SHORT_LOCK_THRESHOLD:
            attempt.locked_until = now + timedelta(minutes=SHORT_LOCK_MINUTES)

        self._session.add(attempt)
        self._session.commit()

    def record_success(self, username: str) -> None:
        username = (username or "").strip()
        if not username:
            return
        attempt = self._get(username)
        if attempt is None:
            return
        self._session.delete(attempt)
        self._session.commit()

    def _get(self, username: str) -> LoginAttempt | None:
        return self._session.get(LoginAttempt, username)

    def _get_or_create(self, username: str) -> LoginAttempt:
        attempt = self._get(username)
        if attempt is not None:
            return attempt
        attempt = LoginAttempt(username=username)
        self._session.add(attempt)
        self._session.commit()
        self._session.refresh(attempt)
        return attempt
