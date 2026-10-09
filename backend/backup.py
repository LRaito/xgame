"""SQLite 库的月度备份。

服务每次启动检查一次：本地当月还没有备份文件就补一份，有就跳过。一个自然月最多一份，
文件名 `<YYYY-MM>.db`，与库同目录（即 `<根目录>/db/`）。不做还原功能——要回滚
就把备份文件改回 `app.db` 手动替换（换之前先把服务停掉）。
"""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.config import Settings

logger = logging.getLogger(__name__)


def monthly_backup_path(db_path: Path, moment: datetime) -> Path:
    """当月备份文件路径：与库同目录、同名后缀，文件名是 `YYYY-MM`。"""
    return db_path.with_name(f"{moment:%Y-%m}{db_path.suffix or '.db'}")


def backup_database(settings: Settings, *, now: datetime | None = None) -> Path | None:
    """当月还没备份过就备一份，返回备份文件路径；已有（或不是文件型 SQLite）返回 None。

    用 sqlite3 的 backup API 而不是拷文件：库在 WAL 模式下随时可能被写，直接拷 `app.db`
    会拿到撕裂、或落后于 `-wal` 的副本。备份先写 `.tmp` 再改名，中途失败不会留下一个
    半截的同名文件挡着后面几个月的备份。
    """
    source = settings.database_path
    if not source.is_file():
        return None

    target = monthly_backup_path(source, now or datetime.now())
    if target.exists():
        logger.info("当月数据库备份已存在，跳过：%s", target)
        return None

    temp = target.with_name(f"{target.name}.tmp")
    try:
        _copy_database(source, temp)
        os.replace(temp, target)
    except Exception as exc:  # noqa: BLE001 - 备份失败不该拦住服务启动
        temp.unlink(missing_ok=True)
        logger.warning("数据库备份失败（不影响启动）：%s", exc)
        return None
    logger.info("已备份数据库到 %s", target)
    return target


def _copy_database(source: Path, dest: Path) -> None:
    source_conn = sqlite3.connect(source)
    try:
        dest_conn = sqlite3.connect(dest)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()
