"""SQLite 月度备份的测试。库固定落在根目录下的 db/app.db，备份也在同一个 db/ 里。"""

import sqlite3
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from backend import create_app
from backend.auth.service import AuthService
from backend.backup import backup_database, monthly_backup_path
from backend.config import Settings

MOMENT = datetime(2026, 10, 2, 12, 0, 0)


def _settings(root: Path) -> Settings:
    """根目录是 STORAGE_ROOT，库固定落在它下面的 db/app.db。"""
    return Settings(TESTING=True, STORAGE_ROOT=str(root))


def _db_path(root: Path) -> Path:
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


def test_monthly_backup_path_keeps_suffix(tmp_path):
    assert monthly_backup_path(tmp_path / "db" / "app.db", MOMENT) == (
        tmp_path / "db" / "2026-10.db"
    )


def test_backup_creates_monthly_file_next_to_db(tmp_path):
    _make_db(tmp_path)

    target = backup_database(_settings(tmp_path), now=MOMENT)
    assert target == tmp_path / "db" / "2026-10.db"
    assert target.is_file()

    # 备份出来的确实是同一个库：能开、表与内容都在
    with sqlite3.connect(target) as conn:
        assert conn.execute("select v from t").fetchall() == [("hello",)]


def test_backup_skips_when_month_file_exists(tmp_path):
    _make_db(tmp_path)
    existing = tmp_path / "db" / "2026-10.db"
    existing.write_bytes(b"already-there")

    assert backup_database(_settings(tmp_path), now=MOMENT) is None
    assert existing.read_bytes() == b"already-there"  # 不覆盖当月已有的那份


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


def test_backup_skips_missing_file(tmp_path):
    assert backup_database(_settings(tmp_path), now=MOMENT) is None
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_backup_failure_does_not_leave_stale_file(tmp_path, monkeypatch):
    """备份中途失败：不留 .tmp，也不留一个半截的同名文件挡着后面几个月的备份。"""
    db_path = _make_db(tmp_path)

    def boom(source, dest):
        Path(dest).write_bytes(b"half-written")
        raise RuntimeError("磁盘满了")

    monkeypatch.setattr("backend.backup._copy_database", boom)
    assert backup_database(_settings(tmp_path), now=MOMENT) is None
    assert [p.name for p in db_path.parent.iterdir()] == ["app.db"]


def test_app_startup_writes_monthly_backup(tmp_path):
    """服务启动就检查一次，备份落在根目录的 db/ 下。"""
    storage = tmp_path / "storage"
    app = create_app(
        {
            "TESTING": True,
            "STORAGE_ROOT": str(storage),
        }
    )

    db_path = app.state.settings.database_path
    target = monthly_backup_path(db_path, datetime.now())
    assert target.is_file()
    assert target.parent == storage / "db"

    with Session(app.state.engine) as session:
        assert AuthService(session).create_user("alice", "secret123")

    # 再次启动（同一个月）不覆盖已存在的那份
    before = target.read_bytes()
    create_app(
        {
            "TESTING": True,
            "STORAGE_ROOT": str(storage),
        }
    )
    assert target.read_bytes() == before

    # 备份发生在建号之前，所以那份快照里还没有用户
    with sqlite3.connect(target) as conn:
        assert conn.execute("select count(*) from users").fetchone() == (0,)
