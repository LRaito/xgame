"""逐版本执行 app.db 结构升级。

事务边界在**运行器**：每个版本一个 ``BEGIN IMMEDIATE``，迁移 SQL 与
``system_config.db_version`` 的更新在同一事务里提交。版本模块只写 SQL，
不得自行 commit / rollback。
"""

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.system_config import DB_VERSION_KEY, LATEST_DB_VERSION
from upgrade.versions import MIGRATIONS

# 升级前备份失败、没有版本模块、版本非法等可预期的失败
class UpgradeError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpgradeResult:
    # not-initialized = 还没有库/业务表；up-to-date = 已是最新；upgraded = 本次升级过
    status: str
    from_version: int
    to_version: int
    applied: tuple[int, ...] = ()
    backup_path: Path | None = None


def _connect(db_path: Path) -> sqlite3.Connection:
    # isolation_level=None：交给本模块显式 BEGIN/COMMIT，避免 sqlite3 隐式事务
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def read_db_version(conn: sqlite3.Connection) -> int:
    """读当前结构版本；表或键还不存在时视为 0（无版本号时代）。"""
    if "system_config" not in _table_names(conn):
        return 0
    row = conn.execute(
        'SELECT value FROM system_config WHERE "key" = ?', (DB_VERSION_KEY,)
    ).fetchone()
    if row is None:
        return 0
    try:
        version = int(row[0])
    except (TypeError, ValueError) as exc:
        raise UpgradeError(
            f'system_config 的 "{DB_VERSION_KEY}" 不是合法整数：{row[0]!r}'
        ) from exc
    if version < 0:
        raise UpgradeError(f"数据库结构版本不能为负数：{version}")
    return version


def _backup_database(
    db_path: Path, conn: sqlite3.Connection, current: int
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = db_path.with_name(f"{db_path.name}.bak-v{current}-{stamp}")
    destination = sqlite3.connect(str(target))
    try:
        conn.backup(destination)
    except BaseException:
        destination.close()
        target.unlink(missing_ok=True)
        raise
    destination.close()
    return target


def run_upgrade(
    db_path: Path,
    *,
    latest: int = LATEST_DB_VERSION,
    migrations: Mapping[int, Callable[[sqlite3.Connection], None]] = MIGRATIONS,
    backup: bool = True,
) -> UpgradeResult:
    """把 ``db_path`` 从当前版本逐级升到 ``latest``。

    ``latest`` / ``migrations`` 只为测试注入；生产调用用默认值。
    """
    db_path = Path(db_path)
    if not db_path.is_file():
        return UpgradeResult("not-initialized", 0, latest)

    conn = _connect(db_path)
    try:
        if not _table_names(conn) - {"system_config"}:
            # 空库或只有 system_config：首次启动会按最新结构建库
            return UpgradeResult("not-initialized", 0, latest)

        current = read_db_version(conn)
        if current > latest:
            raise UpgradeError(
                f"数据库结构版本 {current} 高于当前程序支持的 {latest}，"
                "请使用匹配的程序版本，不能降级升级。"
            )
        if current == latest:
            return UpgradeResult("up-to-date", current, latest)

        missing = [
            version
            for version in range(current + 1, latest + 1)
            if version not in migrations
        ]
        if missing:
            raise UpgradeError(f"缺少升级版本模块：{missing}，不能跳版本升级。")

        backup_path = None
        if backup:
            try:
                backup_path = _backup_database(db_path, conn, current)
            except (OSError, sqlite3.Error) as exc:
                raise UpgradeError(f"升级前备份失败，未执行任何升级：{exc}") from exc

        applied: list[int] = []
        for version in range(current + 1, latest + 1):
            conn.execute("BEGIN IMMEDIATE")
            try:
                # 并发升级兜底：另一个进程可能已经提交了同一版本
                if read_db_version(conn) >= version:
                    conn.execute("COMMIT")
                    continue
                migrations[version](conn)
                conn.execute(
                    'INSERT INTO system_config ("key", value) VALUES (?, ?) '
                    'ON CONFLICT("key") DO UPDATE SET value = excluded.value',
                    (DB_VERSION_KEY, str(version)),
                )
                conn.execute("COMMIT")
            except BaseException as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                if isinstance(exc, Exception):
                    raise UpgradeError(
                        f"升级到版本 {version} 失败，已回滚：{exc}"
                    ) from exc
                raise
            applied.append(version)

        return UpgradeResult(
            "upgraded", current, latest, tuple(applied), backup_path
        )
    finally:
        conn.close()
