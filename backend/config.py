"""应用配置。

这个平台只给自己用、不打算部署到别人的机器上，所以配置基本都写死在代码里，
不再走环境变量。整个仓库只剩两个 `.env` 键，而且**后端进程一个都不读**：

- `STORAGE_HOST_DIR`：宿主侧数据目录，compose 把它挂到容器的 `/data`；
- `WEB_HTTPS_PORT`：对外发布的 HTTPS 端口。

后端自己只认一个环境变量 `STORAGE_ROOT`（容器里由 `backend/Dockerfile` 固定成 `/data`，
本机直接跑 uvicorn 时退化成仓库下的 `data/storage`）。测试用临时目录覆盖它。
`.env` 因此变成可选的：不建它，compose 就用这两个键的默认值。

改配置就是改这个文件。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# session cookie 的签名密钥，写死在这里。改它会让所有已登录会话失效。
# 这是个人自托管平台，密钥跟仓库一起走，不从环境变量读、也不做轮换。
SECRET_KEY = "7DRuoN-aQgNE7vuHsHQ-UGXt2RleZFT2gRJrjKzTtNv9wRuB9CthMDMpPz5M_3hWQOzOadOnupsUW3kpO5Mp7Q"

# 固定应用配置（按需改代码）
SESSION_COOKIE_SECURE = True

# SQLite 库在根目录下的固定子目录（`<根路径>/db/app.db`，月度备份也落在同一个 db/ 里）。
# 写死是为了让「库永远在根目录的 db/ 下」这件事在代码里成立，而不是靠各处的约定。
DB_SUBDIR = "db"
DB_FILENAME = "app.db"


def default_storage_root() -> str:
    """本机开发默认落在仓库下的 data/storage；容器里由 Dockerfile 覆盖成 /data。"""
    return str((BASE_DIR / "data" / "storage").resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    TESTING: bool = False

    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"

    # 项目文件根目录：游戏本体/封面/H5 资源/攻略、云端存档、截图与 SQLite 库都在它下面。
    # 容器里由 backend/Dockerfile 固定为 /data，宿主目录经 compose 挂到该路径。
    STORAGE_ROOT: str = default_storage_root()

    @property
    def database_path(self) -> Path:
        """SQLite 文件路径：根路径/db/app.db。"""
        return Path(self.STORAGE_ROOT) / DB_SUBDIR / DB_FILENAME

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_from_overrides(overrides: dict | None = None) -> Settings:
    if not overrides:
        return get_settings()
    return Settings(**overrides)
