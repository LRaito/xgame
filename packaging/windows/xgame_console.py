"""Windows 包内脚本的控制台输出：固定状态标签 + 颜色。

标签固定为 ``[ OK ]`` / ``[FAIL]`` / ``[WARN]`` / ``[INFO]``。输出是终端时给标签上色，
被管道或重定向时退回纯文本；Windows 控制台先开启 VT 处理再写 ANSI。

这个文件被复制进「解压即用」包，与 launcher.py / winops.py / smoke_win.py 同级。
不能改用 backend 里的实现：launcher 在配置就绪前不 import backend（那会连带 create_app）。
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

_TAGS = {"ok": "[ OK ]", "fail": "[FAIL]", "warn": "[WARN]", "info": "[INFO]"}
_COLORS = {"ok": 32, "fail": 31, "warn": 33, "info": 36}


def _enable_vt(stream: TextIO) -> None:
    """Windows 控制台默认不解释 ANSI，先打开 VT 处理。失败就保持默认。"""
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
