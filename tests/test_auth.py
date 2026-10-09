import pytest
from sqlmodel import Session, select

from backend.auth.login_lockout import LoginLockoutService
from backend.auth.models import LoginAttempt, User
from backend.auth.service import validate_password, validate_username
from backend.errors import LoginLockedError, ValidationError


def test_wrong_password_returns_401(client, user):
    response = client.post(
        "/api/login", json={"username": "alice", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码不正确。"


def test_unknown_user_returns_401(client):
    response = client.post(
        "/api/login", json={"username": "nobody", "password": "whatever"}
    )
    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码不正确。"


def test_login_success_and_me(client, user):
    response = client.post(
        "/api/login", json={"username": "alice", "password": "secret123"}
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"username": "alice"}

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["data"] == {"username": "alice"}


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401


def test_logout_revokes_session(client, user, do_login):
    do_login(client)
    assert client.get("/api/me").status_code == 200

    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


# ---------- 注册 ----------


def test_register_creates_user_and_logs_in(client):
    response = client.post(
        "/api/register", json={"username": "newbie", "password": "secret123"}
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"username": "newbie"}
    # 注册即登录
    assert client.get("/api/me").json()["data"]["username"] == "newbie"


def test_register_password_is_hashed(client, app):
    client.post("/api/register", json={"username": "hashed", "password": "secret123"})
    with Session(app.state.engine) as session:
        row = session.exec(select(User).where(User.username == "hashed")).one()
    assert row.password_hash != "secret123"
    assert row.check_password("secret123")


def test_register_duplicate_username_rejected(client, user):
    response = client.post(
        "/api/register", json={"username": "alice", "password": "secret123"}
    )
    assert response.status_code == 409
    assert "alice" in response.json()["message"]


@pytest.mark.parametrize("username", ["中文名", "a b", "a.b", "a@b", "a" * 33])
def test_register_rejects_illegal_username(client, username):
    response = client.post(
        "/api/register", json={"username": username, "password": "secret123"}
    )
    assert response.status_code == 400
    assert "用户名" in response.json()["message"]


@pytest.mark.parametrize("username", ["ab", "a_b-1", "A1", "a" * 32])
def test_register_accepts_legal_username(client, username):
    response = client.post(
        "/api/register", json={"username": username, "password": "secret123"}
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("password", ["", "12345", "x" * 65])
def test_register_rejects_bad_password(client, password):
    response = client.post(
        "/api/register", json={"username": "someone", "password": password}
    )
    assert response.status_code == 400
    assert "密码" in response.json()["message"]


def test_username_is_case_sensitive(client):
    """用户名大小写不折叠：Alice 与 alice 是两个账号（磁盘目录名也区分）。"""
    assert (
        client.post(
            "/api/register", json={"username": "Alice", "password": "secret123"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/register", json={"username": "alice", "password": "secret123"}
        ).status_code
        == 200
    )


def test_validate_username_and_password_helpers():
    assert validate_username("  bob-1_2  ") == "bob-1_2"
    assert validate_password("  spaced  ") == "  spaced  "  # 密码不 strip
    with pytest.raises(ValidationError):
        validate_username("")
    with pytest.raises(ValidationError):
        validate_password("")


# ---------- 失败锁定 ----------


def test_three_failures_then_short_lock(client, user):
    for _ in range(3):
        response = client.post(
            "/api/login", json={"username": "alice", "password": "wrong-password"}
        )
        assert response.status_code == 401

    response = client.post(
        "/api/login", json={"username": "alice", "password": "wrong-password"}
    )
    assert response.status_code == 429
    assert "5 分钟" in response.json()["message"]


def test_success_resets_failed_attempts(client, user, do_login):
    for _ in range(2):
        client.post(
            "/api/login", json={"username": "alice", "password": "wrong-password"}
        )

    response = do_login(client)
    assert response.status_code == 200

    with Session(client.app.state.engine) as session:
        assert session.get(LoginAttempt, "alice") is None


def test_six_failures_then_day_lock(app, client, user):
    with Session(app.state.engine) as session:
        service = LoginLockoutService(session)
        for _ in range(6):
            service.record_failure("alice")

    response = client.post(
        "/api/login", json={"username": "alice", "password": "secret123"}
    )
    assert response.status_code == 429
    assert "今日" in response.json()["message"]


def test_lockout_service_day_lock_message(app):
    with Session(app.state.engine) as session:
        service = LoginLockoutService(session)
        for _ in range(6):
            service.record_failure("bob")

        with pytest.raises(LoginLockedError) as exc_info:
            service.check_allowed("bob")
        assert "今日" in str(exc_info.value)


# ---------- CSRF ----------


def test_csrf_token_available(client):
    response = client.get("/api/csrf")
    assert response.status_code == 200
    assert response.json()["data"]["csrf_token"]


@pytest.mark.parametrize("path", ["/api/login", "/api/register", "/api/csrf", "/health"])
def test_csrf_exempt_paths(path):
    """注册与登录在 CSRF 白名单里（登录页此时还没拿到 token）；其余写接口仍要校验。"""
    from starlette.requests import Request

    from backend.config import Settings
    from backend.csrf import validate_csrf

    settings = Settings(TESTING=False)
    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("test", 80),
        "path": path,
        "headers": [],
        "session": {},
    }
    validate_csrf(Request(scope), settings)  # 不抛 HTTPException 即通过


def test_csrf_rejects_unlisted_write_path():
    from starlette.requests import Request

    from fastapi import HTTPException

    from backend.config import Settings
    from backend.csrf import validate_csrf

    settings = Settings(TESTING=False)
    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("test", 80),
        "path": "/api/games/manage",
        "headers": [],
        "session": {},
    }
    with pytest.raises(HTTPException):
        validate_csrf(Request(scope), settings)
