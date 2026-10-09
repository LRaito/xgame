"""网络上传：把一个直链下载到本地临时文件，再交给普通上传管线入库。

与 `importer`（7k7k / 4399 / flash.homes 游戏页搬运）分开：那边只认三个站点的
游戏页并解析页面，这边接受任意 http/https 直链，下载完就走和本地上传一样的路。

下载一律在服务端进行（浏览器直连任意域名会被 CORS 拦），所以大小上限也在这里设。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

from backend.games import importer
from backend.games.importer import DownloadError

# 单个远程文件上限：够放最大的 ROM 与 H5 包，又不至于一条地址就把磁盘写满
MAX_REMOTE_BYTES = 512 * 1024 * 1024


def check_url(url: str) -> str:
    """校验直链并返回去掉首尾空白的地址；非 http/https 直接报错。"""
    target = (url or "").strip()
    if not target.lower().startswith(("http://", "https://")):
        raise DownloadError("请填写完整的下载地址（http/https）。")
    return target


def extension_from_url(url: str) -> str:
    """取直链路径里最后一段的扩展名（小写、含点）；看不出扩展名时返回空串。

    只认地址本身，不看响应头：网盘那种 `?id=5` 式直链就是空串，由调用方
    用用户选的类型补默认后缀。
    """
    return Path(unquote(urlsplit(check_url(url)).path)).suffix.lower()


def fetch(url: str, dest: Path) -> tuple[Path, int]:
    """把直链下载到 dest，返回 (路径, 字节数)。失败抛 DownloadError。"""
    target = check_url(url)
    session = importer.make_session()
    try:
        path, size = importer.download_file(session, target, dest, max_bytes=MAX_REMOTE_BYTES)
    finally:
        session.close()
    return Path(path), size
