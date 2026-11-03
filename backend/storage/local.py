import mimetypes
import os
import shutil
import stat
import sys
import uuid
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from backend.errors import StorageError, ValidationError
from backend.storage.types import StoredObject, StoredObjectStream

_CHUNK_SIZE = 256 * 1024
_DEFAULT_MIME = "application/octet-stream"


def _rmtree(path: Path) -> None:
    """递归删除目录，并处理 Windows 的「只读文件删不掉」。

    Windows 上带只读属性的文件 `os.unlink` 会直接失败（POSIX 只看父目录的写权限，不看文件
    自己的位），这里在失败时去掉只读位再试一次。`onerror` 在 3.12 起标记为过时、改名 `onexc`，
    两者回调签名只差一个参数，所以同一个函数能同时喂给它们。
    """
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry_without_readonly)
    else:
        shutil.rmtree(path, onerror=_retry_without_readonly)


def _retry_without_readonly(func, path, *_exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _remove_tree_quietly(path: Path) -> None:
    """尽力删除（挪开的旧目录用）：删不掉就算了，反正它已经不在使用中。"""
    try:
        _rmtree(path)
    except OSError:
        pass


class StorageWriter:
    """按绝对偏移写入一个文件，供分片上传直接写目标文件。

    每个请求各自打开一个 fd：POSIX 上优先用 `os.pwrite`；Windows 没有 `pwrite`，
    退回「本 fd 自己 `lseek` + `write`」。文件位置是每个句柄各自的，所以 5 路并发
    写同一文件的不同偏移不会互相踩。
    """

    def __init__(self, path: Path) -> None:
        self._fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        self._closed = False

    def write_at(self, offset: int, data: bytes) -> None:
        view = memoryview(data)
        written = 0
        try:
            while written < len(view):
                if hasattr(os, "pwrite"):
                    count = os.pwrite(self._fd, view[written:], offset + written)
                else:
                    os.lseek(self._fd, offset + written, os.SEEK_SET)
                    count = os.write(self._fd, view[written:])
                if count <= 0:
                    raise OSError("写入返回 0 字节")
                written += count
        except OSError as exc:
            raise StorageError("写入存储目录失败，请检查存储目录是否可写、空间是否充足。") from exc

    def flush(self) -> None:
        if self._closed:
            return
        try:
            os.fsync(self._fd)
        except OSError as exc:
            raise StorageError("刷新存储文件失败，请检查存储目录。") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            os.close(self._fd)
        except OSError:
            pass


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

    def dir_exists(self, key: str) -> bool:
        """目录在不在（改卡带ID 前判新旧目录的形态时用）；同名的是个文件也算不在。"""
        return self._resolve(key).is_dir()

    def exists(self, key: str) -> bool:
        """文件在不在（分片标记文件用）；同名的是个目录也算不在。"""
        return self._resolve(key).is_file()

    def list_dir(self, key: str) -> list[str]:
        """列出一个目录下的条目名（不递归）；目录不存在返回空列表。"""
        path = self._resolve(key)
        try:
            return sorted(entry.name for entry in path.iterdir())
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise StorageError("读取存储目录失败，请检查存储目录权限。") from exc

    def mtime(self, key: str) -> float | None:
        """条目的修改时间（秒）；不存在或读不到返回 None。"""
        try:
            return self._resolve(key).stat().st_mtime
        except OSError:
            return None

    def open_writer(self, key: str) -> StorageWriter:
        """打开一个按偏移写入的文件句柄（分片上传直写用）；父目录自动建。"""
        path = self._resolve(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return StorageWriter(path)
        except OSError as exc:
            raise StorageError("创建存储文件失败，请检查存储目录是否可写。") from exc

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
            _remove_tree_quietly(stale)
        return True

    def remove_tree(self, key: str) -> None:
        """递归删掉一个目录（删游戏、改卡带ID、H5 换代都用它）；不存在时静默返回。"""
        path = self._resolve(key)
        if not path.exists():
            return
        try:
            _rmtree(path)
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
            _remove_tree_quietly(stale)

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
