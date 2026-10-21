"""把数据根里的 zip 按需解到运行时根。

H5 与攻略都只上传 zip（存数据根），真正的解包推迟到**运行时**：播放 H5 或查看攻略时
调 `ensure()`，解包产物落在运行时根的 `game/{类型}/{卡带ID}/h5|guide/` 下——相对路径
与数据根逐字一致，只是拼的根不同。

三条规矩：

1. 产物永远是派生物，可以随时删，下次访问自动重建。所以 `drop_tree()` 尽力而为、
   失败只记日志；写路径（重传 zip / 换类型 / 改卡带ID / 删游戏）负责让它失效。
2. 解包是「先解到同层暂存目录、再整体改名替换」，所以磁盘上要么没有、要么完整，
   `_is_extracted()` 判据就是入口文件在不在。
3. 必须保持 gunicorn `--workers 1`：进程内的锁只能串行化同一个进程里的并发，
   多进程下并发 `os.replace` 覆盖非空目录会在 POSIX 上报 `ENOTEMPTY`。
"""

from __future__ import annotations

import logging
import threading
import zipfile
from contextlib import closing
from uuid import uuid4

from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games import archive, paths
from backend.storage.types import StorageBackend

logger = logging.getLogger(__name__)

# kind -> (zip 路径, 解包目标目录, 入口文件, 暂存目录名)，全部相对各自的根
_TARGETS = {
    archive.H5: (paths.h5_zip_path, paths.h5_dir, paths.h5_entry_path, paths.h5_temp_dir),
    archive.GUIDE: (
        paths.guide_zip_path,
        paths.guide_dir,
        paths.guide_entry_path,
        paths.guide_temp_dir,
    ),
}

# 进程级锁表：GameService 是每请求一个实例，锁不能挂在实例上。条目数上界就是游戏数
# （乘两个 kind），不清理也无所谓——每个 Lock 只有几十字节。
_locks: dict[tuple[str, str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: tuple[str, str, str]) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


class RuntimeAssets:
    """按需把数据根里的 zip 解到运行时根；同一 (类别, 类型, 卡带ID) 串行。"""

    def __init__(self, data: StorageBackend, runtime: StorageBackend) -> None:
        self._data = data
        self._runtime = runtime

    def root(self) -> str | None:
        """运行时根的绝对路径，只用来算 Windows 的完整路径长度（同 GameService._storage_root）。"""
        root = getattr(self._runtime, "root", None)
        return str(root) if root is not None else None

    def ensure(self, kind: str, game_type: str, cartridge_id: str) -> None:
        """确保该游戏的这个包已经解包好；已经解过就直接返回。

        zip 不在数据根（宿主手删）→ `NotFoundError`；包不合规或损坏（宿主换过）→
        `ValidationError`；写运行时根失败（磁盘满、只读）→ `StorageError`。
        """
        zip_maker, target_maker, entry_maker, temp_maker = _TARGETS[kind]
        target_dir = target_maker(game_type, cartridge_id)
        entry_path = entry_maker(game_type, cartridge_id)
        with _lock_for((kind, game_type, cartridge_id)):
            if self._is_extracted(entry_path):
                return
            self._extract(
                kind,
                zip_maker(game_type, cartridge_id),
                target_dir,
                temp_maker(game_type, cartridge_id, uuid4().hex[:12]),
            )

    def drop_tree(self, relative_dir: str) -> None:
        """作废运行时根下的某个相对目录（解包产物可重建，删掉即可）。

        刻意**不做**「两个根相同就跳过」的分支：重传 zip 只覆盖 `game.zip` 一个文件，
        同一棵树里的 `h5/` 不会被碰到，跳过会漏删；而 `LocalStorage.remove_tree` 对
        不存在的路径本来就静默，同根时其余几处只是多一次 exists() 检查。
        """
        try:
            self._runtime.remove_tree(relative_dir)
        except StorageError as exc:
            logger.warning("清理解包产物失败：%s（下次访问会重新解包）", relative_dir, exc_info=exc)

    def _is_extracted(self, entry_path: str) -> bool:
        """判据 = 入口文件在不在（与 `_has_guide` 同一套「磁盘即真相」口径）。

        `replace_tree` 保证目标目录要么不存在、要么完整，不会出现「半截但有入口」。
        """
        try:
            self._runtime.stat(entry_path)
        except StorageError:
            return False
        return True

    def _extract(self, kind: str, zip_path: str, target_dir: str, temp_dir: str) -> None:
        label = archive.LABELS[kind]
        try:
            source = self._data.open_download(zip_path)
        except StorageError as exc:
            raise NotFoundError(f"{label}压缩包不存在。") from exc
        try:
            with closing(source):
                # 解压前再校验一次：数据根是宿主可写的普通目录，zip 可能已经被换掉了
                entries = archive.read_manifest(source, kind=kind)
                for entry in entries:
                    archive.ensure_path_fits(
                        self.root(), f"{target_dir}/{entry.path}", where=archive.WHERE[kind]
                    )
                source.seek(0)
                with zipfile.ZipFile(archive.SeekableStream(source)) as zf:
                    for entry in entries:
                        spool, actual = archive.read_entry(zf, entry.info)
                        try:
                            stored = self._runtime.upload(
                                f"{temp_dir}/{entry.path}",
                                spool,
                                actual,
                                archive.guess_asset_mime(entry.path),
                            )
                            if stored.size is not None and stored.size != actual:
                                raise StorageError("解包资源写入大小不一致。")
                        finally:
                            spool.close()
            # 全部就位后再换目录：这一步之后磁盘上已经是新内容
            self._runtime.replace_tree(temp_dir, target_dir)
        except (ValidationError, NotFoundError, StorageError):
            self._remove_quietly(temp_dir)
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成领域错误并清掉暂存目录
            logger.warning("解包失败 kind=%s path=%s", kind, zip_path, exc_info=exc)
            self._remove_quietly(temp_dir)
            raise StorageError("解压游戏资源失败。") from exc

    def _remove_quietly(self, key: str) -> None:
        try:
            self._runtime.remove_tree(key)
        except StorageError:
            pass
