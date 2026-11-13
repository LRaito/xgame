#!/usr/bin/env python3
"""处理 vimm.net 的 FC（NES）卡带图。

受支持的源图尺寸与处理步骤（同一轮里按顺序执行完，直接得到最终的
468x526 RGBA PNG，不需要对同一批图重复运行脚本）：

| 源图尺寸 | 1. 缩放 | 2. 裁网址栏/顶部 | 3. 抠两角 | 4. 裁左右黑边 |
|---|---|---|---|---|
| 472x540 | - | 底部 14 像素 | 472 坐标 | 左右各 2 像素 |
| 472x526 | - | - | 472 坐标 | 左右各 2 像素 |
| 468x526 | - | - | 468 坐标 | 已裁过 |
| 236x265 | 放大到 472x530 | 顶部 4 像素 | 472 坐标 | 左右各 2 像素 |

步骤说明：
1. 缩放：236x265 是缩小版，LANCZOS 放大到 472x530 后裁掉顶部 4 像素，
   正好回到 472x526，与正式版式对齐。
2. 裁网址栏/顶部：472x540 底部的白色「Vimm's Lair - vimm.net」网址栏
   直接裁掉 14 像素。
3. 抠两角：底部两块矩形黑背景只把 alpha 置 0，不填白色或任何底色。
   472 宽源图取等宽 29x95（源图坐标，右下开区间）：左 (0,431)-(29,526)、
   右 (443,431)-(472,526)。468 宽源图已裁掉左右各 2 像素，对应矩形各减
   2，左右都是 27 宽。
4. 裁左右黑边：472 宽版式统一左右各裁 2 像素；468 宽版式已经裁过。

文件名不含 `-` 的图片视为异常数据，直接删除，不处理。
尺寸不在上表的图会报 [FAIL] 并跳过（不写出，退出码 1）。

JPG / JPEG 源图转成同名 .png 并删除原图；PNG 源图原地覆盖。输出尺寸
468x526 本身也在支持列表里，重复执行是幂等的。同一批里多个源图会写到
同一个输出文件时（如同名 jpg 与 png），整组跳过。
日志、输入收集、写文件与几何步骤由 vimm_common.py 提供，两个脚本共用。

用法：
    python3 tools/vimm/vimm-fc-crop.py <源图或目录>...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from vimm_common import blank_rects, emit, run

SRC_W = 472
OUT_W = 468
OUT_H = 526
OUT_SIZE = (OUT_W, OUT_H)

# 472x540 版式与底部网址栏高度
BIG_SIZE = (472, 540)
BOTTOM_BAR = 14
# 472 宽版式最后统一左右各裁掉的黑色边框宽度
SIDE_CROP = 2

# 472 宽源图底部两块黑矩形（源图坐标，右下开区间），等宽 29x95、左右对称
CORNER_RECTS = ((0, 431, 29, 526), (443, 431, 472, 526))

# 468 宽源图已经裁掉左右各 2 像素，矩形按同样位移收窄，左右都是 27 宽
CORNER_RECTS_CROPPED = ((0, 431, 27, 526), (441, 431, 468, 526))

# 236x265 小图：2 倍放大后裁掉顶部 4 像素，正好回到 472x526
SMALL_SIZE = (236, 265)
SMALL_UP = (472, 530)
SMALL_TOP_CROP = 4


def drop_abnormal(files: list[Path]) -> list[Path]:
    """文件名不含 `-` 的图片是异常数据，直接删除；返回剩下的文件。"""
    kept: list[Path] = []
    for p in files:
        if "-" in p.stem:
            kept.append(p)
            continue
        try:
            p.unlink()
            emit("warn", f"已删除异常文件（文件名无中划线）：{p.name}")
        except OSError as exc:
            emit("fail", f"删除失败 {p.name}：{exc}")
    return kept


def transform(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """按源图分辨率处理，返回 468x526 的 RGBA 图。尺寸不认识则抛 ValueError。"""
    if size == OUT_SIZE:
        # 左右黑边已经裁过，直接用收窄后的矩形抠角，不再裁边。
        out = blank_rects(im, CORNER_RECTS_CROPPED)
    else:
        if size == BIG_SIZE:
            # 裁掉底部网址栏，剩余画面与 472x526 版式对齐。
            im = im.crop((0, 0, SRC_W, OUT_H))
        elif size == SMALL_SIZE:
            # 放大到 472x530 并裁掉顶部 4 像素，画面与 472x526 版式对齐。
            im = im.resize(SMALL_UP, Image.LANCZOS)
            im = im.crop((0, SMALL_TOP_CROP, SRC_W, SMALL_UP[1]))
        elif size != (SRC_W, OUT_H):
            raise ValueError(f"不支持的尺寸 {size[0]}x{size[1]}")

        out = blank_rects(im, CORNER_RECTS)
        out = out.crop((SIDE_CROP, 0, SRC_W - SIDE_CROP, OUT_H))

    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="处理 vimm.net FC 卡带图并覆盖为 468x526 PNG（按分辨率分派版式）"
    )
    parser.add_argument("inputs", nargs="+", help="源图文件或目录（可多个）")
    args = parser.parse_args(argv)
    return run(args.inputs, transform, OUT_SIZE, prefilter=drop_abnormal)


if __name__ == "__main__":
    sys.exit(main())
