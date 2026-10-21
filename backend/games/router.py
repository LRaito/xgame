from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from backend.deps import CurrentUser, GameServiceDep, GameStatsServiceDep
from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games.models import PROGRESS_NOT_STARTED
from backend.games.service import (
    GAME_TYPES,
    MANAGE_PAGE_SIZE_DEFAULT,
    RECENT_LIMIT_DEFAULT,
    GameUpload,
    allowed_body_extensions,
)
from backend.http import iso, json_err, json_ok
from backend.storage.access import build_download_response, content_disposition

router = APIRouter(prefix="/api/games", tags=["games"])

logger = logging.getLogger(__name__)

_SWF_CONTENT_TYPE = "application/x-shockwave-flash"
_ROM_CONTENT_TYPE = "application/octet-stream"


class UpdateGameBody(BaseModel):
    name: str | None = None
    description: str | None = None
    # 封面类型（封面样式 id）：None = 不改；空串 = 清空；该游戏类型不认的值 400
    cover_type: str | None = None
    clear_cover: bool = False


class RenameCartridgeBody(BaseModel):
    # 缺字段时给空串、走业务侧的中文 400，不要 FastAPI 那句英文 422（与 ImportGameBody.url 同一套）
    cartridge_id: str = ""


class ImportGameBody(BaseModel):
    url: str = ""


class RecentPlayBody(BaseModel):
    game_id: int


def _center_payload(item, stat=None) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "cartridge_id": item.cartridge_id,
        "cover_type": item.cover_type,
        "description": item.description,
        "category": item.game_type,
        "path": item.path,
        "size": item.size,
        "cover_path": item.cover_path,
        "game_path": item.game_path,
        "updated_at": iso(item.updated_at),
        # 攻略按磁盘现状报（guide/index.html 在不在），前端据此决定右键菜单里出不出现
        "has_guide": item.has_guide,
        # 游玩统计按账号走，没有记录时是 0 秒 + 未开始
        "play_seconds": stat.play_seconds if stat else 0,
        "progress": stat.progress if stat else PROGRESS_NOT_STARTED,
    }


def _center_payloads(items, stat_map) -> list[dict]:
    """列表载荷：先一次性取回这批游戏的统计，再逐条合并（避免 N+1 查询）。"""
    return [_center_payload(item, stat_map.get(item.id)) for item in items]


def _manage_payload(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "cartridge_id": item.cartridge_id,
        "cover_type": item.cover_type,
        "description": item.description,
        "game_type": item.game_type,
        "size": item.size,
        "crc32": item.crc32,
        "game_path": item.game_path,
        "cover_path": item.cover_path,
        "path": item.path,
        "created_at": iso(item.created_at),
        "updated_at": iso(item.updated_at),
        "has_guide": item.has_guide,
    }


def _uploaded_size(file: UploadFile) -> int:
    spool = file.file
    spool.seek(0, os.SEEK_END)
    size = spool.tell()
    spool.seek(0)
    return size


def _upload_of(file: UploadFile) -> GameUpload:
    return GameUpload(
        filename=file.filename or "",
        stream=file.file,
        size=_uploaded_size(file),
        mime=file.content_type,
    )


@router.get("/status")
def games_status(_user: CurrentUser):
    """类型列表与可上传格式（前端只用于筛选与 accept 提示）。"""
    return json_ok(
        {
            "game_types": list(GAME_TYPES),
            "body_extensions": list(allowed_body_extensions()),
        }
    )


@router.get("")
def games_list(
    _user: CurrentUser,
    service: GameServiceDep,
    stats: GameStatsServiceDep,
):
    items = service.list_center()
    return json_ok(_center_payloads(items, stats.map_for_games(_user.id, [i.id for i in items])))


@router.get("/recent")
def games_recent(
    _user: CurrentUser,
    service: GameServiceDep,
    stats: GameStatsServiceDep,
    limit: int = Query(RECENT_LIMIT_DEFAULT),
):
    """当前账号最近玩过的游戏（按最近一次开玩时间倒序；limit 越界由 service 收敛）。"""
    items = service.list_recent(_user.id, limit=limit)
    return json_ok(_center_payloads(items, stats.map_for_games(_user.id, [i.id for i in items])))


@router.post("/recent")
def games_mark_recent(body: RecentPlayBody, _user: CurrentUser, service: GameServiceDep):
    """上报一次开玩（播放页真正拉起播放器时调用；失败只丢一条记录，不影响游玩）。"""
    try:
        service.mark_played(_user.id, body.game_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已记录最近游玩 user_id=%s game_id=%s", _user.id, body.game_id)
    return json_ok(None)


@router.get("/manage")
def games_manage_list(
    _user: CurrentUser,
    service: GameServiceDep,
    game_type: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(MANAGE_PAGE_SIZE_DEFAULT),
):
    """管理列表的一页。排序与筛选口径不变；越界参数由 service 收敛（不在这里做范围校验）。"""
    result = service.list_manage(
        game_type=game_type or None,
        keyword=q or None,
        page=page,
        page_size=page_size,
    )
    return json_ok(
        {
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "items": [_manage_payload(item) for item in result.items],
        }
    )


@router.get("/manage/{game_id}")
def games_manage_detail(game_id: int, _user: CurrentUser, service: GameServiceDep):
    try:
        item = service.get(game_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok(_manage_payload(item))


@router.post("/manage/import")
def games_import(body: ImportGameBody, _user: CurrentUser, service: GameServiceDep):
    """从 7k7k / 4399 / flash.homes 游戏页地址搬运游戏：解析、下载并入库（Flash 或 H5）。

    卡带ID 不用传，服务端按本体 CRC32 自动生成 `F-{CRC32}`。
    """
    try:
        item = service.import_from_url(body.url)
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    logger.info("已搬运游戏 id=%s name=%s", item.id, item.name)
    return json_ok(_manage_payload(item), status=201)


@router.post("/manage")
def games_create(
    _user: CurrentUser,
    service: GameServiceDep,
    name: str = Form(...),
    cartridge_id: str = Form(""),
    description: str = Form(""),
    file: UploadFile | None = File(None),
    cover: UploadFile | None = File(None),
    body_url: str = Form(""),
    body_game_type: str = Form(""),
    cover_url: str = Form(""),
):
    """新建游戏并上传本体（可选封面）。

    卡带ID 必填且创建后不可改：它既是游戏的唯一标识，也是磁盘上的目录名。
    本体与封面各自可以给本地文件（`file`/`cover`）或网络直链（`body_url`/`cover_url`）。
    走本地文件时游戏类型由本体文件名自动判定；走直链时地址未必看得出类型，
    所以由前端下拉传入 `body_game_type`，后者必须与地址能认出的类型一致。
    """
    try:
        item = service.create(
            name,
            description,
            _upload_of(file) if file is not None else None,
            _upload_of(cover) if cover is not None else None,
            cartridge_id=cartridge_id,
            body_url=body_url,
            body_game_type=body_game_type,
            cover_url=cover_url,
        )
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    logger.info("已添加游戏 id=%s name=%s", item.id, item.name)
    return json_ok(_manage_payload(item), status=201)


@router.put("/manage/{game_id}")
def games_update(
    game_id: int, body: UpdateGameBody, _user: CurrentUser, service: GameServiceDep
):
    try:
        item = service.update(
            game_id,
            name=body.name,
            description=body.description,
            cover_type=body.cover_type,
            clear_cover=body.clear_cover,
        )
    except ValidationError as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok(_manage_payload(item))


@router.put("/manage/{game_id}/cartridge-id")
def games_rename_cartridge_id(
    game_id: int, body: RenameCartridgeBody, _user: CurrentUser, service: GameServiceDep
):
    """改卡带ID：磁盘目录与库里所有引用它的路径列一起改。

    **独立接口**：`PUT /manage/{id}` 依旧不接受这个字段——改名是搬目录的显式迁移，
    不该混在普通编辑里（见 `docs/architecture.md` 决策 10）。
    """
    try:
        item = service.rename_cartridge_id(game_id, body.cartridge_id)
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已改卡带ID game_id=%s cartridge_id=%s", game_id, item.cartridge_id)
    return json_ok(_manage_payload(item))


@router.delete("/manage/{game_id}")
def games_delete(game_id: int, _user: CurrentUser, service: GameServiceDep):
    try:
        service.delete(game_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    return json_ok(None)


@router.post("/manage/{game_id}/assets")
def games_upload_asset(
    game_id: int,
    _user: CurrentUser,
    service: GameServiceDep,
    kind: str = Form(...),
    file: UploadFile | None = File(None),
    url: str = Form(""),
    game_type: str = Form(""),
    cover_type: str = Form(""),
):
    """一步上传游戏本体或封面：流式写入存储目录 → 删旧文件 → 更新游戏行。

    来源可以是本地文件（`file`）或网络直链（`url`）；换本体时游戏类型随新本体的
    扩展名自动切换——直链看不出类型时由 `game_type` 指定，两者必须一致。

    `cover_type`（封面样式 id）**只在 kind="cover" 且非空时生效**，供「美化封面」
    把所选样式与封面文件一次写进去；kind="game" 时忽略。
    """
    try:
        if file is not None and not file.filename:
            raise ValidationError("请选择要上传的文件。")
        item = service.upload_asset(
            game_id,
            kind=kind,
            upload=_upload_of(file) if file is not None else None,
            url=url,
            game_type=game_type,
            cover_type=cover_type,
        )
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已上传游戏资源 game_id=%s kind=%s", game_id, kind)
    return json_ok(_manage_payload(item), status=201)


@router.post("/manage/{game_id}/guide")
def games_upload_guide(
    game_id: int,
    _user: CurrentUser,
    service: GameServiceDep,
    file: UploadFile | None = File(None),
):
    """上传攻略 ZIP（解压后根目录需含 index.html）。

    与 H5 一样只上传 zip：后端只校验、不解压，查看攻略时才按需解到运行时根。
    """
    try:
        if file is None:
            raise ValidationError("请选择要上传的攻略 ZIP 文件。")
        item = service.upload_guide(game_id, _upload_of(file))
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    logger.info("已上传攻略 game_id=%s", game_id)
    return json_ok(_manage_payload(item), status=201)


@router.get("/{game_id}/cover")
def games_cover(
    game_id: int,
    _user: CurrentUser,
    service: GameServiceDep,
    download: bool = Query(False),
):
    """封面：默认 inline 供 <img> 预览；download=1 时作为附件下载 cover.{后缀}。"""
    try:
        item = service.get(game_id)
        if not item.cover_path:
            raise ValidationError("游戏封面尚未上传。")
        stream = service.open_asset(item.cover_path)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    filename = Path(item.cover_path).name if download else None
    return build_download_response(stream, filename=filename)


def _open_play_asset(service: GameServiceDep, game_id: int):
    """打开游戏本体流，返回 (item, stream, content_type, filename)；错误抛给调用方处理。"""
    item = service.get(game_id)
    if not item.game_path:
        raise ValidationError("游戏文件尚未上传。")
    stream = service.open_asset(item.game_path)
    is_swf = Path(item.game_path).suffix.lower() == ".swf"
    content_type = _SWF_CONTENT_TYPE if is_swf else _ROM_CONTENT_TYPE
    return item, stream, content_type, Path(item.game_path).name


@router.get("/{game_id}/play")
def games_play(game_id: int, _user: CurrentUser, service: GameServiceDep):
    """流式返回游戏本体（SWF 或 ROM），文件名取落盘名（game.<ext>）。

    content-type：Flash（.swf）保持原值以兼容现有播放链路与缓存；其余平台统一
    octet-stream——EmulatorJS 按字节读取，不依赖 content-type，core 由前端指定。
    """
    try:
        _item, stream, content_type, filename = _open_play_asset(service, game_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    return build_download_response(
        stream, filename=filename, content_type=content_type
    )


@router.head("/{game_id}/play")
def games_play_head(game_id: int, _user: CurrentUser, service: GameServiceDep):
    """HEAD 与 GET 同语义：返回相同响应头但不传正文。

    EmulatorJS 启动前会先对本体 URL 发一个 HEAD 探测（此前 405 会报一条网络错误）。
    """
    try:
        item, stream, content_type, filename = _open_play_asset(service, game_id)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except (ValidationError, StorageError) as exc:
        return json_err(str(exc), 400)
    size = stream.size if stream.size is not None else item.size
    stream.close()
    return Response(
        content=b"",
        media_type=content_type,
        headers={
            "Content-Length": str(size),
            "Content-Disposition": content_disposition(filename),
        },
    )


# H5 资源响应头：sandbox 让文档进入不透明源（读不到本站 cookie/DOM、无法注册 SW），
# ACAO 让不透明源下的 fetch/ES module/.wasm 等跨源读取可成；no-cache 避免重传后仍取旧资源。
_H5_HEADERS = {
    "Content-Security-Policy": (
        "sandbox allow-scripts allow-forms allow-modals allow-popups "
        "allow-pointer-lock allow-downloads allow-presentation"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "no-cache, must-revalidate",
}


@router.get("/{game_id}/h5/{asset_path:path}")
def games_h5_asset(game_id: int, asset_path: str, service: GameServiceDep):
    """流式返回 H5 解包后的单个资源（入口固定为 index.html）。

    这是唯一无需登录的业务接口：H5 在沙箱 iframe（不透明源）里播放，浏览器把它的
    所有请求当作跨站，SameSite=Lax 的 session cookie 根本不会带上——加登录依赖只会
    让游戏加载不了 JS/图片。进入播放页本身要登录，未登录拿不到游戏 id 与入口地址。
    """
    try:
        stream, mime, _size = service.open_h5_asset(game_id, asset_path)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except StorageError as exc:
        # 懒解压写运行时根失败（磁盘满/只读）是服务端故障，不是客户端的错
        logger.exception("解压或读取 H5 资源失败 game_id=%s", game_id)
        return json_err(f"{exc}请检查运行时目录是否可写、空间是否充足。", 500)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    return build_download_response(stream, content_type=mime, headers=_H5_HEADERS)


@router.head("/{game_id}/h5/{asset_path:path}")
def games_h5_asset_head(game_id: int, asset_path: str, service: GameServiceDep):
    """HEAD 与 GET 同响应头，供部分引擎的资源探测。"""
    try:
        stream, mime, size = service.open_h5_asset(game_id, asset_path)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except StorageError as exc:
        logger.exception("解压或读取 H5 资源失败 game_id=%s", game_id)
        return json_err(f"{exc}请检查运行时目录是否可写、空间是否充足。", 500)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    stream.close()
    return Response(
        content=b"",
        media_type=mime,
        headers={**_H5_HEADERS, "Content-Length": str(size)},
    )


# 攻略响应头：攻略是**登录用户上传**的同源静态页，在新标签页顶层导航打开（正常带 cookie），
# 所以既不加 H5 那套 CSP sandbox、也不需要它的免登录例外。no-cache 保证重传后立刻生效。
_GUIDE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-cache, must-revalidate",
}


@router.get("/{game_id}/guide/{asset_path:path}")
def games_guide_asset(
    game_id: int, asset_path: str, _user: CurrentUser, service: GameServiceDep
):
    """流式返回攻略里的单个静态文件（入口固定为 index.html）；需登录。"""
    try:
        stream, mime, _size = service.open_guide_asset(game_id, asset_path)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except StorageError as exc:
        # 懒解压写运行时根失败（磁盘满/只读）是服务端故障，不是客户端的错
        logger.exception("解压或读取攻略失败 game_id=%s", game_id)
        return json_err(f"{exc}请检查运行时目录是否可写、空间是否充足。", 500)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    return build_download_response(stream, content_type=mime, headers=_GUIDE_HEADERS)


@router.head("/{game_id}/guide/{asset_path:path}")
def games_guide_asset_head(
    game_id: int, asset_path: str, _user: CurrentUser, service: GameServiceDep
):
    """HEAD 与 GET 同响应头，供浏览器预探测。"""
    try:
        stream, mime, size = service.open_guide_asset(game_id, asset_path)
    except NotFoundError as exc:
        return json_err(str(exc), 404)
    except StorageError as exc:
        logger.exception("解压或读取攻略失败 game_id=%s", game_id)
        return json_err(f"{exc}请检查运行时目录是否可写、空间是否充足。", 500)
    except ValidationError as exc:
        return json_err(str(exc), 400)
    stream.close()
    return Response(
        content=b"",
        media_type=mime,
        headers={**_GUIDE_HEADERS, "Content-Length": str(size)},
    )
