#!/usr/bin/env python3
"""机型简史的素材抓取脚本。

只做三件事，不写业务代码：

1. 从中文/英文维基抓正文，按 `<h2>` 分区拆成段落，存到 `/tmp/platform-intros-raw/`。
2. 从 Wikimedia Commons 抓游戏机图与卡带/载体图，压成 WebP 放进
   `frontend/src/assets/platforms/<id>/`。
3. 生成 `frontend/src/constants/platformIntros/images.js`（显式 import + 图片署名）。

正文定稿在 `frontend/src/constants/platformIntros/index.js` 里人工维护，本脚本不覆盖它。

用法：

    python scripts/build-platform-intros.py --only nes
    python scripts/build-platform-intros.py
    python scripts/build-platform-intros.py --write-images-js

网络请求会限速（默认 1.5 秒），429 时指数退避。重复运行是幂等的：
已下载且大小不为 0 的图片会跳过，加 `--force` 强制重下。
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = ROOT / "frontend" / "src" / "assets" / "platforms"

# 脚本输出统一走 Windows 包里的同一份实现（标签与颜色只有一处定义）。
sys.path.insert(0, str(ROOT / "packaging" / "windows"))
from xgame_console import emit  # noqa: E402
IMAGES_JS = ROOT / "frontend" / "src" / "constants" / "platformIntros" / "images.js"
RAW_DIR = Path("/tmp/platform-intros-raw")

UA = {
    "User-Agent": "xg-platform-intros/1.0 (personal self-hosted project)",
    "Accept-Language": "zh-cn,zh;q=0.9,en;q=0.5",
}
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKI_API = "https://api.wikimedia.org/core/v1/wikipedia/{lang}/page/{title}/html"

IMAGE_WIDTH = 900
WEBP_QUALITY = 80
REQUEST_DELAY = 1.5

# 许可白名单：只收自由许可，遇到合理使用或未标注的一律跳过。
FREE_LICENSES = (
    "public domain",
    "cc0",
    "cc by",
    "cc-by",
    "cc by-sa",
    "cc-by-sa",
    "cc by 2.0",
    "cc by 3.0",
    "cc by 4.0",
)

# 36 个游戏类型的抓取清单。
# gallery 是 Evan-Amos（Vanamo）图库名；没有图库的机种走 category 检索。
# media_queries 用来在 Commons 搜卡带/光盘/软盘等载体照片。
MANIFEST: list[dict] = [
    {
        "id": "flash", "year": 1996, "maker": "Macromedia / Adobe", "generation": "载体类型",
        "media_label": "SWF 文件", "zh": None, "en": "Adobe Flash",
        "gallery": [], "category": [], "media_queries": [],
        "special_copy": [
            {"from": "frontend/src/assets/flash-logo.png", "target": "console-1"},
        ],
    },
    {
        "id": "h5", "year": 2008, "maker": "W3C / 浏览器厂商", "generation": "载体类型",
        "media_label": "网页包（ZIP）", "zh": None, "en": "HTML5",
        "gallery": [], "category": [], "media_queries": [],
        "special_download": [{"file": "HTML5 Badge.svg", "target": "console-1"}],
    },
    {
        "id": "nes", "year": 1983, "maker": "任天堂", "generation": "第三代",
        "media_label": "卡带", "zh": "红白机", "en": "Nintendo Entertainment System",
        "gallery": ["Famicom", "NES"],
        "category": ["Nintendo Entertainment System", "Famicom"],
        "media_queries": ["Famicom cartridge", "NES cartridge"],
    },
    {
        "id": "snes", "year": 1990, "maker": "任天堂", "generation": "第四代",
        "media_label": "卡带", "zh": "超級任天堂", "en": "Super Nintendo Entertainment System",
        "gallery": ["SuperFamicom", "SuperNES"],
        "category": ["Super Nintendo Entertainment System", "Super Famicom"],
        "media_queries": ["Super Famicom cartridge", "Super Nintendo cartridge"],
    },
    {
        "id": "n64", "year": 1996, "maker": "任天堂", "generation": "第五代",
        "media_label": "卡带", "zh": "任天堂64", "en": "Nintendo 64",
        "gallery": ["N64"],
        "category": ["Nintendo 64"],
        "media_queries": ["Nintendo 64 cartridge"],
    },
    {
        "id": "gb", "year": 1989, "maker": "任天堂", "generation": "第四代",
        "media_label": "卡带", "zh": "Game Boy", "en": "Game Boy",
        "gallery": ["GameBoy", "GameBoyColor", "GameBoyPocket"],
        "category": ["Game Boy", "Game Boy Color"],
        "media_queries": ["Game Boy cartridge", "Game Boy Color cartridge"],
    },
    {
        "id": "gba", "year": 2001, "maker": "任天堂", "generation": "第六代",
        "media_label": "卡带", "zh": "Game Boy Advance", "en": "Game Boy Advance",
        "gallery": ["GameBoyAdvance"],
        "category": ["Game Boy Advance"],
        "media_queries": ["Game Boy Advance cartridge"],
    },
    {
        "id": "nds", "year": 2004, "maker": "任天堂", "generation": "第七代",
        "media_label": "DS 卡", "zh": "任天堂DS", "en": "Nintendo DS",
        "gallery": ["NintendoDS"],
        "category": ["Nintendo DS"],
        "media_queries": ["Nintendo DS game card"],
    },
    {
        "id": "vb", "year": 1995, "maker": "任天堂", "generation": "第五代",
        "media_label": "卡带", "zh": "Virtual Boy", "en": "Virtual Boy",
        "gallery": ["VirtualBoy"],
        "category": ["Virtual Boy"],
        "media_queries": ["Virtual Boy cartridge"],
    },
    {
        "id": "segaMD", "year": 1988, "maker": "世嘉", "generation": "第四代",
        "media_label": "卡带", "zh": "Mega Drive", "en": "Sega Genesis",
        "gallery": ["Genesis", "MegaDriveJP"],
        "category": ["Sega Mega Drive", "Sega Genesis"],
        "media_queries": ["Mega Drive cartridge", "Genesis cartridge"],
        "media_pick": [
            "Sonic & Knuckles Genesis Cartridge.jpg",
            "Used Mega Drive catridges.jpg",
            "Mega drive j-cart.jpg",
        ],
    },
    {
        "id": "segaGG", "year": 1990, "maker": "世嘉", "generation": "第四代",
        "media_label": "卡带", "zh": "Game Gear", "en": "Game Gear",
        "gallery": ["GameGear"],
        "category": ["Game Gear"],
        "media_queries": ["Game Gear cartridge"],
    },
    {
        "id": "segaMS", "year": 1985, "maker": "世嘉", "generation": "第三代",
        "media_label": "卡带", "zh": "世嘉Master System", "en": "Master System",
        "gallery": ["MasterSystem"],
        "category": ["Sega Master System"],
        "media_queries": ["Master System cartridge"],
        "media_pick": [
            "Casino Games cartridge for Sega Master System (44931361652).jpg",
            "Taz-Mania cartridge for Sega Master System (32571029347).jpg",
        ],
    },
    {
        "id": "segaCD", "year": 1991, "maker": "世嘉", "generation": "第四代",
        "media_label": "CD-ROM", "zh": "Mega-CD", "en": "Sega CD",
        "gallery": ["GenesisAdd-ons"],
        "category": ["Sega CD", "Mega-CD"],
        "media_queries": ["Mega-CD disc", "Sega CD disc"],
    },
    {
        "id": "sega32x", "year": 1994, "maker": "世嘉", "generation": "第五代",
        "media_label": "卡带", "zh": "Super 32X", "en": "32X",
        "gallery": ["GenesisAdd-ons"],
        "category": ["Sega 32X"],
        "media_queries": ["32X cartridge"],
    },
    {
        "id": "segaSaturn", "year": 1994, "maker": "世嘉", "generation": "第五代",
        "media_label": "CD-ROM", "zh": "世嘉土星", "en": "Sega Saturn",
        "gallery": ["SaturnJP", "SaturnNA"],
        "category": ["Sega Saturn"],
        "media_queries": ["Sega Saturn disc"],
    },
    {
        "id": "psx", "year": 1994, "maker": "索尼", "generation": "第五代",
        "media_label": "CD-ROM", "zh": "PlayStation", "en": "PlayStation (console)",
        "gallery": ["PlayStation", "PSone"],
        "category": ["PlayStation (console)"],
        "media_queries": ["PlayStation game disc", "PS1 disc"],
        "media_pick": ["CD-ROM for PlayStation.jpg"],
    },
    {
        "id": "psp", "year": 2004, "maker": "索尼", "generation": "第七代",
        "media_label": "UMD", "zh": "PlayStation Portable", "en": "PlayStation Portable",
        "gallery": ["PSP"],
        "category": ["PlayStation Portable"],
        "media_queries": ["PlayStation Portable UMD"],
    },
    {
        "id": "pce", "year": 1987, "maker": "NEC", "generation": "第四代",
        "media_label": "HuCard", "zh": "PC Engine", "en": "TurboGrafx-16",
        "gallery": ["PC-Engine", "TurboGrafx-16"],
        "category": ["PC Engine", "TurboGrafx-16"],
        "media_queries": ["PC Engine HuCard", "TurboGrafx HuCard"],
    },
    {
        "id": "pcfx", "year": 1994, "maker": "NEC", "generation": "第五代",
        "media_label": "CD-ROM", "zh": "PC-FX", "en": "PC-FX",
        "gallery": ["PCFX"],
        "category": ["PC-FX"],
        "media_queries": ["PC-FX disc"],
    },
    {
        "id": "ngp", "year": 1998, "maker": "SNK", "generation": "第五代",
        "media_label": "卡带", "zh": "Neo Geo Pocket", "en": "Neo Geo Pocket",
        "gallery": ["NeoGeoPocket", "NeoGeoPocketColor"],
        "category": ["Neo Geo Pocket"],
        "media_queries": ["Neo Geo Pocket cartridge"],
    },
    {
        "id": "ws", "year": 1999, "maker": "万代", "generation": "第五代",
        "media_label": "卡带", "zh": "WonderSwan", "en": "WonderSwan",
        "gallery": ["WonderSwan"],
        "category": ["WonderSwan"],
        "media_queries": ["WonderSwan cartridge"],
    },
    {
        "id": "atari2600", "year": 1977, "maker": "雅达利", "generation": "第二代",
        "media_label": "卡带", "zh": "雅達利2600", "en": "Atari 2600",
        "gallery": ["Atari2600", "Atari2600Jr"],
        "category": ["Atari 2600"],
        "media_queries": ["Atari 2600 cartridge"],
    },
    {
        "id": "atari5200", "year": 1982, "maker": "雅达利", "generation": "第二代",
        "media_label": "卡带", "zh": "雅達利5200", "en": "Atari 5200",
        "gallery": ["Atari5200"],
        "category": ["Atari 5200"],
        "media_queries": ["Atari 5200 cartridge"],
        "media_pick": ["Atari-5200-Cartridge.jpg"],
    },
    {
        "id": "atari7800", "year": 1986, "maker": "雅达利", "generation": "第三代",
        "media_label": "卡带", "zh": "雅达利7800", "en": "Atari 7800",
        "gallery": ["Atari7800"],
        "category": ["Atari 7800"],
        "media_queries": ["Atari 7800 cartridge"],
    },
    {
        "id": "jaguar", "year": 1993, "maker": "雅达利", "generation": "第五代",
        "media_label": "卡带", "zh": "雅達利Jaguar", "en": "Atari Jaguar",
        "gallery": ["AtariJaguar"],
        "category": ["Atari Jaguar"],
        "media_queries": ["Atari Jaguar cartridge"],
    },
    {
        "id": "lynx", "year": 1989, "maker": "雅达利", "generation": "第四代",
        "media_label": "卡带", "zh": "雅达利Lynx", "en": "Atari Lynx",
        "gallery": ["AtariLynx"],
        "category": ["Atari Lynx"],
        "media_queries": ["Atari Lynx cartridge"],
    },
    {
        "id": "coleco", "year": 1982, "maker": "Coleco", "generation": "第二代",
        "media_label": "卡带", "zh": "ColecoVision", "en": "ColecoVision",
        "gallery": ["ColecoVision"],
        "category": ["ColecoVision"],
        "media_queries": ["ColecoVision cartridge"],
    },
    {
        "id": "3do", "year": 1993, "maker": "松下 / 3DO", "generation": "第五代",
        "media_label": "CD-ROM", "zh": "3DO", "en": "3DO Interactive Multiplayer",
        "gallery": ["3DO"],
        "category": ["3DO"],
        "media_queries": ["3DO game disc"],
    },
    {
        "id": "c64", "year": 1982, "maker": "Commodore", "generation": "第二代",
        "media_label": "卡带 / 软盘", "zh": "康懋達64", "en": "Commodore 64",
        "gallery": ["Commodore64"],
        "category": ["Commodore 64"],
        "media_queries": ["Commodore 64 cartridge", "Commodore 64 floppy"],
        "console_pick": [
            "Commodore-64-Computer-FL.jpg",
            "Commodore-64-Computer-FR.jpg",
            "Commodore-64-Computer-BL.jpg",
        ],
    },
    {
        "id": "c128", "year": 1985, "maker": "Commodore", "generation": "第三代",
        "media_label": "软盘 / 卡带", "zh": None, "en": "Commodore 128",
        "gallery": ["Commodore128"],
        "category": ["Commodore 128"],
        "media_queries": ["Commodore 128 floppy"],
        "media_pick": ["C128-C128D Bootdiskette CPM-Modus.png"],
    },
    {
        "id": "pet", "year": 1977, "maker": "Commodore", "generation": "第二代",
        "media_label": "卡带 / 磁带", "zh": None, "en": "Commodore PET",
        "gallery": [],
        "category": ["Commodore PET"],
        "media_queries": ["Commodore PET cassette", "PET computer"],
        "console_pick": [
            "Commodore PET 2001 Bonami 01.jpg",
            "Commodore PET.jpg",
            "Commodore PET 2001.jpg",
        ],
    },
    {
        "id": "plus4", "year": 1984, "maker": "Commodore", "generation": "第三代",
        "media_label": "卡带 / 软盘", "zh": None, "en": "Commodore Plus/4",
        "gallery": [],
        "category": ["Commodore Plus/4"],
        "media_queries": ["Commodore Plus/4 cartridge"],
        "console_pick": [
            "Commodore Plus 4.jpg",
            "Commodore Plus-4 with 1551.jpg",
        ],
        "media_pick": ["Steckmodulhälften für Commodore Plus 4.png"],
    },
    {
        "id": "vic20", "year": 1980, "maker": "Commodore", "generation": "第二代",
        "media_label": "卡带 / 磁带", "zh": "VIC-20", "en": "VIC-20",
        "gallery": ["CommodoreVIC20"],
        "category": ["Commodore VIC-20"],
        "media_queries": ["VIC-20 cartridge"],
        "console_pick": [
            "Commodore-VIC-20-FL.jpg",
            "Commodore-VIC-20-FR.jpg",
            "Commodore-VIC-20-BL.jpg",
            "Commodore-VIC-20-BR.jpg",
        ],
        "media_pick": [
            "Commodore VIC-20 computer VIC-1212 Programmer's aid cartridge Tietokonemuseo.JPG",
            "ViC20 Cartridge.jpg",
        ],
    },
    {
        "id": "amiga", "year": 1985, "maker": "Commodore", "generation": "第三代",
        "media_label": "软盘", "zh": "Amiga", "en": "Amiga",
        "gallery": [],
        "category": ["Amiga computers"],
        "media_queries": ["Amiga floppy disk"],
        "console_pick": [
            "Amiga500 system.jpg",
            "Amiga-Computer.jpg",
            "Amiga 500, front, Google NY office computer museum.jpg",
        ],
    },
    {
        "id": "dos", "year": 1981, "maker": "微软", "generation": "电脑平台",
        "media_label": "软盘 / CD-ROM", "zh": "DOS", "en": "MS-DOS",
        "gallery": [],
        "category": ["MS-DOS"],
        "media_queries": ["MS-DOS floppy", "DOS game disc"],
        "console_pick": [
            "IBM PC 5150.jpg",
            "IBM PC, 1981, Computer History Museum.jpg",
            "IBM Personal Computer (1981).jpg",
        ],
        "media_pick": [
            "MS-DOS 6 floppy disks.jpg",
            "MS-DOS 6.22 floppy disks german.jpg",
        ],
    },
    {
        "id": "arcade", "year": 1971, "maker": "多厂商", "generation": "街机",
        "media_label": "街机基板", "zh": "街机", "en": "Arcade game",
        "gallery": [],
        "category": ["Arcade games", "Arcade cabinets"],
        "media_queries": ["arcade PCB", "arcade cabinet"],
        "media_pick": [
            "Nintendo Donkey Kong pcb2.jpg",
            "Rainbow Islands PCB.jpg",
            "Gorf game board.jpg",
        ],
    },
]

# 载体图文件名必须命中的机型词，避免把「步枪子弹（cartridge）」之类的搜索结果收进来。
MEDIA_MATCH: dict[str, tuple[str, ...]] = {
    "nes": ("famicom", "nes"),
    "snes": ("super famicom", "super nintendo", "snes", "super nes"),
    "n64": ("nintendo 64", "n64"),
    "gb": ("game boy", "gameboy"),
    "gba": ("game boy advance", "gba"),
    "nds": ("nintendo ds", "ds game", "game card"),
    "vb": ("virtual boy",),
    "segaMD": ("mega drive", "megadrive", "genesis"),
    "segaGG": ("game gear",),
    "segaMS": ("master system",),
    "segaCD": ("mega-cd", "mega cd", "sega cd"),
    "sega32x": ("32x",),
    "segaSaturn": ("saturn",),
    "psx": ("playstation", "ps1", "psx"),
    "psp": ("psp", "playstation portable", "umd"),
    "pce": ("pc engine", "turbografx", "hucard"),
    "pcfx": ("pc-fx", "pc fx"),
    "ngp": ("neo geo pocket", "neogeo pocket"),
    "ws": ("wonderswan", "wonder swan"),
    "atari2600": ("atari 2600", "atari vcs"),
    "atari5200": ("atari 5200",),
    "atari7800": ("atari 7800",),
    "jaguar": ("atari jaguar", "jaguar"),
    "lynx": ("atari lynx", "lynx"),
    "coleco": ("coleco",),
    "3do": ("3do",),
    "c64": ("commodore 64", "c64"),
    "c128": ("commodore 128", "c128"),
    "pet": ("commodore pet", "pet"),
    "plus4": ("plus/4", "plus 4", "commodore plus"),
    "vic20": ("vic-20", "vic 20"),
    "amiga": ("amiga",),
    "dos": ("ms-dos", "dos"),
    "arcade": ("arcade",),
}

EXCLUDE_WORDS = (
    "motherboard", "deconstruction", "teardown", "chip", "logo", "manual",
    "power-supply", "power supply", "adapter", "zapper", "light-gun",
    "game-genie", "cartridge-board", "cart-board", "pin-adapter",
    "screw", "battery", "screen-only", "packaging", "box",
    "datasette", "cassette", "tape", "drive", "1541", "keyboard",
)
PREFER_WORDS = (
    "console-set", "console-", "wcontroller", "handheld", "computer",
)
MEDIA_EXCLUDE = (
    "adaptor", "adapter", "converter", "cleaning", "patent", "manual",
    "board", "pcb", "cable", "kit", "schematic", "screw", "sticker",
    "label", "shell", "case", "drive", "console", "computer", "box", "chip",
)
MEDIA_WORDS = (
    "cartridge", "cart", "disc", "disk", "hucard", "floppy",
    "umd", "cassette", "game card", "game pak", "memory card",
)

def log(message: str, level: str = "info") -> None:
    emit(level, message)


def http_get(url: str, *, retries: int = 6, timeout: int = 60) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 429 是 Commons 的常态限流，退避时间要明显长于普通错误。
            wait = 10 * (attempt + 1)
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = max(wait, int(retry_after))
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"请求失败：{url}（{last_error}）")


def get_json(url: str) -> dict:
    return json.loads(http_get(url).decode("utf-8"))


def commons_api(params: dict) -> dict:
    params = {"format": "json", **params}
    return get_json(f"{COMMONS_API}?{urllib.parse.urlencode(params)}")


def wiki_html(lang: str, title: str) -> str:
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    return http_get(WIKI_API.format(lang=lang, title=encoded)).decode("utf-8", "replace")


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", fragment, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\[[编辑編輯]+\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_sections(page_html: str) -> list[dict]:
    """按 h2 切段，返回 [{title, paragraphs}]，忽略导航与参考文献。"""
    parts = re.split(r"(<h2[^>]*>.*?</h2>)", page_html, flags=re.S)
    sections: list[dict] = []
    for index in range(1, len(parts), 2):
        title = strip_tags(parts[index]).strip()
        body = parts[index + 1] if index + 1 < len(parts) else ""
        paragraphs = [strip_tags(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, flags=re.S)]
        paragraphs = [p for p in paragraphs if len(p) >= 25]
        if title and paragraphs:
            sections.append({"title": title, "paragraphs": paragraphs})
    return sections


HISTORY_TITLES = ("历史", "歷史", "沿革", "开发", "開發", "发展", "發展", "背景", "起源")


def pick_history(sections: list[dict]) -> list[str]:
    picked: list[str] = []
    for section in sections:
        if any(key in section["title"] for key in HISTORY_TITLES):
            picked.extend(section["paragraphs"])
    if picked:
        return picked[:8]
    for section in sections:
        if section["title"] not in ("参考文献", "參考文獻", "参见", "參見", "外部链接", "外部連結"):
            picked.extend(section["paragraphs"])
    return picked[:8]


def fetch_raw(entry: dict, force: bool = False) -> dict:
    raw_path = RAW_DIR / f"{entry['id']}.json"
    if raw_path.exists() and not force:
        return json.loads(raw_path.read_text(encoding="utf-8"))
    result = {"id": entry["id"], "zh": [], "en": []}
    if entry.get("zh"):
        try:
            page = wiki_html("zh", entry["zh"])
            result["zh"] = pick_history(extract_sections(page))
        except Exception as exc:  # noqa: BLE001 - 抓取失败不该中断整批
            result["zh_error"] = str(exc)
        time.sleep(REQUEST_DELAY)
    if entry.get("en"):
        try:
            page = wiki_html("en", entry["en"])
            result["en"] = pick_history(extract_sections(page))
        except Exception as exc:  # noqa: BLE001
            result["en_error"] = str(exc)
        time.sleep(REQUEST_DELAY)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def commons_gallery_files(gallery: str) -> list[str]:
    data = commons_api({"action": "parse", "prop": "images", "page": f"User:Evan-Amos/VOGM/{gallery}"})
    return list(data.get("parse", {}).get("images", []))


def commons_category_files(category: str, limit: int = 60) -> list[str]:
    data = commons_api({
        "action": "query", "list": "categorymembers",
        "cmtitle": f"Category:{category}", "cmtype": "file", "cmlimit": str(limit),
    })
    return [item["title"].removeprefix("File:") for item in data.get("query", {}).get("categorymembers", [])]


def commons_search_files(query: str, limit: int = 12) -> list[str]:
    data = commons_api({
        "action": "query", "list": "search", "srsearch": query,
        "srnamespace": "6", "srlimit": str(limit),
    })
    return [item["title"].removeprefix("File:") for item in data.get("query", {}).get("search", [])]


def image_info(files: list[str]) -> dict[str, dict]:
    """批量取缩略图 URL、作者与许可。"""
    result: dict[str, dict] = {}
    for start in range(0, len(files), 20):
        chunk = files[start:start + 20]
        data = commons_api({
            "action": "query", "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": str(IMAGE_WIDTH),
            "titles": "|".join(f"File:{name}" for name in chunk),
        })
        for page in data.get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            metadata = info.get("extmetadata", {})
            result[page["title"].removeprefix("File:")] = {
                "url": info.get("thumburl") or info.get("url"),
                "license": strip_tags(metadata.get("LicenseShortName", {}).get("value", "")),
                "author": strip_tags(metadata.get("Artist", {}).get("value", ""))[:120],
                "descriptionurl": info.get("descriptionurl", ""),
            }
        time.sleep(REQUEST_DELAY)
    return result


def is_free(license_text: str) -> bool:
    normalized = license_text.lower()
    return any(token in normalized for token in FREE_LICENSES)


def base_name(filename: str) -> str:
    return re.sub(r"\.(jpg|jpeg|png|gif|webp|svg)$", "", filename, flags=re.I)


def rank_gallery(gallery_files: list[str]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for name in gallery_files:
        if not re.search(r"\.(jpg|jpeg|png)$", name, re.I):
            continue
        lowered = name.lower()
        if any(word in lowered for word in EXCLUDE_WORDS):
            continue
        key = base_name(lowered)
        if key in seen:  # PNG/JPG 同图只留一张
            continue
        seen.add(key)
        candidates.append(name)
    candidates.sort(key=lambda name: 0 if any(word in name.lower() for word in PREFER_WORDS) else 1)
    return candidates


def pick_console_files(ranked_galleries: list[list[str]], limit: int = 4) -> list[str]:
    """多个图库轮流取，保证不同型号（如 Famicom 与 NES）都出现。"""
    picked: list[str] = []
    depth = 0
    ranked = [rank for rank in ranked_galleries if rank]
    while len(picked) < limit and any(depth < len(rank) for rank in ranked):
        for rank in ranked:
            if depth < len(rank):
                picked.append(rank[depth])
                if len(picked) >= limit:
                    break
        depth += 1
    return picked


def pick_media_files(
    files: list[str], infos: dict[str, dict], match: tuple[str, ...], limit: int = 3
) -> list[str]:
    def acceptable(name: str) -> bool:
        lowered = name.lower()
        if not re.search(r"\.(jpg|jpeg|png|gif)$", lowered):
            return False
        if any(word in lowered for word in MEDIA_EXCLUDE):
            return False
        if not any(token in lowered for token in match):
            return False
        if not any(word in lowered for word in MEDIA_WORDS):
            return False
        info = infos.get(name)
        if not info or not info.get("url") or not is_free(info.get("license", "")):
            return False
        return True

    # 只收文件名里明确带载体词的照片；宁可少一张，也不拿整机图凑数。
    return [name for name in files if acceptable(name)][:limit]


def save_webp(name: str, target: Path, info: dict, force: bool = False) -> bool:
    if target.exists() and target.stat().st_size > 0 and not force:
        return True
    if not info or not info.get("url"):
        log(f"  跳过（取不到地址）：{name}", "warn")
        return False
    try:
        data = http_get(info["url"])
        image = Image.open(io.BytesIO(data))
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")
        if image.width > IMAGE_WIDTH:
            ratio = IMAGE_WIDTH / image.width
            image = image.resize((IMAGE_WIDTH, int(image.height * ratio)), Image.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"  处理失败：{name}（{exc}）", "warn")
        return False


def build_images(entry: dict, force: bool = False) -> dict[str, dict]:
    """下载一个类型的图片，返回 {key: {author, license, source}}。"""
    platform_id = entry["id"]
    folder = ASSET_ROOT / platform_id
    credits: dict[str, dict] = {}

    if force and folder.is_dir():
        # 重跑时先清掉旧图，避免换了候选后残留 console-4 / media-3 这类孤儿文件。
        for stale in folder.glob("*.webp"):
            stale.unlink()

    for item in entry.get("special_download", []):
        info = image_info([item["file"]]).get(item["file"], {})
        target = folder / f"{item['target']}.webp"
        if save_webp(item["file"], target, info, force=force):
            credits[f"{platform_id}-{item['target']}"] = {
                "author": info.get("author", ""),
                "license": info.get("license", ""),
                "source": info.get("descriptionurl", ""),
            }
        time.sleep(REQUEST_DELAY)

    for item in entry.get("special_copy", []):
        source = ROOT / item["from"]
        target = folder / f"{item['target']}.webp"
        target.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(source)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")
        if image.width > IMAGE_WIDTH:
            ratio = IMAGE_WIDTH / image.width
            image = image.resize((IMAGE_WIDTH, int(image.height * ratio)), Image.LANCZOS)
        image.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
        credits[f"{platform_id}-{item['target']}"] = {
            "author": "项目内置素材",
            "license": "随项目提供",
            "source": "",
        }

    if entry.get("console_pick"):
        # 个别机种的图库命名太杂（如 VIC-20 的 Datasette、Amiga 的蝴蝶属），人工指定。
        picked_consoles = list(entry["console_pick"])
        console_infos = image_info(picked_consoles)
        log(f"  游戏机图人工指定 {len(picked_consoles)}：{picked_consoles}")
    else:
        gallery_files: list[list[str]] = []
        for gallery in entry.get("gallery", []):
            gallery_files.append(commons_gallery_files(gallery))
            time.sleep(REQUEST_DELAY)
        if sum(len(files) for files in gallery_files) < 2:
            for category in entry.get("category", []):
                gallery_files.append(commons_category_files(category))
                time.sleep(REQUEST_DELAY)

        picked_consoles = pick_console_files(
            [rank_gallery(files) for files in gallery_files], limit=4
        )
        log(
            f"  游戏机图候选 {sum(len(f) for f in gallery_files)}，"
            f"选用 {len(picked_consoles)}：{picked_consoles}"
        )
        console_infos = image_info(picked_consoles) if picked_consoles else {}

    if entry.get("media_pick"):
        picked_media = list(entry["media_pick"])
        media_infos = image_info(picked_media)
        log(f"  载体图人工指定 {len(picked_media)}：{picked_media}")
    else:
        media_groups: list[list[str]] = []
        for query in entry.get("media_queries", []):
            media_groups.append(commons_search_files(query))
            time.sleep(REQUEST_DELAY)
        media_files: list[str] = []
        for index in range(max((len(group) for group in media_groups), default=0)):
            for group in media_groups:
                if index < len(group):
                    media_files.append(group[index])
        unique_media = list(dict.fromkeys(media_files))
        media_infos = image_info(unique_media) if unique_media else {}
        match = MEDIA_MATCH.get(platform_id, (platform_id.lower(),))
        picked_media = pick_media_files(unique_media, media_infos, match, limit=3)
        log(f"  载体图候选 {len(unique_media)}，选用 {len(picked_media)}：{picked_media}")

    for index, name in enumerate(picked_consoles, start=1):
        target = folder / f"console-{index}.webp"
        info = console_infos.get(name, {})
        if save_webp(name, target, info, force=force):
            credits[f"{platform_id}-console-{index}"] = {
                "author": info.get("author", ""),
                "license": info.get("license", ""),
                "source": info.get("descriptionurl", ""),
            }
        time.sleep(REQUEST_DELAY)
    for index, name in enumerate(picked_media, start=1):
        target = folder / f"media-{index}.webp"
        info = media_infos.get(name, {})
        if save_webp(name, target, info, force=force):
            credits[f"{platform_id}-media-{index}"] = {
                "author": info.get("author", ""),
                "license": info.get("license", ""),
                "source": info.get("descriptionurl", ""),
            }
        time.sleep(REQUEST_DELAY)
    return credits


def js_identifier(key: str) -> str:
    return "img_" + re.sub(r"[^a-zA-Z0-9_]", "_", key)


def write_images_js() -> None:
    """按磁盘上实际存在的图片生成 import 与 URL 映射。"""
    keys = sorted(set(scan_image_keys()))
    lines = [
        "// 本文件由 scripts/build-platform-intros.py 生成，不要手改。",
        "// 重跑：python scripts/build-platform-intros.py --write-images-js",
        "",
    ]
    for key in keys:
        path = key.replace("-", "/", 1)
        lines.append(f'import {js_identifier(key)} from "@/assets/platforms/{path}.webp";')
    lines.append("")
    lines.append("/** 图片 key → Vite 处理后的 URL。 */")
    lines.append("export const PLATFORM_IMAGES = {")
    for key in keys:
        lines.append(f'    "{key}": {js_identifier(key)},')
    lines.append("};")
    lines.append("")
    IMAGES_JS.parent.mkdir(parents=True, exist_ok=True)
    IMAGES_JS.write_text("\n".join(lines), encoding="utf-8")


CREDITS_JSON = RAW_DIR / "credits.json"


def load_existing_credits() -> dict[str, dict]:
    if CREDITS_JSON.exists():
        try:
            return json.loads(CREDITS_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_credits(credits: dict[str, dict]) -> None:
    CREDITS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CREDITS_JSON.write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_image_keys() -> list[str]:
    keys: list[str] = []
    for folder in sorted(ASSET_ROOT.glob("*")):
        if not folder.is_dir():
            continue
        for file in sorted(folder.glob("*.webp")):
            keys.append(f"{folder.name}-{file.stem}")
    return keys


def assert_ids() -> None:
    sys.path.insert(0, str(ROOT))
    from backend.games.platforms import playable_platforms  # noqa: PLC0415

    expected = {"flash", "h5", *(platform.id for platform in playable_platforms())}
    actual = {entry["id"] for entry in MANIFEST}
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise SystemExit(f"清单与 GAME_TYPES 不一致：缺少 {sorted(missing)}，多出 {sorted(extra)}")
    if len(MANIFEST) != 36:
        raise SystemExit(f"清单应有 36 条，实际 {len(MANIFEST)} 条")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取机型简史素材")
    parser.add_argument("--only", action="append", default=[], help="只处理指定 id，可重复")
    parser.add_argument("--force", action="store_true", help="强制重下已存在的图片")
    parser.add_argument("--write-images-js", action="store_true", help="只根据已下载的图片重建 images.js")
    parser.add_argument("--skip-images", action="store_true", help="只抓正文")
    parser.add_argument("--skip-done", action="store_true", help="跳过已有正文与图片的条目（断点续跑）")
    args = parser.parse_args()

    assert_ids()
    selected = [entry for entry in MANIFEST if not args.only or entry["id"] in args.only]
    if not selected:
        log(f"未知 id：{args.only}", "fail")
        raise SystemExit(1)

    if args.write_images_js:
        write_images_js()
        log(f"已重建 {IMAGES_JS}", "ok")
        return

    credits = load_existing_credits()
    for entry in selected:
        if args.skip_done:
            has_raw = (RAW_DIR / f"{entry['id']}.json").exists()
            folder = ASSET_ROOT / entry["id"]
            has_images = folder.is_dir() and any(folder.glob("*.webp"))
            if has_raw and has_images:
                log(f"[{entry['id']}] 已完成，跳过")
                continue
        log(f"[{entry['id']}] 抓取正文")
        fetch_raw(entry, force=args.force)
        if not args.skip_images:
            log(f"[{entry['id']}] 抓取图片")
            credits.update(build_images(entry, force=args.force))
            save_credits(credits)
        time.sleep(REQUEST_DELAY)

    if not args.only:
        write_images_js()
        log(f"已写入 {IMAGES_JS}", "ok")
    else:
        log("只处理了部分 id，未重建 images.js（全部跑完会自动重建）", "warn")


if __name__ == "__main__":
    main()
