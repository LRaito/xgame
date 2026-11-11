"""``python -m upgrade`` 命令行入口。"""

import argparse
import os
import sys
from pathlib import Path

from backend.config import DB_FILENAME, DB_SUBDIR
from upgrade.runner import UpgradeError, run_upgrade


def _database_path(args: argparse.Namespace) -> Path:
    if args.db is not None:
        return Path(args.db)
    root = args.runtime_root or args.storage_root
    if root is None:
        root = (
            os.environ.get("RUNTIME_ROOT")
            or os.environ.get("STORAGE_ROOT")
            or Path.cwd() / "data" / "storage"
        )
    return Path(root) / DB_SUBDIR / DB_FILENAME


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m upgrade",
        description="按版本逐级升级 app.db 的结构。执行前请先停止服务。",
    )
    parser.add_argument("--db", type=Path, help="直接指定 app.db 路径。")
    parser.add_argument("--runtime-root", type=Path, help="运行时根目录。")
    parser.add_argument("--storage-root", type=Path, help="数据根目录（未配运行时根时使用）。")
    parser.add_argument(
        "--no-backup", action="store_true", help="升级前不生成 app.db 备份。"
    )
    args = parser.parse_args(argv)

    db_path = _database_path(args)
    print(f"数据库：{db_path}")

    try:
        result = run_upgrade(db_path, backup=not args.no_backup)
    except UpgradeError as exc:
        print(f"升级失败：{exc}", file=sys.stderr)
        return 1

    if result.status == "not-initialized":
        print("数据库尚未初始化，无需升级；首次启动服务会按最新结构建库。")
        return 0
    if result.status == "up-to-date":
        print("当前已是最新版本，无需升级")
        return 0

    if result.backup_path is not None:
        print(f"升级前已备份：{result.backup_path}")
    for version in result.applied:
        print(f"已升级到结构版本 {version}。")
    print(f"数据库升级完成，当前版本 {result.to_version}。")
    return 0
