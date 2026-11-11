"""服务端 CLI（``make index`` / ``make upgrade``）的控制台输出。

标签固定为 ``[ OK ]`` / ``[FAIL]`` / ``[WARN]`` / ``[INFO]``。输出是终端时给标签上色，
被管道或重定向时退回纯文本；Windows 控制台先开启 VT 处理再写 ANSI。

与 ``packaging/windows/xgame_console.py`` 行为一致，但两份不能合并：那份要进
「解压即用」包，由启动器在 import backend 之前使用；这份只给已经依赖 backend 的 CLI 用。
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

_TAGS = {"ok": "[ OK ]", "fail": "[FAIL]", "warn": "[WARN]", "info": "[INFO]"}
_COLORS = {"ok": 32, "fail": 31, "warn": 33, "info": 36}


def _enable_vt(stream: TextIO) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11 if stream is sys.stdout else -12)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:  # noqa: BLE001 - 拿不到控制台就写纯文本
        pass


def emit(level: str, message: str = "") -> None:
    """按级别输出一行或多行；多行时每行都带标签。"""
    tag = _TAGS[level]
    color = _COLORS[level]
    stream = sys.stderr if level == "fail" else sys.stdout
    colored = stream.isatty()
    if colored:
        _enable_vt(stream)
    for line in str(message).splitlines() or [""]:
        if colored:
            stream.write(f"\033[{color}m{tag}\033[0m {line}\n")
        else:
            stream.write(f"{tag} {line}\n")
    stream.flush()


def ok(message: str = "") -> None:
    emit("ok", message)


def fail(message: str = "") -> None:
    emit("fail", message)


def warn(message: str = "") -> None:
    emit("warn", message)


def info(message: str = "") -> None:
    emit("info", message)
