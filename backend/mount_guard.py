"""数据根目录的哨兵文件：`create_app()` 启动时确保 `<STORAGE_ROOT>/.mounted` 在，缺了就建一个。

`.mounted` 是「这个目录就是本项目的数据根」的标记文件。启动流程只在 `create_app()` 里检查
这一处（早于建目录、建库），补上之后照常启动。

**它不拦启动。** 数据根目录放在 WSL 挂载的 Windows 盘上（`/mnt/…`）时，开机可能 docker 先起来、
盘还没挂上，bind 会把宿主上一个**空目录**挂进容器，服务就在那儿建了一个新库。这层风险不做拦截，
哨兵文件只作为标记与排障线索保留。所以数据目录必须指向 docker 启动前就可达的路径，见
[`DEVELOP.md`](../DEVELOP.md) 的「排障」。
"""

from pathlib import Path

from backend.config import Settings

# 哨兵文件名：放在数据根目录里，内容是空的
SENTINEL_NAME = ".mounted"


def sentinel_path(settings: Settings) -> Path:
    """哨兵文件的完整路径：数据根目录下。库与游戏文件都在这个根目录里，一个就够。"""
    return Path(settings.STORAGE_ROOT) / SENTINEL_NAME


def has_sentinel(settings: Settings) -> bool:
    """根目录里有没有哨兵文件（没建过、或盘被挂成了空目录时为假）。"""
    return sentinel_path(settings).is_file()


def ensure_mounted(settings: Settings) -> Path:
    """确保数据根目录带着哨兵文件：目录或文件缺了就建出来，返回哨兵路径。"""
    path = sentinel_path(settings)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return path
