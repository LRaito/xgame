from __future__ import annotations

from urllib.parse import quote

from fastapi.responses import StreamingResponse

from backend.storage.types import StoredObjectStream

_CHUNK_SIZE = 256 * 1024


def content_disposition(filename: str) -> str:
    """Content-Disposition：附件下载，原名走 RFC5987（支持中文等非 ASCII）。"""
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "download"
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def build_download_response(
    stream: StoredObjectStream,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """把已打开的文件流分块吐给客户端。带 filename 时作为附件下载。

    headers 用于附加自定义响应头（如 H5 资源的 CSP/缓存策略）；默认不改动。
    """
    media_type = content_type or stream.mime or "application/octet-stream"
    response_headers: dict[str, str] = dict(headers or {})
    if stream.size is not None:
        response_headers["Content-Length"] = str(stream.size)
    if filename:
        response_headers["Content-Disposition"] = content_disposition(filename)

    def chunks():
        try:
            while True:
                block = stream.read(_CHUNK_SIZE)
                if not block:
                    break
                yield block
        finally:
            stream.close()

    return StreamingResponse(chunks(), media_type=media_type, headers=response_headers)
