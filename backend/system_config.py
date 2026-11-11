"""系统配置表：平台级、与具体功能无关的键值配置。

目前只有一项：``db_version`` = ``app.db`` 的结构版本。业务代码不读写其它键。
表由 ``init_db()`` 在全新库上建出；已有库由 ``upgrade/versions/v1.py`` 建出，
之后每次结构升级由 ``make upgrade``（Windows 包双击「升级数据库.cmd」）更新 ``db_version``。
"""

from sqlmodel import Field, SQLModel

# ``system_config`` 里记录数据库结构版本的键
DB_VERSION_KEY = "db_version"

# 当前代码要求的 app.db 结构版本。每次结构变化加 1，并在 upgrade/versions 里
# 新增一个同号模块；服务启动只校验这个值，不自动改表。
LATEST_DB_VERSION = 1


class SystemConfig(SQLModel, table=True):
    """一条通用系统配置。键唯一，值按字符串存。"""

    __tablename__ = "system_config"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(max_length=255, unique=True, index=True)
    value: str = Field(max_length=1024)
