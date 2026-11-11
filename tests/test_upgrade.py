import ast
import sqlite3
from pathlib import Path

import pytest

from backend.config import Settings
from backend.database import ensure_data_dir, init_db, make_engine
from backend.system_config import LATEST_DB_VERSION
from upgrade.runner import UpgradeError, run_upgrade
from upgrade.versions import MIGRATIONS

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


def _legacy_db(tmp_path: Path) -> Path:
    """无版本号时代的老库：缺列、缺表、缺索引、有废弃表。"""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER NOT NULL,
            username VARCHAR(32) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id)
        );
        INSERT INTO users VALUES (1, 'alice', 'hash', '2026-01-01 00:00:00');

        CREATE TABLE games (
            id INTEGER PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            cartridge_id VARCHAR(64) NOT NULL,
            description VARCHAR(200) NOT NULL,
            game_type VARCHAR(50) NOT NULL,
            size INTEGER NOT NULL,
            crc32 VARCHAR(8) NOT NULL,
            game_path VARCHAR(500) NOT NULL,
            cover_path VARCHAR(500),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        INSERT INTO games VALUES (
            7, '老游戏', 'OLD1', '', 'nes', 0, '', '', NULL,
            '2026-01-01 00:00:00', '2026-01-01 00:00:00'
        );

        CREATE TABLE game_cloud_snapshots (
            id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            remark VARCHAR(100) NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id)
        );
        INSERT INTO game_cloud_snapshots VALUES (
            3, 1, 7, '旧快照', '2026-01-01 00:00:00'
        );

        CREATE TABLE game_h5_files (
            id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    return path


def _schema(path: Path) -> dict[str, tuple]:
    conn = sqlite3.connect(path)
    try:
        tables = sorted(
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        schema = {}
        for table in tables:
            columns = tuple(
                (row[1], row[2], row[3], row[4])
                for row in conn.execute(f'PRAGMA table_info("{table}")')
            )
            indexes = tuple(
                sorted(
                    (row[1], row[2])
                    for row in conn.execute(f'PRAGMA index_list("{table}")')
                )
            )
            schema[table] = (columns, indexes)
        return schema
    finally:
        conn.close()


def _fresh_database(tmp_path: Path) -> Path:
    settings = Settings(TESTING=True, STORAGE_ROOT=str(tmp_path / "fresh"))
    ensure_data_dir(settings)
    init_db(make_engine(settings))
    return settings.database_path


def _read_version(path: Path) -> str | None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT value FROM system_config WHERE \"key\" = 'db_version'"
        ).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def test_v1_upgrades_legacy_database(tmp_path):
    path = _legacy_db(tmp_path)

    result = run_upgrade(path, backup=False)

    assert result.status == "upgraded"
    assert result.from_version == 0
    assert result.to_version == LATEST_DB_VERSION
    assert result.applied == (1,)
    assert _read_version(path) == str(LATEST_DB_VERSION)

    conn = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == _ALL_TABLES

        games_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'games'"
        ).fetchone()[0]
        assert "AUTOINCREMENT" in games_sql.upper()

        game_columns = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
        assert {"cover_type", "guide_kind"} <= game_columns

        snapshot_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(game_cloud_snapshots)")
        }
        assert {"parent_id", "sort_order"} <= snapshot_columns

        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name = 'game_h5_files'"
        ).fetchone()[0] == 0

        # 旧数据保留
        assert conn.execute("SELECT name FROM games WHERE id = 7").fetchone()[0] == "老游戏"
        assert conn.execute(
            "SELECT remark FROM game_cloud_snapshots WHERE id = 3"
        ).fetchone()[0] == "旧快照"

        # 新 id 接续；删除最大 id 后不复用（AUTOINCREMENT）
        conn.execute(
            "INSERT INTO games (name, cartridge_id, description, game_type, size, "
            "crc32, game_path, created_at, updated_at) VALUES "
            "('新游戏', 'NEW1', '', 'nes', 0, '', '', "
            "'2026-01-02 00:00:00', '2026-01-02 00:00:00')"
        )
        assert conn.execute(
            "SELECT id FROM games WHERE cartridge_id = 'NEW1'"
        ).fetchone()[0] == 8
        conn.execute("DELETE FROM games WHERE id = 8")
        conn.execute(
            "INSERT INTO games (name, cartridge_id, description, game_type, size, "
            "crc32, game_path, created_at, updated_at) VALUES "
            "('再新游戏', 'NEW2', '', 'nes', 0, '', '', "
            "'2026-01-02 00:00:00', '2026-01-02 00:00:00')"
        )
        assert conn.execute(
            "SELECT id FROM games WHERE cartridge_id = 'NEW2'"
        ).fetchone()[0] == 9
        conn.commit()
    finally:
        conn.close()


def test_v1_schema_matches_fresh_database(tmp_path):
    legacy = _legacy_db(tmp_path)
    run_upgrade(legacy, backup=False)

    assert _schema(legacy) == _schema(_fresh_database(tmp_path))


def test_upgrade_is_up_to_date_on_second_run(tmp_path):
    path = _legacy_db(tmp_path)
    run_upgrade(path, backup=False)

    result = run_upgrade(path, backup=False)

    assert result.status == "up-to-date"
    assert result.applied == ()
    assert _read_version(path) == str(LATEST_DB_VERSION)


def test_upgrade_without_database_does_not_create_file(tmp_path):
    path = tmp_path / "missing.db"

    result = run_upgrade(path, backup=False)

    assert result.status == "not-initialized"
    assert not path.exists()


def test_upgrade_with_empty_database_is_not_initialized(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()

    result = run_upgrade(path, backup=False)

    assert result.status == "not-initialized"


def test_upgrade_rejects_newer_database(tmp_path):
    path = tmp_path / "newer.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY);
        CREATE TABLE system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "key" VARCHAR(255) NOT NULL,
            value VARCHAR(1024) NOT NULL
        );
        INSERT INTO system_config ("key", value) VALUES ('db_version', '99');
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(UpgradeError, match="高于当前程序支持"):
        run_upgrade(path, backup=False)

    assert _read_version(path) == "99"


def test_upgrade_refuses_to_skip_versions(tmp_path):
    path = tmp_path / "skip.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY);
        CREATE TABLE system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "key" VARCHAR(255) NOT NULL,
            value VARCHAR(1024) NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(UpgradeError, match="缺少升级版本"):
        run_upgrade(path, latest=2, migrations={1: lambda _conn: None}, backup=False)


def test_failed_version_keeps_previous_committed_version(tmp_path):
    path = tmp_path / "fail.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY);
        CREATE TABLE system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "key" VARCHAR(255) NOT NULL,
            value VARCHAR(1024) NOT NULL
        );
        CREATE UNIQUE INDEX ix_system_config_key ON system_config ("key");
        """
    )
    conn.commit()
    conn.close()

    def v1(conn):
        conn.execute("CREATE TABLE marker_one (id INTEGER)")

    def v2(conn):
        conn.execute("CREATE TABLE marker_two (id INTEGER)")
        raise RuntimeError("故意失败")

    with pytest.raises(UpgradeError, match="升级到版本 2 失败"):
        run_upgrade(
            path,
            latest=2,
            migrations={1: v1, 2: v2},
            backup=False,
        )

    assert _read_version(path) == "1"
    conn = sqlite3.connect(path)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        conn.close()
    assert "marker_one" in names
    assert "marker_two" not in names


def test_upgrade_creates_backup_before_migrating(tmp_path):
    path = _legacy_db(tmp_path)

    result = run_upgrade(path, backup=True)

    assert result.backup_path is not None
    assert result.backup_path.is_file()
    backup_schema = _schema(result.backup_path)
    assert "system_config" not in backup_schema
    assert "game_h5_files" in backup_schema
    assert _read_version(path) == str(LATEST_DB_VERSION)


def test_cli_reports_up_to_date_message(tmp_path, capsys):
    from upgrade.cli import main

    path = _legacy_db(tmp_path)
    run_upgrade(path, backup=False)

    assert main(["--db", str(path), "--no-backup"]) == 0
    assert "当前已是最新版本，无需升级" in capsys.readouterr().out


def test_version_registry_matches_code_version():
    assert sorted(MIGRATIONS) == list(range(1, LATEST_DB_VERSION + 1))


def test_version_modules_are_isolated_from_runtime_code():
    versions_dir = Path(__file__).resolve().parent.parent / "upgrade" / "versions"
    forbidden = {"backend", "sqlmodel", "sqlalchemy"}
    for path in sorted(versions_dir.glob("v*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, path
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in forbidden, path
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
            ):
                # 事务由运行器负责，版本模块不得自己提交/回滚/执行脚本
                assert node.func.attr not in {
                    "commit",
                    "rollback",
                    "executescript",
                }, path
