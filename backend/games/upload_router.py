"""本体分片上传的 HTTP 入口。

分片请求不经过 `UploadFile`：路由直接读 `request.stream()`，交给
`BodyUploadService` 的写入器按偏移落盘，所以 nginx 与 Starlette 都不会再
把整包缓冲成临时文件。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.deps import BodyUploadServiceDep, CurrentUser
from backend.errors import NotFoundError, StorageError, ValidationError
from backend.http import json_ok, json_err

router = APIRouter(prefix="/api/games/uploads", tags=["game-uploads"])

logger = logging.getLogger(__name__)


class InitUploadBody(BaseModel):
    filename: str = ""
    size: int = 0
    game_type: str = ""


def _content_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@router.post("")
def games_create_upload(
    body: InitUploadBody, _user: CurrentUser, uploads: BodyUploadServiceDep
):
    """开一个分片会话；返回分片大小与总数。"""
    try:
        return json_ok(uploads.create(body.filename, body.size, body.game_type))
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)


@router.put("/{upload_id}/chunks/{index}")
async def games_upload_chunk(
    upload_id: str,
    index: int,
    request: Request,
    _user: CurrentUser,
    uploads: BodyUploadServiceDep,
):
    """直接接收原始分片字节并写到 `body.part` 的对应偏移。"""
    try:
        writer = uploads.open_chunk_writer(upload_id, index, _content_length(request))
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)

    try:
        async for block in request.stream():
            if block:
                await run_in_threadpool(writer.write, block)
        await run_in_threadpool(writer.finish)
    except (ValidationError, StorageError) as exc:
        writer.close()
        return json_err(str(exc), 400)
    except BaseException:
        writer.close()
        raise
    return json_ok({"index": index, "size": writer.written})


@router.post("/{upload_id}/complete")
def games_complete_upload(
    upload_id: str, _user: CurrentUser, uploads: BodyUploadServiceDep
):
    """分片到齐后把会话置为可提交；只校验标记与大小，不读整包。"""
    try:
        return json_ok(uploads.complete(upload_id))
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)


@router.delete("/{upload_id}")
def games_discard_upload(
    upload_id: str, _user: CurrentUser, uploads: BodyUploadServiceDep
):
    """放弃整次上传并删除暂存目录；幂等。"""
    try:
        uploads.discard(upload_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except StorageError as exc:
        return json_err(str(exc), 400)
    return json_ok(None)
