import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.auth.login_lockout import LoginLockoutService
from backend.auth.service import AuthService
from backend.csrf import generate_csrf_token
from backend.deps import SESSION_USER_KEY, CurrentUser, DbSession
from backend.errors import AuthError, LoginLockedError, ValidationError
from backend.http import json_err, json_ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])


class CredentialsBody(BaseModel):
    username: str = ""
    password: str = ""


@router.get("/csrf")
def csrf_token(request: Request):
    token = generate_csrf_token(request.session)
    return json_ok({"csrf_token": token})


@router.post("/register")
def register(body: CredentialsBody, request: Request, session: DbSession):
    """开放注册：只填用户名与密码，注册成功即登录。"""
    try:
        user = AuthService(session).create_user(body.username, body.password)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    except AuthError as exc:
        return json_err(str(exc), 409)
    request.session[SESSION_USER_KEY] = user.id
    logger.info("新用户已注册并登录 id=%s", user.id)
    return json_ok(_me_payload(user))


@router.post("/login")
def login(body: CredentialsBody, request: Request, session: DbSession):
    username = (body.username or "").strip()
    lockout = LoginLockoutService(session)
    try:
        lockout.check_allowed(username)
        user = AuthService(session).authenticate(body.username, body.password)
    except LoginLockedError as exc:
        return json_err(str(exc), 429)
    except AuthError as exc:
        if username:
            lockout.record_failure(username)
        return json_err(str(exc), 401)
    if username:
        lockout.record_success(username)
    request.session[SESSION_USER_KEY] = user.id
    logger.info("用户已登录 id=%s", user.id)
    return json_ok(_me_payload(user))


@router.post("/logout")
def logout(request: Request, user: CurrentUser):
    user_id = user.id
    request.session.pop(SESSION_USER_KEY, None)
    logger.info("用户已退出 id=%s", user_id)
    return json_ok({})


@router.get("/me")
def me(user: CurrentUser):
    return json_ok(_me_payload(user))


def _me_payload(user) -> dict:
    return {"username": user.username}
