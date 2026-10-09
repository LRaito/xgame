from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from backend.config import Settings

_engines: dict[str, Engine] = {}

# create_all 只建缺失的表，不会给已存在的表补列；老库靠这张表补上（只加列，不改不删）。
# DDL 是代码里的常量，不拼接任何外部输入。
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "games": {"cartridge_type": "VARCHAR(20) NOT NULL DEFAULT 'default'"},
}


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
    """建出库所在目录（根路径/db）。"""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)


def init_db(engine: Engine) -> None:
    # 导入模型以注册 metadata
    from backend.auth import models as auth_models  # noqa: F401
    from backend.games import models as game_models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_columns(engine)


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


def get_session(engine: Engine):
    with Session(engine) as session:
        yield session
