"""game.db 结构迁移测试。"""

import ast
import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from backend.cli import cli
from backend.config import Settings
from backend.games.search_index import (
    RANKING_SCHEMA_VERSION,
    ensure_empty_game_db,
    game_db_is_current,
)
from upgrade.game_db import GameDbUpgradeError, run_game_upgrade


def _make_v6(path: Path, rows: list[tuple[str, str, str, list[str]]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE ranking(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                console TEXT NOT NULL,
                score REAL NOT NULL,
                zh TEXT NOT NULL,
                en TEXT NOT NULL,
                cartridge_ids TEXT NOT NULL
            );
            """
        )
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES(?, ?)",
            [
                ("schema_version", "2"),
                ("ranking_schema_version", "6"),
                ("ranking_fingerprint", "fp"),
                ("ranking_rows", str(len(rows))),
            ],
        )
        conn.executemany(
            "INSERT INTO ranking(platform, console, score, zh, en, cartridge_ids) "
            "VALUES(?, ?, 8.0, ?, ?, ?)",
            [
                (platform, platform, zh, en, json.dumps(ids))
                for platform, zh, en, ids in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _ranking_rows(path: Path) -> list[tuple]:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT id, platform, score, zh, en, cartridge_ids FROM ranking ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _meta(path: Path, key: str) -> str | None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def test_v6_to_v7_migrates_structure_and_mapping(tmp_path):
    path = tmp_path / "game.db"
    _make_v6(
        path,
        [
            ("nes", "马里奥", "Mario", ["ABC-1", "abc-1"]),
            ("gba", "黄金太阳", "Golden Sun", ["GSAE"]),
            ("gba", "无编号", "No ID", []),
        ],
    )
    before = _ranking_rows(path)

    result = run_game_upgrade(path)

    assert result.status == "upgraded"
    assert result.from_version == 6
    assert result.to_version == 7
    assert _meta(path, "ranking_schema_version") == "7"
    assert _meta(path, "ranking_fingerprint") == "fp"
    assert _ranking_rows(path) == before  # 不改榜单行

    conn = sqlite3.connect(path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ranking)")}
        assert "in_library" in columns
        assert conn.execute("SELECT cartridge_id, ranking_id FROM ranking_cartridges").fetchall() == [
            ("ABC-1", 1),
            ("GSAE", 2),
        ]
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(ranking)")
        }
        assert {
            "idx_ranking_in_library_score",
            "idx_ranking_platform_in_library_score",
        } <= indexes
    finally:
        conn.close()


def test_duplicate_cartridge_rolls_back_and_keeps_version(tmp_path):
    path = tmp_path / "game.db"
    _make_v6(
        path,
        [
            ("nes", "A", "Game A", ["SAME-ID"]),
            ("gba", "B", "Game B", ["same-id"]),
        ],
    )

    with pytest.raises(GameDbUpgradeError, match="SAME-ID"):
        run_game_upgrade(path)

    assert _meta(path, "ranking_schema_version") == "6"
    conn = sqlite3.connect(path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ranking)")}
        assert "in_library" not in columns
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name = 'ranking_cartridges'"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_missing_game_db_creates_empty_structure(tmp_path):
    path = tmp_path / "game.db"
    result = run_game_upgrade(path)

    assert result.status == "created"
    assert result.from_version == 0
    assert result.to_version == int(RANKING_SCHEMA_VERSION)
    assert path.is_file()
    assert _meta(path, "schema_version") == "2"
    assert _meta(path, "ranking_schema_version") == RANKING_SCHEMA_VERSION
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT count(*) FROM game").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM ranking").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM ranking_cartridges").fetchone()[0] == 0
    finally:
        conn.close()
    assert game_db_is_current(path)


def test_empty_file_gets_empty_structure(tmp_path):
    path = tmp_path / "game.db"
    path.write_bytes(b"")

    assert ensure_empty_game_db(path)
    assert game_db_is_current(path)


def test_existing_game_db_is_not_touched_by_bootstrap(tmp_path):
    path = tmp_path / "game.db"
    _make_v6(path, [("nes", "A", "Game A", ["ID1"])])

    assert not ensure_empty_game_db(path)
    assert _meta(path, "ranking_schema_version") == "6"
    assert not game_db_is_current(path)


def test_search_schema_mismatch_requires_rebuild(tmp_path):
    path = tmp_path / "game.db"
    _make_v6(path, [("nes", "A", "Game A", ["ID1"])])
    conn = sqlite3.connect(path)
    conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    with pytest.raises(GameDbUpgradeError, match="删除"):
        run_game_upgrade(path)


def test_newer_game_db_is_rejected(tmp_path):
    path = tmp_path / "game.db"
    _make_v6(path, [("nes", "A", "Game A", ["ID1"])])
    conn = sqlite3.connect(path)
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'ranking_schema_version'")
    conn.commit()
    conn.close()

    with pytest.raises(GameDbUpgradeError, match="高于"):
        run_game_upgrade(path)


def test_v7_with_missing_mapping_is_repaired(tmp_path):
    path = tmp_path / "game.db"
    _make_v6(path, [("nes", "A", "Game A", ["ID1"])])
    assert run_game_upgrade(path).status == "upgraded"

    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE ranking_cartridges")
    conn.commit()
    conn.close()

    result = run_game_upgrade(path)
    assert result.status == "upgraded"
    assert _meta(path, "ranking_schema_version") == "7"
    conn = sqlite3.connect(path)
    try:
        assert conn.execute(
            "SELECT cartridge_id, ranking_id FROM ranking_cartridges"
        ).fetchall() == [("ID1", 1)]
    finally:
        conn.close()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        TESTING=True,
        STORAGE_ROOT=str(tmp_path / "storage"),
        RUNTIME_ROOT=str(tmp_path / "runtime"),
    )


def test_make_index_refuses_missing_game_db(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr("backend.cli.get_settings", lambda: settings)

    result = CliRunner().invoke(cli, ["index"])

    assert result.exit_code == 1
    assert "make upgrade" in result.output
    assert not settings.game_index_path.exists()


def test_make_index_refuses_old_game_db_without_touching_it(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    settings.game_index_path.parent.mkdir(parents=True)
    _make_v6(settings.game_index_path, [("nes", "A", "Game A", ["ID1"])])
    monkeypatch.setattr("backend.cli.get_settings", lambda: settings)

    result = CliRunner().invoke(cli, ["index"])

    assert result.exit_code == 1
    assert "make upgrade" in result.output
    assert _meta(settings.game_index_path, "ranking_schema_version") == "6"


def test_game_version_modules_are_isolated():
    root = Path(__file__).resolve().parent.parent / "upgrade" / "game_versions"
    forbidden = {"backend", "sqlmodel", "sqlalchemy"}
    for path in sorted(root.glob("v*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, path
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden, path
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "commit",
                    "rollback",
                    "executescript",
                }, path
