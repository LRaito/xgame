"""SQLite 库的滚动备份。

服务启动时备一次，之后每 `BACKUP_INTERVAL_SECONDS`（1 小时）再备一次。一个自然月只有一份，
文件名 `<YYYY-MM>.db`，**每次备份都整份重写**（先写 `.tmp` 再 `os.replace`，读的人永远看到
一个完整文件），所以快照最多落后一小时。

备份**不跟库放同一个目录**：库在运行时根里（一直在被写，网盘/外部备份拷不动它），备份写在
数据根的 `db/` 里——数据根才是用户会整体拷走的那一份。不做还原功能，要回滚就把备份文件改名成
`app.db` 手动替换（换之前先把服务停掉）。

备份走独立线程，进程里只有一个（gunicorn 固定 `--workers 1`）：两个进程同时备份会撞同一个
`.tmp` 名字。单次失败只记 warning，不拦启动也不打断循环。
"""

import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from backend.config import Settings

logger = logging.getLogger(__name__)

# 备份间隔。改大只会让快照更旧，改小会让网盘/外部备份更频繁地重新同步这个文件。
BACKUP_INTERVAL_SECONDS = 3600


def monthly_backup_path(backup_dir: Path, moment: datetime) -> Path:
    """当月备份文件路径：`<备份目录>/YYYY-MM.db`。同一个月的多次备份写的是同一个文件。"""
    return backup_dir / f"{moment:%Y-%m}.db"


def backup_database(settings: Settings, *, now: datetime | None = None) -> Path | None:
    """把当前的库整份备到当月的那个文件里（覆盖已有内容），返回备份文件路径。

    库还不是文件（第一次启动、表都没建）就返回 None。
    用 sqlite3 的 backup API 而不是拷文件：服务一直在跑、随时可能有人写入，直接拷 `app.db`
    会拿到撕裂的副本（哪怕没开 WAL，写到一半的页也会被拷进去）。备份先写 `.tmp` 再改名，
    中途失败不会留下一个半截的同名文件。
    """
    source = settings.database_path
    if not source.is_file():
        return None

    target = monthly_backup_path(settings.backup_dir, now or datetime.now())
    # 备份目录（数据根/db/）与库所在目录是两个根，这里自己建，不指望 ensure_data_dir()
    target.parent.mkdir(parents=True, exist_ok=True)

    temp = target.with_name(f"{target.name}.tmp")
    try:
        _copy_database(source, temp)
        os.replace(temp, target)
    except Exception as exc:  # noqa: BLE001 - 备份失败不该拦住服务启动
        temp.unlink(missing_ok=True)
        logger.warning("数据库备份失败（不影响运行）：%s", exc)
        return None
    logger.info("已备份数据库到 %s", target)
    return target


def backup_loop(
    settings: Settings,
    *,
    interval: float = BACKUP_INTERVAL_SECONDS,
    stop_event: threading.Event,
) -> None:
    """每 `interval` 秒备一次，直到 `stop_event` 被 set。启动那一次由 `create_app()` 同步做掉。"""
    while not stop_event.wait(interval):
        try:
            backup_database(settings)
        except Exception as exc:  # noqa: BLE001 - 守护线程不能被一次意外打死，否则备份静默停掉
            logger.warning("数据库备份失败（不影响运行）：%s", exc)


def start_backup_loop(
    settings: Settings,
    *,
    interval: float = BACKUP_INTERVAL_SECONDS,
    stop_event: threading.Event | None = None,
) -> threading.Thread | None:
    """起一个守护线程跑 `backup_loop`，返回该线程；`TESTING` 下不起（返回 None）。

    守护线程随进程一起结束，不需要停机钩子；`stop_event` 只为测试留口。
    """
    if settings.TESTING:
        return None
    thread = threading.Thread(
        target=backup_loop,
        args=(settings,),
        kwargs={"interval": interval, "stop_event": stop_event or threading.Event()},
        name="db-backup",
        daemon=True,
    )
    thread.start()
    return thread


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
