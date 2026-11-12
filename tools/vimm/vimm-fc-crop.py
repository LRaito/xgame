#!/usr/bin/env python3
"""处理 vimm.net 的 FC（NES）卡带图。

源图有四种固定版式，按分辨率分派，不做任何检测；统一输出 468x526 的
RGBA PNG，直接覆盖原图位置：

- 472x540：先裁掉底部 14 像素网址栏，再抠底部两角，最后左右各裁 2 像素黑边。
- 472x526：抠底部两角，再左右各裁 2 像素黑边。
- 468x526：已经裁过左右黑边，只抠底部两角，不再裁边。
- 236x265：先放大到 472x530，裁掉顶部 4 像素，再按 472x526 的同一组
  矩形抠掉底部两角，最后左右各裁 2 像素黑边。

抠角只把 alpha 置 0，不填白色或任何底色。矩形取自卡带底部两个倒角，
472 宽源图实测约 28x95（源图坐标，右下开区间）：
左 (0,431)-(28,526)，右 (443,431)-(472,526)。
468 宽源图已裁掉左右各 2 像素，对应矩形各减 2：左宽 26、右宽 27。

文件名不含 `-` 的图片视为异常数据，直接删除，不处理。
尺寸不在这三种之内的图片跳过（不写出），退出码 1。

JPG / JPEG 源图转成同名 .png 并删除原图；PNG 源图原地覆盖。
同一批里多个源图会写到同一个输出文件时（如同名 jpg 与 png），整组跳过。

用法：
    python3 tools/vimm/vimm-fc-crop.py <源图或目录>... [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PIL import Image

SRC_W = 472
OUT_W = 468
OUT_H = 526

# 472x540 版式与底部网址栏高度
BIG_SIZE = (472, 540)
BOTTOM_BAR = 14
# 所有版式最后统一左右各裁掉的黑色边框宽度
SIDE_CROP = 2

# 472 宽源图底部两块黑矩形（源图坐标，右下开区间），实测约 28x95
CORNER_RECTS = ((0, 431, 28, 526), (443, 431, 472, 526))

# 468 宽源图已经裁掉左右各 2 像素，矩形按同样位移收窄
CORNER_RECTS_CROPPED = ((0, 431, 26, 526), (441, 431, 468, 526))

# 236x265 小图：2 倍放大后裁掉顶部 4 像素，正好回到 472x526
SMALL_SIZE = (236, 265)
SMALL_UP = (472, 530)
SMALL_TOP_CROP = 4

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
    """把文件/目录参数展开成图片文件列表（去重、保持顺序）。目录只取直接子文件。"""
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_paths:
        p = Path(raw)
        if p.is_dir():
            candidates = sorted(
                q
                for q in p.iterdir()
                if q.is_file() and q.suffix.lower() in IMAGE_SUFFIXES
            )
        elif p.is_file():
            if p.suffix.lower() not in IMAGE_SUFFIXES:
                emit("warn", f"不是支持的图片，已跳过：{p}")
                continue
            candidates = [p]
        else:
            emit("fail", f"找不到：{p}")
            continue
        for q in candidates:
            key = q.resolve()
            if key in seen:
                continue
            seen.add(key)
            files.append(q)
    return files


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


def output_path(src: Path) -> Path:
    """JPG / JPEG 转同名 .png；PNG 原地覆盖。"""
    if src.suffix.lower() == ".png":
        return src
    return src.with_suffix(".png")


def blank_corners(im: Image.Image, rects) -> Image.Image:
    """把底部两块矩形黑背景的 alpha 置 0。"""
    alpha = im.getchannel("A")
    for x0, y0, x1, y1 in rects:
        alpha.paste(0, (x0, y0, x1, y1))
    im.putalpha(alpha)
    return im


def transform(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """按源图分辨率处理，返回 468x526 的 RGBA 图。尺寸不认识则抛 ValueError。"""
    if size == BIG_SIZE:
        # 底部网址栏为白底，直接裁掉；剩余画面与 472x526 版式对齐。
        im = im.crop((0, 0, SRC_W, BIG_SIZE[1] - BOTTOM_BAR))
        im = blank_corners(im, CORNER_RECTS)
    elif size == (SRC_W, OUT_H):
        # 源图坐标下先抠掉两个底角，再裁左右黑边。
        im = blank_corners(im, CORNER_RECTS)
    elif size == (OUT_W, OUT_H):
        # 左右黑边已经裁过，直接用收窄后的矩形抠角，不再裁边。
        return blank_corners(im, CORNER_RECTS_CROPPED)
    elif size == SMALL_SIZE:
        # 放大并裁掉顶部 2 个源像素后，画面与 472x526 版式对齐，同样抠角。
        im = im.resize(SMALL_UP, Image.LANCZOS)
        im = im.crop((0, SMALL_TOP_CROP, SRC_W, SMALL_UP[1]))
        im = blank_corners(im, CORNER_RECTS)
    else:
        raise ValueError(f"不支持的尺寸 {size[0]}x{size[1]}")

    return im.crop((SIDE_CROP, 0, SRC_W - SIDE_CROP, OUT_H))


def process(src: Path, dst: Path, *, dry_run: bool = False) -> bool:
    """处理一张并写到 dst；失败或尺寸不符返回 False，不动文件。"""
    tmp: Path | None = None
    try:
        with Image.open(src) as im:
            size = im.size
            im.load()
            out = transform(im.convert("RGBA"), size)

        if out.size != (OUT_W, OUT_H):
            raise ValueError(f"输出尺寸异常 {out.size[0]}x{out.size[1]}")
        if dry_run:
            emit("info", f"{src.name} -> {dst.name}（未写入）")
            return True

        # 先写临时文件再原子替换；源文件关闭后才动它。
        tmp = dst.with_name(f".{dst.name}.tmp")
        out.save(tmp, format="PNG")
        os.replace(tmp, dst)
        tmp = None
        if src != dst:
            src.unlink()
        emit("ok", f"{src.name} -> {dst.name}")
        return True

    except Exception as exc:  # 读不了/写不了都要报出来，不能让批处理静默漏图
        emit("fail", f"{src.name} {exc}")
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="处理 vimm.net FC 卡带图并覆盖为 468x526 PNG（按分辨率分派版式）"
    )
    parser.add_argument("inputs", nargs="+", help="源图文件或目录（可多个）")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只报告会处理的文件，不写盘、不删除",
    )
    args = parser.parse_args(argv)

    files = collect_inputs(args.inputs)
    if not files:
        emit("fail", "没有可处理的图片。")
        return 2

    if args.dry_run:
        # dry-run 也不删异常文件，只报告。
        abnormal = [p for p in files if "-" not in p.stem]
        for p in abnormal:
            emit("warn", f"异常文件（文件名无中划线）：{p.name}")
        files = [p for p in files if "-" in p.stem]
    else:
        files = drop_abnormal(files)

    if not files:
        emit("fail", "没有可处理的图片。")
        return 2

    # 先规划每张源图的输出，再按输出文件分组：同一批里多个源图写到同一个
    # 输出文件（如同名 jpg + png）视为冲突，整组静默跳过。
    seen: set[Path] = set()
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
        if not process(src, dst, dry_run=args.dry_run):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
