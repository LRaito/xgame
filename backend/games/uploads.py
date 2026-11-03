"""游戏本体的分片上传会话。

前端对超过 30MB 的本体切成 16MB 分片并发上传。这里负责暂存会话：每个分片直接写
`upload/{upload_id}/body.part` 的对应偏移，写完落一个空标记；全部到齐后由
`GameService` 把 `body.part` 改名到 `game/…` 即完成，不做整包合并复制。

多文件本体（cue+bin / m3u / 多盘）的每个物理文件各开一个这样的会话，创建/换本体时
用 `claim_many()` 一次取全，再由 `body_bundle` 校验成组；本节不引入打包格式。

DOS（`.jsdos` / `.zip`）与街机（romset `.zip`）仍是单文件会话：
DOS 由引擎解包，街机由 FBNeo 直接读 zip；`uploads.create()` 只按所选类型放行
`.zip`，不在这里做内容校验。

暂存区在**数据根**下（与最终素材同一文件系统），提交只是 `os.replace`。会话元数据
用 JSON 落盘，进程重启后仍能清理；超过 24 小时的会话在启动时删掉。
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath

from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games import archive, paths
from backend.games.body_bundle import MAX_BUNDLE_FILES
from backend.games.platforms import (
    all_body_extensions,
    all_bundle_extensions,
    playable_platforms_for_any_extension,
)
from backend.storage.local import LocalStorage, StorageWriter

logger = logging.getLogger(__name__)

# 超过这个大小的本地本体走分片；小于等于它仍用原单文件接口。
SINGLE_FILE_MAX = 30 * 1024 * 1024
CHUNK_SIZE = 16 * 1024 * 1024
# 未完成的暂存会话保留多久；启动时清掉更旧的。
SESSION_TTL_SECONDS = 24 * 60 * 60

_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_FLUSH_BYTES = 1024 * 1024
_STATUS_UPLOADING = "uploading"
_STATUS_READY = "ready"

# 可上传本体的全部后缀：可玩机种单文件 + 多文件包内文件 + Flash 的 .swf + H5 的 .zip。
# `.cue` / `.bin` / `.m3u` 只作多文件本体的成员暂存，不能单独成盘。
_BODY_EXTENSIONS = (
    frozenset(all_body_extensions())
    | frozenset(all_bundle_extensions())
    | {".swf", ".zip"}
)


@dataclass(frozen=True)
class StagedUpload:
    """已完成分片、等待落库的暂存本体。"""

    upload_id: str
    filename: str
    size: int

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_game_types(extension: str) -> tuple[str, ...]:
    if extension == ".swf":
        return ("flash",)
    if extension == ".zip":
        # ZIP 同时是 H5 静态包、DOS 的 jsdos 包与街机 romset；具体类型由用户选。
        return (
            "h5",
            *(platform.id for platform in playable_platforms_for_any_extension(".zip")),
        )
    return tuple(
        platform.id for platform in playable_platforms_for_any_extension(extension)
    )


def _clean_filename(raw: str) -> str:
    """只保留最后一段文件名；路径分隔符不进入任何磁盘路径。"""
    name = PurePosixPath((raw or "").replace("\\", "/")).name.strip()
    if not name:
        raise ValidationError("请选择要上传的文件。")
    return name


class ChunkWriter:
    """一个分片请求的写入器：按偏移写、限制字节数、完成后落标记。"""

    def __init__(
        self,
        storage: LocalStorage,
        writer: StorageWriter,
        *,
        upload_id: str,
        index: int,
        offset: int,
        expected: int,
    ) -> None:
        self._storage = storage
        self._writer = writer
        self._upload_id = upload_id
        self._index = index
        self._offset = offset
        self._expected = expected
        self._written = 0
        self._buffer = bytearray()
        self._closed = False

    @property
    def written(self) -> int:
        return self._written

    def write(self, data: bytes) -> None:
        if self._closed:
            raise ValidationError("分片写入已结束。")
        if self._written + len(data) > self._expected:
            raise ValidationError("分片内容超过约定大小。")
        self._buffer.extend(data)
        if len(self._buffer) >= _FLUSH_BYTES:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        self._writer.write_at(self._offset + self._written, bytes(self._buffer))
        self._written += len(self._buffer)
        self._buffer.clear()

    def finish(self) -> None:
        """校验长度、刷盘、关闭，再落分片标记。"""
        self._flush()
        if self._written != self._expected:
            raise ValidationError("分片大小不符合约定。")
        self._writer.flush()
        self._writer.close()
        self._closed = True
        self._storage.upload(
            paths.upload_chunk_marker_path(self._upload_id, self._index),
            BytesIO(b""),
            0,
            "application/octet-stream",
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._writer.close()


class BodyUploadService:
    """一个账号的分片上传会话；所有方法都按当前 user_id 做归属校验。"""

    def __init__(self, storage: LocalStorage, user_id: int) -> None:
        self._storage = storage
        self._user_id = user_id

    # ------------------------------------------------------------------ #
    # 会话
    # ------------------------------------------------------------------ #
    def create(self, filename: str, size: int, game_type: str = "") -> dict:
        name = _clean_filename(filename)
        extension = Path(name).suffix.lower()
        if extension not in _BODY_EXTENSIONS:
            allowed = "、".join(sorted(_BODY_EXTENSIONS))
            raise ValidationError(f"无法识别的游戏文件格式，仅支持 {allowed}。")
        if not isinstance(size, int) or size <= 0:
            raise ValidationError("文件大小无效。")
        hint = (game_type or "").strip()
        # 128MB 只约束 H5 静态包；DOS 的 jsdos 包与街机 romset 不受这个应用层上限。
        if (
            extension == ".zip"
            and hint not in ("dos", "arcade")
            and size > archive.MAX_ZIP_SIZE
        ):
            raise ValidationError("压缩包过大。")
        candidates = _candidate_game_types(extension)
        if hint and hint not in candidates:
            raise ValidationError("所选游戏类型与文件后缀不符。")
        upload_id = uuid.uuid4().hex
        total = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        meta = {
            "upload_id": upload_id,
            "user_id": self._user_id,
            "filename": name,
            "size": size,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": total,
            "game_type": hint,
            "status": _STATUS_UPLOADING,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._write_meta(meta)
        return {
            "upload_id": upload_id,
            "filename": name,
            "size": size,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": total,
        }

    def open_chunk_writer(
        self, upload_id: str, index: int, content_length: int | None
    ) -> ChunkWriter:
        meta = self._load_meta(upload_id)
        if meta.get("status") != _STATUS_UPLOADING:
            raise ValidationError("该上传已完成或不可再写。")
        total = int(meta["total_chunks"])
        if index < 0 or index >= total:
            raise ValidationError("分片序号不合法。")
        chunk_size = int(meta["chunk_size"])
        size = int(meta["size"])
        offset = index * chunk_size
        expected = min(chunk_size, size - offset)
        if content_length is not None and content_length != expected:
            raise ValidationError("分片大小不符合约定。")
        writer = self._storage.open_writer(paths.upload_part_path(upload_id))
        return ChunkWriter(
            self._storage,
            writer,
            upload_id=upload_id,
            index=index,
            offset=offset,
            expected=expected,
        )

    def complete(self, upload_id: str) -> dict:
        meta = self._load_meta(upload_id)
        if meta.get("status") == _STATUS_READY:
            return self._summary(meta)
        if meta.get("status") != _STATUS_UPLOADING:
            raise ValidationError("该上传已完成或不可再写。")
        size = int(meta["size"])
        total = int(meta["total_chunks"])
        try:
            part_size = self._storage.stat(paths.upload_part_path(upload_id)).size
        except StorageError as exc:
            raise ValidationError("分片尚未上传完成。") from exc
        if part_size != size:
            raise ValidationError("分片尚未上传完成。")
        names = set(self._storage.list_dir(paths.upload_chunks_dir(upload_id)))
        missing = [index for index in range(total) if str(index) not in names]
        if missing:
            raise ValidationError(f"还有 {len(missing)} 个分片未上传完成。")
        meta["status"] = _STATUS_READY
        meta["updated_at"] = _now()
        self._write_meta(meta)
        return self._summary(meta)

    def claim(self, upload_id: str) -> StagedUpload:
        """提交前取会话；必须已经 complete，且文件大小与声明一致。"""
        meta = self._load_meta(upload_id)
        if meta.get("status") != _STATUS_READY:
            raise ValidationError("分片尚未上传完成。")
        size = int(meta["size"])
        try:
            part_size = self._storage.stat(paths.upload_part_path(upload_id)).size
        except StorageError as exc:
            raise ValidationError("暂存的本体文件不存在。") from exc
        if part_size != size:
            raise ValidationError("暂存的本体文件大小不符。")
        return StagedUpload(
            upload_id=upload_id,
            filename=str(meta["filename"]),
            size=size,
        )

    def claim_many(self, upload_ids: list[str]) -> list[StagedUpload]:
        """一次取多个已完成会话（多文件本体）；先去重/限数，再逐个校验归属与大小。"""
        if not upload_ids:
            raise ValidationError("请选择要上传的文件。")
        if len(upload_ids) > MAX_BUNDLE_FILES:
            raise ValidationError(f"多文件本体最多 {MAX_BUNDLE_FILES} 个文件。")
        seen: set[str] = set()
        for upload_id in upload_ids:
            if upload_id in seen:
                raise ValidationError("同一个上传会话被重复引用。")
            seen.add(upload_id)
        # 先全部 claim 再返回：任何一个不完整都不会动到磁盘
        return [self.claim(upload_id) for upload_id in upload_ids]

    def discard(self, upload_id: str) -> None:
        """放弃会话；不存在时静默返回（DELETE 幂等）。"""
        if not _UPLOAD_ID_RE.match(upload_id or ""):
            return
        meta = self._load_meta(upload_id, allow_missing=True)
        if meta is None:
            return
        self._storage.remove_tree(paths.upload_session_dir(upload_id))

    # ------------------------------------------------------------------ #
    # 清理
    # ------------------------------------------------------------------ #
    @staticmethod
    def cleanup_stale(
        storage: LocalStorage, max_age_seconds: int = SESSION_TTL_SECONDS
    ) -> int:
        """删除超过 max_age_seconds 未更新的暂存会话；返回删除数量。"""
        now = time.time()
        removed = 0
        try:
            names = storage.list_dir(paths.UPLOAD_DIR)
        except StorageError as exc:
            logger.warning("清理分片暂存目录失败：%s", exc)
            return 0
        for name in names:
            if not _UPLOAD_ID_RE.match(name):
                continue
            session_dir = paths.upload_session_dir(name)
            if not storage.dir_exists(session_dir):
                continue
            stamp = storage.mtime(paths.upload_meta_path(name))
            if stamp is None:
                stamp = storage.mtime(session_dir)
            if stamp is None or now - stamp <= max_age_seconds:
                continue
            try:
                storage.remove_tree(session_dir)
            except StorageError as exc:
                logger.warning("删除过期上传会话失败 upload_id=%s：%s", name, exc)
                continue
            removed += 1
        return removed

    # ------------------------------------------------------------------ #
    # 元数据
    # ------------------------------------------------------------------ #
    def _write_meta(self, meta: dict) -> None:
        payload = json.dumps(meta, ensure_ascii=False).encode("utf-8")
        self._storage.upload(
            paths.upload_meta_path(str(meta["upload_id"])),
            BytesIO(payload),
            len(payload),
            "application/json",
        )

    def _load_meta(self, upload_id: str, *, allow_missing: bool = False) -> dict | None:
        if not _UPLOAD_ID_RE.match(upload_id or ""):
            if allow_missing:
                return None
            raise NotFoundError("上传会话不存在或已过期。")
        try:
            stream = self._storage.open_download(paths.upload_meta_path(upload_id))
        except StorageError as exc:
            if allow_missing:
                return None
            raise NotFoundError("上传会话不存在或已过期。") from exc
        try:
            raw = stream.read()
        finally:
            stream.close()
        try:
            meta = json.loads(raw)
        except (ValueError, TypeError) as exc:
            if allow_missing:
                return None
            raise NotFoundError("上传会话不存在或已过期。") from exc
        if not isinstance(meta, dict) or meta.get("upload_id") != upload_id:
            if allow_missing:
                return None
            raise NotFoundError("上传会话不存在或已过期。")
        if meta.get("user_id") != self._user_id:
            raise NotFoundError("上传会话不存在或已过期。")
        return meta

    @staticmethod
    def _summary(meta: dict) -> dict:
        return {
            "upload_id": meta["upload_id"],
            "filename": meta["filename"],
            "size": int(meta["size"]),
        }
