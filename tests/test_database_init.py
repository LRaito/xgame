import logging
import sqlite3

import pytest

import backend
from backend import create_app
from backend.config import Settings
from backend.database import ensure_data_dir, init_db, make_engine, read_db_version
from backend.system_config import LATEST_DB_VERSION

_ALL_TABLES = {
    "users",
    "login_attempts",
    "user_shortcuts",
    "games",
    "game_cloud_snapshots",
    "game_cloud_snapshot_files",
    "game_screenshots",
    "game_gallery_images",
    "game_emulator_settings",
    "game_recent_plays",
    "game_user_stats",
    "system_config",
}


class _Blocked(RuntimeError):
    pass


def _settings(tmp_path) -> Settings:
    return Settings(TESTING=True, STORAGE_ROOT=str(tmp_path / "storage"))


def _table_names(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        conn.close()


def _db_version(path) -> str | None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT value FROM system_config WHERE \"key\" = 'db_version'"
        ).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def _write_legacy_database(path, *, version: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE users ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "username VARCHAR(32) NOT NULL, "
            "password_hash VARCHAR(255) NOT NULL, "
            "created_at DATETIME NOT NULL)"
        )
        conn.execute(
            "INSERT INTO users VALUES (1, 'alice', 'hash', '2026-01-01 00:00:00')"
        )
        if version is not None:
            conn.execute(
                "CREATE TABLE system_config ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                '"key" VARCHAR(255) NOT NULL, '
                "value VARCHAR(1024) NOT NULL)"
            )
            conn.execute(
                'INSERT INTO system_config ("key", value) VALUES (?, ?)',
                ("db_version", version),
            )
        conn.commit()
    finally:
        conn.close()


def test_fresh_database_is_initialized_at_latest(tmp_path):
    settings = _settings(tmp_path)

    app = create_app(
        {"TESTING": True, "STORAGE_ROOT": settings.STORAGE_ROOT}
    )

    assert _table_names(settings.database_path) == _ALL_TABLES
    assert _db_version(settings.database_path) == str(LATEST_DB_VERSION)
    conn = sqlite3.connect(settings.database_path)
    try:
        games_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'games'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert "AUTOINCREMENT" in games_sql.upper()
    assert app.state.engine is not None


def test_existing_database_at_latest_starts_twice(tmp_path):
    settings = _settings(tmp_path)
    ensure_data_dir(settings)
    engine = make_engine(settings)
    init_db(engine)
    init_db(engine)  # 第二次走「已有库只校验版本」路径

    assert read_db_version(engine) == LATEST_DB_VERSION


def test_old_database_without_version_blocks_startup(tmp_path, monkeypatch, caplog):
    settings = _settings(tmp_path)
    _write_legacy_database(settings.database_path)

    def stop(_exc=None):
        raise _Blocked()

    monkeypatch.setattr(backend, "block_forever", stop)
    caplog.set_level(logging.ERROR)

    with pytest.raises(_Blocked):
        create_app({"TESTING": True, "STORAGE_ROOT": settings.STORAGE_ROOT})

    assert "make upgrade" in caplog.text
    assert "升级数据库.cmd" in caplog.text
    assert "服务不会启动" in caplog.text
    # 启动路径没有偷偷补表或写版本
    assert _table_names(settings.database_path) == {"users"}


def test_newer_database_blocks_startup(tmp_path, monkeypatch, caplog):
    settings = _settings(tmp_path)
    _write_legacy_database(settings.database_path, version="99")

    def stop(_exc=None):
        raise _Blocked()

    monkeypatch.setattr(backend, "block_forever", stop)
    caplog.set_level(logging.ERROR)

    with pytest.raises(_Blocked):
        create_app({"TESTING": True, "STORAGE_ROOT": settings.STORAGE_ROOT})

    assert "高于当前程序需要" in caplog.text
    assert _db_version(settings.database_path) == "99"
