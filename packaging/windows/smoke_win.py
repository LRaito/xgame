"""组装后的自检：用包里那份 Windows Python 跑一遍关键假设。

在 WSL 里由 `build-win-dist.sh` 通过 interop 自动调用（`python/python.exe smoke_win.py`），
也可以在 Windows 上手动跑一遍排查环境问题。它只读不写，不会碰数据目录。

检查的是「缺了会让整条路线悄悄坏掉」的那几件事：

- SQLite 带不带 FTS5（不带 → 「游戏发现」的游戏名录标签永远显示尚未构建，且没人知道为什么）；
- 依赖是否齐全、能不能 import（半边装好时会在启动那一刻炸）；
- 有没有混进 gunicorn / uvloop（它们根本跑不了 Windows）；
- MSVC 运行库在不在（不在 → 双击后进程直接没了，连报错都没有）。
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from xgame_console import fail, info, ok

REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "sqlmodel",
    "pydantic_settings",
    "multipart",
    "itsdangerous",
    "requests",
    "click",
    "werkzeug",
    "backend.static_site",
    "backend.games.search_index",
    "backend.asgi",
    "upgrade.cli",
]
FORBIDDEN_MODULES = ["gunicorn", "uvloop"]


def main() -> int:
    problems: list[str] = []

    info(f"Python {sys.version.split()[0]}（{sys.executable}）")
    info(f"SQLite {sqlite3.sqlite_version}")

    connection = sqlite3.connect(":memory:")
    options = [row[0] for row in connection.execute("pragma compile_options")]
    if "ENABLE_FTS5" not in options:
        problems.append("这份 SQLite 没有编译 FTS5，游戏发现页的游戏名录会一直显示尚未构建。")
    else:
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")
            connection.execute("INSERT INTO probe VALUES ('测试')")
            ok("FTS5：可用")
        except sqlite3.Error as exc:
            problems.append(f"FTS5 建表失败：{exc}")
    connection.close()

    # backend.asgi 在 import 时会 create_app()，会建数据目录 —— 指到临时目录去
    os.environ.setdefault("STORAGE_ROOT", tempfile.mkdtemp(prefix="xgame-smoke-"))
    os.environ["TESTING"] = "1"

    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
            ok(f"import {name}：OK")
        except Exception as exc:  # noqa: BLE001 - 自检要把所有失败都收上来
            problems.append(f"import {name} 失败：{exc!r}")

    for name in FORBIDDEN_MODULES:
        try:
            importlib.import_module(name)
            problems.append(f"包里混进了 {name}，它在 Windows 上不可用也不该被打进来。")
        except ImportError:
            ok(f"确认没有 {name}：OK")

    python_dir = Path(sys.executable).parent
    missing_dlls = [
        name
        for name in ("vcruntime140.dll", "vcruntime140_1.dll")
        if not (python_dir / name).exists()
    ]
    if missing_dlls:
        problems.append(
            f"python/ 下缺少 {'、'.join(missing_dlls)}，"
            "在一台没装过 VC 运行库的机器上双击会毫无反应。"
        )
    else:
        ok("MSVC 运行库：在位")

    if problems:
        fail("自检发现问题：")
        for item in problems:
            fail(f"  - {item}")
        return 1
    ok("自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
