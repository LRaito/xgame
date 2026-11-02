"""数据根与运行时根的哨兵文件：它们在 Windows 盘挂载路径下时，启动前确认 `.mounted` 在。

`.mounted` 是「这个目录就是本项目那个根目录」的标记，**只能人工创建**（本仓库只检查、不代建）。
两个根都要查，缺一不可：数据根是空的会「游戏全没了」，运行时根是空的会**新建一个空 app.db**，
看起来就是「账号全没了」。

要它是因为宿主 bind 的时序问题：目录放在 WSL 挂载的 Windows 盘上（`/mnt/…`）时，可能
docker 先起来、盘还没挂上，bind 把宿主上一个**空目录**挂进容器——那时 `.mounted` 不在，服务
若照常启动就会在空目录里新建一个空库，看起来就像「数据全没了」（窗口期内的写入还落在内存里，
重启即丢）。哨兵在不在是容器内部唯一能识破空挂载的判据：目录可写、能 `statvfs` 都测不出来。

**只对 Windows 盘挂载前缀下的目录检查**（前缀可配，默认 `/mnt`，见 `config.WINDOWS_MOUNT_PREFIX`）：
只有那种目录才有上面这条竞态，放在普通 Linux 目录（如 `/srv/xgame`）里就直接启动，不要求哨兵。
判断用的是「宿主路径」：容器里是 compose 传进来的 `STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR`
（容器内固定挂到 `/data` / `/runtime`，看不出宿主路径），本机直跑退回 `STORAGE_ROOT` /
`RUNTIME_ROOT`；而**检查的文件**始终是进程能看到的挂载点下的 `.mounted`。

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

# 哨兵文件名：放在根目录里，内容是空的。根目录本身不入库（gitignore），它也一样
SENTINEL_NAME = ".mounted"

# 缺哨兵时先等这么久再退出：留出看日志的时间，也别让容器陷入热重启
RESTART_DELAY_SECONDS = 5

# 退出码取 3（gunicorn 的 WORKER_BOOT_ERROR）：入口脚本只是把这个码原样透传出去，容器退出后
# 由 compose 的 `restart: unless-stopped` 重新拉起；万一有人绕过入口脚本直接跑 gunicorn，
# master 见到这个码也会跟着退出（换别的码它只会 fork 一个新 worker 重试，容器根本不重启）。
EXIT_CODE = 3


def mount_pairs(settings: Settings) -> list[tuple[Path, Path]]:
    """要检查的 (宿主路径, 挂载点) 列表：数据根一对、运行时根一对。

    宿主路径用来判断「要不要检查」，挂载点是进程能看到的那个目录（哨兵文件在它下面）。
    两个根指向同一个目录时（默认就是）按挂载点去重，只剩一条——行为与只看数据根时一模一样。
    """
    pairs = [
        (Path(settings.STORAGE_HOST_DIR or settings.STORAGE_ROOT), Path(settings.STORAGE_ROOT)),
        (
            Path(settings.RUNTIME_HOST_DIR or settings.RUNTIME_ROOT or settings.STORAGE_ROOT),
            settings.runtime_root,
        ),
    ]
    seen: set[Path] = set()
    result: list[tuple[Path, Path]] = []
    for host_dir, mount_point in pairs:
        if mount_point in seen:
            continue
        seen.add(mount_point)
        result.append((host_dir, mount_point))
    return result


def on_windows_mount(path: Path) -> bool:
    """路径是不是落在 Windows 盘的挂载前缀下（按路径分量比，`/mnt` 不会匹配上 `/mntfoo`）。

    前缀可配（`config.WINDOWS_MOUNT_PREFIX`，默认 `/mnt`）；把它设成 `/` 就等于对所有路径都要求哨兵。
    """
    prefix = Path(WINDOWS_MOUNT_PREFIX).parts
    return path.resolve().parts[: len(prefix)] == prefix


def require_mounted(settings: Settings) -> None:
    """某个根在 Windows 盘挂载前缀下、却没有哨兵文件时：打完日志等 5 秒、退出进程。

    两个根（数据根、运行时根）逐个检查；不在那个前缀下的（放普通 Linux 目录里）直接跳过——
    那种路径没有「盘没挂上」的竞态。检查只 stat 各挂载点下的哨兵，**不建目录也不建库**：
    这件事必须早于 `ensure_data_dir()`，否则空挂载下新库已经被建出来了。
    """
    if settings.TESTING:
        # 测试用临时根目录，不摆哨兵文件，照常启动
        return

    for host_dir, mount_point in mount_pairs(settings):
        if not on_windows_mount(host_dir):
            continue
        if (mount_point / SENTINEL_NAME).is_file():
            continue

        # 这条日志可能跑在入口脚本里（那时 create_app() 还没配过日志），先补一次全局配置；
        # basicConfig 只在根 logger 还没有 handler 时生效，create_app() 里那次调用不受影响。
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        logger.error(
            "根目录 %s 里没有哨兵文件 %s：它的宿主目录 %s 在 Windows 盘挂载前缀 %s 下，"
            "盘可能还没挂上（bind 把宿主空目录挂进来了），服务拒绝启动，以免在空目录里新建空库。"
            "请在宿主侧的目录里手动创建这个空文件（touch %s），%d 秒后重启容器重试。",
            mount_point,
            SENTINEL_NAME,
            host_dir,
            WINDOWS_MOUNT_PREFIX,
            host_dir / SENTINEL_NAME,
            RESTART_DELAY_SECONDS,
        )
        time.sleep(RESTART_DELAY_SECONDS)
        sys.exit(EXIT_CODE)
