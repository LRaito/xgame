"""数据根目录的哨兵文件：数据根在 Windows 盘挂载路径下时，启动前确认 `.mounted` 在。

`.mounted` 是「这个目录就是本项目的数据根」的标记，**只能人工创建**（本仓库只检查、不代建）。

要它是因为宿主 bind 的时序问题：数据目录放在 WSL 挂载的 Windows 盘上（`/mnt/…`）时，可能
docker 先起来、盘还没挂上，bind 把宿主上一个**空目录**挂进容器——那时 `.mounted` 不在，服务
若照常启动就会在空目录里新建一个空库，看起来就像「数据全没了」（窗口期内的写入还落在内存里，
重启即丢）。哨兵在不在是容器内部唯一能识破空挂载的判据：目录可写、能 `statvfs` 都测不出来。

**只对 Windows 盘挂载前缀下的数据根检查**（前缀可配，默认 `/mnt`，见 `config.WINDOWS_MOUNT_PREFIX`）：
只有那种目录才有上面这条竞态，放在普通 Linux 目录（如 `/srv/xgame`）里就直接启动，不要求哨兵。
判断用的是「数据根路径」：容器里是 compose 传进来的宿主路径 `STORAGE_HOST_DIR`（容器内固定挂到
`/data`，看不出宿主路径），本机直跑退回 `STORAGE_ROOT`；而**检查的文件**始终是进程能看到的
`<STORAGE_ROOT>/.mounted`。

缺哨兵时这里做三件事：打一条中文提示日志 → 等 `RESTART_DELAY_SECONDS` 秒 → 让进程以非零码
退出。容器里真正保证「退出的是容器主进程、compose 会把容器重新拉起来」的是入口脚本
`backend/entrypoint.sh`（它在 `exec gunicorn` 之前调这里的函数），判断与日志只有这一份。
"""

import logging
import sys
import time
from pathlib import Path

from backend.config import LOG_FORMAT, WINDOWS_MOUNT_PREFIX, Settings

logger = logging.getLogger(__name__)

# 哨兵文件名：放在数据根目录里，内容是空的。数据根目录本身不入库（gitignore），它也一样
SENTINEL_NAME = ".mounted"

# 缺哨兵时先等这么久再退出：留出看日志的时间，也别让容器陷入热重启
RESTART_DELAY_SECONDS = 5

# 退出码取 3（gunicorn 的 WORKER_BOOT_ERROR）：入口脚本只是把这个码原样透传出去，容器退出后
# 由 compose 的 `restart: unless-stopped` 重新拉起；万一有人绕过入口脚本直接跑 gunicorn，
# master 见到这个码也会跟着退出（换别的码它只会 fork 一个新 worker 重试，容器根本不重启）。
EXIT_CODE = 3


def sentinel_path(settings: Settings) -> Path:
    """哨兵文件的完整路径：数据根目录下。库与游戏文件都在这个根目录里，一个哨兵够了。"""
    return Path(settings.STORAGE_ROOT) / SENTINEL_NAME


def mounted_root(settings: Settings) -> Path:
    """用来判断「要不要检查」的那个数据根路径。

    容器里 `STORAGE_ROOT` 固定是 bind 目标 `/data`，看不出宿主路径，所以优先用 compose 传进来的
    宿主路径 `STORAGE_HOST_DIR`；本机直跑没有它，退回 `STORAGE_ROOT`。
    """
    return Path(settings.STORAGE_HOST_DIR or settings.STORAGE_ROOT)


def on_windows_mount(path: Path) -> bool:
    """路径是不是落在 Windows 盘的挂载前缀下（按路径分量比，`/mnt` 不会匹配上 `/mntfoo`）。

    前缀可配（`config.WINDOWS_MOUNT_PREFIX`，默认 `/mnt`）；把它设成 `/` 就等于对所有路径都要求哨兵。
    """
    prefix = Path(WINDOWS_MOUNT_PREFIX).parts
    return path.resolve().parts[: len(prefix)] == prefix


def require_mounted(settings: Settings) -> None:
    """数据根在 Windows 盘挂载前缀下、却没有哨兵文件时：打完日志等 5 秒、退出进程。

    数据根不在那个前缀下（放普通 Linux 目录里）就直接放行——那种路径没有「盘没挂上」的竞态。
    检查只 stat 根目录下的哨兵，**不建目录也不建库**：这件事必须早于 `ensure_data_dir()`，
    否则空挂载下新库已经被建出来了。
    """
    if settings.TESTING:
        # 测试用临时数据根目录，不摆哨兵文件，照常启动
        return

    root = mounted_root(settings)
    if not on_windows_mount(root):
        return

    path = sentinel_path(settings)
    if path.is_file():
        return

    # 这条日志可能跑在入口脚本里（那时 create_app() 还没配过日志），先补一次全局配置；
    # basicConfig 只在根 logger 还没有 handler 时生效，create_app() 里那次调用不受影响。
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logger.error(
        "数据根目录 %s 里没有哨兵文件 %s：它在 Windows 盘挂载前缀 %s 下，盘可能还没挂上"
        "（bind 把宿主空目录挂进来了），服务拒绝启动，以免在空目录里新建空库。"
        "请在宿主侧的数据目录里手动创建这个空文件（touch %s），%d 秒后重启容器重试。",
        settings.STORAGE_ROOT,
        SENTINEL_NAME,
        WINDOWS_MOUNT_PREFIX,
        root / SENTINEL_NAME,
        RESTART_DELAY_SECONDS,
    )
    time.sleep(RESTART_DELAY_SECONDS)
    sys.exit(EXIT_CODE)
