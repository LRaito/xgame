from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from backend.config import Settings
from backend.errors import DatabaseVersionError
from backend.system_config import DB_VERSION_KEY, LATEST_DB_VERSION

_engines: dict[str, Engine] = {}


def make_engine(settings: Settings) -> Engine:
    url = settings.database_url
    if url in _engines:
        return _engines[url]
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, connect_args=connect_args)
    _engines[url] = engine
    return engine


def ensure_data_dir(settings: Settings) -> None:
    """建出库所在目录（运行时根/db）。没配运行时根时它就是数据根/db。"""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def has_business_tables(engine: Engine) -> bool:
    """库里是否已有业务表。

    只有 ``system_config``（或什么都没有）视为全新库：首次启动可以按最新结构一次性建好。
    任何其它表存在都说明是已有库，必须走版本校验。
    """
    return bool(_table_names(engine) - {"system_config"})


def read_db_version(engine: Engine) -> int:
    """读 ``system_config.db_version``；表或键不存在时返回 0（无版本号时代）。"""
    if "system_config" not in _table_names(engine):
        return 0
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            'SELECT value FROM system_config WHERE "key" = ?', (DB_VERSION_KEY,)
        ).first()
    if row is None:
        return 0
    try:
        version = int(row[0])
    except (TypeError, ValueError) as exc:
        raise DatabaseVersionError(
            f'system_config 的 "{DB_VERSION_KEY}" 不是合法整数：{row[0]!r}；'
            "请检查数据库或从备份恢复。"
        ) from exc
    if version < 0:
        raise DatabaseVersionError(f"数据库结构版本不能为负数：{version}")
    return version


def _create_latest_schema(engine: Engine) -> None:
    """全新库：按当前模型建全部表，并在同一事务里写入最新结构版本。"""
    # 导入模型以注册 metadata（升级/兼容代码不在这里，结构变化请新增 upgrade 版本）
    from backend.auth import models as auth_models  # noqa: F401
    from backend.games import models as game_models  # noqa: F401
    from backend.shortcuts import models as shortcut_models  # noqa: F401
    from backend.system_config import SystemConfig  # noqa: F401

    with engine.begin() as conn:
        SQLModel.metadata.create_all(conn)
        conn.exec_driver_sql(
            'INSERT INTO system_config ("key", value) VALUES (?, ?) '
            'ON CONFLICT("key") DO UPDATE SET value = excluded.value',
            (DB_VERSION_KEY, str(LATEST_DB_VERSION)),
        )


def _version_error(current: int) -> DatabaseVersionError:
    if current > LATEST_DB_VERSION:
        return DatabaseVersionError(
            f"数据库结构版本 {current} 高于当前程序需要的 {LATEST_DB_VERSION}："
            "请使用与数据库匹配的程序版本，不能降级运行。"
        )
    if current == 0:
        return DatabaseVersionError(
            f"数据库没有结构版本记录（视为 0），当前程序需要 {LATEST_DB_VERSION}："
            "请先停止服务并执行 make upgrade 更新数据库"
            "（Windows 解压即用包：关闭启动窗口后双击「升级数据库.cmd」）。"
        )
    return DatabaseVersionError(
        f"数据库结构版本 {current} 低于当前程序需要的 {LATEST_DB_VERSION}："
        "请先停止服务并执行 make upgrade 更新数据库"
        "（Windows 解压即用包：关闭启动窗口后双击「升级数据库.cmd」）。"
    )


def init_db(engine: Engine) -> None:
    """初始化全新库，或校验已有库的结构版本。

    已有库**绝不**在这里改表：兼容升级只允许由 ``make upgrade`` 执行。
    版本不匹配时抛 ``DatabaseVersionError``，由启动入口负责记录日志并阻塞。
    """
    if not has_business_tables(engine):
        _create_latest_schema(engine)
        return

    version = read_db_version(engine)
    if version != LATEST_DB_VERSION:
        raise _version_error(version)


def get_session(engine: Engine):
    with Session(engine) as session:
        yield session
