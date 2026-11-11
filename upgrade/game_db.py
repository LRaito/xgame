"""game.db 结构迁移运行器（由 make upgrade 触发）。

只按 `meta.ranking_schema_version` 逐版本升级结构与映射；不读 CSV、不改榜单数据。
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.games.search_index import (
    RANKING_SCHEMA_VERSION,
    SCHEMA_VERSION,
    ensure_empty_game_db,
)
from upgrade.game_versions import MIGRATIONS


class GameDbUpgradeError(RuntimeError):
    pass


@dataclass(frozen=True)
class GameDbUpgradeResult:
    status: str  # created / up-to-date / upgraded
    from_version: int
    to_version: int


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else row[0]


def run_game_upgrade(db_path: Path) -> GameDbUpgradeResult:
    db_path = Path(db_path)
    target = int(RANKING_SCHEMA_VERSION)
    # 文件不存在或没有任何表：建一份最新的空结构。已有表的库不动——
    # 结构只由这里迁移，数据只由 make index 写入。
    try:
        if ensure_empty_game_db(db_path):
            return GameDbUpgradeResult("created", 0, target)
    except (OSError, sqlite3.Error) as exc:
        raise GameDbUpgradeError(f"创建空 game.db 结构失败：{exc}") from exc

    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        if not _table_exists(conn, "meta"):
            raise GameDbUpgradeError(
                f"game.db 缺少 meta 表：{db_path}。请停止服务、删除该文件后重新启动"
                "（会建空结构），再执行 make index。"
            )
        search_version = _meta(conn, "schema_version")
        if search_version != SCHEMA_VERSION:
            raise GameDbUpgradeError(
                f"game.db 游戏名录结构版本为 {search_version!r}，当前程序需要 "
                f"{SCHEMA_VERSION}。游戏名录结构不能原地升级；请停止服务、删除 "
                f"{db_path} 后重新启动（会建空结构），再执行 make index。"
            )
        raw_version = _meta(conn, "ranking_schema_version")
        if raw_version is None:
            raise GameDbUpgradeError(
                f"game.db 缺少 ranking_schema_version：{db_path}。"
                "请停止服务、删除该文件后重新启动（会建空结构），再执行 make index。"
            )
        try:
            current = int(raw_version)
        except (TypeError, ValueError) as exc:
            raise GameDbUpgradeError(
                f"game.db 的 ranking_schema_version 不是整数：{raw_version!r}"
            ) from exc
        if current > target:
            raise GameDbUpgradeError(
                f"game.db 榜单结构版本 {current} 高于当前程序支持的 {target}，"
                "请使用匹配的程序版本。"
            )

        needs_repair = current == target and (
            not _table_exists(conn, "ranking_cartridges")
            or "in_library"
            not in {
                row[1] for row in conn.execute("PRAGMA table_info(ranking)").fetchall()
            }
        )
        if current == target and not needs_repair:
            return GameDbUpgradeResult("up-to-date", current, target)

        versions = [target] if needs_repair else list(range(current + 1, target + 1))
        missing = [version for version in versions if version not in MIGRATIONS]
        if missing:
            raise GameDbUpgradeError(
                f"缺少 game.db 升级模块：{missing}，不能跳版本升级。"
            )
        for version in versions:
            migration = MIGRATIONS[version]
            conn.execute("BEGIN IMMEDIATE")
            try:
                migration(conn)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('ranking_schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(version),),
                )
                conn.execute("COMMIT")
            except BaseException as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                if isinstance(exc, Exception):
                    raise GameDbUpgradeError(
                        f"game.db 升级到榜单结构版本 {version} 失败，已回滚：{exc}"
                    ) from exc
                raise

        return GameDbUpgradeResult("upgraded", current, target)
    finally:
        conn.close()
