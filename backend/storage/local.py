import mimetypes
import os
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from backend.errors import StorageError, ValidationError
from backend.storage.types import StoredObject, StoredObjectStream

_CHUNK_SIZE = 256 * 1024
_DEFAULT_MIME = "application/octet-stream"


class LocalStorage:
    """把「相对路径」映射到项目文件根目录下的真实文件的存储实现。

    SQLite 里存的是相对路径（如 `game/nes/AB12/game.nes`），这里负责拼上根路径
    读写；写文件先落同目录临时文件再改名，避免读到的文件只写了一半。
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def upload(
        self, key: str, stream: BinaryIO, size: int, mime: str | None = None
    ) -> StoredObject:
        target = self._resolve(key)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("创建存储目录失败，请检查存储目录是否可写。") from exc
        temp = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex[:8]}")
        written = 0
        try:
            with open(temp, "wb") as handle:
                while True:
                    block = stream.read(_CHUNK_SIZE)
                    if not block:
                        break
                    handle.write(block)
                    written += len(block)
            os.replace(temp, target)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise StorageError("写入存储目录失败，请检查存储目录是否可写、空间是否充足。") from exc
        return StoredObject(
            key=self._normalize(key),
            size=written,
            mime=mime or self._guess_mime(target.name),
        )

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink()
        except FileNotFoundError:
            return  # 已经不在了，删两次不算错
        except OSError as exc:
            raise StorageError("删除文件失败，请检查存储目录权限。") from exc

    def stat(self, key: str) -> StoredObject:
        path = self._resolve(key)
        try:
            if not path.is_file():
                raise OSError("not a file")
            info = path.stat()
        except OSError as exc:
            raise StorageError("文件不存在或已被删除。") from exc
        return StoredObject(
            key=self._normalize(key), size=info.st_size, mime=self._guess_mime(path.name)
        )

    def open_download(self, key: str) -> StoredObjectStream:
        path = self._resolve(key)
        try:
            handle = open(path, "rb")
        except OSError as exc:
            raise StorageError("文件不存在或已被删除。") from exc
        return StoredObjectStream(
            key=self._normalize(key),
            size=os.fstat(handle.fileno()).st_size,
            mime=self._guess_mime(path.name),
            reader=handle,
        )

    def move(self, source_key: str, target_key: str) -> bool:
        """把单个文件挪到新路径（封面随游戏类型换目录时用）；源文件不在就返回 False。"""
        source = self._resolve(source_key)
        target = self._resolve(target_key)
        if not source.is_file():
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
        except OSError as exc:
            raise StorageError("移动文件失败，请检查存储目录权限。") from exc
        return True

    def move_tree(self, source_key: str, target_key: str) -> bool:
        """把整个目录挪到新路径（图集随游戏类型换目录时用）；源目录不在就返回 False。

        目标位置理论上不会有内容（新类型目录刚建成），真有就先改名挪开再删，
        免得改名直接失败——与 `replace_tree` 同一套手法。
        """
        source = self._resolve(source_key)
        target = self._resolve(target_key)
        if source == target:
            # 同一路径：什么也不用做（否则下面那套改名腾位会把自己挪走）
            return source.is_dir()
        if not source.is_dir():
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("创建存储目录失败，请检查存储目录是否可写。") from exc
        stale: Path | None = None
        if target.exists():
            stale = target.with_name(f".{target.name}.old-{uuid.uuid4().hex[:8]}")
            os.replace(target, stale)
        try:
            os.replace(source, target)
        except OSError as exc:
            if stale is not None:
                os.replace(stale, target)  # 尽力还原旧目录
            raise StorageError("移动目录失败，请检查存储目录权限。") from exc
        if stale is not None:
            shutil.rmtree(stale, ignore_errors=True)
        return True

    def remove_tree(self, key: str) -> None:
        """递归删掉一个目录（删游戏、换类型、H5 换代都用它）；不存在时静默返回。"""
        path = self._resolve(key)
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
        except OSError as exc:
            raise StorageError("删除目录失败，请检查存储目录权限。") from exc

    def replace_tree(self, source_key: str, target_key: str) -> None:
        """用 source 目录整体替换 target 目录，失败不留下半截结果。

        先把旧 target 改名挪开（同文件系统内是原子操作），再把 source 改名就位，
        最后删掉挪开的旧目录——中途任一步失败，旧目录都还在。
        """
        source = self._resolve(source_key)
        target = self._resolve(target_key)
        if not source.is_dir():
            raise StorageError("待替换的目录不存在。")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("创建存储目录失败，请检查存储目录是否可写。") from exc
        stale: Path | None = None
        if target.exists():
            stale = target.with_name(f".{target.name}.old-{uuid.uuid4().hex[:8]}")
            os.replace(target, stale)
        try:
            os.replace(source, target)
        except OSError as exc:
            if stale is not None:
                os.replace(stale, target)  # 尽力还原旧目录
            raise StorageError("替换目录失败，请检查存储目录权限。") from exc
        if stale is not None:
            shutil.rmtree(stale, ignore_errors=True)

    def _resolve(self, key: str) -> Path:
        parts = PurePosixPath(self._normalize(key)).parts
        return self._root.joinpath(*parts)

    @staticmethod
    def _normalize(key: str) -> str:
        """归一化并挡掉越界路径：只接受根目录内的相对路径。"""
        raw = (key or "").strip()
        if not raw:
            raise ValidationError("文件路径不能为空。")
        posix = PurePosixPath(raw)
        if "\\" in raw or posix.is_absolute() or any(part == ".." for part in posix.parts):
            raise ValidationError("文件路径非法。")
        return posix.as_posix()

    @staticmethod
    def _guess_mime(name: str) -> str:
        return mimetypes.guess_type(name)[0] or _DEFAULT_MIME
