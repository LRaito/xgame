"""服务端 CLI（``make index`` / ``make upgrade``）的控制台输出。

标签固定为 ``[ OK ]`` / ``[FAIL]`` / ``[WARN]`` / ``[INFO]``。输出是终端时给标签上色，
被管道或重定向时退回纯文本；Windows 控制台先开启 VT 处理再写 ANSI。

与 ``packaging/windows/xgame_console.py`` 行为一致，但两份不能合并：那份要进
「解压即用」包，由启动器在 import backend 之前使用；这份只给已经依赖 backend 的 CLI 用。
"""

from __future__ import annotations

import os
import sys
import threading
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


# 进度条宽度与不确定进度时的转轮。只用 ASCII：Windows 控制台不保证能显示方块字符。
_BAR_WIDTH = 24
_SPINNER = "|/-\\"
_SPINNER_INTERVAL = 0.15


class Progress:
    """单行进度条，直接把 ``report`` 交给 ``build_index(on_progress=...)`` 即可。

    终端里用 ``\\r`` 原地刷新，每个阶段结束时把当时的进度留成一行；无确定总数的阶段
    （``total <= 0``，如构建后的 VACUUM）显示转轮。输出被管道或重定向时每阶段只打
    一行 ``[INFO]``，不写进度字符。
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = sys.stdout if stream is None else stream
        self._enabled = self._stream.isatty()
        if self._enabled:
            _enable_vt(self._stream)
        self._label = ""
        self._total = 0
        self._percent = -1
        self._open = False
        self._spinner: threading.Thread | None = None
        self._spinner_stop: threading.Event | None = None

    def report(self, label: str, current: int = 0, total: int = 0) -> None:
        """报告某个阶段已完成 ``current`` / ``total``；总数未知时传 0。"""
        if label != self._label:
            self.finish()
            self._label = label
            self._total = max(total, 0)
            self._percent = -1
            if self._total <= 0:
                self._start_spinner()
                return
            if not self._enabled:
                self._plain(label)
                return
        if self._total <= 0 or not self._enabled:
            return

        current = min(max(current, 0), self._total)
        percent = current * 100 // self._total
        if percent == self._percent:
            return
        self._percent = percent
        filled = _BAR_WIDTH * percent // 100
        bar = "#" * filled + "-" * (_BAR_WIDTH - filled)
        color = _COLORS["info"]
        line = (
            f"\r{self._tag()} {label} "
            f"\033[{color}m[{bar}]\033[0m {percent:3d}%\033[K"
        )
        self._write(line)
        self._open = True

    def finish(self) -> None:
        """收尾当前阶段；可以重复调用。"""
        if self._spinner_stop is not None and self._spinner is not None:
            self._spinner_stop.set()
            self._spinner.join()
            self._spinner = None
            self._spinner_stop = None
            self._write(f"\r{self._tag()} {self._label}\033[K\n")
            self._open = False
            return
        if self._open:
            self._write("\n")
            self._open = False

    def _start_spinner(self) -> None:
        if not self._enabled:
            self._plain(self._label)
            return
        stop = threading.Event()
        self._spinner_stop = stop
        self._spinner = threading.Thread(target=self._spin, args=(stop,), daemon=True)
        self._spinner.start()

    def _spin(self, stop: threading.Event) -> None:
        index = 0
        while not stop.wait(_SPINNER_INTERVAL):
            frame = _SPINNER[index % len(_SPINNER)]
            index += 1
            self._write(f"\r{self._tag()} {self._label} {frame}\033[K")

    def _tag(self) -> str:
        return f"\033[{_COLORS['info']}m{_TAGS['info']}\033[0m"

    def _plain(self, label: str) -> None:
        """非进度阶段（或输出不是终端）只写一行带标签的说明。"""
        tag = self._tag() if self._enabled else _TAGS["info"]
        self._write(f"{tag} {label}\n")

    def _write(self, text: str) -> None:
        self._stream.write(text)
        self._stream.flush()
