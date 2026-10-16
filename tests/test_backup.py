"""SQLite 备份的测试。

库落在**运行时根**的 `db/app.db` 里（不配运行时根时就是数据根，即默认行为），
备份落在**数据根**的 `db/<YYYY-MM>.db` 里，每次备份整份重写。
"""

import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from backend import create_app
from backend.auth.service import AuthService
from backend.backup import (
    backup_database,
    backup_loop,
    monthly_backup_path,
    start_backup_loop,
)
from backend.config import Settings

MOMENT = datetime(2026, 10, 2, 12, 0, 0)


def _settings(root: Path, runtime_root: Path | None = None) -> Settings:
    """根目录是 STORAGE_ROOT；不传 runtime_root 时库落在它下面的 db/app.db。"""
    return Settings(
        TESTING=True,
        STORAGE_ROOT=str(root),
        RUNTIME_ROOT=str(runtime_root) if runtime_root is not None else None,
    )


def _db_path(root: Path) -> Path:
    """没配运行时根时库的位置。"""
    return root / "db" / "app.db"


def _make_db(root: Path) -> Path:
    db_path = _db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table t (v text)")
        conn.execute("insert into t values ('hello')")
    return db_path


def test_database_path_is_fixed_under_root(tmp_path):
    settings = Settings(TESTING=True, STORAGE_ROOT=str(tmp_path))
    assert settings.database_path == tmp_path / "db" / "app.db"
    assert settings.database_url == f"sqlite:///{tmp_path / 'db' / 'app.db'}"


def test_database_path_follows_runtime_root(tmp_path):
    """配了运行时根就只换根，db/app.db 这段相对路径不变。"""
    runtime = tmp_path / "runtime"
    settings = _settings(tmp_path / "storage", runtime)

    assert settings.runtime_root == runtime
    assert settings.database_path == runtime / "db" / "app.db"
    # 备份目录与检索索引仍在数据根里
    assert settings.backup_dir == tmp_path / "storage" / "db"
    assert settings.game_index_path == tmp_path / "storage" / "db" / "game.db"


def test_database_path_falls_back_when_runtime_root_empty(tmp_path):
    settings = _settings(tmp_path, "")
    assert settings.runtime_root == tmp_path
    assert settings.database_path == tmp_path / "db" / "app.db"


def test_monthly_backup_path_is_named_by_month(tmp_path):
    assert monthly_backup_path(tmp_path / "db", MOMENT) == tmp_path / "db" / "2026-10.db"


def test_backup_writes_monthly_file_into_backup_dir(tmp_path):
    _make_db(tmp_path)

    target = backup_database(_settings(tmp_path), now=MOMENT)
    assert target == tmp_path / "db" / "2026-10.db"
    assert target.is_file()

    # 备份出来的确实是同一个库：能开、表与内容都在
    with sqlite3.connect(target) as conn:
        assert conn.execute("select v from t").fetchall() == [("hello",)]


def test_backup_overwrites_existing_month_file(tmp_path):
    """当月那份每次都重写：快照最多落后一个备份间隔，而不是一整个月。"""
    _make_db(tmp_path)
    existing = tmp_path / "db" / "2026-10.db"
    existing.write_bytes(b"stale")

    assert backup_database(_settings(tmp_path), now=MOMENT) == existing
    with sqlite3.connect(existing) as conn:
        assert conn.execute("select v from t").fetchall() == [("hello",)]


def test_backup_creates_backup_dir_if_missing(tmp_path):
    """备份目录在另一个根下（数据根/db 可能还不存在），备份自己建出来。"""
    runtime = tmp_path / "runtime"
    db_path = runtime / "db" / "app.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table t (v text)")

    target = backup_database(_settings(tmp_path / "storage", runtime), now=MOMENT)
    assert target == tmp_path / "storage" / "db" / "2026-10.db"
    assert target.is_file()


def test_backup_new_month_creates_second_file(tmp_path):
    _make_db(tmp_path)

    assert backup_database(_settings(tmp_path), now=MOMENT) == tmp_path / "db" / "2026-10.db"
    november = backup_database(_settings(tmp_path), now=datetime(2026, 11, 1, 0, 5, 0))
    assert november == tmp_path / "db" / "2026-11.db"
    assert sorted(p.name for p in (tmp_path / "db").iterdir()) == [
        "2026-10.db",
        "2026-11.db",
        "app.db",
    ]


def test_backup_returns_none_when_db_missing(tmp_path):
    assert backup_database(_settings(tmp_path), now=MOMENT) is None
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_backup_failure_does_not_leave_stale_file(tmp_path, monkeypatch):
    """备份中途失败：不留 .tmp，也不留一个半截的同名文件挡着下一次备份。"""
    db_path = _make_db(tmp_path)

    def boom(source, dest):
        Path(dest).write_bytes(b"half-written")
        raise RuntimeError("磁盘满了")

    monkeypatch.setattr("backend.backup._copy_database", boom)
    assert backup_database(_settings(tmp_path), now=MOMENT) is None
    assert [p.name for p in db_path.parent.iterdir()] == ["app.db"]


def test_backup_loop_keeps_running_until_stopped(tmp_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr("backend.backup.backup_database", lambda settings, **kw: calls.append(1))

    stop = threading.Event()
    thread = threading.Thread(
        target=backup_loop,
        args=(_settings(tmp_path),),
        kwargs={"interval": 0.01, "stop_event": stop},
        daemon=True,
    )
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while len(calls) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        stop.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(calls) >= 3


def test_start_backup_loop_skipped_in_testing(tmp_path):
    assert start_backup_loop(_settings(tmp_path)) is None


def test_start_backup_loop_runs_backups(tmp_path):
    storage = tmp_path / "storage"
    settings = Settings(TESTING=False, STORAGE_ROOT=str(storage))
    _make_db(storage)

    stop = threading.Event()
    thread = start_backup_loop(settings, interval=0.01, stop_event=stop)
    try:
        assert thread is not None and thread.daemon
        target = monthly_backup_path(settings.backup_dir, datetime.now())
        deadline = time.monotonic() + 5
        while not target.is_file() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert target.is_file()
    finally:
        stop.set()
        thread.join(timeout=5)


def test_app_startup_backs_up_into_storage_root(tmp_path):
    """服务启动就备一次，且备份落在数据根的 db/ 下——即使库被挪到了别的运行时根。"""
    storage = tmp_path / "storage"
    runtime = tmp_path / "runtime"
    app = create_app(
        {
            "TESTING": True,
            "STORAGE_ROOT": str(storage),
            "RUNTIME_ROOT": str(runtime),
        }
    )

    assert app.state.settings.database_path == runtime / "db" / "app.db"
    target = monthly_backup_path(app.state.settings.backup_dir, datetime.now())
    assert target.is_file()
    assert target.parent == storage / "db"

    with Session(app.state.engine) as session:
        assert AuthService(session).create_user("alice", "secret123")

    # 备份发生在建号之前，所以那份快照里还没有用户
    with sqlite3.connect(target) as conn:
        assert conn.execute("select count(*) from users").fetchone() == (0,)

    # 再备一次就覆盖了：这次的快照里有刚建的号（每月仍是这一个文件）
    assert backup_database(app.state.settings) == target
    with sqlite3.connect(target) as conn:
        assert conn.execute("select count(*) from users").fetchone() == (1,)
    assert sorted(p.name for p in (storage / "db").iterdir()) == [target.name]
    assert sorted(p.name for p in (runtime / "db").iterdir()) == ["app.db"]
