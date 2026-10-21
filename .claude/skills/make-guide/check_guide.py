#!/usr/bin/env python3
"""攻略目录自检：检查一个待导入的攻略目录是否满足平台约束与转换规范。

只读，不写任何文件；只用标准库。用法：

    python3 check_guide.py [攻略目录] [--quiet]

有 error 时退出码 1，只有 warning 时退出码 0。检查项分三块：
  1. 平台侧硬约束——根 index.html、文件数/体积上限、路径合法性、大小写重名（越界会被后端 400 拒掉）。
  2. 页面本身——外壳剥干净没（script/iframe/form/广告）、链接是不是相对路径且都指得到、页面基础外壳齐不齐。
  3. 转换规范——残留外文（假名/韩文等）、description 没翻、空壳容器、CSS 里的外文与日文字体栈。

「残留外文」的判据：`中文（原文）` 这种**括号内**的原文算合规（本技能的专有名词约定），
括号外的算疑似漏译。日文汉字与中文同形，无法自动区分，所以只扫假名/韩文/西里尔/泰文。
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

# ---- 平台侧上限（与 backend/games/service.py 的常量保持一致，改那边要同步改这里）----
MAX_FILES = 2000
MAX_FILE_SIZE = 64 * 1024 * 1024
MAX_TOTAL_SIZE = 256 * 1024 * 1024
NGINX_BODY_LIMIT = 128 * 1024 * 1024  # Docker 路线 nginx 的 client_max_body_size，先于后端拦住
MAX_PATH_LENGTH = 512
MAX_PATH_SEGMENTS = 32
ENTRY_NAME = "index.html"

# 路径里不能出现的字符（= 后端的 _ASSET_ILLEGAL_CHARS；`\` 与 `#` `%` 另有更明确的消息）
ILLEGAL_CHARS = set(':*?"<>|')
# Windows 保留设备名（按段的主名判断，不分大小写）
RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"COM{i}" for i in range(10)}
    | {f"LPT{i}" for i in range(10)}
)

# 自闭合标签：不压栈
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
# 这些标签允许省略结束标签，遇到同名开标签就先闭合上一个
IMPLICIT_CLOSE = {"p", "li", "td", "th", "tr", "dt", "dd", "option", "tbody", "thead"}
# 只对这几个标签报「空容器」（div/span 做纯结构包装是常态，报了全是噪音）
EMPTY_CHECK_TAGS = {"ul", "ol", "aside", "section"}

# 疑似漏译的外文范围：日文汉字与中文同形，不列入；`・`（U+30FB）是中日通用的间隔号，也不列入
FOREIGN_RANGES = (
    (0x3040, 0x309F, "平假名"),
    (0x30A0, 0x30FA, "片假名"),
    (0x30FC, 0x30FF, "片假名"),
    (0xFF66, 0xFF9D, "半角片假名"),
    (0xAC00, 0xD7A3, "韩文"),
    (0x1100, 0x11FF, "韩文字母"),
    (0x0400, 0x04FF, "西里尔字母"),
    (0x0E00, 0x0E7F, "泰文"),
)
FOREIGN_RE = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi, _ in FOREIGN_RANGES) + "]+")

# CSS 里引用的资源
CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")
# 日文字体名（中文站该换掉）
JP_FONT_RE = re.compile(r"Meiryo|メイリオ|ヒラギノ|Hiragino|Yu\s*Gothic|YuGothic|MS\s*PGothic|Osaka")

IMAGE_EXTS = {".gif", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp", ".svg", ".ico"}

# 明细里最多列几处（其余折成「共 N 处」）
SAMPLES_PER_KIND = 5


def foreign_runs(text: str) -> list[str]:
    """返回文本里所有疑似外文片段。"""
    return [m.group(0) for m in FOREIGN_RE.finditer(text)]


def paren_depths(text: str) -> list[int]:
    """逐字符给出「处理完该字符之后」的括号深度（中英文括号都算）。"""
    depths = []
    depth = 0
    for ch in text:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        depths.append(depth)
    return depths


class GuidePage(HTMLParser):
    """扫一个 HTML 页：收集基础外壳、标签、链接、可见文本、空容器。"""

    def __init__(self, path: Path, rel: str) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.rel = rel
        self.lang: str | None = None
        self.charset: str | None = None
        self.title: str | None = None
        self.description: str | None = None
        self.links: list[tuple[str, str, int]] = []  # (属性名, 值, 行号)
        self.images_without_src: list[int] = []
        self.stripped_tags: list[tuple[str, int]] = []  # 该剥掉却还在的标签
        self.attr_texts: list[tuple[str, str, int]] = []  # alt/title 属性里的文本
        self.texts: list[tuple[str, int]] = []  # 可见文本
        self.empty_tags: list[tuple[str, int]] = []
        self._stack: list[dict] = []
        self._skip_depth = 0  # script/style 里的内容不是可见文本
        self._in_title = False

    # -- HTMLParser 回调 --------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        line = self.getpos()[0]
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "meta":
            if a.get("charset"):
                self.charset = a["charset"]
            if a.get("name", "").lower() == "description":
                self.description = a.get("content", "")
        elif tag == "title":
            self._in_title = True

        if tag in ("script", "style"):
            self._skip_depth += 1
        if tag in ("script", "iframe", "form", "ins"):
            self.stripped_tags.append((tag, line))
        for key in ("href", "src"):
            if key in a:
                self.links.append((key, a[key], line))
        if tag == "img" and not a.get("src"):
            self.images_without_src.append(line)
        for key in ("alt", "title"):
            if a.get(key):
                self.attr_texts.append((key, a[key], line))

        if tag in VOID_TAGS:
            for entry in self._stack:
                entry["content"] = True
            return
        if tag in IMPLICIT_CLOSE and self._stack and self._stack[-1]["tag"] == tag:
            self._close_entry(len(self._stack) - 1)
        for entry in self._stack:
            entry["content"] = True
        self._stack.append({"tag": tag, "line": line, "content": False})

    def handle_startendtag(self, tag: str, attrs) -> None:
        # 自闭合写法：先按开标签收集，再尝试闭合（void 标签没入栈，闭合是空操作）
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]["tag"] == tag:
                self._close_entry(i)
                break

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data
            return
        if self._skip_depth or not data.strip():
            return
        for entry in self._stack:
            entry["content"] = True
        self.texts.append((data, self.getpos()[0]))

    def _close_entry(self, index: int) -> None:
        entry = self._stack[index]
        if not entry["content"] and entry["tag"] in EMPTY_CHECK_TAGS:
            self.empty_tags.append((entry["tag"], entry["line"]))
        del self._stack[index:]


class Report:
    """错误 / 警告 / 统计的收集器。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.stats: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _fmt_size(size: int) -> str:
    """按大小挑单位，别把 100MB 写成 102400.0 KB。"""
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _sample(items: list[str], total: int) -> str:
    """列出前几处明细，其余折成「共 N 处」。"""
    head = "\n      ".join(items[:SAMPLES_PER_KIND])
    if total > SAMPLES_PER_KIND:
        return f"{head}\n      …（共 {total} 处）"
    return head


# ---- 1. 路径与体积 ------------------------------------------------------
def check_paths(root: Path, files: list[Path], report: Report) -> None:
    seen: dict[str, str] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        segments = rel.split("/")

        problems = []
        if "\\" in rel:
            problems.append("含反斜杠")
        for ch in "#%":  # `?` 在 ILLEGAL_CHARS 里，别报两遍
            if ch in rel:
                problems.append(f"含非法字符 {ch}")
                break
        if any(ord(ch) < 32 for ch in rel):
            problems.append("含控制字符")
        bad = sorted(ILLEGAL_CHARS & set(rel))
        if bad:
            problems.append("含非法字符 " + " ".join(bad))
        if rel.startswith("/"):
            problems.append("是绝对路径")
        if any(seg in ("", ".", "..") for seg in segments):
            problems.append("含空段或 . / .. 段")
        if any(seg.endswith((".", " ")) for seg in segments):
            problems.append("有段以点或空格结尾")
        reserved = [seg for seg in segments if seg.split(".")[0].upper() in RESERVED_NAMES]
        if reserved:
            problems.append("含 Windows 保留设备名 " + reserved[0])
        if len(rel) > MAX_PATH_LENGTH:
            problems.append(f"路径超过 {MAX_PATH_LENGTH} 字符")
        if len(segments) > MAX_PATH_SEGMENTS:
            problems.append(f"超过 {MAX_PATH_SEGMENTS} 层目录")

        if problems:
            report.error(f"路径不合法：{rel}（{'；'.join(problems)}）")

        key = rel.lower()
        if key in seen:
            report.error(f"路径大小写不敏感重名：{seen[key]} 与 {rel}")
        else:
            seen[key] = rel


def check_sizes(root: Path, files: list[Path], report: Report) -> tuple[int, int, Path, int]:
    total = 0
    largest = (files[0], 0) if files else (root, 0)
    for path in files:
        size = path.stat().st_size
        total += size
        if size > largest[1]:
            largest = (path, size)
        if size > MAX_FILE_SIZE:
            report.error(
                f"单个文件超过 {MAX_FILE_SIZE // 1024 // 1024}MB："
                f"{path.relative_to(root)}（{_fmt_size(size)}）"
            )
    if len(files) > MAX_FILES:
        report.error(f"文件数 {len(files)} 超过上限 {MAX_FILES}（后端会拒）")
    if total > MAX_TOTAL_SIZE:
        report.error(f"总体积 {_fmt_size(total)} 超过上限 {MAX_TOTAL_SIZE // 1024 // 1024}MB")
    elif total > NGINX_BODY_LIMIT:
        report.warn(
            f"总体积 {_fmt_size(total)} 超过 128MB："
            "Docker 路线 nginx 的 client_max_body_size 会先拦，传不上去"
        )
    return len(files), total, largest[0], largest[1]


# ---- 2. 页面检查 --------------------------------------------------------
def check_page(page: GuidePage, report: Report, agg: dict[str, list[str]], desc_hits: list[str]) -> None:
    rel = page.rel
    if page.lang is None:
        report.error(f"{rel}: <html> 缺 lang 属性（应为 zh-CN）")
    elif page.lang.lower().replace("_", "-") != "zh-cn":
        report.error(f'{rel}: <html lang="{page.lang}"> 应为 zh-CN')
    if not page.charset:
        report.error(f"{rel}: 缺 <meta charset>")
    if not (page.title or "").strip():
        report.error(f"{rel}: <title> 为空或缺失")

    if page.stripped_tags:
        detail = "、".join(f"{tag}（第 {line} 行）" for tag, line in page.stripped_tags[:SAMPLES_PER_KIND])
        report.error(
            f"{rel}: 还留着该剥掉的标签 {len(page.stripped_tags)} 处：{detail}"
            "（script/iframe/form/广告 ins 都要删干净）"
        )
    if page.images_without_src:
        report.error(f"{rel}: 有 <img> 没有 src（第 {page.images_without_src[0]} 行）")

    # 链接：外链 / 绝对路径 / 断链
    external, absolute, broken = [], [], []
    for attr, value, line in page.links:
        v = value.strip()
        if not v:
            report.error(f"{rel}:{line} {attr} 是空值")
            continue
        low = v.lower()
        if low.startswith(("http://", "https://", "//")):
            external.append(f"{rel}:{line} {attr}={v}")
        elif v.startswith("/"):
            absolute.append(f"{rel}:{line} {attr}={v}")
        elif low.startswith(("mailto:", "data:", "tel:", "#")):
            continue
        elif low.startswith("javascript:"):
            report.error(f"{rel}:{line} 有 javascript: 链接")
        else:
            target = unquote(v.split("#")[0].split("?")[0])
            if target and not (page.path.parent / target).exists():
                broken.append(f"{rel}:{line} {attr}={v}")
    if external:
        report.error(
            f"还有外链 {len(external)} 处：\n      " + _sample(external, len(external))
        )
    if absolute:
        report.error(
            f"还有绝对路径链接 {len(absolute)} 处（攻略下必然 404）：\n      "
            + _sample(absolute, len(absolute))
        )
    if broken:
        report.error(
            f"断链 {len(broken)} 处（目标文件不存在）：\n      " + _sample(broken, len(broken))
        )

    # 残留外文：可见文本（`中文（原文）` 这种括号内的原文算合规）
    for text, line in page.texts:
        depths = paren_depths(text)
        for match in FOREIGN_RE.finditer(text):
            start, end = match.span()
            inside = depths[start] > 0 and depths[end - 1] > 0
            if not inside:
                snippet = text[max(0, start - 12):end + 12].strip()
                agg["loose"].append(f"{rel}:{line} …{snippet}…")

    # 属性文本
    for name, value, line in page.attr_texts:
        if foreign_runs(value):
            agg["attr"].append(f'{rel}:{line} {name}="{value}"')

    # description
    if page.description is not None and foreign_runs(page.description):
        desc_hits.append(rel)

    # 空容器
    for tag, line in page.empty_tags:
        agg["empty"].append(f"{rel}:{line} <{tag}>")


def check_css(path: Path, rel: str, report: Report) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    external, absolute, broken = [], [], []
    for match in CSS_URL_RE.finditer(text):
        url = match.group(1).strip()
        low = url.lower()
        if low.startswith(("http://", "https://", "//")):
            external.append(url)
        elif url.startswith("/"):
            absolute.append(url)
        elif url.startswith("data:"):
            continue
        elif not (path.parent / unquote(url.split("#")[0].split("?")[0])).exists():
            broken.append(url)
    if external:
        report.error(f"{rel}: CSS 里还有外链资源 {len(external)} 处：{'、'.join(external[:3])}")
    if absolute:
        report.error(f"{rel}: CSS 里有绝对路径资源 {len(absolute)} 处：{'、'.join(absolute[:3])}")
    if broken:
        report.error(f"{rel}: CSS 里引用的资源不存在 {len(broken)} 处：{'、'.join(broken[:3])}")

    foreign = [f"{rel}:{i} {line.strip()[:60]}" for i, line in enumerate(lines, 1) if foreign_runs(line)]
    if foreign:
        report.warn(f"CSS 里还有外文 {len(foreign)} 处：\n      " + _sample(foreign, len(foreign)))
    fonts = [f"{rel}:{i}" for i, line in enumerate(lines, 1) if JP_FONT_RE.search(line)]
    if fonts:
        report.warn(
            f"CSS 字体栈还是日文字体（第 {fonts[0].split(':')[1]} 行起，共 {len(fonts)} 处）："
            "中文站应换成中文优先的字体栈"
        )


# ---- 主流程 -------------------------------------------------------------
def check_guide(root: Path, quiet: bool) -> int:
    report = Report()

    if not root.is_dir():
        print(f"攻略目录不存在：{root}")
        return 1

    files = sorted(p for p in root.rglob("*") if p.is_file())
    html_files = [p for p in files if p.suffix.lower() in (".html", ".htm")]
    css_files = [p for p in files if p.suffix.lower() == ".css"]

    # 入口
    entry = root / ENTRY_NAME
    if not entry.is_file():
        others = [p.name for p in root.iterdir() if p.name.lower() == ENTRY_NAME]
        hint = f"（根目录里叫 {others[0]}，大小写不对，落盘要统一成 {ENTRY_NAME}）" if others else ""
        report.error(f"根目录没有 {ENTRY_NAME}，攻略导入会被 400 拒掉{hint}")

    check_paths(root, files, report)
    count, total, largest, largest_size = check_sizes(root, files, report)

    desc_hits: list[str] = []
    agg: dict[str, list[str]] = {"loose": [], "attr": [], "empty": []}
    for path in html_files:
        rel = path.relative_to(root).as_posix()
        page = GuidePage(path, rel)
        try:
            page.feed(path.read_text(encoding="utf-8", errors="replace"))
            page.close()
        except Exception as exc:  # 解析崩了也要报出来，别静默跳过
            report.error(f"{rel}: HTML 解析失败（{exc}）")
            continue
        check_page(page, report, agg, desc_hits)

    for path in css_files:
        check_css(path, path.relative_to(root).as_posix(), report)

    if agg["loose"]:
        report.warn(
            f"疑似漏译（括号外的外文）{len(agg['loose'])} 处：\n      "
            + _sample(agg["loose"], len(agg["loose"]))
            + "\n      （`中文（原文）` 这种括号内的原文算合规，不算漏译；反过来写成"
            "「原文（中文注释）」的会被报出来，确认是刻意的就忽略）"
        )
    if agg["attr"]:
        report.warn(
            f"alt/title 属性里还有外文 {len(agg['attr'])} 处：\n      "
            + _sample(agg["attr"], len(agg["attr"]))
        )
    if desc_hits:
        report.warn(
            f'<meta name="description"> 仍是外文：{len(desc_hits)} 个页面'
            f"（首个 {desc_hits[0]}）——它也是可见文本，要一起翻"
        )
    if agg["empty"]:
        report.warn(
            f"空壳容器 {len(agg['empty'])} 个（外壳没删干净，或删剩了空容器）：\n      "
            + _sample(agg["empty"], len(agg["empty"]))
        )

    # 首页出处
    if entry.is_file():
        head = entry.read_text(encoding="utf-8", errors="replace")
        if "出处" not in head:
            report.warn("首页 footer 里没有「出处」字样：转换来的攻略必须写出来处 URL")

    # 统计
    images = [p for p in files if p.suffix.lower() in IMAGE_EXTS]
    others = count - len(html_files) - len(css_files) - len(images)
    report.stats.append(f"页面 {len(html_files)} 个 / 样式表 {len(css_files)} 个 / 图片 {len(images)} 个 / 其他 {others} 个")
    report.stats.append(
        f"文件 {count} 个（上限 {MAX_FILES}），合计 {_fmt_size(total)}"
        f"（上限 {MAX_TOTAL_SIZE // 1024 // 1024} MB）"
    )
    if count:
        report.stats.append(
            f"最大文件：{largest.relative_to(root).as_posix()}（{_fmt_size(largest_size)}）"
        )

    # 输出
    print(f"攻略目录：{root}")
    print()
    if report.errors:
        print(f"错误（{len(report.errors)}）—— 平台会拒或页面必然坏，必须修：")
        for i, msg in enumerate(report.errors, 1):
            print(f"  {i}. {msg}")
    else:
        print("错误（0）—— 平台侧硬约束全部通过。")
    print()
    if report.warnings:
        print(f"警告（{len(report.warnings)}）—— 逐条人工确认：")
        if quiet:
            for i, msg in enumerate(report.warnings, 1):
                print(f"  {i}. {msg.splitlines()[0]}")
        else:
            for i, msg in enumerate(report.warnings, 1):
                print(f"  {i}. {msg}")
    else:
        print("警告（0）。")
    print()
    print("统计：")
    for line in report.stats:
        print(f"  {line}")
    print()
    print("结论：" + ("有错误，先修完再导入。" if report.errors else "可以导入（警告请人工确认）。"))
    return 1 if report.errors else 0


def main() -> int:
    try:  # Windows 控制台默认代码页打不出中文
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="检查攻略目录能否导入本平台")
    parser.add_argument("guide_dir", nargs="?", default=".", help="攻略根目录（含 index.html 那一层），默认当前目录")
    parser.add_argument("--quiet", action="store_true", help="只打印结论与错误，警告只列首行")
    args = parser.parse_args()
    return check_guide(Path(args.guide_dir).resolve(), args.quiet)


if __name__ == "__main__":
    sys.exit(main())
