"""应用配置。

这个平台只给自己用、不打算部署到别人的机器上，所以配置基本都写死在代码里，
不再走环境变量。整个仓库只剩三个 `.env` 键，而且**后端进程一个都不读**：

- `STORAGE_HOST_DIR`：宿主侧数据目录，compose 把它挂到容器的 `/data`；
- `RUNTIME_HOST_DIR`：宿主侧运行时目录，compose 把它挂到容器的 `/runtime`；
- `WEB_HTTPS_PORT`：对外发布的 HTTPS 端口。

后端自己认的环境变量只有下面 `Settings` 里那几个（容器里 `STORAGE_ROOT` / `RUNTIME_ROOT` 由
`backend/Dockerfile` 固定成 `/data` / `/runtime`，本机直接跑 uvicorn 时退化成仓库下的
`data/storage`）。测试用临时目录覆盖它。`.env` 因此变成可选的：不建它，compose 就用这三个键的默认值。

**例外是「解压即用」的 Windows 包**（`packaging/windows/`）：那条路线没有 nginx，由启动器
（`launcher.py`）设几个环境变量再把 uvicorn 拉起来，所以多出来 `STATIC_DIR`
这种只会由启动器设置的字段。它们的默认值保证 Docker 路线行为一字不变。

改配置就是改这个文件。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# session cookie 的签名密钥，写死在这里。改它会让所有已登录会话失效。
# 这是个人自托管平台，密钥跟仓库一起走，不从环境变量读、也不做轮换。
SECRET_KEY = "7DRuoN-aQgNE7vuHsHQ-UGXt2RleZFT2gRJrjKzTtNv9wRuB9CthMDMpPz5M_3hWQOzOadOnupsUW3kpO5Mp7Q"

# 日志格式：`create_app()` 与启动前的哨兵检查（`backend/mount_guard.py`）各配一次日志，
# 后者跑在入口脚本里、早于 `create_app()`，所以两处共用这一个常量。
LOG_FORMAT = "%(levelname)s %(name)s %(message)s"

# Windows 盘的挂载路径前缀（可改；设成 "/" 表示对所有路径都要求哨兵）。
# WSL 里挂进来的 Windows 盘都在这个前缀下（如 /mnt/x/xgame/storage）。根目录落在它下面时，开机存在
# 「盘还没挂上、bind 把宿主空目录挂进容器」的竞态，所以启动前要求 `.mounted` 哨兵；其它路径
# （普通 Linux 目录）没有这个风险，不检查、直接启动。判断细节见 backend/mount_guard.py。
WINDOWS_MOUNT_PREFIX = "/mnt"

# SQLite 库在根目录下的固定子目录。库落在**运行时根**的 db/ 下（`<运行时根>/db/app.db`），
# 备份落在**数据根**的 db/ 下——两个根在 `.env` 里默认就是分开的（`./data/storage` 与
# `./data/runtime`），不设 RUNTIME_ROOT 时才是同一个目录。
# 写死是为了让「库永远在某个根的 db/ 下」这件事在代码里成立，而不是靠各处的约定。
DB_SUBDIR = "db"
DB_FILENAME = "app.db"

# 游戏检索用的索引库，在**数据根**的 db/ 下（`<数据根>/db/game.db`）。它是从 CSV 名录派生的只读库：
# **只有 `make index` 写它**，运行期一律以 mode=ro 打开；也不参与备份（备份只认 DB_FILENAME）。
GAME_INDEX_FILENAME = "game.db"

# 生成游戏检索索引的 CSV 名录（`机种,中文,英文` 三列）。这份数据只在仓库/宿主机上存在——
# 它随 backend/ 一起进 api 镜像，所以容器里也能在启动时自动补建。
SEARCH_CSV_DIR = BASE_DIR / "backend" / "search" / "csv"


def default_storage_root() -> str:
    """本机开发默认落在仓库下的 data/storage；容器里由 Dockerfile 覆盖成 /data。"""
    return str((BASE_DIR / "data" / "storage").resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    TESTING: bool = False

    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"

    # session cookie 的 Secure 标记。Docker 路线全程 HTTPS，必须是 True。
    # 「解压即用」的 Windows 包走 http（局域网里手机/平板也要能连，自签证书对它们等于没有），
    # 此时必须由启动器设成 False，否则浏览器根本不保存这个 cookie——症状是「登录看着成功、
    # 下一个请求就 401、在登录页来回跳」。
    SESSION_COOKIE_SECURE: bool = True

    # 项目文件根目录：游戏本体/封面/H5 资源/攻略、云端存档、截图、检索索引与备份都在它下面。
    # 容器里由 backend/Dockerfile 固定为 /data，宿主目录经 compose 挂到该路径。
    STORAGE_ROOT: str = default_storage_root()

    # 运行时根目录：SQLite 库（app.db）落在这下面的 db/ 里，与游戏文件分开。为空时退回 STORAGE_ROOT。
    # 单独放是为了让数据根可以整体交给网盘/外部工具备份——那个客户端拷不动一个一直被写着的库文件，
    # 而它下面那堆游戏文件、存档、截图又必须能拷走。容器里由 backend/Dockerfile 固定为 /runtime。
    RUNTIME_ROOT: str | None = None

    # 宿主侧数据目录：compose 把 .env 的 STORAGE_HOST_DIR 也传进容器，**只**用于启动时判断
    # 「数据根是不是在 Windows 盘挂载前缀下」——容器里 STORAGE_ROOT 固定是 /data，看不出宿主
    # 路径（见 backend/mount_guard.py）。本机直跑没有它，判断退回 STORAGE_ROOT。
    # 业务代码不读它，`.env` 文件本身后端仍然不读。
    STORAGE_HOST_DIR: str | None = None

    # 宿主侧运行时目录，与 STORAGE_HOST_DIR 同理：只给哨兵判断用（两个宿主目录都要过哨兵，
    # 缺一不可——空挂载里新建一个空 app.db 就等于账号全没了）。为空时判断退回 RUNTIME_ROOT。
    RUNTIME_HOST_DIR: str | None = None

    # 前端构建产物（dist）的目录。**只有「解压即用」的 Windows 包会设它**：那条路线没有 nginx，
    # 由后端顺带托管静态站（见 backend/static_site.py）。为空时一条静态路由都不注册，Docker
    # 路线（nginx 托管）行为完全不变。
    STATIC_DIR: str | None = None

    # 请求体上限，替代 nginx 的 client_max_body_size（撤掉 nginx 后没有任何全局闸门：
    # Starlette 的 max_part_size 只管非文件字段，文件部分是不设上限的）。
    # 默认取得比 nginx 的 128MB 宽松，是为了让「攻略 256MB 总量」这个应用层上限真正可达——
    # nginx 那条 128m 本来就和它对不上。Docker 路线上 nginx 先拦，这个值只是兜底。
    MAX_REQUEST_BODY_BYTES: int = 512 * 1024 * 1024

    @property
    def runtime_root(self) -> Path:
        """运行时根目录：SQLite 库放它下面。没配 RUNTIME_ROOT 时就是数据根（= 不分开）。"""
        return Path(self.RUNTIME_ROOT or self.STORAGE_ROOT)

    @property
    def database_path(self) -> Path:
        """SQLite 文件路径：运行时根/db/app.db。"""
        return self.runtime_root / DB_SUBDIR / DB_FILENAME

    @property
    def database_url(self) -> str:
        # 用 as_posix()：Windows 下 str(Path) 是反斜杠，且路径里出现 `#` `?` `%` 时会被当成
        # URL 的一部分解析坏掉。检索索引那边（search_service.py）早就用 as_uri() 绕这个坑了，
        # 这里取同样的原则。
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def backup_dir(self) -> Path:
        """备份目录：数据根/db/。备份**不跟着库走**——它要留在会被外部备份的那个根里。"""
        return Path(self.STORAGE_ROOT) / DB_SUBDIR

    @property
    def game_index_path(self) -> Path:
        """游戏检索索引路径：数据根/db/game.db。运行期只读，不存在时视为「尚未构建索引」。"""
        return Path(self.STORAGE_ROOT) / DB_SUBDIR / GAME_INDEX_FILENAME


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_from_overrides(overrides: dict | None = None) -> Settings:
    if not overrides:
        return get_settings()
    return Settings(**overrides)
