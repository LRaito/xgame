import secrets

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.config import Settings
from backend.http import json_err

CSRF_SESSION_KEY = "csrf_token"
CSRF_HEADER = "X-CSRFToken"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token(session: dict) -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf(request: Request, settings: Settings) -> None:
    if settings.TESTING:
        return
    if request.method in CSRF_SAFE_METHODS:
        return
    path = request.url.path
    if path in ("/health", "/api/csrf", "/api/register", "/api/login"):
        return
    session_token = request.session.get(CSRF_SESSION_KEY)
    header_token = request.headers.get(CSRF_HEADER)
    if (
        not session_token
        or not header_token
        or not secrets.compare_digest(session_token, header_token)
    ):
        raise HTTPException(status_code=400, detail="请求校验失败，请刷新后重试。")


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            validate_csrf(request, self._settings)
        except HTTPException as exc:
            return json_err(str(exc.detail), exc.status_code)
        return await call_next(request)
