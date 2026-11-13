#!/usr/bin/env python3
"""处理 vimm.net 的 SFC 卡带图。

源图固定 532x358（PNG 或 JPG）；用这批图的固定版式，不做任何检测：

1. 左上、右上两块矩形黑背景 -> 透明（只把 alpha 置 0，不填白色或任何底色）。
   中间封面顶到画面上边，一点不动。
   矩形边界取自银色卡带转折：左角 x 0..86、右角 x 449..532，y 都是 0..18。
2. 底部白底「Vimm's Lair - vimm.net」网址栏 -> 裁掉 14 像素（y=344 起全白）。

输出统一是 532x344 的 RGBA PNG，直接写回源图位置：
- PNG 原地覆盖；
- JPG / JPEG 另存旁边的同名 .png，成功后删除原图。
尺寸不是 532x358 的图会被跳过（不处理、不写出，退出码 1）。
同一批里多个源图会写到同一个输出文件时（如同名 jpg 与 png），整组跳过。

用法：
    python3 tools/vimm/vimm-sfc-crop.py <源图或目录>...
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

# 输出需要透明通道，统一写 PNG；JPG 源图也转成同名 .png。
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

TAGS = {
    "ok": ("[ OK ]", 32),
    "fail": ("[FAIL]", 31),
    "warn": ("[WARN]", 33),
    "info": ("[INFO]", 36),
}


def emit(kind: str, text: str) -> None:
    """按项目脚本输出规范打一行日志；非终端输出退回纯文本。"""
    tag, color = TAGS[kind]
    stream = sys.stderr if kind in ("fail", "warn") else sys.stdout
    if stream.isatty():
        print(f"\x1b[{color}m{tag}\x1b[0m {text}", file=stream)
    else:
        print(f"{tag} {text}", file=stream)


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
            emit("fail", f"找不到：{p}")
    return files


def output_path(src: Path) -> Path:
    """PNG 原地覆盖；JPG / JPEG 另存同名 .png。"""
    if src.suffix.lower() == ".png":
        return src
    return src.with_suffix(".png")


def process(src: Path, dst: Path) -> bool:
    """处理一张并写到 dst。尺寸不符返回 False，不动文件。"""
    try:
        if src.suffix.lower() not in IMAGE_SUFFIXES:
            return False

        with Image.open(src) as im:
            size = im.size
            if size != (SRC_W, SRC_H):
                return False
            im.load()
            # 先裁掉底部网址栏，再按源图坐标处理两个角。
            out = im.convert("RGBA").crop((0, 0, SRC_W, BOTTOM_END))
            alpha = out.getchannel("A")
            for x0, y0, x1, y1 in (LEFT_RECT, RIGHT_RECT):
                alpha.paste(0, (x0, y0, x1, y1))
            out.putalpha(alpha)

        # 源文件已关闭，再写出；JPG 转出的 .png 写好后才删原图。
        dst.parent.mkdir(parents=True, exist_ok=True)
        out.save(dst, format="PNG")
        if src != dst:
            src.unlink()
        emit("ok", src.name)
        return True

    except Exception as exc:  # 读不了/写不了都要报出来，不能让批处理静默漏图
        emit("fail", f"{src.name} {exc}")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="处理 vimm.net SFC 卡带图并覆盖为 532x344 PNG（源图固定 532x358，支持 PNG / JPG）"
    )
    parser.add_argument("inputs", nargs="+", help="源图文件或目录（可多个）")
    args = parser.parse_args(argv)

    files = collect_inputs(args.inputs)
    if not files:
        emit("fail", "没有可处理的图片。")
        return 2

    # 先规划每张源图的输出，再按输出文件分组：同一批里多个源图写到同一个
    # 输出文件（如同名 jpg + png）视为冲突，整组静默跳过。
    seen: set[Path] = set()  # 已排队的源图，避免同一文件处理两遍
    plans: list[tuple[Path, Path]] = []
    groups: dict[Path, list[Path]] = {}
    for src in files:
        src_key = src.resolve()
        if src_key in seen:
            continue
        seen.add(src_key)
        dst = output_path(src)
        plans.append((src, dst))
        groups.setdefault(dst.resolve(), []).append(src)

    ok = True
    for src, dst in plans:
        if len(groups[dst.resolve()]) > 1:
            emit("warn", f"跳过 {src.name}：多个源图会写到 {dst.name}")
            ok = False
            continue
        if not process(src, dst):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
