"""请求体上限：顶替 nginx 的 `client_max_body_size`。

Docker 路线上，上传的唯一全局闸门是 nginx 的 `client_max_body_size 512m`。
「解压即用」的 Windows 包没有 nginx（前端由 `backend/static_site.py` 托管），
撤掉它之后请求体就没有任何上限了——Starlette 表单解析的 `max_part_size`（1MB）
只作用于**非文件字段**，文件部分不设上限，于是局域网里任何一台设备都能一直写，
直到把磁盘写爆。所以补这个进程内的闸门，两条规则：

1. 带了 `Content-Length` 且超过上限 → 直接 413（中文 JSON），请求体一个字节都不读。
2. 写方法却没带 `Content-Length`（即 `Transfer-Encoding: chunked`）→ 411 拒掉。

不做「边读边计数」：那样只能读到一半才失败，而那时应用已经开始解析表单了，
用户拿到的是解析层的 500 而不是一条看得懂的中文错误。浏览器（axios / fetch + FormData）
发多部分上传时总是带 Content-Length，nginx 反代默认也是缓冲后带 Content-Length 转发，
所以这两条规则在实际链路上不会误伤。

Docker 路线也挂它，但 nginx 的 512m 先拦，这里只是兜底（默认值与 nginx 一致）。
"""

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.http import json_err

# 只对可能带请求体的方法做 chunked 检查；GET/HEAD/DELETE 照常放行。
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is None:
            if scope["method"] in _BODY_METHODS:
                await json_err("上传请求缺少 Content-Length。", 411)(scope, receive, send)
                return
        else:
            try:
                size = int(content_length)
            except ValueError:
                # 畸形的 Content-Length 交给下游按自己的方式处理，这里不猜。
                size = 0
            if size > self._max_bytes:
                limit_mb = self._max_bytes // 1024 // 1024
                await json_err(f"上传内容过大，最多 {limit_mb} MB。", 413)(scope, receive, send)
                return

        await self._app(scope, receive, send)
