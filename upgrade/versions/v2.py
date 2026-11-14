"""v2：库存表增加「是否在榜单内」标记与筛选索引。

冻结迁移：只加列/索引，不碰数据。标记值由 make index 全量对账、新增/改卡带ID/删除时
增量维护。
"""

import sqlite3

VERSION = 2
DESCRIPTION = "games 增加 in_ranking 标记与筛选索引"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
    if "in_ranking" not in columns:
        # 与 SQLModel 生成的 DDL 保持完全一致（BOOLEAN DEFAULT '0' NOT NULL）
        conn.execute(
            "ALTER TABLE games ADD COLUMN in_ranking BOOLEAN DEFAULT '0' NOT NULL"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_in_ranking ON games (in_ranking)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_in_ranking_updated "
        "ON games (in_ranking, updated_at, id)"
    )
