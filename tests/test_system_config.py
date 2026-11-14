import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.system_config import LATEST_DB_VERSION, SystemConfig


def _columns(path) -> dict[str, dict]:
    conn = sqlite3.connect(path)
    try:
        return {
            row[1]: {"type": row[2], "nullable": not row[3]}
            for row in conn.execute("PRAGMA table_info(system_config)")
        }
    finally:
        conn.close()


def test_system_config_columns_and_unique_index(app):
    path = app.state.settings.database_path

    columns = _columns(path)
    assert columns["id"]["type"].upper() == "INTEGER"
    assert columns["key"]["type"].upper() == "VARCHAR(255)"
    assert columns["value"]["type"].upper() == "VARCHAR(1024)"

    conn = sqlite3.connect(path)
    try:
        indexes = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA index_list(system_config)")
        }
    finally:
        conn.close()
    assert indexes.get("ix_system_config_key") == 1


def test_db_version_row_is_present(app):
    with Session(app.state.engine) as session:
        row = session.exec(
            select(SystemConfig).where(SystemConfig.key == "db_version")
        ).one()
    assert row.value == str(LATEST_DB_VERSION)


def test_system_config_key_is_unique(app):
    with Session(app.state.engine) as session:
        session.add(SystemConfig(key="db_version", value="1"))
        with pytest.raises(IntegrityError):
            session.commit()
