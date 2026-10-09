"""图片入库的公共校验：截图（按账号）与图集（按游戏）共用同一套判据。

两处都从浏览器来、都可能被换过扩展名，所以格式一律**按内容 magic 认**，
不看文件名也不看 content-type；后缀也由 magic 定下来，落盘时用它拼。
"""

from __future__ import annotations

from backend.errors import ValidationError

# 单张上限：引擎原生帧或同帧拷贝的 PNG 通常几百 KB 到几 MB，
# 16MB 留足余量，同时远小于 nginx 的 128m 网关，不会先被网关拦掉。
IMAGE_MAX_SIZE = 16 * 1024 * 1024

# 收哪些图片：播放页截的固定是 PNG，手动上传的还允许常见网页图片格式。
IMAGE_TYPES = (
    (".png", "image/png", 0, b"\x89PNG\r\n\x1a\n"),
    (".jpg", "image/jpeg", 0, b"\xff\xd8\xff"),
    (".gif", "image/gif", 0, b"GIF8"),
    (".webp", "image/webp", 8, b"WEBP"),  # RIFF????WEBP
)
_RIFF_MAGIC = b"RIFF"

SUPPORTED_IMAGE_LABEL = "PNG / JPG / WebP / GIF"

_HEAD_BYTES = 12  # 够看到 RIFF....WEBP 的 WEBP 标记


def detect_image_type(stream) -> tuple[str, str] | None:
    """按 magic 认图片格式，返回 (后缀, mime)；不认识返回 None。读完复位。"""
    head = stream.read(_HEAD_BYTES)
    stream.seek(0)
    for extension, mime, offset, magic in IMAGE_TYPES:
        if head[offset : offset + len(magic)] == magic:
            if extension == ".webp" and head[:4] != _RIFF_MAGIC:
                continue
            return extension, mime
    return None


def validate_image_size(size: int | None, *, label: str) -> None:
    """体积校验：空文件与超限都直接拒（中文 400）。"""
    if size is None or size <= 0:
        raise ValidationError(f"{label}文件为空。")
    if size > IMAGE_MAX_SIZE:
        raise ValidationError(f"{label}文件过大。")


def clean_image_description(value: str | None, *, label: str, max_length: int) -> str:
    """去掉首尾空白并校验长度，超长直接抛错而不是静默截断。"""
    text = (value or "").strip()
    if len(text) > max_length:
        raise ValidationError(f"{label}描述不能超过 {max_length} 个字。")
    return text
