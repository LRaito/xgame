"""把组装好的包目录打成 zip。

有两处和命令行的 `zip` 不一样，都是刻意的：

1. **条目直接躺在压缩包根上**，不再套一层 `xgame/`——解压出来就是包本体，
   用户不用再进一层目录。
2. **中文文件名带 UTF-8 标记**（general purpose bit 11）。Info-ZIP 把非 ASCII 名字按本地
   编码原样写进去、却**不设**这个标记位，Windows 资源管理器读不到标记就按 OEM 代码页解释
   那些字节，于是 `启动游戏平台.cmd` 变成一串乱码；而 WinRAR 会自己猜 UTF-8，所以它的
   预解压窗口里看着一切正常——很容易误以为包没问题。Python 的 `zipfile` 对非 ASCII 名字
   一律写 UTF-8 并设上标记位，Windows 原生解压与资源管理器都认。

用法：`python3 make_zip.py <包目录> <输出.zip>`
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

SKIP_DIR_NAMES = {"__pycache__"}


def collect(root: Path) -> list[Path]:
    """包目录下的全部条目（含空目录），按路径排序，跳过字节码缓存。"""
    items: list[Path] = []
    for path in sorted(root.rglob("*")):
        if SKIP_DIR_NAMES.intersection(path.relative_to(root).parts):
            continue
        if path.suffix == ".pyc":
            continue
        items.append(path)
    return items


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"用法：{argv[0]} <包目录> <输出.zip>", file=sys.stderr)
        return 2

    root = Path(argv[1]).resolve()
    out = Path(argv[2]).resolve()
    if not root.is_dir():
        print(f"没有这个目录：{root}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)

    entries = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in collect(root):
            # write() 会把修改时间与权限位一起带上（Windows 解压不看权限，但在 WSL/Linux 上
            # 解压时 `python/python.exe` 的执行位靠它）
            archive.write(path, path.relative_to(root).as_posix())
            entries += 1

    size = out.stat().st_size
    print(f"已打包 {entries} 个条目：{out.name}（{size / 1024 / 1024:.1f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
