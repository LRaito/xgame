#!/usr/bin/env python3
"""处理 vimm.net 的 SFC 卡带图（原地覆盖）。

源图固定 532x358；用这批图的固定版式，不做任何检测：

1. 左上、右上两块矩形黑背景 -> 透明（只把 alpha 置 0，不填白色或任何底色）。
   中间封面顶到画面上边，一点不动。
   矩形边界取自银色卡带转折：左角 x 0..86、右角 x 449..532，y 都是 0..18。
2. 底部白底「Vimm's Lair - vimm.net」网址栏 -> 裁掉 14 像素（y=344 起全白）。

直接覆盖源文件，输出 532x344 的 RGBA PNG（所以要透明通道，只处理 .png）。
尺寸不是 532x358 的图会被跳过（不处理、不覆盖，退出码 1）。

用法：
    python3 tools/vimm-sfc-crop.py <源图或目录>...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

SRC_W = 532
SRC_H = 358

BOTTOM_END = 344  # 保留到这一行（不含），即裁掉底部 14 像素白条

# 两个角上的黑矩形（源图坐标，右下开区间）
LEFT_RECT = (0, 0, 86, 18)
RIGHT_RECT = (449, 0, SRC_W, 18)

# 原地覆盖需要透明通道，只处理 PNG。
IMAGE_SUFFIXES = {".png"}


def collect_inputs(raw_paths: list[str]) -> list[Path]:
    """把文件/目录参数展开成图片文件列表。目录只取直接子文件。"""
    files: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(
                sorted(
                    q
                    for q in p.iterdir()
                    if q.is_file() and q.suffix.lower() in IMAGE_SUFFIXES
                )
            )
        elif p.is_file():
            files.append(p)
        else:
            print(f"找不到：{p}", file=sys.stderr)
    return files


def process(src: Path) -> bool:
    """处理一张并覆盖源文件。尺寸不符返回 False，不动文件。"""
    try:
        if src.suffix.lower() not in IMAGE_SUFFIXES:
            print(f"跳过 {src.name}：原地覆盖需要透明通道，只处理 .png")
            return False

        with Image.open(src) as im:
            size = im.size
            if size != (SRC_W, SRC_H):
                print(f"跳过 {src.name}：尺寸 {size[0]}x{size[1]}，不是 {SRC_W}x{SRC_H}")
                return False
            im.load()
            # 先裁掉底部网址栏，再按源图坐标处理两个角。
            out = im.convert("RGBA").crop((0, 0, SRC_W, BOTTOM_END))
            alpha = out.getchannel("A")
            for x0, y0, x1, y1 in (LEFT_RECT, RIGHT_RECT):
                alpha.paste(0, (x0, y0, x1, y1))
            out.putalpha(alpha)

        # 源文件已关闭，再覆盖写回。
        out.save(src, format="PNG")
        print(f"已覆盖 {src} ({out.width}x{out.height})")
        return True

    except Exception as exc:  # 读不了/写不了都要报出来，不能让批处理静默漏图
        print(f"失败 {src.name}：{exc}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="处理 vimm.net SFC 卡带图并覆盖原文件（源图固定 532x358、PNG）"
    )
    parser.add_argument("inputs", nargs="+", help="源图文件或目录（可多个）")
    args = parser.parse_args(argv)

    files = collect_inputs(args.inputs)
    if not files:
        print("没有可处理的图片。", file=sys.stderr)
        return 2

    ok = True
    for src in files:
        if not process(src):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
