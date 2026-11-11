"""game.db 榜单结构 v6 → v7。

只做结构与映射迁移：不读 CSV、不改 ranking 行、不改榜单指纹。
"""

import json
import sqlite3

VERSION = 7
DESCRIPTION = "ranking 增加 in_library 标记与卡带 ID 映射表"


class GameDbMigrationError(RuntimeError):
    pass


_RANKING_DDL = """
CREATE TABLE IF NOT EXISTS ranking(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,
    console       TEXT NOT NULL,
    score         REAL NOT NULL,
    zh            TEXT NOT NULL,
    en            TEXT NOT NULL,
    cartridge_ids TEXT NOT NULL,
    in_library    INTEGER NOT NULL DEFAULT 0
)
"""

_MAPPING_DDL = """
CREATE TABLE IF NOT EXISTS ranking_cartridges(
    cartridge_id TEXT PRIMARY KEY,
    ranking_id   INTEGER NOT NULL REFERENCES ranking(id)
)
"""

_INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_ranking_platform_en ON ranking(platform, en)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_score ON ranking(score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_platform_score ON ranking(platform, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_in_library_score ON ranking(in_library, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_platform_in_library_score "
    "ON ranking(platform, in_library, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ranking_cartridges_ranking "
    "ON ranking_cartridges(ranking_id)",
)


def _normalize(raw: str) -> str:
    return (raw or "").strip().upper()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def migrate(conn: sqlite3.Connection) -> None:
    """在已有事务内执行；调用方负责 commit/rollback。"""
    conn.execute(_RANKING_DDL)
    if "in_library" not in _column_names(conn, "ranking"):
        conn.execute(
            "ALTER TABLE ranking ADD COLUMN in_library INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute(_MAPPING_DDL)
    for statement in _INDEX_DDL:
        conn.execute(statement)

    # 从现有 ranking.cartridge_ids 重建映射；不改变 ranking 行本身。
    conn.execute("DELETE FROM ranking_cartridges")
    mapping: dict[str, int] = {}
    conflicts: list[str] = []
    for ranking_id, platform, zh, en, ids_text in conn.execute(
        "SELECT id, platform, zh, en, cartridge_ids FROM ranking ORDER BY id"
    ).fetchall():
        try:
            raw_ids = json.loads(ids_text)
        except (TypeError, ValueError) as exc:
            raise GameDbMigrationError(
                f"ranking.id={ranking_id} 的 cartridge_ids 不是合法 JSON：{ids_text!r}"
            ) from exc
        if not isinstance(raw_ids, list):
            raise GameDbMigrationError(
                f"ranking.id={ranking_id} 的 cartridge_ids 不是数组：{ids_text!r}"
            )
        seen: set[str] = set()
        for raw in raw_ids:
            normalized = _normalize(str(raw))
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            previous = mapping.get(normalized)
            if previous is not None and previous != ranking_id:
                conflicts.append(
                    f"{normalized}（ranking.id={previous} ↔ ranking.id={ranking_id}，"
                    f"{platform} / {zh or en or '未命名'}）"
                )
                continue
            mapping[normalized] = ranking_id

    if conflicts:
        raise GameDbMigrationError(
            "榜单中存在同一卡带 ID 映射到多行，无法建立唯一映射：\n  "
            + "\n  ".join(conflicts)
            + "\n请先修正榜单 CSV，再执行 make index 构建游戏名录与游戏榜单。"
        )

    conn.executemany(
        "INSERT INTO ranking_cartridges(cartridge_id, ranking_id) VALUES(?, ?)",
        list(mapping.items()),
    )
