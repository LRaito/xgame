from __future__ import annotations

import logging
import os

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel

from backend.deps import CurrentUser, GalleryServiceDep
from backend.errors import NotFoundError, StorageError, ValidationError
from backend.http import iso, json_err, json_ok
from backend.storage.access import build_download_response

router = APIRouter(prefix="/api/games/gallery", tags=["game-gallery"])

logger = logging.getLogger(__name__)


class GalleryUpdateBody(BaseModel):
    description: str = ""


class GalleryMoveBody(BaseModel):
    # 拖动后的落点（0 起，按当前列表的下标算）
    to_index: int = -1


def _uploaded_size(file: UploadFile) -> int:
    spool = file.file
    spool.seek(0, os.SEEK_END)
    size = spool.tell()
    spool.seek(0)
    return size


def _payload(item) -> dict:
    # 磁盘路径是内部实现细节，不下发（前端按 id 取图）
    return {
        "id": item.id,
        "game_id": item.game_id,
        "sort_order": item.sort_order,
        "description": item.description,
        "size": item.size,
        "created_at": iso(item.created_at),
    }


@router.get("")
def gallery_list(
    _user: CurrentUser,
    service: GalleryServiceDep,
    game_id: int = Query(...),
):
    """某游戏的图集列表，按展示顺序（sort_order）升序；全站共享，谁都能看。"""
    items = service.list_images(game_id=game_id)
    return json_ok([_payload(item) for item in items])


@router.post("")
def gallery_create(
    _user: CurrentUser,
    service: GalleryServiceDep,
    game_id: int = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
):
    """上传一张图集图片（描述可选；格式按内容 magic 判定，不看文件名）。"""
    try:
        item = service.create_image(
            game_id=game_id,
            description=description,
            stream=file.file,
            size=_uploaded_size(file),
        )
    except ValidationError as exc:
        return json_err(str(exc), 400)
    except StorageError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已上传图集图片 user_id=%s game_id=%s", _user.id, game_id)
    return json_ok(_payload(item), status=201)


@router.post("/{image_id}/move")
def gallery_move(
    image_id: int,
    body: GalleryMoveBody,
    _user: CurrentUser,
    service: GalleryServiceDep,
):
    """拖到指定位置，返回整份有序列表。"""
    try:
        items = service.move_image(image_id=image_id, to_index=body.to_index)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok([_payload(item) for item in items])


@router.get("/{image_id}/image")
def gallery_image(
    image_id: int,
    _user: CurrentUser,
    service: GalleryServiceDep,
):
    """inline 返回图集图片本体（需登录：图集虽共享，也不对外匿名开放）。"""
    try:
        stream, content_type = service.open_image(image_id=image_id)
    except StorageError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    # 不传 filename 即 inline 预览；内容不可变（id 唯一、不会覆盖写）
    return build_download_response(stream, content_type=content_type)


@router.put("/{image_id}")
def gallery_update(
    image_id: int,
    body: GalleryUpdateBody,
    _user: CurrentUser,
    service: GalleryServiceDep,
):
    """改图集图片描述（上限 15 字）。"""
    try:
        item = service.update_description(
            image_id=image_id, description=body.description
        )
    except ValidationError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok(_payload(item))


@router.delete("/{image_id}")
def gallery_delete(
    image_id: int,
    _user: CurrentUser,
    service: GalleryServiceDep,
):
    """删除一张图集图片：删行并清理磁盘文件。"""
    try:
        service.delete_image(image_id=image_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已删除图集图片 user_id=%s image_id=%s", _user.id, image_id)
    return json_ok(None)
