#!/usr/bin/env python3
"""vimm 卡带图裁切脚本的公共部分。

`vimm-fc-crop.py` 与 `vimm-sfc-crop.py` 共用这里的日志、输入收集、写文件与
几何步骤。两个脚本的 `transform()` 都按同一顺序组合这些步骤：

    缩放 -> 裁网址栏/顶部 -> 抠角 -> 裁左右黑边 -> 镜像去水印

镜像去水印目前只有 SFC 使用。任何受支持的源图尺寸都会在一轮里处理到
最终输出，不需要重复执行脚本。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Sequence

from PIL import Image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

TAGS = {
    "ok": ("[ OK ]", 32),
    "fail": ("[FAIL]", 31),
    "warn": ("[WARN]", 33),
    "info": ("[INFO]", 36),
}

# 每个脚本把自己的 transform 传给 run()，统一签名：(RGBA 图, 源图尺寸) -> 输出图
Transform = Callable[[Image.Image, tuple[int, int]], Image.Image]
Rects = Sequence[tuple[int, int, int, int]]


def emit(kind: str, text: str) -> None:
    """按项目脚本输出规范打一行日志；非终端输出退回纯文本。"""
    tag, color = TAGS[kind]
    stream = sys.stderr if kind in ("fail", "warn") else sys.stdout
    if stream.isatty():
        print(f"\x1b[{color}m{tag}\x1b[0m {text}", file=stream)
    else:
        print(f"{tag} {text}", file=stream)


def collect_inputs(raw_paths: Sequence[str]) -> list[Path]:
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


def output_path(src: Path) -> Path:
    """PNG 原地覆盖；JPG / JPEG 另存同名 .png。"""
    if src.suffix.lower() == ".png":
        return src
    return src.with_suffix(".png")


def blank_rects(im: Image.Image, rects: Rects) -> Image.Image:
    """把若干矩形区域的黑背景只把 alpha 置 0，不填任何底色。"""
    alpha = im.getchannel("A")
    for x0, y0, x1, y1 in rects:
        alpha.paste(0, (x0, y0, x1, y1))
    im.putalpha(alpha)
    return im


def mirror_right(im: Image.Image, width: int, height: int | None = None) -> Image.Image:
    """用左侧等宽矩形的水平镜像逐像素替换右侧，去掉右侧水印。

    height 为 None 时取整幅高度（替换右侧整条）；否则取紧贴底边的条带。
    """
    height = im.height if height is None else height
    y0 = im.height - height
    left = im.crop((0, y0, width, y0 + height)).transpose(
        Image.Transpose.FLIP_LEFT_RIGHT
    )
    im.paste(left, (im.width - width, y0))
    return im


def process(
    src: Path,
    dst: Path,
    transform: Transform,
    out_size: tuple[int, int],
) -> bool:
    """处理一张并写到 dst；失败返回 False，不动源文件。"""
    tmp: Path | None = None
    try:
        with Image.open(src) as im:
            size = im.size
            im.load()
            out = transform(im.convert("RGBA"), size)

        if out.size != out_size:
            raise ValueError(f"输出尺寸异常 {out.size[0]}x{out.size[1]}")

        # 先写临时文件再原子替换；源文件关闭后才动它。
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f".{dst.name}.tmp")
        out.save(tmp, format="PNG")
        os.replace(tmp, dst)
        tmp = None
        if src != dst:
            src.unlink()
        emit("ok", src.name)
        return True

    except Exception as exc:  # 读不了/写不了都要报出来，不能让批处理静默漏图
        emit("fail", f"{src.name} {exc}")
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
        return False


def run(
    raw_paths: Sequence[str],
    transform: Transform,
    out_size: tuple[int, int],
    prefilter: Callable[[list[Path]], list[Path]] | None = None,
) -> int:
    """收集输入、规划输出并逐张处理；返回退出码。

    一轮就把所有受支持尺寸处理到最终输出，输出格式本身也在支持范围内，
    重复执行是幂等的。
    """
    files = collect_inputs(raw_paths)
    if prefilter is not None:
        files = prefilter(files)
    if not files:
        emit("fail", "没有可处理的图片。")
        return 2

    # 先规划每张源图的输出，再按输出文件分组：同一批里多个源图写到同一个
    # 输出文件（如同名 jpg + png）视为冲突，整组跳过。
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
        if not process(src, dst, transform, out_size):
            ok = False
    return 0 if ok else 1
