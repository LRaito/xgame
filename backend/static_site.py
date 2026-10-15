"""把前端构建产物（dist）挂在后端上——**只有「解压即用」的 Windows 包会用到**。

Docker 路线由 nginx 托管静态站并把 `/api` 反代给后端，那条路线不设 `STATIC_DIR`，
这里一条路由都不会注册（`mount_static_site()` 直接返回），行为一字不变。

Windows 包没有 nginx，而静态站和 API 必须**同源**，否则前端直接坏掉：前端所有请求都是
相对 `/api`；更要命的是 EmulatorJS 宿主页（`emulator-host.html`）由 SPA 以**同源 iframe**
打开，父页直接读 `contentWindow.__ejsRpc`、直接给它挂 keydown 监听——跨源即废，且没有
postMessage 回退。

行为规范是 `frontend/nginx.conf.template`，下面七条逐条对着它写，漏一条就是一个只在
局域网复现、极难排查的怪 bug：

1. catch-all 路由必须注册在所有 API 路由**之后**；`/api/` 下没匹配到的路径回 JSON 404，
   绝不回落 index.html（回落了前端 axios 会拿到一坨 HTML）。
2. `/version.txt` 不缓存，且**文件不存在时 404**、绝不回落 index.html——回落的后果是
   「提示有新版 → 刷新 → 还是同一版」死循环。
3. `/assets/`、`/ruffle/`、`/emulatorjs/` 长缓存 immutable，**没命中就 404、不回落**：
   旧页面请求已下线的旧哈希 JS 时若拿到 200 + HTML，报错是 `Unexpected token '<'`。
4. index.html / emulator-host.html 必须 no-cache：`FileResponse` 默认不带 Cache-Control，
   浏览器会启发式缓存 HTML，表现就是「部署完打开还是旧页面」。
5. 其余未命中回落 index.html（SPA history 模式，手机深链 `/games/123` 靠它）。
6. MIME 用**显式表**，不用 `mimetypes`：Windows 上 `mimetypes` 会读注册表
   `HKEY_CLASSES_ROOT`，`.js` 被注册成 `text/plain` 的机器是真实存在的，表现是整站白屏 +
   控制台 MIME 报错。仓库里 `games/service.py` 的 `_ASSET_MIME_TYPES` 出于同样的理由
   也不依赖系统 MIME 表。
7. 路径安全自己兜：拒绝 `..`、反斜杠、NUL、含 `:` 的段（Windows 盘符 / ADS），
   解析后确认仍在 dist 根之内。
"""

import logging
from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from backend.config import Settings
from backend.http import json_err

logger = logging.getLogger(__name__)

_INDEX = "index.html"

# 长缓存前缀（对齐 nginx 那三条 immutable location）。目录名本身（`/assets/`）也算在里，
# 免得它落进 SPA 回落——nginx 那边 `try_files $uri $uri/ =404` 是直接 404 的。
_IMMUTABLE_PREFIXES = ("assets/", "ruffle/", "emulatorjs/")
_IMMUTABLE_NAMES = tuple(prefix.rstrip("/") for prefix in _IMMUTABLE_PREFIXES)
# 文件名固定、不带内容哈希，一旦被启发式缓存就会与换名的新产物错配
_NO_CACHE_FILES = frozenset({_INDEX, "emulator-host.html", "version.txt"})

_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-cache"

# 显式 MIME 表：前端的 dist 里会出现的东西都在这里，没收录的一律 octet-stream
# （`.data` 这类 EmulatorJS 内核文件以 arraybuffer 抓取，MIME 不敏感）。
_MIME_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".wasm": "application/wasm",
    ".data": "application/octet-stream",
    ".mem": "application/octet-stream",
    ".bin": "application/octet-stream",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".swf": "application/x-shockwave-flash",
}
_DEFAULT_MIME = "application/octet-stream"


def mount_static_site(app: FastAPI, settings: Settings) -> None:
    """按 `STATIC_DIR` 挂载前端静态站；没配（含 Docker 路线）就什么都不做。"""
    if not settings.STATIC_DIR:
        return

    root = Path(settings.STATIC_DIR).expanduser()
    if not root.is_dir():
        logger.warning("静态目录不存在，跳过前端托管：%s", root)
        return
    root = root.resolve()
    logger.info("前端静态站改由后端托管：%s", root)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str) -> Response:
        # 第 1 条：/api 下没匹配到的路径必须回 JSON，不能落进 SPA 回落
        if full_path == "api" or full_path.startswith("api/"):
            return json_err("接口不存在。", 404)

        rel = _normalize(full_path)
        if rel is None:
            return json_err("路径非法。", 404)

        target = _resolve(root, rel)
        if target is not None and target.is_file():
            return _file_response(target, rel)

        # 第 2、3 条：长缓存前缀与版本探针没命中就是 404，绝不回落 index.html
        if rel == "version.txt" or rel in _IMMUTABLE_NAMES or rel.startswith(_IMMUTABLE_PREFIXES):
            return json_err("文件不存在。", 404)

        # 第 5 条：其余回落 SPA 入口
        index = root / _INDEX
        if not index.is_file():
            return json_err("前端资源不存在。", 404)
        return _file_response(index, _INDEX)


def _file_response(path: Path, rel: str) -> FileResponse:
    """带缓存策略的静态响应。显式传 media_type，绕开 mimetypes 对注册表的依赖（第 6 条）。"""
    headers: dict[str, str] = {}
    if rel.startswith(_IMMUTABLE_PREFIXES):
        headers["Cache-Control"] = _IMMUTABLE_CACHE
    elif rel in _NO_CACHE_FILES:
        headers["Cache-Control"] = _NO_CACHE
    return FileResponse(
        path,
        media_type=_mime_for(rel),
        headers=headers or None,
    )


def _mime_for(rel: str) -> str:
    return _MIME_TYPES.get(PurePosixPath(rel).suffix.lower(), _DEFAULT_MIME)


def _normalize(raw: str) -> str | None:
    """把 URL 路径归一化成 dist 内的相对路径；非法返回 None（第 7 条）。"""
    if "\x00" in raw or "\\" in raw:
        return None
    parts: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in ("", ".", "/"):
            continue
        if part == ".." or ":" in part:
            return None
        parts.append(part)
    return "/".join(parts)


def _resolve(root: Path, rel: str) -> Path | None:
    """拼出真实路径并确认它仍在 dist 根之内（挡住符号链接与一切绕法）。"""
    if not rel:
        return None
    candidate = root.joinpath(*rel.split("/"))
    try:
        candidate.resolve().relative_to(root)
    except (OSError, ValueError):
        return None
    return candidate
