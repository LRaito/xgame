"""会话中间件行为：未变化不重发、迟到旧响应无法反咬登录、CSRF 摸活滑续、登出清 cookie。

背景：Starlette 原版 SessionMiddleware 每个响应都重发 session cookie，会话内容
变化的瞬间（登录/登出），同批在途旧会话请求的响应会把新 cookie 覆盖回旧值——
用户偶现「登录后又被踹回登录页」。替换为 ModifiedOnlySessionMiddleware 后，
这里用真实 app 验证替换前后的关键差异。
"""

import json
from base64 import b64decode

from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from backend.config import SECRET_KEY
from backend.session_middleware import signed_at_expired


def cookie_value_of(set_cookie: str) -> str:
    """从 Set-Cookie 头取 cookie 值：`session=xxx; path=...` → `xxx`。"""
    return set_cookie.split(";")[0].split("=", 1)[1]


def session_payload_of(set_cookie: str) -> dict:
    """解出 Set-Cookie 里签名的会话内容（测试专用）。"""
    payload = TimestampSigner(SECRET_KEY).unsign(cookie_value_of(set_cookie).encode("utf-8"))
    return json.loads(b64decode(payload))


def test_login_changes_session_so_response_carries_cookie(client, user):
    """登录改了会话内容，响应必然带 Set-Cookie。"""
    response = client.post("/api/login", json={"username": "alice", "password": "secret123"})
    assert response.status_code == 200, response.text
    assert "session=" in response.headers["set-cookie"]


def test_unchanged_response_does_not_resend_cookie(client, user):
    """未变化的会话不再重发 Set-Cookie（这是对原实现的关键差异）。"""
    client.post("/api/login", json={"username": "alice", "password": "secret123"})
    response = client.get("/api/me")
    assert response.status_code == 200
    assert not response.headers.get_list("set-cookie")


def test_stale_response_cannot_revert_login(client, user):
    """竞态回归：登录后，一个「读到登录前会话」的迟到请求无法靠 Set-Cookie 干掉登录。

    模拟登录页的时序：先 GET /api/csrf 拿到「登录前」的 cookie（只有 csrf_token），
    登录写入新 cookie（csrf_token + user_id）后，把客户端 cookie 换回旧值发一个
    请求——旧会话内容没变化，新实现不发 Set-Cookie；换回登录 cookie 时登录仍然
    有效。原实现的这个迟到请求会重发旧 cookie，把登录反咬掉。
    """
    old_cookie = cookie_value_of(client.get("/api/csrf").headers["set-cookie"])
    login = client.post("/api/login", json={"username": "alice", "password": "secret123"})
    assert login.status_code == 200, login.text
    new_cookie = cookie_value_of(login.headers["set-cookie"])

    client.cookies.clear()
    client.cookies.set("session", old_cookie)
    stale = client.get("/api/me")  # 未登录只该拿 401，绝不带 Set-Cookie
    assert stale.status_code == 401
    assert not stale.headers.get_list("set-cookie")

    # 回到登录后的 cookie：登录态没有被迟到请求毁掉
    client.cookies.set("session", new_cookie)
    assert client.get("/api/me").json()["data"]["username"] == "alice"


def test_csrf_touch_carries_cookie_and_keeps_token(logged_in):
    """/api/csrf 的摸活让日常整页加载依旧滑续时效（响应带 Set-Cookie）。"""
    response = logged_in.get("/api/csrf")
    assert response.status_code == 200
    data = session_payload_of(response.headers["set-cookie"])
    # 摸的是内部时间戳，登录态与 csrf_token 不变
    assert data["user_id"]
    assert "__ts" in data
    assert response.json()["data"]["csrf_token"] == data["csrf_token"]


def test_logout_clears_browser_cookie(client):
    """登出后（会话清空）响应显式删 cookie，而不是让它继续留着。"""
    client.post("/api/register", json={"username": "bob", "password": "secret123"})
    logout = client.post("/api/logout")
    header_cookie = logout.headers["set-cookie"]
    assert "Max-Age=0" in header_cookie or "1970" in header_cookie
    # 客户端 cookie 已被服务端作废
    assert client.get("/api/me").status_code == 401


def test_signer_timestamp_expiry_unit():
    """签名时刻距 now 超过 max_age 视为过期（决定是否清会话的临界点）。"""
    now = 1_000_000_000
    assert not signed_at_expired(now - 100, now, 14 * 86400)
    assert signed_at_expired(now - 15 * 86400, now, 14 * 86400)
    assert not signed_at_expired(now - 9999999, now, None)  # None = 永不过期
