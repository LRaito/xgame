#!/usr/bin/env python3
"""补全游戏榜单 CSV 的中文名与卡带 ID。

数据源与优先级：

- 中文名：先查 `backend/search/catalog/` 的中英名录（同机种优先，跨机种仅接受唯一译名），
  再接受人工/联网补录的 `apply` 建议文件。
- 卡带 ID：只写权威 DAT 里逐字存在或按官方编号规则可直接拼出的值：
  - MAME `hash/*.xml` 的 `<info name="serial">`；
  - No-Intro DAT 的 `<rom serial="...">`（NDS / GBA / N64 / VB 会按
    `NTR-XXXX-USA` 这类官方编号规则补全，已用现有榜单数据验证）。
  查不到就留空，**不猜测、不用美版编号推日版**。

用法：

    # 1. 同步 DAT（MAME 走 jsdelivr；No-Intro 用本地 zip，避免下载 100MB）
    python tools/rankings/fill_data.py sync --no-intro-zip ~/Downloads/no-intro.zip

    # 2. 试运行，看每个机种能补多少
    python tools/rankings/fill_data.py fill

    # 3. 真正写入
    python tools/rankings/fill_data.py fill --write --report /tmp/ranking-report.json

    # 4. 应用联网调研得到的建议（只填空白，卡带 ID 必须带 source_url 与 verified）
    python tools/rankings/fill_data.py apply suggestions.json --write

缓存目录默认 `~/.cache/xgame-ranking-dats`，可用 `--cache` 或环境变量
`XGAME_DAT_CACHE` 覆盖。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RANKING_DIR = REPO_ROOT / "backend" / "search" / "rankings"
CATALOG_DIR = REPO_ROOT / "backend" / "search" / "catalog"
DEFAULT_CACHE = Path(os.environ.get("XGAME_DAT_CACHE", Path.home() / ".cache" / "xgame-ranking-dats"))

MAME_JSdelivr = "https://cdn.jsdelivr.net/gh/mamedev/mame@master/hash/{name}.xml"
MAME_RAW = "https://raw.githubusercontent.com/mamedev/mame/master/hash/{name}.xml"

# 榜单机种 → MAME hash 文件。一个机种可以对应多个文件（GB 榜单含 GBC、PCE 榜单含 CD）。
MAME_FILES: dict[str, list[str]] = {
    "nes": ["nes"],
    "snes": ["snes"],
    "n64": ["n64"],
    "gb": ["gameboy", "gbcolor"],
    "gba": ["gba"],
    "nds": ["nds"],
    "segaMD": ["megadriv"],
    "segaGG": ["gamegear"],
    "segaMS": ["sms"],
    "segaCD": ["megacd"],
    "sega32x": ["32x"],
    "segaSaturn": ["saturn"],
    "psx": ["psx"],
    "pce": ["pce", "pcecd"],
    "pcfx": ["pcfx"],
    "ngp": ["ngp"],
    "ws": ["wswan"],
    "atari2600": ["a2600"],
    "atari5200": ["a5200"],
    "atari7800": ["a7800"],
    "jaguar": ["jaguar"],
    "lynx": ["lynx"],
    "3do": ["3do"],
    "coleco": ["coleco"],
    "c64": ["c64_cart"],
}

# 榜单机种 → catalog 文件名（不带 .csv）。没有对应名录的机种走跨机种唯一译名。
CATALOG_STEMS: dict[str, list[str]] = {
    "nes": ["nes"],
    "snes": ["snes", "snes-sufami-turbo"],
    "n64": ["n64"],
    "gb": ["gb", "gbc"],
    "gba": ["gba"],
    "nds": ["nds"],
    "vb": ["vb"],
    "segaMD": ["segaMD"],
    "segaGG": ["segaGG"],
    "segaCD": ["segaCD"],
    "sega32x": ["sega32x"],
    "segaSaturn": ["segaSaturn"],
    "psx": ["psx"],
    "psp": ["psp"],
    "pce": ["pce", "pcecd"],
    "ngp": ["ngp"],
    "ws": ["ws"],
    "atari2600": ["atari2600"],
    "atari5200": ["atari5200"],
    "atari7800": ["atari7800"],
    "jaguar": ["jaguar"],
    "lynx": ["lynx"],
    "3do": ["3do"],
}

# No-Intro DAT：平台 → 压缩包内文件名前缀。
NOINTRO_PLATFORMS = {
    "nds": "Nintendo - Nintendo DS (Decrypted)",
    "gba": "Nintendo - Game Boy Advance (",
    "n64": "Nintendo - Nintendo 64 (BigEndian)",
    "vb": "Nintendo - Virtual Boy",
}

# No-Intro 的 4 位游戏编号 → 完整卡带编号的官方前缀。
NOINTRO_PREFIX = {"nds": "NTR", "gba": "AGB", "n64": "NUS", "vb": "VUE"}
REGION_SUFFIX = {
    "E": "USA",
    "J": "JPN",
    "P": "EUR",
    "K": "KOR",
    "C": "CHN",
    "U": "AUS",
    "A": "ASI",
}

# 非零售版本不拿来做卡带 ID（Demo/Beta 的编号也是真的，但不是玩家手里的那盘卡）。
NON_RETAIL = re.compile(
    r"\b(demo|kiosk|beta|proto(?:type)?|sample|preview|test|debug|unl|unlicensed|"
    r"aftermarket|pirate|program|hack|translation|patch|fixed)\b",
    re.I,
)

REGION_WORDS = (
    r"usa|u\.s\.a\.?|us|europe|japan|jpn|jp|world|asia|korea|kor|china|chn|taiwan|"
    r"hong kong|australia|aus|brazil|bra|canada|can|germany|france|spain|italy|"
    r"netherlands|sweden|denmark|norway|finland|russia|poland|portugal|mexico|"
    r"argentina|new zealand|south africa|india|singapore|malaysia|thailand|"
    r"philippines|indonesia|united kingdom|uk|england|ireland|belgium|switzerland|"
    r"austria|greece|turkey|israel|saudi arabia|uae|latam|latin america|eur"
)
LANG_CODES = (
    r"en|fr|de|es|it|ja|jp|ko|kr|zh|cn|tw|nl|sv|no|da|fi|pt|ru|pl|ca|cs|hu|tr|el|"
    r"ar|he|th|vi|id|ms|ro|uk|bg|hr|sk|sl|et|lv|lt|is|ga|cy"
)
REV_WORDS = (
    r"rev(?:ision)?\s*[a-z0-9.]+|v(?:ersion)?\s*[0-9.]+|beta|proto(?:type)?|demo|"
    r"sample|unl|unlicensed|aftermarket|pirate|program|alt|fixed|prg[0-9]|ch[0-9]|"
    r"m[0-9]{1,2}|e[0-9]|p[0-9]|kiosk|bundle|promo|preview|test|debug|bootleg|hack|"
    r"translation|patch"
)

# 长音符号 → 双写元音：MobyGames 用 macron，MAME/No-Intro 常写 ou/uu。
_MACRONS = str.maketrans(
    {
        "ā": "aa",
        "ī": "ii",
        "ū": "uu",
        "ē": "ee",
        "ō": "ou",
        "Ā": "AA",
        "Ī": "II",
        "Ū": "UU",
        "Ē": "EE",
        "Ō": "OU",
    }
)

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")

# 名录里有 `[PS2]`、`（美版）` 这类平台/地区标签，补进榜单时去掉。
_ZH_PLATFORM_TAG = re.compile(
    r"^(?:\[(?:PS[0-9]|PSP|PSV|FC|SFC|GB|GBC|GBA|NDS|N64|MD|SS|DC|ARC|PC|DOS|街机)\])+",
    re.I,
)
_ZH_REGION_TAG = (
    r"美版|日版|欧版|世界版|亚洲版|韩版|中文版|英文版|日文版|汉化版|演示版|试玩版|"
    r"测试版|工程版|修正版|无敌版|盗版|正版|简中|繁中|美欧版|日英版|多语言|日文|英文|"
    r"非官方版|未授权版|版本\s*[0-9.]+|v[0-9.]+|修正版\s*[0-9]*|"
    r"巴西|巴西版|加拿大|加拿大版|澳大利亚|澳大利亚版|德国|德国版|法国|法国版|"
    r"意大利|意大利版|西班牙|西班牙版|荷兰|荷兰版|瑞典|瑞典版|丹麦|丹麦版|"
    r"挪威|挪威版|芬兰|芬兰版|俄罗斯|俄罗斯版|波兰|波兰版|葡萄牙|葡萄牙版|"
    r"墨西哥|墨西哥版|阿根廷|阿根廷版"
)


# ---------------------------------------------------------------------------
# 文本归一化
# ---------------------------------------------------------------------------


def _is_tag_content(text: str) -> bool:
    text = text.strip()
    if not text:
        return True
    parts = [p.strip() for p in re.split(r"[,/;]", text)]
    zh_parts = [p.strip() for p in re.split(r"[,/;\s]+", text)]
    if re.fullmatch(_ZH_REGION_TAG, text):
        return True
    if all(re.fullmatch(_ZH_REGION_TAG, p) for p in zh_parts if p):
        return True
    if all(re.fullmatch(REGION_WORDS, p, re.I) for p in parts if p):
        return True
    # 中英混写，如 `日版, USA`、`美版, 巴西`
    if all(
        re.fullmatch(_ZH_REGION_TAG + "|" + REGION_WORDS + "|" + LANG_CODES, p, re.I)
        for p in zh_parts
        if p
    ):
        return True
    if all(re.fullmatch(LANG_CODES, p, re.I) for p in parts if p):
        return True
    if re.fullmatch(REV_WORDS, text, re.I):
        return True
    if all(
        re.fullmatch(REGION_WORDS + "|" + LANG_CODES + "|" + REV_WORDS, p, re.I)
        for p in parts
        if p
    ):
        return True
    if re.fullmatch(r"[a-z0-9]{1,4}", text, re.I) and text.upper() in {
        "USA",
        "EUR",
        "JPN",
        "WORLD",
        "ASIA",
        "KOR",
        "CHN",
        "AUS",
        "BRA",
        "CAN",
    }:
        return True
    return False


def strip_tags(text: str) -> str:
    """剥掉**可识别**的地区/语言/版本标签，保留有意义的括号（如版本名）。"""

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        return " " if _is_tag_content(inner) else match.group(0)

    text = re.sub(r"\(([^()]*)\)|\[([^\[\]]*)\]", repl, text)
    return re.sub(r"\s+", " ", text).strip()


def clean_zh(text: str) -> str:
    """去掉名录中文名里的平台/地区/版本标签，得到可直接展示的中文名。"""
    text = unicodedata.normalize("NFKC", text or "")
    previous = None
    while previous != text:
        previous, text = text, _ZH_PLATFORM_TAG.sub("", text).strip()
    text = strip_tags(text)
    # 名录里有 `(美版 欧版` 这种漏了右括号的坏行，直接截掉尾巴。
    if text.count("(") > text.count(")"):
        text = text[: text.rfind("(")]
    return text.strip(" -:：,，;；、")


def norm(text: str) -> str:
    """标题归一：大小写、全半角、变音符号、标点、&/and、长音符号统一。"""
    text = unicodedata.normalize("NFKC", text or "").translate(_MACRONS)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"\s*&\s*", " and ", text)
    text = re.sub(r"[^0-9a-z㐀-䶿一-鿿]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_keys(text: str) -> list[str]:
    """标题匹配键：容忍常见写法差异，但不做模糊匹配。

    - `Disney's DuckTales` ↔ `DuckTales`
    - `Addams Family, The` ↔ `The Addams Family`
    - `Spider-Man / Venom` ↔ `Spider-Man & Venom`
    - `NewZealand` ↔ `New Zealand`（驼峰拆分）
    - `New Zealand` ↔ `NewZealand`（去空格）
    """
    base = norm(strip_tags(text))
    out: list[str] = []

    def add(value: str) -> None:
        if value and value not in out:
            out.append(value)

    add(base)
    for prefix in ("walt disney s ", "disney s ", "disney "):
        if base.startswith(prefix):
            add(base[len(prefix):])
    if base.endswith(" the"):
        add("the " + base[:-4])
    if "/" in text:
        add(norm(strip_tags(text.replace("/", " & "))))
    if not _CJK.search(text):
        split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        if split != text:
            add(norm(strip_tags(split)))
        add(base.replace(" ", ""))
        add(base.replace(" and ", " "))
    for value in list(out):
        if value.startswith("the "):
            add(value[4:])
    return out


def region_of_label(label: str) -> str:
    low = label.strip().lower().strip("()[]")
    if re.search(r"usa|u\.s\.a|america", low):
        return "us"
    if re.search(r"japan|jpn|\bjp\b", low):
        return "jp"
    return "other"


def classify_regions(desc: str, serial: str = "") -> set[str]:
    """从标题标签、序列号后缀、PS 盘号前缀判断区域。"""
    regions: set[str] = set()
    for tag in re.findall(r"\(([^()]*)\)", desc):
        low = tag.lower()
        if re.search(r"usa|u\.s\.a|america", low):
            regions.add("us")
        elif re.search(r"japan|jpn", low):
            regions.add("jp")
        elif re.search(r"europe|eur|world|asia|korea|china|australia|brazil|canada", low):
            regions.add("other")
    if re.search(r"[-_ ]USA$", serial, re.I):
        regions.add("us")
    elif re.search(r"[-_ ]JPN$", serial, re.I):
        regions.add("jp")
    elif re.search(
        r"[-_ ](EUR|PAL|AUS|KOR|CHN|CAN|BRA|ASI|NOE|FAH|UKV|FRG|ITA|ESP|HOL|"
        r"SCN|SWE|DEN|NOR|FIN|POL|POR|RUS|GER|FRA)$",
        serial,
        re.I,
    ):
        regions.add("other")
    # PS1/PS2/PSP 盘号前缀是官方区域标识。
    if re.match(r"(SLUS|SCUS|ULUS|UCUS|LSP|PAPX)", serial, re.I):
        regions.add("us")
    elif re.match(r"(SLPS|SLPM|SCPS|ULJM|UCJS|SLKA)", serial, re.I):
        regions.add("jp")
    elif re.match(r"(SLES|SCES|ULES|UCES|SLED|SLKA|ULAS|UCAS|ULKS|UCKS)", serial, re.I):
        regions.add("other")
    return regions


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class RankingRow:
    platform: str
    line: int
    fields: list[str]

    @property
    def zh(self) -> str:
        return self.fields[0].strip() if len(self.fields) > 0 else ""

    @zh.setter
    def zh(self, value: str) -> None:
        while len(self.fields) < 1:
            self.fields.append("")
        self.fields[0] = value

    @property
    def en(self) -> str:
        return self.fields[1].strip() if len(self.fields) > 1 else ""

    @property
    def score(self) -> str:
        return self.fields[2].strip() if len(self.fields) > 2 else ""

    @property
    def cid(self) -> str:
        return self.fields[3].strip() if len(self.fields) > 3 else ""

    @cid.setter
    def cid(self, value: str) -> None:
        while len(self.fields) < 4:
            self.fields.append("")
        self.fields[3] = value


@dataclass
class SourceHit:
    ids: list[str]
    source: str


# ---------------------------------------------------------------------------
# 榜单读写
# ---------------------------------------------------------------------------


def read_ranking(path: Path) -> tuple[list[RankingRow], bool]:
    rows: list[RankingRow] = []
    has_header = False
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for idx, raw in enumerate(reader, start=1):
            if not any(cell.strip() for cell in raw):
                continue
            if not has_header and [c.strip() for c in raw[:4]] == [
                "中文名",
                "英文名",
                "评分",
                "卡带ID",
            ]:
                has_header = True
                continue
            if len(raw) < 2 or not raw[1].strip():
                continue
            rows.append(RankingRow(path.stem, idx, list(raw)))
    return rows, has_header


def write_ranking(path: Path, rows: list[list[str]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\r\n")
        for row in rows:
            writer.writerow(row)
    os.replace(tmp, path)


def ranking_paths(platforms: list[str] | None = None) -> list[Path]:
    out = []
    for path in sorted(RANKING_DIR.glob("*.csv")):
        if path.stem == "README":
            continue
        if platforms and path.stem not in platforms:
            continue
        out.append(path)
    return out


def load_all(platforms: list[str] | None = None) -> dict[Path, tuple[list[list[str]], bool]]:
    result: dict[Path, tuple[list[list[str]], bool]] = {}
    for path in ranking_paths(platforms):
        rows, has_header = read_ranking(path)
        result[path] = ([r.fields for r in rows], has_header)
    return result


# ---------------------------------------------------------------------------
# catalog 中文名
# ---------------------------------------------------------------------------


def load_catalog() -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str]]]]:
    """返回 (按文件名的索引, 全局索引)。key 是归一化标题，值是 (中文名, 原英文名)。"""
    by_stem: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    global_idx: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for path in sorted(CATALOG_DIR.glob("*.csv")):
        if path.stem == "README":
            continue
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if len(row) < 2:
                    continue
                zh, en = clean_zh(row[0].strip()), row[1].strip()
                if not zh or not en or not _CJK.search(zh):
                    continue
                for key in title_keys(en):
                    by_stem[path.stem][key].append((zh, en))
                    global_idx[key].append((zh, en))
    return by_stem, global_idx


def pick_zh(candidates: list[tuple[str, str]], require_unique: bool = False) -> str | None:
    """同一条目可能有多个地区译名：取出现次数最多的；并列时取名录里靠前的那条。

    同一机种内英文名相同基本就是同一个游戏，地区译名不同不影响使用；
    跨机种匹配要求唯一译名，避免把同名不同游戏翻错。
    """
    if not candidates:
        return None
    counts = Counter(zh for zh, _ in candidates)
    if require_unique and len(counts) > 1:
        ranked = counts.most_common()
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return None
    top_count = max(counts.values())
    for zh, _ in candidates:
        if counts[zh] == top_count:
            return zh
    return None


def catalog_zh(
    en: str,
    platform: str,
    by_stem: dict[str, dict[str, list[tuple[str, str]]]],
    global_idx: dict[str, list[tuple[str, str]]],
) -> tuple[str, str] | None:
    keys = title_keys(en)
    stems = CATALOG_STEMS.get(platform, [])
    for key in keys:
        merged: list[tuple[str, str]] = []
        for stem in stems:
            merged.extend(by_stem.get(stem, {}).get(key, []))
        picked = pick_zh(merged)
        if picked:
            return picked, "catalog"
    # 跨机种只接受唯一译名；多个译名说明有歧义，留给联网补录。
    for key in keys:
        picked = pick_zh(global_idx.get(key, []), require_unique=True)
        if picked:
            return picked, "catalog-cross"
    return None


# ---------------------------------------------------------------------------
# MAME
# ---------------------------------------------------------------------------


def split_serials(value: str) -> list[str]:
    """按括号外的逗号/分号拆分 MAME 的 serial 字段。"""
    parts: list[str] = []
    depth = 0
    cur = ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch in ",;/" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def clean_serial(piece: str) -> tuple[str, set[str]] | None:
    """清理一段 serial，返回 (编号, 区域集合)；明显不是编号的返回 None。"""
    regions: set[str] = set()
    for tag in re.findall(r"\(([^()]*)\)", piece):
        if re.fullmatch(REGION_WORDS, tag.strip(), re.I):
            regions.add(region_of_label(tag))
    bare = re.sub(r"\s*\([^()]*\)", "", piece).strip().upper()
    if not bare:
        return None
    if re.search(r"PART\s*NO|^N/?A$|^!|^#+$|^0+$", bare):
        return None
    if any(ch.isspace() for ch in bare):
        # 带空格的多数是 "Part No. 7004 0894" 或两个编号拼在一起；不猜。
        return None
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._/\-]{0,39}", bare):
        return None
    regions |= classify_regions("", bare)
    return bare, regions


def load_mame(cache: Path, platform: str) -> dict[str, list[SourceHit]]:
    """返回 normalized title → 按区域优先级排列的候选 ID。

    同一个标题在 MAME 里会按地区拆成多条（USA / Europe / Japan），必须在
    **整个标题**上合并后再选号，否则会按文件顺序先拿到欧版。
    """
    merged: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for name in MAME_FILES.get(platform, []):
        path = cache / "mame" / f"{name}.xml"
        if not path.exists() or path.stat().st_size < 1000:
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for software in root.iter("software"):
            desc = (software.findtext("description") or "").strip()
            if not desc or (desc.startswith("[") and "BIOS" in desc):
                continue
            if NON_RETAIL.search(desc):
                continue
            serials = []
            for info in software.findall("info"):
                if info.get("name") == "serial":
                    serials.append(info.get("value") or "")
            if not serials:
                continue
            desc_regions = classify_regions(desc)
            candidates: dict[str, list[str]] = defaultdict(list)
            for raw in serials:
                for piece in split_serials(raw):
                    cleaned = clean_serial(piece)
                    if not cleaned:
                        continue
                    value, regions = cleaned
                    # MAME 的 `M/SNS-...` 里 `M/` 表示 Made in Mexico，不是编号的一部分。
                    if platform == "snes" and value.startswith("M/"):
                        value = value[2:]
                    if not id_allowed(platform, value):
                        continue
                    for region in regions or desc_regions or {"other"}:
                        if value not in candidates[region]:
                            candidates[region].append(value)
            if not candidates:
                continue
            for key in title_keys(desc):
                for region, values in candidates.items():
                    for value in values:
                        if value not in merged[key][region]:
                            merged[key][region].append(value)
    idx: dict[str, list[SourceHit]] = {}
    for key, regions in merged.items():
        ordered = _order_ids(regions)
        if ordered:
            idx[key] = [SourceHit(ordered, "mame")]
    return idx


# 世嘉系 DAT 里有些 serial 只是完整编号的后半截（如 `4407`、`2530-50`），
# 按现有榜单里出现过的编号形状过滤，免得写进榜单却不是卡带标签上的编号。
SEGA_ID_PATTERNS = {
    "segaMD": r"^(MK-\d+|G-\d+|T-\d+|\d{6,})(-\d+)?$",
    "segaGG": r"^(T-\d+|G-\d+|MK-\d+|\d{6,})(-\d+)?$",
    "segaMS": r"^(MK-\d+|G-\d+|C-\d+|\d{4,})(-\d+)?$",
    "segaCD": r"^(MK-\d+|G-\d+|T-\d+|\d{6,})(-\d+)?$",
    "sega32x": r"^(MK-\d+|G-\d+|T-\d+|\d{6,})(-\d+)?$",
    "segaSaturn": r"^(T-\d+[A-Z]?|MK-?\d+|GS-\d+|ST-\d+|\d{6,})(-\d+)?$",
}


PLATFORM_ID_PATTERNS = {
    "gba": r"^AGB-[A-Z0-9]{4}-[A-Z]{3}$",
    "nds": r"^NTR-.+",
    "n64": r"^NUS-.+",
    "vb": r"^VUE-.+",
    "gb": r"^(DMG|CGB)-.+",
    "snes": r"^(SNS|SHVC|SNSP)-.+",
    "psx": r"^(SLUS|SCUS|SLES|SCES|SLPS|SLPM|SCPS|SIPS|SLKA|SLAS|LSP|PAPX)-.+",
}


def id_allowed(platform: str, value: str) -> bool:
    if value.endswith(("-", ".", "_", "/")):
        return False
    if platform in SEGA_ID_PATTERNS and not re.fullmatch(
        SEGA_ID_PATTERNS[platform], value, re.I
    ):
        return False
    if platform in PLATFORM_ID_PATTERNS and not re.fullmatch(
        PLATFORM_ID_PATTERNS[platform], value, re.I
    ):
        return False
    return True


def _order_ids(candidates: dict[str, list[str]]) -> list[str]:
    """按「美版 + 日版」优先的规则取号。

    - 有美版：取美版；有日版再补一个日版（最多两个）。
    - 没美版有日版：只取日版。
    - 都没有：取一个其他地区。
    """
    us = candidates.get("us", [])
    jp = candidates.get("jp", [])
    other = candidates.get("other", [])
    if us:
        return [us[0]] + ([jp[0]] if jp else [])
    if jp:
        return [jp[0]]
    if other:
        return [other[0]]
    return []


# ---------------------------------------------------------------------------
# No-Intro
# ---------------------------------------------------------------------------


def sync_no_intro(zip_path: Path, cache: Path) -> dict[str, str]:
    import zipfile

    out_dir = cache / "no-intro"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for platform, prefix in NOINTRO_PLATFORMS.items():
            hits = [n for n in names if n.startswith(prefix)]
            if not hits:
                continue
            name = hits[0]
            target = out_dir / Path(name).name
            with zf.open(name) as src, target.open("wb") as dst:
                dst.write(src.read())
            manifest[platform] = str(target)
    (cache / "no-intro" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def load_no_intro(cache: Path, platform: str) -> dict[str, list[SourceHit]]:
    manifest_path = cache / "no-intro" / "manifest.json"
    if not manifest_path.exists() or platform not in NOINTRO_PLATFORMS:
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = Path(manifest.get(platform, ""))
    if not path.exists():
        return {}
    merged: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {}
    for game in root.iter("game"):
        desc = (game.findtext("description") or game.get("name") or "").strip()
        if not desc or NON_RETAIL.search(desc):
            continue
        serial = ""
        for rom in game.findall("rom"):
            value = (rom.get("serial") or "").strip()
            if value and value.lower() not in ("n/a", "!n/a", "!none"):
                serial = value
                break
        if not serial:
            continue
        value = construct_no_intro_id(platform, serial)
        if not value:
            continue
        regions = classify_regions(desc, serial) or {"other"}
        for key in title_keys(desc):
            for region in regions:
                if value not in merged[key][region]:
                    merged[key][region].append(value)
    idx: dict[str, list[SourceHit]] = {}
    for key, regions in merged.items():
        ordered = _order_ids(regions)
        if ordered:
            idx[key] = [SourceHit(ordered, "no-intro")]
    return idx


def construct_no_intro_id(platform: str, serial: str) -> str | None:
    prefix = NOINTRO_PREFIX.get(platform)
    if not prefix:
        return None
    if not re.fullmatch(r"[A-Z0-9]{4}", serial):
        return None
    suffix = REGION_SUFFIX.get(serial[-1])
    if suffix not in ("USA", "JPN", "EUR"):
        return None
    return f"{prefix}-{serial}-{suffix}"


# ---------------------------------------------------------------------------
# 旧版 ranking.csv（可选）
# ---------------------------------------------------------------------------

CONSOLE_TO_PLATFORM = {
    "FC": "nes",
    "SFC": "snes",
    "N64": "n64",
    "GB/GBC": "gb",
    "GBA": "gba",
    "NDS": "nds",
    "PS1": "psx",
    "PSP": "psp",
    "MD": "segaMD",
    "SMS": "segaMS",
    "GG": "segaGG",
    "SEGA CD": "segaCD",
    "SS": "segaSaturn",
    "ATARI 2600": "atari2600",
    "3DO": "3do",
    "COLECOVISION": "coleco",
    "PCE": "pce",
    "WS": "ws",
    "C64": "c64",
    "C128": "c128",
    "PLUS/4": "plus4",
    "VIC-20": "vic20",
    "AMIGA": "amiga",
    "DOS": "dos",
    "ARCADE": "arcade",
    "NGPC": "ngp",
    "LYNX": "lynx",
    "ATARI 5200": "atari5200",
    "JAGUAR": "jaguar",
    "ATARI 7800": "atari7800",
    "PC-FX": "pcfx",
    "PET": "pet",
    "32X": "sega32x",
    "VB": "vb",
}


def load_legacy(path: Path) -> dict[str, list[tuple[str, str, str]]]:
    """旧版五列 CSV → platform → [(中文名, 英文名, 卡带ID)]。"""
    out: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if len(row) < 5 or row[0].strip() == "序号":
                continue
            platform = CONSOLE_TO_PLATFORM.get(row[1].strip().upper())
            if not platform:
                continue
            out[platform].append((row[2].strip(), row[3].strip(), row[4].strip()))
    return out


# ---------------------------------------------------------------------------
# 核心补全
# ---------------------------------------------------------------------------


def find_source_hit(en: str, idx: dict[str, list[SourceHit]]) -> SourceHit | None:
    for key in title_keys(en):
        hits = idx.get(key)
        if not hits:
            continue
        for hit in hits:
            if hit.ids:
                return hit
    return None


@dataclass
class Change:
    platform: str
    line: int
    en: str
    field: str
    old: str
    new: str
    source: str


@dataclass
class PlatformStat:
    rows: int = 0
    miss_zh: int = 0
    miss_id: int = 0
    zh_filled: Counter = field(default_factory=Counter)
    id_filled: Counter = field(default_factory=Counter)


def fill_rows(
    platform: str,
    rows: list[RankingRow],
    by_stem: dict[str, dict[str, list[tuple[str, str]]]],
    global_catalog: dict[str, list[tuple[str, str]]],
    mame_idx: dict[str, list[SourceHit]],
    nointro_idx: dict[str, list[SourceHit]],
    legacy: dict[str, list[tuple[str, str, str]]] | None,
) -> tuple[list[Change], PlatformStat]:
    changes: list[Change] = []
    stat = PlatformStat(rows=len(rows))
    legacy_idx: dict[str, tuple[str, str, str]] = {}
    if legacy:
        for zh, en, cid in legacy.get(platform, []):
            for key in title_keys(en):
                legacy_idx.setdefault(key, (zh, en, cid))

    for row in rows:
        if not row.zh:
            stat.miss_zh += 1
            got = None
            if legacy_idx:
                for key in title_keys(row.en):
                    if key in legacy_idx:
                        got = (legacy_idx[key][0], "legacy")
                        break
            if not got:
                got = catalog_zh(row.en, platform, by_stem, global_catalog)
            if got and got[0] and _CJK.search(got[0]):
                row.zh = got[0]
                stat.zh_filled[got[1]] += 1
                changes.append(Change(platform, row.line, row.en, "zh", "", got[0], got[1]))
        if not row.cid:
            stat.miss_id += 1
            got = None
            # MAME 优先：它的 serial 是卡带标签上的完整编号。
            for idx in (mame_idx, nointro_idx):
                hit = find_source_hit(row.en, idx)
                if hit:
                    got = (hit.ids[:2], hit.source)
                    break
            if got and got[0]:
                row.cid = ";".join(got[0])
                stat.id_filled[got[1]] += 1
                changes.append(Change(platform, row.line, row.en, "cid", "", row.cid, got[1]))
    return changes, stat


def fill(
    platforms: list[str] | None,
    cache: Path,
    write: bool,
    legacy_path: Path | None,
    report_path: Path | None,
) -> int:
    by_stem, global_catalog = load_catalog()
    legacy = load_legacy(legacy_path) if legacy_path else None
    all_changes: list[Change] = []
    stats: dict[str, PlatformStat] = {}

    for path in ranking_paths(platforms):
        platform = path.stem
        rows, has_header = read_ranking(path)
        mame_idx = load_mame(cache, platform)
        nointro_idx = load_no_intro(cache, platform)
        changes, stat = fill_rows(
            platform, rows, by_stem, global_catalog, mame_idx, nointro_idx, legacy
        )
        stats[platform] = stat
        all_changes.extend(changes)
        if write and changes:
            out_rows = [row.fields for row in rows]
            if has_header:
                out_rows.insert(0, ["中文名", "英文名", "评分", "卡带ID"])
            write_ranking(path, out_rows)

    _print_stats(stats)
    if report_path:
        report = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cache": str(cache),
            "platforms": {
                platform: {
                    "rows": stat.rows,
                    "miss_zh": stat.miss_zh,
                    "miss_id": stat.miss_id,
                    "zh_filled": dict(stat.zh_filled),
                    "id_filled": dict(stat.id_filled),
                }
                for platform, stat in sorted(stats.items())
            },
            "changes": [change.__dict__ for change in all_changes],
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告写入 {report_path}")
    return 0


def _print_stats(stats: dict[str, PlatformStat]) -> None:
    print(f"{'机种':12} {'行数':>5} {'缺中文':>6} {'补中文':>6} {'缺ID':>6} {'补ID':>6}")
    total = PlatformStat()
    for platform, stat in sorted(stats.items()):
        total.rows += stat.rows
        total.miss_zh += stat.miss_zh
        total.miss_id += stat.miss_id
        total.zh_filled.update(stat.zh_filled)
        total.id_filled.update(stat.id_filled)
        print(
            f"{platform:12} {stat.rows:5} {stat.miss_zh:6} "
            f"{sum(stat.zh_filled.values()):6} {stat.miss_id:6} "
            f"{sum(stat.id_filled.values()):6}"
        )
    print(
        f"{'合计':12} {total.rows:5} {total.miss_zh:6} "
        f"{sum(total.zh_filled.values()):6} {total.miss_id:6} "
        f"{sum(total.id_filled.values()):6}"
    )
    print("中文名来源:", dict(total.zh_filled))
    print("卡带ID来源:", dict(total.id_filled))


# ---------------------------------------------------------------------------
# 输出待补清单（交给联网调研）
# ---------------------------------------------------------------------------


def gaps(
    platforms: list[str] | None, outdir: Path, top: int, include_all: bool
) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    summary = []
    for path in ranking_paths(platforms):
        platform = path.stem
        rows, _ = read_ranking(path)
        items = []
        for rank, row in enumerate(rows, start=1):
            need_zh, need_id = not row.zh, not row.cid
            if not need_zh and not need_id:
                continue
            if need_zh and need_id:
                priority = 3 if rank <= top else 4
            elif need_id:
                priority = 2
            else:
                priority = 1
            if priority == 4 and not include_all:
                continue
            items.append(
                {
                    "line": row.line,
                    "rank": rank,
                    "priority": priority,
                    "missing": "both" if need_zh and need_id else ("zh" if need_zh else "cartridge_id"),
                    "en": row.en,
                    "zh": row.zh,
                    "cartridge_id": row.cid,
                    "score": row.score,
                }
            )
        target = outdir / f"{platform}.json"
        target.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        counts = Counter(item["priority"] for item in items)
        summary.append((platform, len(items), counts.get(1, 0), counts.get(2, 0), counts.get(3, 0), counts.get(4, 0)))
    print(f"{'机种':12} {'待补':>5} {'有ID缺名':>8} {'有名缺ID':>8} {'都缺(前N)':>9} {'都缺(其余)':>10}")
    for platform, total, p1, p2, p3, p4 in summary:
        print(f"{platform:12} {total:5} {p1:8} {p2:8} {p3:9} {p4:10}")
    print(f"清单目录 {outdir}")
    return 0


# ---------------------------------------------------------------------------
# 同步 DAT
# ---------------------------------------------------------------------------


def _download(url: str, target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "xgame-ranking-fill/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp, target.open("wb") as fh:
                fh.write(resp.read())
            if target.stat().st_size > 1000:
                return True
        except Exception as exc:  # noqa: BLE001 - 下载重试
            print(f"  下载失败 {url} ({attempt + 1}/3): {exc}")
            time.sleep(2)
    return False


def sync(cache: Path, no_intro_zip: Path | None, mame_only: bool) -> int:
    added = 0
    for name in sorted({n for names in MAME_FILES.values() for n in names}):
        target = cache / "mame" / f"{name}.xml"
        if target.exists() and target.stat().st_size > 1000:
            continue
        for url in (MAME_JSdelivr.format(name=name), MAME_RAW.format(name=name)):
            if _download(url, target):
                print(f"  MAME {name}.xml")
                added += 1
                break
    if no_intro_zip and not mame_only:
        if not no_intro_zip.exists():
            print(f"No-Intro zip 不存在: {no_intro_zip}", file=sys.stderr)
            return 1
        manifest = sync_no_intro(no_intro_zip, cache)
        print(f"  No-Intro 解出 {len(manifest)} 个 DAT: {sorted(manifest)}")
        added += len(manifest)
    print(f"缓存目录 {cache}，本次新增 {added} 项")
    return 0


# ---------------------------------------------------------------------------
# 应用联网调研建议
# ---------------------------------------------------------------------------

ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._ /\-]{1,39}$")

# 联网补录的卡带 ID 只认这些数据库/官方站，避免把普通网页的二手信息写进来。
ID_SOURCE_HOSTS = (
    "redump.org",
    "no-intro.org",
    "mamedev.org",
    "github.com",
    "raw.githubusercontent.com",
    "cdn.jsdelivr.net",
    "wikipedia.org",
    "segaretro.org",
    "gamefaqs.gamespot.com",
    "nintendo.com",
    "sony.com",
    "sega.com",
    "atari.com",
    "mobygames.com",
)


def _valid_suggestion(item: dict) -> str | None:
    if not isinstance(item, dict):
        return "不是对象"
    platform = item.get("platform")
    if platform not in {p.stem for p in ranking_paths()}:
        return "未知机种"
    if not isinstance(item.get("line"), int) or item["line"] < 1:
        return "line 无效"
    if not str(item.get("en", "")).strip():
        return "en 为空"
    zh = clean_zh(str(item.get("zh", "")).strip())
    cid = str(item.get("cartridge_id", "")).strip().upper()
    if not zh and not cid:
        return "zh 与 cartridge_id 都为空"
    if zh and not _CJK.search(zh):
        return "zh 不含中文"
    url = str(item.get("source_url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return "缺少 source_url"
    if cid:
        if not item.get("verified"):
            return "卡带 ID 未标记 verified"
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in ID_SOURCE_HOSTS):
            return f"卡带 ID 来源不是权威数据库: {host}"
        parts = [p.strip() for p in re.split(r"[;、,，/；]", cid) if p.strip()]
        if not 1 <= len(parts) <= 2:
            return "卡带 ID 数量不是 1~2 个"
        if any(not ID_RE.fullmatch(p) for p in parts):
            return f"卡带 ID 格式可疑: {cid}"
        cid = ";".join(parts)
    return None


def apply_suggestions(path: Path, write: bool, report_path: Path | None) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("suggestions", [])
    if not isinstance(data, list):
        print("建议文件必须是 JSON 数组（或 {suggestions: [...]}）", file=sys.stderr)
        return 1

    grouped: dict[str, list[dict]] = defaultdict(list)
    rejected = Counter()
    for item in data:
        reason = _valid_suggestion(item)
        if reason:
            rejected[reason] += 1
            continue
        grouped[item["platform"]].append(item)
    if rejected:
        print("拒绝的建议:", dict(rejected))

    all_changes: list[Change] = []
    for platform, items in sorted(grouped.items()):
        path_csv = RANKING_DIR / f"{platform}.csv"
        rows, has_header = read_ranking(path_csv)
        by_line = {row.line: row for row in rows}
        platform_changes: list[Change] = []
        for item in items:
            row = by_line.get(item["line"])
            if row is None or norm(row.en) != norm(item["en"]):
                continue
            if not row.zh and item.get("zh"):
                row.zh = clean_zh(str(item["zh"]))
                platform_changes.append(
                    Change(platform, row.line, row.en, "zh", "", row.zh, "web")
                )
            if not row.cid and item.get("cartridge_id"):
                row.cid = ";".join(
                    p.strip().upper()
                    for p in re.split(r"[;、,，/；]", str(item["cartridge_id"]))
                    if p.strip()
                )
                platform_changes.append(
                    Change(platform, row.line, row.en, "cid", "", row.cid, "web")
                )
        all_changes.extend(platform_changes)
        if write and platform_changes:
            out = [r.fields for r in rows]
            if has_header:
                out.insert(0, ["中文名", "英文名", "评分", "卡带ID"])
            write_ranking(path_csv, out)
    print(f"应用 {len(all_changes)} 处建议")
    for change in all_changes[:20]:
        print(f"  {change.platform}:{change.line} {change.field} -> {change.new} ({change.en})")
    if report_path:
        report_path.write_text(
            json.dumps([c.__dict__ for c in all_changes], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="补全榜单 CSV 的中文名与卡带 ID")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="下载/解压 DAT 数据源")
    p_sync.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p_sync.add_argument("--no-intro-zip", type=Path, help="本地 No-Intro 全量 DAT 压缩包")
    p_sync.add_argument("--mame-only", action="store_true", help="只同步 MAME")

    p_fill = sub.add_parser("fill", help="按 catalog 与 DAT 补全")
    p_fill.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p_fill.add_argument("--write", action="store_true", help="真正写回 CSV（默认只试运行）")
    p_fill.add_argument("--platforms", help="逗号分隔的机种，如 nes,snes,gba")
    p_fill.add_argument("--legacy", type=Path, help="旧版五列 ranking.csv，用于回收人工整理数据")
    p_fill.add_argument("--report", type=Path, help="输出 JSON 报告")

    p_apply = sub.add_parser("apply", help="应用联网调研建议 JSON")
    p_apply.add_argument("suggestions", type=Path)
    p_apply.add_argument("--write", action="store_true")
    p_apply.add_argument("--report", type=Path)

    p_gaps = sub.add_parser("gaps", help="输出待补清单 JSON，供联网调研")
    p_gaps.add_argument("--outdir", type=Path, default=Path("/tmp/xgame-ranking-gaps"))
    p_gaps.add_argument("--platforms", help="逗号分隔的机种")
    p_gaps.add_argument("--top", type=int, default=20, help="都缺时只列出前 N 名")
    p_gaps.add_argument("--all", action="store_true", help="连排名靠后的都缺行也输出")

    args = parser.parse_args(argv)
    if args.command == "sync":
        return sync(args.cache, args.no_intro_zip, args.mame_only)
    if args.command == "fill":
        platforms = (
            [p.strip() for p in args.platforms.split(",") if p.strip()]
            if args.platforms
            else None
        )
        return fill(platforms, args.cache, args.write, args.legacy, args.report)
    if args.command == "gaps":
        platforms = (
            [p.strip() for p in args.platforms.split(",") if p.strip()]
            if args.platforms
            else None
        )
        return gaps(platforms, args.outdir, args.top, args.all)
    return apply_suggestions(args.suggestions, args.write, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
