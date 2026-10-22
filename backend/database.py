from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from backend.config import Settings

_engines: dict[str, Engine] = {}

# create_all 只建缺失的表，不会给已存在的表补列；老库靠这张表补上（只加列，不改不删）。
# DDL 是代码里的常量，不拼接任何外部输入。
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    # 封面类型可空：老库里的旧行没有值，加列时不能带 NOT NULL（也没必要给默认值）
    "games": {
        "cover_type": "VARCHAR(20)",
        # 攻略形态（""/"zip"/"pdf"）。老库里的旧行一律是空串；不做磁盘回填。
        "guide_kind": "VARCHAR(10) NOT NULL DEFAULT ''",
    },
}

# 已删除的表：create_all 只建不删，老库里可能还留着，启动时顺手清掉。没有迁移框架，
# 破坏性动作只允许「删掉整张已经没有任何代码读写的表」这一种；表名是代码里的常量，
# 不拼接任何外部输入。
_DROPPED_TABLES: tuple[str, ...] = ("game_h5_files",)


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


def init_db(engine: Engine) -> None:
    # 导入模型以注册 metadata
    from backend.auth import models as auth_models  # noqa: F401
    from backend.games import models as game_models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_columns(engine)
    _drop_tables(engine)


def _ensure_columns(engine: Engine) -> None:
    """给已存在的表补上后来新增的列（SQLite 的 ADD COLUMN 只加不重建）。"""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _drop_tables(engine: Engine) -> None:
    """删掉已经没有任何代码读写的表（见 `_DROPPED_TABLES`）。"""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in _DROPPED_TABLES:
            if inspector.has_table(table):
                conn.exec_driver_sql(f"DROP TABLE {table}")


def get_session(engine: Engine):
    with Session(engine) as session:
        yield session
