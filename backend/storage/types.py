from dataclasses import dataclass
from typing import BinaryIO, Protocol


class StoredObjectStream:
    """已打开的文件流：带元数据，read(n) 分块读取，close() 释放句柄。

    浏览器不直连磁盘，所有字节都由应用服务以该流的形式代理下发。

    还透传 seek/tell/seekable/readable：H5 与攻略的 zip 需要被 `zipfile` 当底层流读
    （它要求可 seek）。本地实现打开的就是普通文件，永远支持；换成远端后端时，
    要么在那里也实现 seek，要么调用方先把整包 spool 到临时文件。
    """

    def __init__(
        self,
        *,
        key: str,
        size: int | None = None,
        mime: str | None = None,
        reader=None,
    ) -> None:
        self.key = key
        self.size = size
        self.mime = mime
        self._reader = reader

    def read(self, n: int = -1) -> bytes:
        if self._reader is None:
            return b""
        if n is None or n < 0:
            return self._reader.read()
        return self._reader.read(n)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._reader.seek(offset, whence)

    def tell(self) -> int:
        return self._reader.tell()

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        if self._reader is None:
            return
        try:
            close = getattr(self._reader, "close", None)
            if close is not None:
                close()
        finally:
            self._reader = None


@dataclass
class StoredObject:
    """一次落盘后的文件元数据；key 即相对路径。"""

    key: str
    size: int | None = None
    mime: str | None = None


class StorageBackend(Protocol):
    """文件存储协议：游戏素材与存档都按「相对路径」读写。

    相对路径相对项目文件根目录（`STORAGE_ROOT`），SQLite 里存的就是它；
    实现负责把它拼成真实磁盘路径。路径分隔符一律用 `/`。
    """

    def upload(self, key: str, stream: BinaryIO, size: int, mime: str | None) -> StoredObject:
        ...

    def delete(self, key: str) -> None:
        ...

    def stat(self, key: str) -> StoredObject:
        ...

    def open_download(self, key: str) -> StoredObjectStream:
        ...
