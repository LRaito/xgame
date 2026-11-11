"""跨 app.db / game.db 同步「是否在榜单内 / 是否在库存内」标记。

- `read_ranking_ids()`：新增/改卡带 ID 时用映射表快速判断是否命中榜单。
- `refresh_all_flags()`：`make index` 成功后全量对账两个库的标记。
- `refresh_ranking_flags()`：新增/改卡带 ID/删除游戏后，只重算受影响的榜单行。

game.db 是派生索引库；这些函数只写标记，不重建榜单数据。
"""

import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.games.cartridge import normalize_cartridge_id

logger = logging.getLogger(__name__)


class FlagSyncError(RuntimeError):
    """标记同步的前置条件不满足（缺表、缺列、缺版本信息）。"""


@dataclass(frozen=True)
class FlagSyncStats:
    games_changed: int = 0
    rankings_changed: int = 0


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def read_ranking_ids(
    game_index_path: Path, raw_ids: Sequence[str]
) -> dict[str, int] | None:
    """返回 {归一卡带ID: ranking.id}；映射不可用时返回 None。

    None = game.db 缺失、版本过旧或缺映射表；调用方不要据此把已有标记清掉。
    """
    wanted = {normalize_cartridge_id(raw) for raw in raw_ids}
    wanted.discard("")
    if not wanted or not Path(game_index_path).is_file():
        return {}

    try:
        conn = sqlite3.connect(
            f"{Path(game_index_path).as_uri()}?mode=ro", uri=True
        )
    except sqlite3.Error:
        return None
    try:
        conn.execute("PRAGMA query_only = 1")
        if not _table_exists(conn, "ranking_cartridges"):
            logger.warning("game.db 缺少 ranking_cartridges，请执行 make index：%s", game_index_path)
            return None
        placeholders = ", ".join("?" for _ in wanted)
        rows = conn.execute(
            "SELECT cartridge_id, ranking_id FROM ranking_cartridges "
            f"WHERE cartridge_id IN ({placeholders})",
            list(wanted),
        ).fetchall()
        return {row[0]: int(row[1]) for row in rows}
    except sqlite3.Error as exc:
        logger.warning("读取榜单卡带映射失败：%s", exc)
        return None
    finally:
        conn.close()


def _require_mapping(conn: sqlite3.Connection, game_index_path: Path) -> None:
    if not _table_exists(conn, "ranking_cartridges"):
        raise FlagSyncError(
            f"game.db 缺少 ranking_cartridges 映射表：{game_index_path}。"
            "请先执行 make upgrade（结构迁移），再执行 make index（构建游戏名录与游戏榜单）。"
        )
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'ranking_fingerprint'"
    ).fetchone()
    if not row or not row[0]:
        raise FlagSyncError(
            f"game.db 没有榜单指纹：{game_index_path}。请执行 make index 构建游戏名录与游戏榜单。"
        )


def _has_games_flag(conn: sqlite3.Connection) -> bool:
    return "in_ranking" in {
        row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()
    }


def refresh_all_flags(
    database_path: Path,
    game_index_path: Path,
    *,
    strict: bool = False,
) -> FlagSyncStats | None:
    """全量重算两个标记。`strict=True` 时前置条件不满足直接抛错。"""
    game_index_path = Path(game_index_path)
    database_path = Path(database_path)

    if not game_index_path.is_file():
        error = FlagSyncError(
            f"game.db 不存在：{game_index_path}。"
            "请先启动一次服务（或执行 make upgrade）创建空结构，再执行 make index。"
        )
        if strict:
            raise error
        logger.warning("%s", error)
        return None

    stats = FlagSyncStats()
    game_conn = None
    try:
        game_conn = _connect(game_index_path)
        _require_mapping(game_conn, game_index_path)

        if database_path.is_file():
            app_conn = _connect(database_path)
            try:
                if not _has_games_flag(app_conn):
                    raise FlagSyncError(
                        "app.db 的 games 表缺少 in_ranking 列。请先执行 make upgrade 升级数据库。"
                    )
            finally:
                app_conn.close()

        if database_path.is_file():
            game_conn.execute("ATTACH DATABASE ? AS app", (str(database_path),))
        game_conn.execute("BEGIN IMMEDIATE")
        try:
            if database_path.is_file():
                cursor = game_conn.execute(
                    "UPDATE ranking SET in_library = EXISTS ("
                    "  SELECT 1 FROM ranking_cartridges rc"
                    "  JOIN app.games g ON g.cartridge_id = rc.cartridge_id"
                    "  WHERE rc.ranking_id = ranking.id)"
                )
            else:
                cursor = game_conn.execute(
                    "UPDATE ranking SET in_library = 0 WHERE in_library <> 0"
                )
            stats = FlagSyncStats(rankings_changed=cursor.rowcount)
            game_conn.execute("COMMIT")
        except BaseException:
            game_conn.execute("ROLLBACK")
            raise
    except FlagSyncError as exc:
        if strict:
            raise
        logger.warning("%s", exc)
        return None
    except sqlite3.Error as exc:
        error = FlagSyncError(f"同步榜单库存标记失败：{exc}")
        if strict:
            raise error from exc
        logger.warning("%s", error)
        return None
    finally:
        if game_conn is not None:
            game_conn.close()

    if not database_path.is_file():
        return stats

    app_conn = None
    try:
        app_conn = _connect(database_path)
        if not _has_games_flag(app_conn):
            raise FlagSyncError(
                "app.db 的 games 表缺少 in_ranking 列。请先执行 make upgrade 升级数据库。"
            )
        app_conn.execute("ATTACH DATABASE ? AS idx", (str(game_index_path),))
        app_conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = app_conn.execute(
                "UPDATE games SET in_ranking = EXISTS ("
                "  SELECT 1 FROM idx.ranking_cartridges rc"
                "  WHERE rc.cartridge_id = games.cartridge_id)"
            )
            stats = FlagSyncStats(
                games_changed=cursor.rowcount,
                rankings_changed=stats.rankings_changed,
            )
            app_conn.execute("COMMIT")
        except BaseException:
            app_conn.execute("ROLLBACK")
            raise
    except FlagSyncError as exc:
        if strict:
            raise
        logger.warning("%s", exc)
        return None
    except sqlite3.Error as exc:
        error = FlagSyncError(f"同步游戏榜单标记失败：{exc}")
        if strict:
            raise error from exc
        logger.warning("%s", error)
        return None
    finally:
        if app_conn is not None:
            app_conn.close()

    return stats


def refresh_ranking_flags(
    database_path: Path,
    game_index_path: Path,
    raw_ids: Sequence[str],
) -> int:
    """只重算这些卡带 ID 命中的榜单行；返回更新的行数。

    一行榜单可能有两个卡带 ID，所以按 `ranking.id` 重算整行，而不是简单把标记置 0。
    """
    wanted = {normalize_cartridge_id(raw) for raw in raw_ids}
    wanted.discard("")
    game_index_path = Path(game_index_path)
    if not wanted or not game_index_path.is_file():
        return 0

    conn = None
    try:
        conn = _connect(game_index_path)
        if not _table_exists(conn, "ranking_cartridges"):
            logger.warning(
                "game.db 缺少 ranking_cartridges，跳过增量标记：%s", game_index_path
            )
            return 0
        placeholders = ", ".join("?" for _ in wanted)
        ranking_ids = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT ranking_id FROM ranking_cartridges "
                f"WHERE cartridge_id IN ({placeholders})",
                list(wanted),
            ).fetchall()
        ]
        if not ranking_ids:
            return 0

        database_path = Path(database_path)
        if database_path.is_file():
            conn.execute("ATTACH DATABASE ? AS app", (str(database_path),))
        conn.execute("BEGIN IMMEDIATE")
        try:
            ids_sql = ", ".join("?" for _ in ranking_ids)
            if database_path.is_file():
                cursor = conn.execute(
                    "UPDATE ranking SET in_library = EXISTS ("
                    "  SELECT 1 FROM ranking_cartridges rc"
                    "  JOIN app.games g ON g.cartridge_id = rc.cartridge_id"
                    f"  WHERE rc.ranking_id = ranking.id) WHERE id IN ({ids_sql})",
                    ranking_ids,
                )
            else:
                cursor = conn.execute(
                    f"UPDATE ranking SET in_library = 0 WHERE id IN ({ids_sql})",
                    ranking_ids,
                )
            conn.execute("COMMIT")
            return cursor.rowcount
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        if conn is not None:
            conn.close()
