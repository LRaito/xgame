"""``python -m upgrade`` 命令行入口。"""

import argparse
import os
from pathlib import Path

from backend import console
from backend.config import DB_FILENAME, DB_SUBDIR
from upgrade.game_db import GameDbUpgradeError, run_game_upgrade
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
        description="升级 app.db 与 game.db 的结构。执行前请先停止服务。",
    )
    parser.add_argument("--db", type=Path, help="直接指定 app.db 路径。")
    parser.add_argument("--game-db", type=Path, help="直接指定 game.db 路径。")
    parser.add_argument("--runtime-root", type=Path, help="运行时根目录。")
    parser.add_argument("--storage-root", type=Path, help="数据根目录（未配运行时根时使用）。")
    parser.add_argument(
        "--no-backup", action="store_true", help="升级前不生成 app.db 备份。"
    )
    args = parser.parse_args(argv)

    db_path = _database_path(args)
    game_path = args.game_db or db_path.with_name("game.db")
    console.info(f"app.db：{db_path}")

    try:
        result = run_upgrade(db_path, backup=not args.no_backup)
    except UpgradeError as exc:
        console.fail(f"升级失败：{exc}")
        return 1

    if result.status == "not-initialized":
        console.warn(
            f"app.db 尚未初始化，无需升级；首次启动服务会按最新结构建库"
            f"（版本 {result.to_version}）。"
        )
    elif result.status == "up-to-date":
        console.ok(f"app.db 结构已是最新（版本 {result.to_version}）。")
    else:
        if result.backup_path is not None:
            console.info(f"app.db 升级前已备份：{result.backup_path}")
        for version in result.applied:
            console.info(f"app.db 已升级到结构版本 {version}。")
        console.ok(f"app.db 升级完成，当前版本 {result.to_version}。")

    console.info(f"game.db：{game_path}")
    try:
        game_result = run_game_upgrade(game_path)
    except GameDbUpgradeError as exc:
        console.fail(f"game.db 升级失败：{exc}")
        return 1

    if game_result.status == "created":
        console.ok(
            f"已创建空 game.db 结构（版本 {game_result.to_version}）。"
            "游戏名录、游戏榜单数据与标记请执行 make index。"
        )
    elif game_result.status == "up-to-date":
        console.ok(f"game.db 结构已是最新（版本 {game_result.to_version}）。")
    else:
        console.ok(
            f"game.db 已升级到结构版本 {game_result.to_version}。"
            "游戏名录、游戏榜单数据与标记请执行 make index 重建。"
        )
    return 0
