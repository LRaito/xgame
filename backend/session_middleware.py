"""只按「会话内容是否变化」决定是否重发 session cookie 的会话中间件。

Starlette 自带的 SessionMiddleware 每个响应都会重发 cookie（签名里还带该请求读到的
旧会话内容）。会话内容变化的瞬间（注册/登录/登出、首次生成 CSRF），同批在途的
旧会话请求的响应若后到，会把浏览器刚写入的新 cookie 覆盖回旧值——表现为登录后
立刻又掉线、必须重新登录。因此这里替换为：**内容没变就不重发**，旧响应没关系，
它不再带 Set-Cookie，不可能反咬；内容变化时照常发出新 cookie。

时效从签名时间挪到这里显式校验：签名只在内容变化时发生，「最后一次变化」就是
有效期起点；日常续期由 `/api/csrf` 的 touch 完成（见 backend/auth/router.py），
即每打开一次页面顺带滑续一次，行为与原实现等效。
"""

import json
import time
from base64 import b64decode, b64encode
from typing import Literal

import itsdangerous
from itsdangerous.exc import BadData
from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 签名时间戳与当前时刻的判定都基于 UTC 纪元秒
SECONDS_PER_DAY = 86400


def signed_at_expired(signed_at: float, now: float, max_age: int | None) -> bool:
    """签名时刻距 now 是否超过 max_age。max_age 为 None 表示永不过期。"""
    return max_age is not None and (now - signed_at) > max_age


class ModifiedOnlySessionMiddleware:
    """与 starlette.middleware.sessions.SessionMiddleware 同参数、同 cookie 格式的替代实现。

    差别只有一处：会话内容没变的响应不再附 Set-Cookie（见模块 docstring）。
    cookie 格式不变：值仍是 itsdangerous TimestampSigner 签名的 base64 JSON，
    老版本写入的已登录会话可以无缝继续使用。
    """

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str | Secret,
        session_cookie: str = "session",
        max_age: int | None = 14 * SECONDS_PER_DAY,
        path: str = "/",
        same_site: Literal["lax", "strict", "none"] = "lax",
        https_only: bool = False,
        domain: str | None = None,
    ) -> None:
        self.app = app
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.path = path
        self.security_flags = "httponly; samesite=" + same_site
        if https_only:
            self.security_flags += "; secure"
        if domain is not None:
            self.security_flags += f"; domain={domain}"

    # ---------- 载入 ----------

    def _load_session(self, connection: HTTPConnection, scope: Scope) -> bool:
        """解析请求 cookie 并写入 scope["session"]。

        返回值是 initial_session_was_empty：cookie 缺失或解析失败 → True；
        cookie 正常且已有数据 → False（登出清空时要用它决定是否发删除 cookie）。
        """
        if self.session_cookie not in connection.cookies:
            scope["session"] = {}
            return True
        value = connection.cookies[self.session_cookie].encode("utf-8")
        try:
            payload, signed_at = self.signer.unsign(value, return_timestamp=True)
            if signed_at_expired(signed_at.timestamp(), time.time(), self.max_age):
                # 过期等同没有数据，但 cookie「曾经存在」——响应会把它清掉
                scope["session"] = {}
                return False
            scope["session"] = json.loads(b64decode(payload))
            return False
        except (BadData, ValueError):  # noqa: RUF007 - payload 损坏 / JSON 结构不对
            scope["session"] = {}
            # 无法解析的 cookie 直接当作不存在，避免在别人的非法值上纠缠
            return True

    # ---------- 写出 ----------

    def _set_cookie_header(self, session: dict) -> str:
        data = b64encode(json.dumps(session).encode("utf-8"))
        value = self.signer.sign(data).decode("utf-8")
        max_age = f"Max-Age={self.max_age}; " if self.max_age else ""
        return "{name}={value}; path={path}; {max_age}{flags}".format(
            name=self.session_cookie,
            value=value,
            path=self.path,
            max_age=max_age,
            flags=self.security_flags,
        )

    def _delete_cookie_header(self) -> str:
        expires = "expires=Thu, 01 Jan 1970 00:00:00 GMT; "
        max_age = "Max-Age=0; " if self.max_age else ""
        return "{name}=null; path={path}; {expires}{max_age}{flags}".format(
            name=self.session_cookie,
            path=self.path,
            expires=expires,
            max_age=max_age,
            flags=self.security_flags,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        # 快照进来的会话内容：响应阶段与它比对，只有「动了会话」的请求才重发 cookie
        initial_session_was_empty = self._load_session(connection, scope)
        initial_session = dict(scope["session"])

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                modified = scope["session"] != initial_session
                headers = MutableHeaders(scope=message)
                if scope["session"] and modified:
                    headers.append("Set-Cookie", self._set_cookie_header(scope["session"]))
                elif not scope["session"] and not initial_session_was_empty:
                    # 会话被清空（退出登录 / 过期）：显式删掉浏览器里的 cookie
                    headers.append("Set-Cookie", self._delete_cookie_header())
            await send(message)

        await self.app(scope, receive, send_wrapper)
