"""几个 Windows 外壳操作：桌面快捷方式、开机自启、解除「来自 Internet」锁定。

没有安装程序，这些事就得由包内脚本顶上来。全部免管理员：

- **桌面快捷方式**：往当前用户的桌面写一个 `.lnk`，指向 `启动游戏平台.cmd`。
- **开机自启**：往「启动」文件夹（`shell:startup`）放/删 `.lnk`，再点一次就是取消。
- **解除锁定**：从网上下载的 zip 解压出来的文件都带「来自 Internet」标记（MOTW），
  双击 `.cmd` 可能被 SmartScreen 拦下，整棵树跑一次 `Unblock-File` 就好。

`.lnk` 是通过 PowerShell 的 `WScript.Shell` 建的，不引第三方依赖（不想为一个快捷方式
把 pywin32 打进包）。非 Windows 平台上这些函数直接返回一句「跳过」，方便在开发机上
把打包流程跑通。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("xgame.winops")

LAUNCHER_SCRIPT = "launcher.py"
LAUNCH_CMD = "启动游戏平台.cmd"
SHORTCUT_NAME = "XGame.lnk"


def _run_powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - 调的是系统自带的 powershell
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _quote(value: str) -> str:
    """PowerShell 单引号字符串字面量：单引号本身翻倍即可。"""
    return "'" + str(value).replace("'", "''") + "'"


def _new_shortcut(link: Path, target: Path, arguments: str, workdir: Path, icon: Path) -> str:
    """建一个 .lnk，返回空串表示成功、否则返回错误信息。"""
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$lnk = $ws.CreateShortcut({_quote(str(link))}); "
        f"$lnk.TargetPath = {_quote(str(target))}; "
        f"$lnk.Arguments = {_quote(arguments)}; "
        f"$lnk.WorkingDirectory = {_quote(str(workdir))}; "
        f"$lnk.IconLocation = {_quote(str(icon))} + ',0'; "
        "$lnk.Description = 'XGame'; "
        "$lnk.Save()"
    )
    result = _run_powershell(script)
    if result.returncode != 0:
        return (result.stderr or result.stdout or "未知错误").strip()
    return ""


def _system_folder(name: str) -> Path:
    """取「桌面」「启动」这类系统文件夹的真实位置（可能被 OneDrive 重定向过）。"""
    result = _run_powershell(f"[Environment]::GetFolderPath({_quote(name)})")
    path = (result.stdout or "").strip()
    if not path:
        raise RuntimeError(f"拿不到系统文件夹 {name} 的位置。")
    return Path(path)


def _python_exe(root: Path) -> Path:
    return root / "python" / ("python.exe" if os.name == "nt" else "python")


def _pythonw_exe(root: Path) -> Path:
    return root / "python" / ("pythonw.exe" if os.name == "nt" else "python")


def _icon(root: Path) -> Path:
    """快捷方式图标：包里那张 .ico；没有就退回 python.exe 自带的图标（能用但很通用）。"""
    icon = root / "xgame.ico"
    return icon if icon.is_file() else _python_exe(root)


def create_desktop_shortcut(root: Path) -> str:
    if os.name != "nt":
        return "当前系统不是 Windows，跳过。"
    link = _system_folder("Desktop") / SHORTCUT_NAME
    error = _new_shortcut(link, root / LAUNCH_CMD, "", root, _icon(root))
    if error:
        return f"创建失败：{error}"
    return f"已在桌面创建快捷方式：{link}"


def toggle_autostart(root: Path) -> str:
    """开机自启开关：已经有快捷方式就删掉（= 取消），没有就建一个。

    自启用 `pythonw.exe`（没有控制台窗口），所以带上 `--quiet`：出问题时看日志
    `<数据目录>\\logs\\xgame.log`，以及包目录下的 `runtime\\last-error.txt`。
    """
    if os.name != "nt":
        return "当前系统不是 Windows，跳过。"
    link = _system_folder("Startup") / SHORTCUT_NAME
    if link.exists():
        link.unlink()
        return f"已取消开机自启（删掉了 {link}）。"
    error = _new_shortcut(
        link,
        _pythonw_exe(root),
        f'"{root / LAUNCHER_SCRIPT}" --quiet',
        root,
        _icon(root),
    )
    if error:
        return f"设置失败：{error}"
    return f"已设置开机自启（{link}）。再运行一次本脚本即可取消。"


def unlock_tree(root: Path) -> str:
    """去掉整棵树的「来自 Internet」标记。"""
    if os.name != "nt":
        return "当前系统不是 Windows，跳过。"
    result = _run_powershell(
        "Get-ChildItem -LiteralPath "
        + _quote(str(root))
        + " -Recurse -File -ErrorAction SilentlyContinue | Unblock-File"
    )
    if result.returncode != 0:
        return f"解除锁定失败：{(result.stderr or '').strip()}"
    return "已解除这一份的所有文件锁定。"


_ACTIONS = {
    "create-shortcut": create_desktop_shortcut,
    "toggle-autostart": toggle_autostart,
    "unlock": unlock_tree,
}


def run_action(action: str, root: Path | None = None) -> str:
    """执行一个外壳动作并返回一句中文结果（启动器与那几个 .bat 包装都走这里）。"""
    handler = _ACTIONS.get(action)
    if handler is None:
        raise SystemExit(f"未知动作：{action}（可用：{'、'.join(_ACTIONS)}）")
    return handler(root or Path(__file__).resolve().parent)


def main(argv: list[str]) -> int:
    """直接运行本文件时用：`python winops.py create-shortcut`。"""
    if len(argv) != 1 or argv[0] not in _ACTIONS:
        print(f"用法：{sys.argv[0]} {{{'|'.join(_ACTIONS)}}}", file=sys.stderr)
        return 2
    print(run_action(argv[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
