"""v1：无版本号时代 → 数据库结构版本 1。

这是**冻结快照**：下面列出的 DDL 是 v1 当时的完整结构，之后任何模型变化都只能
新增 ``v2.py``，不要回头改这个文件。否则老库升级路径会随当前代码漂移。

约束：

- 只使用标准库 ``sqlite3`` 与显式 SQL，不 import ``backend`` / SQLModel / SQLAlchemy。
- ``upgrade()`` 假定运行器已经开启写事务；禁止 commit / rollback / executescript。
"""

import sqlite3

VERSION = 1
DESCRIPTION = "建立完整表结构、补齐历史列与索引、删除 game_h5_files、games.id 改为自增"

# v1 时 games 表的全部列（顺序即建表顺序）。重建时只搬新旧表都有的列。
_GAMES_COLUMNS = (
    "id",
    "name",
    "cartridge_id",
    "cover_type",
    "description",
    "game_type",
    "size",
    "crc32",
    "game_path",
    "cover_path",
    "guide_kind",
    "created_at",
    "updated_at",
)

# 当前 12 张表的完整结构。game_h5_files 已废弃，不在其中。
_TABLE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER NOT NULL,
        username VARCHAR(32) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS login_attempts (
        username VARCHAR(32) NOT NULL,
        failed_count INTEGER NOT NULL,
        locked_until DATETIME,
        PRIMARY KEY (username)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_shortcuts (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        action_id VARCHAR(64) NOT NULL,
        binding VARCHAR(64) NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (user_id, action_id),
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(255) NOT NULL,
        cartridge_id VARCHAR(64) NOT NULL,
        cover_type VARCHAR(20),
        description VARCHAR(200) NOT NULL,
        game_type VARCHAR(50) NOT NULL,
        size INTEGER NOT NULL,
        crc32 VARCHAR(8) NOT NULL,
        game_path VARCHAR(500) NOT NULL,
        cover_path VARCHAR(500),
        guide_kind VARCHAR(10) DEFAULT '' NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_cloud_snapshots (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        parent_id INTEGER,
        sort_order FLOAT NOT NULL,
        remark VARCHAR(100) NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_cloud_snapshot_files (
        id INTEGER NOT NULL,
        snapshot_id INTEGER NOT NULL,
        sort_order INTEGER NOT NULL,
        local_key VARCHAR(500) NOT NULL,
        name VARCHAR(255) NOT NULL,
        size INTEGER NOT NULL,
        mime VARCHAR(200),
        file_path VARCHAR(500) NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(snapshot_id) REFERENCES game_cloud_snapshots (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_screenshots (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        sort_order FLOAT NOT NULL,
        description VARCHAR(15) NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        size INTEGER NOT NULL,
        mime VARCHAR(200),
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_gallery_images (
        id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        sort_order FLOAT NOT NULL,
        description VARCHAR(15) NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        size INTEGER NOT NULL,
        mime VARCHAR(200),
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_emulator_settings (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        game_type VARCHAR(50) NOT NULL,
        payload VARCHAR NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (user_id, game_type),
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_recent_plays (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        played_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (user_id, game_id),
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_user_stats (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        play_seconds INTEGER NOT NULL,
        progress VARCHAR(20) NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (user_id, game_id),
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS system_config (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        "key" VARCHAR(255) NOT NULL,
        value VARCHAR(1024) NOT NULL
    )
    """,
)

# 全部索引。放在 games 重建之后执行：重建会带走旧表上的索引。
_INDEX_DDL = (
    'CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)',
    'CREATE INDEX IF NOT EXISTS ix_user_shortcuts_user_id ON user_shortcuts (user_id)',
    'CREATE INDEX IF NOT EXISTS ix_games_game_type ON games (game_type)',
    'CREATE INDEX IF NOT EXISTS ix_games_name ON games (name)',
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_games_cartridge_id ON games (cartridge_id)',
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_games_game_type_name ON games (game_type, name)',
    (
        "CREATE INDEX IF NOT EXISTS ix_game_cloud_snapshots_game_id "
        "ON game_cloud_snapshots (game_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_cloud_snapshots_parent_id "
        "ON game_cloud_snapshots (parent_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_cloud_snapshots_user_game_order "
        "ON game_cloud_snapshots (user_id, game_id, sort_order)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_cloud_snapshots_user_id "
        "ON game_cloud_snapshots (user_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_cloud_snapshot_files_snapshot_id "
        "ON game_cloud_snapshot_files (snapshot_id)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_game_screenshots_game_id ON game_screenshots (game_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_game_screenshots_user_game_order "
        "ON game_screenshots (user_id, game_id, sort_order)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_screenshots_user_id "
        "ON game_screenshots (user_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_gallery_images_game_id "
        "ON game_gallery_images (game_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_gallery_images_game_order "
        "ON game_gallery_images (game_id, sort_order)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_game_emulator_settings_user_id "
        "ON game_emulator_settings (user_id)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_game_recent_plays_game_id ON game_recent_plays (game_id)",
    "CREATE INDEX IF NOT EXISTS ix_game_recent_plays_user_id ON game_recent_plays (user_id)",
    'CREATE INDEX IF NOT EXISTS ix_game_user_stats_game_id ON game_user_stats (game_id)',
    'CREATE INDEX IF NOT EXISTS ix_game_user_stats_user_id ON game_user_stats (user_id)',
    'CREATE UNIQUE INDEX IF NOT EXISTS ix_system_config_key ON system_config ("key")',
)

# games 重建用的建表语句（与上面的冻结 DDL 一致，只换表名）。
_GAMES_REBUILD_DDL = """
CREATE TABLE games__rebuild (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    cartridge_id VARCHAR(64) NOT NULL,
    cover_type VARCHAR(20),
    description VARCHAR(200) NOT NULL,
    game_type VARCHAR(50) NOT NULL,
    size INTEGER NOT NULL,
    crc32 VARCHAR(8) NOT NULL,
    game_path VARCHAR(500) NOT NULL,
    cover_path VARCHAR(500),
    guide_kind VARCHAR(10) DEFAULT '' NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""

# 老库用 ALTER 补的快照列是 REAL DEFAULT 0、且排在表尾；与当前模型的
# FLOAT / 无默认值 / 列顺序不同。重建一次，让升级库与新建库的 PRAGMA 完全一致。
_SNAPSHOT_COLUMNS = (
    "id",
    "user_id",
    "game_id",
    "parent_id",
    "sort_order",
    "remark",
    "created_at",
)
_SNAPSHOT_EXPECTED = (
    ("id", "INTEGER", 1, None, 1),
    ("user_id", "INTEGER", 1, None, 0),
    ("game_id", "INTEGER", 1, None, 0),
    ("parent_id", "INTEGER", 0, None, 0),
    ("sort_order", "FLOAT", 1, None, 0),
    ("remark", "VARCHAR(100)", 1, None, 0),
    ("created_at", "DATETIME", 1, None, 0),
)
_SNAPSHOT_REBUILD_DDL = """
CREATE TABLE game_cloud_snapshots__rebuild (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    parent_id INTEGER,
    sort_order FLOAT NOT NULL,
    remark VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id)
)
"""


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _add_missing_columns(
    conn: sqlite3.Connection, table: str, columns: tuple[tuple[str, str], ...]
) -> None:
    if not _table_exists(conn, table):
        return
    existing = _column_names(conn, table)
    for name, ddl in columns:
        if name not in existing:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}')


def _ensure_games_autoincrement(conn: sqlite3.Connection) -> None:
    """老库的 games.id 没有 AUTOINCREMENT 时重建；已有则跳过。"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'games'"
    ).fetchone()
    if row is None or "AUTOINCREMENT" in (row[0] or "").upper():
        return

    existing = _column_names(conn, "games")
    columns = [name for name in _GAMES_COLUMNS if name in existing]
    if not columns:
        return
    column_list = ", ".join(f'"{name}"' for name in columns)

    conn.execute("DROP TABLE IF EXISTS games__rebuild")
    conn.execute(_GAMES_REBUILD_DDL)
    conn.execute(
        f"INSERT INTO games__rebuild ({column_list}) SELECT {column_list} FROM games"
    )
    conn.execute("DROP TABLE games")
    conn.execute("ALTER TABLE games__rebuild RENAME TO games")


def _table_signature(conn: sqlite3.Connection, table: str) -> tuple:
    return tuple(
        (row[1], (row[2] or "").upper(), row[3], row[4], row[5])
        for row in conn.execute(f'PRAGMA table_info("{table}")')
    )


def _ensure_game_cloud_snapshots_schema(conn: sqlite3.Connection) -> None:
    """把 ALTER 补出来的快照表重建成与当前模型完全一致的形状。"""
    if not _table_exists(conn, "game_cloud_snapshots"):
        return
    if _table_signature(conn, "game_cloud_snapshots") == _SNAPSHOT_EXPECTED:
        return

    existing = _column_names(conn, "game_cloud_snapshots")
    columns = [name for name in _SNAPSHOT_COLUMNS if name in existing]
    column_list = ", ".join(f'"{name}"' for name in columns)

    conn.execute("DROP TABLE IF EXISTS game_cloud_snapshots__rebuild")
    conn.execute(_SNAPSHOT_REBUILD_DDL)
    conn.execute(
        "INSERT INTO game_cloud_snapshots__rebuild "
        f"({column_list}) SELECT {column_list} FROM game_cloud_snapshots"
    )
    conn.execute("DROP TABLE game_cloud_snapshots")
    conn.execute(
        "ALTER TABLE game_cloud_snapshots__rebuild RENAME TO game_cloud_snapshots"
    )


def upgrade(conn: sqlite3.Connection) -> None:
    for statement in _TABLE_DDL:
        conn.execute(statement)

    # 无版本号时代逐步加过的列
    _add_missing_columns(
        conn,
        "games",
        (
            ("cover_type", "VARCHAR(20)"),
            ("guide_kind", "VARCHAR(10) NOT NULL DEFAULT ''"),
        ),
    )
    _add_missing_columns(
        conn,
        "game_cloud_snapshots",
        (
            ("parent_id", "INTEGER"),
            ("sort_order", "REAL NOT NULL DEFAULT 0"),
        ),
    )
    _ensure_game_cloud_snapshots_schema(conn)

    # 已废弃的 H5 清单表
    conn.execute("DROP TABLE IF EXISTS game_h5_files")

    # 先重建 games，再统一建索引
    _ensure_games_autoincrement(conn)
    for statement in _INDEX_DDL:
        conn.execute(statement)
