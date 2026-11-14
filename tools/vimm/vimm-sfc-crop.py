#!/usr/bin/env python3
"""处理 vimm.net 的 SFC 卡带图。

受支持的源图尺寸与处理步骤（同一轮里按顺序执行完，直接得到最终的
532x344 RGBA PNG，不需要对同一批图重复运行脚本）：

| 源图尺寸 | 1. 缩放 | 2. 裁网址栏 | 3. 抠两角 | 4. 右侧镜像 |
|---|---|---|---|---|
| 532x358 | - | 底部 14 像素 | 是 | 是 |
| 532x344 | - | 已裁过 | 是 | 是 |
| 264x169 / 265x172 / 266x167 / 267x167 | 放大到 532x344 | - | 是 | 是 |

步骤说明：
1. 缩放：缩略图是正式版式的缩小版，LANCZOS 拉到 532x344 后坐标对齐。
2. 裁网址栏：532x358 底部「Vimm's Lair - vimm.net」白底栏（y=344 起全白）
   直接裁掉。
3. 抠两角：左上、右上两块矩形黑背景只把 alpha 置 0，不填白色或任何底色；
   中间封面顶到画面上边，一点不动。各版式画面顶部对齐，矩形坐标相同，
   取自银色卡带转折：左角 x 0..86、右角 x 449..532，y 都是 0..18
   （源图坐标，右下开区间）。532x344 的 PNG 源图这两块本来就是透明的，
   再置 0 没有影响；JPG 源图没有透明通道，原透明区被压成近黑色，正是靠
   这一步清掉。
4. 右侧镜像：把右侧 86 像素宽的条带换成左侧等宽条带的水平镜像（含
   alpha），用于去掉部分图右侧的水印。左上透明角正好 86 宽，替换后
   右上角同样透明。

输出统一写回源图位置：PNG 原地覆盖；JPG / JPEG 另存旁边的同名 .png，
成功后删除原图。输出尺寸 532x344 本身也在支持列表里，重复执行是幂等的。
尺寸不在上表的图会报 [FAIL] 并跳过（不写出，退出码 1）。同一批里多个
源图会写到同一个输出文件时（如同名 jpg 与 png），整组跳过。
日志、输入收集、写文件与几何步骤由 vimm_common.py 提供，两个脚本共用。

用法：
    python3 tools/vimm/vimm-sfc-crop.py <源图或目录>...
"""
from __future__ import annotations

import argparse
import sys

from PIL import Image

from vimm_common import blank_rects, mirror_right, run

SRC_W = 532
SRC_H = 358  # 带底部网址栏的版式
OUT_H = 344  # 裁掉网址栏后的统一输出高度
OUT_SIZE = (SRC_W, OUT_H)

# 各版式画面顶部对齐，角上的黑矩形坐标相同（源图坐标，右下开区间）。
CORNER_RECTS = ((0, 0, 86, 18), (449, 0, SRC_W, 18))

# vimm 上少数封面只有缩略图；尺寸是 532x344 版式缩小后的取整结果，
# 统一拉到 532x344 再抠角。
SMALL_SIZES = {(264, 169), (265, 172), (266, 167), (267, 167)}

# 右侧去水印用的镜像条带宽度：与左上角透明矩形同宽（x 0..86）。
MIRROR_W = 86


def transform(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """按源图分辨率处理，返回 532x344 的 RGBA 图。尺寸不认识则抛 ValueError。"""
    if size == (SRC_W, SRC_H):
        # 裁掉底部网址栏，剩余画面与 532x344 版式对齐。
        im = im.crop((0, 0, SRC_W, OUT_H))
    elif size in SMALL_SIZES:
        # 缩略图放大到 532x344，与正式版式对齐。
        im = im.resize(OUT_SIZE, Image.LANCZOS)
    elif size != OUT_SIZE:
        raise ValueError(f"不支持的尺寸 {size[0]}x{size[1]}")

    im = blank_rects(im, CORNER_RECTS)
    return mirror_right(im, MIRROR_W)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="处理 vimm.net SFC 卡带图并覆盖为 532x344 PNG（按分辨率分派版式）"
    )
    parser.add_argument("inputs", nargs="+", help="源图文件或目录（可多个）")
    args = parser.parse_args(argv)
    return run(args.inputs, transform, OUT_SIZE)


if __name__ == "__main__":
    sys.exit(main())
