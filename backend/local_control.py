"""本地控制口：让包内的自动升级脚本把服务停下来。

「解压即用」的 Windows 包里，升级要把整个 `xgame` 目录换掉（连着 `python/` 一起换，所以升级
能带新的解释器和依赖），前提是**服务真的退干净了**——Windows 上被进程占着的文件既不能改名
也不能覆盖。硬杀（`taskkill /F`）会把 SQLite 留在半路（可能留下 `-journal`），所以升级脚本
先走这个接口请求优雅退出：`uvicorn` 收工后关掉连接、关掉监听端口，进程自己结束。

三重设防，缺一不可——这是个能停服务的接口：

1. 只在 `LOCAL_CONTROL` 打开时注册（启动器设，Docker 路线永远不设，所以那条路线上这个
   路由根本不存在，访问就是普通的 404）；
2. 只认来自回环地址的请求（局域网里的手机发过来一律 403）；
3. 必须带对 `X-XGame-Token`，与启动器每次启动随机生成、写进 `runtime/control.token` 的值
   做常量时间比较。

它同时也是 `backend/csrf.py` 白名单里的路径：这里已经有自己的 token 守卫，不需要 CSRF 头。
"""

import hmac
import logging
from collections.abc import Callable

from fastapi import FastAPI, Request
from starlette.responses import Response

from backend.config import Settings
from backend.http import json_err, json_ok

logger = logging.getLogger(__name__)

CONTROL_TOKEN_HEADER = "X-XGame-Token"
SHUTDOWN_PATH = "/api/local/shutdown"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def mount_local_control(app: FastAPI, settings: Settings) -> None:
    """挂上关机接口；没开 `LOCAL_CONTROL` 或没给 token 就什么都不做。"""
    if not settings.LOCAL_CONTROL or not settings.LOCAL_CONTROL_TOKEN:
        return

    expected = settings.LOCAL_CONTROL_TOKEN

    @app.post(SHUTDOWN_PATH, include_in_schema=False)
    async def shutdown(request: Request) -> Response:
        if not _is_loopback(request):
            logger.warning("拒绝来自 %s 的关机请求：只接受本机。", _client_host(request))
            return json_err("只接受本机请求。", 403)
        token = request.headers.get(CONTROL_TOKEN_HEADER) or ""
        if not hmac.compare_digest(token, expected):
            logger.warning("拒绝关机请求：token 不匹配。")
            return json_err("请求校验失败。", 403)

        hook: Callable[[], None] | None = getattr(app.state, "request_shutdown", None)
        if hook is None:
            # 启动器没挂回调（比如用 uvicorn 命令行直接起的），只能如实相告
            return json_err("当前进程不支持优雅退出。", 501)

        logger.info("收到本机升级请求，准备优雅退出。")
        hook()
        return json_ok({"stopping": True})


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def _is_loopback(request: Request) -> bool:
    return _client_host(request) in _LOOPBACK_HOSTS
