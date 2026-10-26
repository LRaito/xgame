#!/usr/bin/env python3
"""一次性数据升级：把全 NULL 的云端存档组按时间串成链。

只处理同一个 (user_id, game_id) 下、所有 parent_id 都是 NULL 的组；
组内按 created_at ASC, id ASC 排序，第一条保持 NULL，后续指向前一条。
组内只要已有一条非 NULL 父级，整组跳过并列出，交给人工处理。

默认 dry-run；加 --apply 才写库。脚本不进入任何文档。
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

# 允许直接 python3 scripts/backfill_save_parents.py
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.database import make_engine  # noqa: E402
from backend.games.models import GameCloudSnapshot  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把全 NULL 的云端存档组按时间顺序串成父子链。",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将发生的变更（默认）",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="真正写库",
    )
    parser.add_argument("--user-id", type=int, default=None, help="只处理指定用户")
    parser.add_argument("--game-id", type=int, default=None, help="只处理指定游戏")
    return parser.parse_args()


def sort_key(row: GameCloudSnapshot) -> tuple[str, int]:
    # datetime 统一是 UTC；转成字符串排序可避开 aware/naive 混用。
    return (str(row.created_at or ""), row.id or 0)


def main() -> int:
    args = parse_args()
    apply = bool(args.apply)
    settings = get_settings()
    db_path = settings.database_path
    print(f"数据库：{db_path}")
    print(f"模式：{'apply' if apply else 'dry-run'}")
    if not db_path.exists():
        print("数据库不存在，先启动一次服务或确认 RUNTIME_ROOT/STORAGE_ROOT。")
        return 1

    engine = make_engine(settings)
    inspector = inspect(engine)
    if not inspector.has_table("game_cloud_snapshots"):
        print("game_cloud_snapshots 表不存在，先启动一次服务建库。")
        return 1
    columns = {column["name"] for column in inspector.get_columns("game_cloud_snapshots")}
    if "parent_id" not in columns:
        print("game_cloud_snapshots.parent_id 列不存在，先启动一次服务让 _ensure_columns 补列。")
        return 1

    if apply:
        print("提示：写库前建议先备份 app.db，并尽量停掉正在运行的服务。")

    query = select(GameCloudSnapshot)
    if args.user_id is not None:
        query = query.where(GameCloudSnapshot.user_id == args.user_id)
    if args.game_id is not None:
        query = query.where(GameCloudSnapshot.game_id == args.game_id)

    with Session(engine) as session:
        rows = session.exec(query).all()
        groups: dict[tuple[int, int], list[GameCloudSnapshot]] = defaultdict(list)
        for row in rows:
            groups[(row.user_id, row.game_id)].append(row)

        processable = 0
        updated = 0
        skipped_mixed: list[tuple[int, int, int, int]] = []
        noop = 0

        try:
            for (user_id, game_id), items in sorted(groups.items()):
                items.sort(key=sort_key)
                non_null = sum(1 for item in items if item.parent_id is not None)
                if non_null:
                    skipped_mixed.append((user_id, game_id, len(items), non_null))
                    continue
                processable += 1
                if len(items) <= 1:
                    noop += 1
                    continue
                for index in range(1, len(items)):
                    item = items[index]
                    previous_id = items[index - 1].id
                    if item.parent_id != previous_id:
                        item.parent_id = previous_id
                        session.add(item)
                        updated += 1
                        if not apply:
                            print(
                                f"将设置 user_id={user_id} game_id={game_id} "
                                f"snapshot_id={item.id} parent_id={previous_id}"
                            )
            if apply and updated:
                session.commit()
            else:
                session.rollback()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            print(f"失败：{exc}")
            return 1

    print()
    print(f"扫描分组：{len(groups)}")
    print(f"可处理组（全 NULL）：{processable}")
    print(f"{'已更新' if apply else '将更新'}行：{updated}")
    print(f"无需处理组（单条）：{noop}")
    print(f"跳过混合组：{len(skipped_mixed)}")
    if skipped_mixed:
        print("混合组列表（未修改）：")
        for user_id, game_id, total, non_null in skipped_mixed:
            print(
                f"  user_id={user_id} game_id={game_id}："
                f"{total} 条，其中 {non_null} 条已有父级"
            )
    if not apply:
        print("dry-run 未写库；确认无误后加 --apply。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
