from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel

from backend.deps import CurrentUser, SaveServiceDep
from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games.save_service import SaveUpload
from backend.http import iso, json_err, json_ok
from backend.storage.access import build_download_response

router = APIRouter(prefix="/api/games/saves", tags=["game-saves"])

logger = logging.getLogger(__name__)

_SOL_DOWNLOAD_CONTENT_TYPE = "application/octet-stream"


class CloudSaveUpdateBody(BaseModel):
    remark: str = ""


def _uploaded_size(file: UploadFile) -> int:
    spool = file.file
    spool.seek(0, os.SEEK_END)
    size = spool.tell()
    spool.seek(0)
    return size


def _item_payload(item) -> dict:
    return {
        "id": item.id,
        "game_id": item.game_id,
        "remark": item.remark,
        "file_count": item.file_count,
        "total_size": item.total_size,
        "created_at": iso(item.created_at),
    }


def _detail_payload(detail) -> dict:
    return {
        "id": detail.id,
        "game_id": detail.game_id,
        "remark": detail.remark,
        "created_at": iso(detail.created_at),
        "files": [
            {
                "id": file_.id,
                "sort_order": file_.sort_order,
                "local_key": file_.local_key,
                "name": file_.name,
                "size": file_.size,
            }
            for file_ in detail.files
        ],
    }


@router.get("")
def cloud_saves_list(
    _user: CurrentUser,
    service: SaveServiceDep,
    game_id: int = Query(...),
):
    """某游戏的云端存档（整体快照）列表，按创建时间倒序。"""
    items = service.list_snapshots(user_id=_user.id, game_id=game_id)
    return json_ok([_item_payload(item) for item in items])


@router.post("")
def cloud_saves_create(
    _user: CurrentUser,
    service: SaveServiceDep,
    game_id: int = Form(...),
    remark: str = Form(""),
    manifest: str = Form(...),
    sols: list[UploadFile] = File(...),
):
    """把一个游戏此刻的全部本地 .sol 上传成一个整体快照。

    manifest 为 JSON 数组 [{local_key, name}]，与 sols 顺序一一对应；
    local_key 是还原到浏览器 localStorage 时要写回的原键。
    """
    try:
        try:
            entries = json.loads(manifest)
            if not isinstance(entries, list):
                raise ValueError
        except ValueError:
            raise ValidationError("存档文件清单格式错误。") from None
        if len(entries) != len(sols):
            raise ValidationError("存档文件清单与文件数量不一致。")
        uploads: list[SaveUpload] = []
        for index, file in enumerate(sols):
            item = entries[index]
            if not isinstance(item, dict):
                raise ValidationError("存档文件清单格式错误。")
            local_key = item.get("local_key") or ""
            name = item.get("name") or ""
            if not isinstance(local_key, str) or not isinstance(name, str):
                raise ValidationError("存档文件清单格式错误。")
            uploads.append(
                SaveUpload(
                    local_key=local_key,
                    name=name,
                    stream=file.file,
                    size=_uploaded_size(file),
                    mime=file.content_type,
                )
            )
        detail = service.create_snapshot(
            user_id=_user.id,
            game_id=game_id,
            remark=remark,
            uploads=uploads,
        )
    except ValidationError as exc:
        return json_err(str(exc), 400)
    except StorageError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已同步云端存档 user_id=%s game_id=%s files=%s", _user.id, game_id, len(sols))
    return json_ok(_detail_payload(detail), status=201)


@router.get("/{snapshot_id}")
def cloud_saves_detail(
    snapshot_id: int,
    _user: CurrentUser,
    service: SaveServiceDep,
):
    """快照详情：文件清单（含还原用的 local_key 与顺序）。"""
    try:
        detail = service.get_snapshot(user_id=_user.id, snapshot_id=snapshot_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok(_detail_payload(detail))


@router.get("/{snapshot_id}/files/{file_id}/download")
def cloud_saves_file_download(
    snapshot_id: int,
    file_id: int,
    _user: CurrentUser,
    service: SaveServiceDep,
):
    """流式返回快照里单个 .sol 的内容，供“同步至本地”取回字节。"""
    try:
        stream, filename = service.open_file(
            user_id=_user.id, snapshot_id=snapshot_id, file_id=file_id
        )
    except StorageError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return build_download_response(
        stream, filename=filename, content_type=_SOL_DOWNLOAD_CONTENT_TYPE
    )


@router.put("/{snapshot_id}")
def cloud_saves_update(
    snapshot_id: int,
    body: CloudSaveUpdateBody,
    _user: CurrentUser,
    service: SaveServiceDep,
):
    """修改云端存档的描述（备注）。"""
    try:
        detail = service.update_remark(
            user_id=_user.id, snapshot_id=snapshot_id, remark=body.remark
        )
    except ValidationError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok(_detail_payload(detail))


@router.delete("/{snapshot_id}")
def cloud_saves_delete(
    snapshot_id: int,
    _user: CurrentUser,
    service: SaveServiceDep,
):
    """删除某个云端存档：删行并清理对应存档文件。"""
    try:
        service.delete_snapshot(user_id=_user.id, snapshot_id=snapshot_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已删除云端存档 user_id=%s snapshot_id=%s", _user.id, snapshot_id)
    return json_ok(None)
