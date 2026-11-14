"""机种词表——全项目「这是哪台机器」的唯一权威来源。

同一个平台在项目里原本有三套写法，互相看不出是同一个东西：

- **游戏管理**用 `game_type`（`nes` / `segaMD` / …，同时是磁盘目录名）；
- **游戏名录**用名录 CSV 的文件名（`nes.csv`、`segaMD.csv`、`gb.csv`、`gbc.csv` …），
  文件名经 `SEARCH_CSV_CONSOLE_NAMES` 还原成中文长名（`任天堂FC`、`世嘉MD`、`任天堂GB` …）；
- **游戏榜单**用 `backend/search/rankings/` 下的文件名，stem 就是机种 id（`nes.csv`、`segaMD.csv` …）。

这里把三者收敛到一份词表上：**机种 id 取 EmulatorJS 的 system key**——游戏最终要在 EmulatorJS 里
跑，能玩不能玩由引擎决定，所以引擎的机种表就是标准。id 集合与每个机种的 core 列表**逐字**取自
EJS 4.2.3 的 `EmulatorJS.getCores()`
（`frontend/public/emulatorjs/data/emulator.min.js`，升级引擎版本时这两处要一起看）。

三条约束：

1. **`id` 就是 `game_type` 的值**（对已收录可玩的机种而言），所以磁盘目录名、库里已有的
   `games.game_type`、EJS 的 `EJS_core` 天然一致，改这张表**不会**挪动任何文件。
2. **`label` 是三处共用的显示名**（中文，厂商 + 空格 + 型号；没有厂商名的只写型号），
   前端 `constants/gameTypes.js` 里按 id 保留图标/描述等 UI 元数据，
   label 与扩展名由 `/api/games/status` 从本表派生。
3. **`extensions` 非空才代表本项目已收录、可上传可玩**——当前 34 个机种有；`sega` / `mame`
   两个兜底 key 只用来给外部名录「对上号」，不开放上传。
   `bundle_extensions` 描述多文件本体的包内后缀（cue/bin/m3u 这类），不影响单文件判型。
   `threads` 表示该机种的核只能用线程变体（PSP / DOS），宿主页据此打开 `EJS_threads`。

`flash` / `h5` **不是机种**（它们是载体类型：Ruffle 播的 SWF 与上传 ZIP 解包的网页游戏），
所以不在这张表里，它们的 `game_type` 与显示名仍由 `service.py` 自己管。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BiosSpec:
    """一个机种需要的用户自备 BIOS 包。

    ZIP 放在 `frontend/public/emulatorjs/bios/`，包根目录直接放 `required_files`，
    不能套一层子目录。`optional=True` 表示核心有内置回退，缺包也能启动。
    """

    file: str  # emulatorjs/bios/ 下的 ZIP 文件名
    required_files: tuple[str, ...]  # ZIP 根目录必须包含的文件名
    optional: bool = False  # True = 缺包不阻塞启动


@dataclass(frozen=True)
class Platform:
    """一个机种。

    `aliases` 是外部名录里出现过的各种写法（含名录 CSV 的实际取值），
    用于把 `console` 那一列的自由文本解析回机种；匹配时忽略大小写与所有空白。
    """

    id: str  # EmulatorJS system key
    label: str  # 统一显示名（中文）
    cores: tuple[str, ...]  # EJS 该 system 的 core，逐字取自 EJS
    aliases: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()  # 非空 = 本项目已收录可玩；值即 game_type
    default_extension: str = ""  # 网络直链看不出后缀时补的那个（只有可玩机种有）
    bios: BiosSpec | None = None  # 需要 BIOS 的机种在这里声明
    # 多文件本体：包内允许出现的全部后缀（含只作分轨、不能当入口的 .bin）。
    # 非空即表示该机种支持「一个游戏目录下放多个文件」。
    bundle_extensions: tuple[str, ...] = ()
    # 多文件本体里可以当入口的后缀；必须是 bundle_extensions 的子集。
    bundle_entries: tuple[str, ...] = ()
    # 核只有线程变体（EJS requiresThreads）；宿主页要打开 EJS_threads，
    # 因此页面必须带 COOP/COEP 让 SharedArrayBuffer 可用。
    threads: bool = False


# 顺序即下拉展示顺序：按厂商分组。
#
# **这一列的顺序是有约束的**：`service.GAME_TYPES` 直接从 `playable_platforms()` 派生，
# 所以可玩机种在表里的先后 = 管理页下拉与游戏中心分组的先后。可玩机种刻意保持
# 项目既有顺序（`nes` `snes` `gb` `gba` `nds` `segaMD` `segaGG` `segaMS`，世嘉那三个 GG 在 SMS 前），
# NDS 插在 GBA 之后，免得这次统一顺手把界面顺序也改了。
#
# 前端展示层的 label 与扩展名不再手写镜像：由 `/api/games/status` 从本表派生，
# 前端只保留图标、描述这类纯 UI 元数据。
# 加机种：id / label / aliases / cores / extensions / bios 只改这里；
# 另补 core 资产、前端帧缓冲与 `emulatorjs/bios/<id>.zip`（需要 BIOS 时）。
# 扩展名**允许跨机种重叠**（Commodore 的 `.d64` / `.prg`），
# 重叠时由 `playable_platforms_for_extension()` 给出候选，用户在创建时选。
#
# **加机种只改这里**：id 必须是 EJS 的 system key，cores 照抄 EJS，别名要覆盖外部名录的写法。
PLATFORMS: tuple[Platform, ...] = (
    # —— 任天堂 ——
    Platform(
        id="nes",
        label="任天堂 FC",
        cores=("fceumm", "nestopia"),
        aliases=("任天堂FC", "任天堂FC磁碟机", "FC", "Famicom", "NES", "红白机"),
        extensions=(".nes",),
        default_extension=".nes",
    ),
    Platform(
        id="snes",
        label="任天堂 SFC",
        cores=("snes9x",),
        aliases=("任天堂SFC", "任天堂SFC - Sufami Turbo", "SFC", "SNES", "Super Famicom"),
        extensions=(".sfc", ".smc"),
        default_extension=".sfc",
    ),
    Platform(
        id="n64",
        label="任天堂 N64",
        cores=("mupen64plus_next", "parallel_n64"),
        aliases=("任天堂N64", "N64"),
        # 单文件卡带镜像；.bin 与 Atari 机种歧义，继续不收
        extensions=(".z64", ".n64", ".v64"),
        default_extension=".z64",
    ),
    Platform(
        id="gb",
        label="任天堂 GB/GBC",
        cores=("gambatte",),
        aliases=("任天堂GB", "任天堂GBC", "GB", "GBC", "GB/GBC", "Game Boy", "Game Boy Color"),
        extensions=(".gb", ".gbc"),
        default_extension=".gb",
    ),
    Platform(
        id="gba",
        label="任天堂 GBA",
        cores=("mgba",),
        aliases=("任天堂GBA", "GBA", "Game Boy Advance"),
        extensions=(".gba",),
        default_extension=".gba",
    ),
    Platform(
        id="nds",
        label="任天堂 NDS",
        cores=("melonds", "desmume", "desmume2015"),
        aliases=("任天堂NDS", "NDS", "DS"),
        # 只打包 melonds 核（EJS 的 nds 默认核），desmume / desmume2015 不在资产清单里
        extensions=(".nds",),
        default_extension=".nds",
        bios=BiosSpec(
            file="nds.zip",
            required_files=("bios7.bin", "bios9.bin", "firmware.bin"),
        ),
    ),
    Platform(
        id="vb",
        label="任天堂 VB",
        cores=("beetle_vb",),
        aliases=("任天堂Virtual Boy", "VB", "Virtual Boy"),
        extensions=(".vb",),
        default_extension=".vb",
    ),
    # —— 世嘉 ——
    Platform(
        id="segaMD",
        label="世嘉 MD",
        cores=("genesis_plus_gx", "picodrive"),
        aliases=("世嘉MD", "MD", "Mega Drive", "Genesis"),
        extensions=(".md", ".gen"),
        default_extension=".md",
    ),
    Platform(
        id="segaGG",
        label="世嘉 GG",
        cores=("genesis_plus_gx",),
        aliases=("世嘉GG", "GG", "Game Gear"),
        extensions=(".gg",),
        default_extension=".gg",
    ),
    Platform(
        id="segaMS",
        label="世嘉 SMS",
        cores=("smsplus", "genesis_plus_gx", "picodrive"),
        aliases=("世嘉SMS", "SMS", "Master System"),
        extensions=(".sms",),
        default_extension=".sms",
    ),
    Platform(
        id="segaCD",
        label="世嘉 CD",
        cores=("genesis_plus_gx", "picodrive"),
        aliases=("世嘉cd游戏", "SEGA CD", "Mega CD"),
        # 单文件只收 .chd；cue+bin / m3u 多碟走 bundle_extensions。
        extensions=(".chd",),
        default_extension=".chd",
        bundle_extensions=(".cue", ".bin", ".m3u", ".chd"),
        bundle_entries=(".m3u", ".cue", ".chd"),
        bios=BiosSpec(
            "segaCD.zip",
            ("bios_CD_E.bin", "bios_CD_U.bin", "bios_CD_J.bin"),
        ),
    ),
    Platform(
        id="sega32x",
        label="世嘉 32X",
        cores=("picodrive",),
        aliases=("世嘉32x", "32X"),
        extensions=(".32x",),
        default_extension=".32x",
    ),
    Platform(
        id="segaSaturn",
        label="世嘉 土星",
        cores=("yabause",),
        aliases=("世嘉土星", "世嘉土星SS", "SS", "Saturn"),
        # 只收单文件 CHD；cue+bin 不支持
        extensions=(".chd",),
        default_extension=".chd",
        # yabause 有 HLE 回退，但兼容性差；按必需处理，缺包时给中文提示
        bios=BiosSpec(
            file="segaSaturn.zip",
            required_files=("saturn_bios.bin",),
        ),
    ),
    # EJS 的通用世嘉 system（不区分 MD/MS/GG），只作引擎侧的兜底，没有外部名录对应
    Platform(
        id="sega",
        label="世嘉 通用机",
        cores=("genesis_plus_gx", "picodrive"),
        aliases=("世嘉（通用）",),
    ),
    # —— 索尼 ——
    Platform(
        id="psx",
        label="索尼 PS1",
        cores=("pcsx_rearmed", "mednafen_psx_hw"),
        aliases=("索尼PS1", "PS1", "PSX", "PlayStation"),
        # 单文件镜像；cue+bin 不支持
        extensions=(".chd", ".pbp", ".iso"),
        default_extension=".chd",
        # 三个区版 BIOS 放同一个 ZIP；.iso 只保留数据轨，CD 音轨会丢
        bios=BiosSpec(
            file="psx.zip",
            required_files=("scph5500.bin", "scph5501.bin", "scph5502.bin"),
        ),
    ),
    Platform(
        id="psp",
        label="索尼 PSP",
        cores=("ppsspp",),
        aliases=("索尼PSP", "PSP"),
        # 只收单文件镜像；.iso 与 PS1 / 3DO 共用，创建时由用户选类型。
        extensions=(".iso", ".cso"),
        default_extension=".iso",
        # ppsspp 只有线程变体，还强制 WebGL2。
        threads=True,
    ),
    # —— 日电 ——
    Platform(
        id="pce",
        label="日电 PCE",
        cores=("mednafen_pce",),
        aliases=("日电PCE", "日电pcecd", "PCE", "PC Engine"),
        # 只开 HuCard；CD 游戏要先有多文件上传与 syscard3.pce，暂不开放
        extensions=(".pce", ".sgx"),
        default_extension=".pce",
    ),
    Platform(
        id="pcfx",
        label="日电 PC-FX",
        cores=("mednafen_pcfx",),
        aliases=("PC-FX",),
        # 核心只接受 cue / ccd / toc / chd；单文件路线用 chd
        extensions=(".chd",),
        default_extension=".chd",
        # pcfx.rom 是硬性必需，且必须正好 1 MiB
        bios=BiosSpec(file="pcfx.zip", required_files=("pcfx.rom",)),
    ),
    # —— SNK ——
    Platform(
        id="ngp",
        label="SNK NGPC",
        cores=("mednafen_ngp",),
        aliases=("SNK公司NGPC", "NGPC", "Neo Geo Pocket"),
        extensions=(".ngc", ".ngp"),
        default_extension=".ngc",
    ),
    # —— 万代 ——
    Platform(
        id="ws",
        label="万代 WS",
        cores=("mednafen_wswan",),
        aliases=("万代WS,WSC", "WS", "WSC", "WonderSwan"),
        extensions=(".ws", ".wsc"),
        default_extension=".ws",
    ),
    # —— 雅达利 ——
    Platform(
        id="atari2600",
        label="雅达利 2600",
        cores=("stella2014",),
        aliases=("雅达利2600", "ATARI 2600"),
        # 不收 .bin：2600/5200/7800 都用它，没法判型
        extensions=(".a26",),
        default_extension=".a26",
    ),
    Platform(
        id="atari5200",
        label="雅达利 5200",
        cores=("a5200",),
        aliases=("雅达利5200", "ATARI 5200"),
        extensions=(".a52",),
        default_extension=".a52",
        # a5200 内置 AltirraOS；5200.rom 缺失时自动回退，因此 BIOS 可选
        bios=BiosSpec(
            file="atari5200.zip",
            required_files=("5200.rom",),
            optional=True,
        ),
    ),
    Platform(
        id="atari7800",
        label="雅达利 7800",
        cores=("prosystem",),
        aliases=("雅达利7800", "ATARI 7800"),
        # BIOS 可选；缺 BIOS 时少数游戏黑屏，先按无 BIOS 开放
        extensions=(".a78",),
        default_extension=".a78",
    ),
    Platform(
        id="jaguar",
        label="雅达利 Jaguar",
        cores=("virtualjaguar",),
        aliases=("雅达利Jaguar", "JAGUAR", "Atari Jaguar"),
        # 核兼容性较差，先开放再按实际 ROM 回归
        extensions=(".j64", ".jag"),
        default_extension=".j64",
    ),
    Platform(
        id="lynx",
        label="雅达利 Lynx",
        cores=("handy",),
        aliases=("雅达利Lynx", "LYNX", "Atari Lynx"),
        extensions=(".lnx",),
        default_extension=".lnx",
        # EJS 文档正文写无 BIOS、表格标 Required；按必需处理，缺包时给中文提示
        bios=BiosSpec(
            file="lynx.zip",
            required_files=("lynxboot.img",),
        ),
    ),
    # —— 其他 ——
    Platform(
        id="coleco",
        label="ColecoVision",
        cores=("gearcoleco",),
        aliases=("COLECOVISION",),
        extensions=(".col",),
        default_extension=".col",
        # GearColeco 的 BIOS 必需
        bios=BiosSpec(
            file="coleco.zip",
            required_files=("colecovision.rom",),
        ),
    ),
    Platform(
        id="3do",
        label="松下 3DO",
        cores=("opera",),
        aliases=("松下3DO游戏", "3DO"),
        # opera 接受 iso / chd；cue+bin 不支持
        extensions=(".iso", ".chd"),
        default_extension=".iso",
        # EJS 文档列出多种 3DO BIOS；panafz1 是最常见的 FZ-1 版
        bios=BiosSpec(file="3do.zip", required_files=("panafz1.bin",)),
    ),
    # Commodore 五个共用 .d64 / .prg：后缀不唯一时由用户选类型，
    # 候选顺序取本表的先后，因此默认候选是 c64。
    Platform(
        id="c64",
        label="康懋达 64",
        cores=("vice_x64sc",),
        # 「Commodore 64」是改名前的显示名，外部名录里可能还在用，保留为别名。
        aliases=("C64", "Commodore 64"),
        extensions=(".d64", ".tap", ".crt", ".prg"),
        default_extension=".d64",
    ),
    Platform(
        id="c128",
        label="康懋达 128",
        cores=("vice_x128",),
        aliases=("C128", "Commodore 128"),
        extensions=(".d64", ".d71", ".prg"),
        default_extension=".d64",
    ),
    Platform(
        id="pet",
        label="康懋达 PET",
        cores=("vice_xpet",),
        aliases=("PET", "Commodore PET"),
        extensions=(".prg", ".d64"),
        default_extension=".prg",
    ),
    Platform(
        id="plus4",
        label="康懋达 Plus/4",
        cores=("vice_xplus4",),
        aliases=("PLUS/4", "Commodore Plus/4"),
        extensions=(".prg", ".d64"),
        default_extension=".prg",
    ),
    Platform(
        id="vic20",
        label="康懋达 VIC-20",
        cores=("vice_xvic",),
        aliases=("VIC-20", "Commodore VIC-20"),
        extensions=(".prg", ".d64"),
        default_extension=".prg",
    ),
    Platform(
        id="amiga",
        label="Amiga",
        cores=("puae",),
        aliases=("AMIGA",),
        extensions=(".adf", ".hdf"),
        default_extension=".adf",
        bundle_extensions=(".adf", ".hdf", ".m3u"),
        bundle_entries=(".m3u", ".adf", ".hdf"),
        # PUAE 打包了 AROS 回退，Kickstart 有更兼容、缺包不拦启动。
        bios=BiosSpec(
            "amiga.zip",
            ("kick34005.A500", "kick40068.A1200"),
            optional=True,
        ),
    ),
    Platform(
        id="dos",
        label="DOS",
        cores=("dosbox_pure",),
        aliases=("DOS",),
        # .jsdos 是 jsdos 打包的 zip；也接受普通 .zip，创建时由用户显式选 DOS。
        extensions=(".jsdos", ".zip"),
        default_extension=".jsdos",
        threads=True,
    ),
    Platform(
        id="arcade",
        label="街机",
        cores=("fbneo", "fbalpha2012_cps1", "fbalpha2012_cps2"),
        aliases=("ARCADE",),
        # romset zip：落盘名必须保持集合名（如 mslug.zip），FBNeo 用 URL 末段找集合。
        extensions=(".zip",),
        default_extension=".zip",
        # BIOS 由集合自带或放可选 arcade.zip（内含 neogeo.zip / pgm.zip 等），缺包不拦启动。
        bios=BiosSpec(
            file="arcade.zip",
            required_files=("neogeo.zip", "pgm.zip"),
            optional=True,
        ),
    ),
    # 与 arcade 重叠的另一个街机 system，只作引擎侧的兜底，没有外部名录对应
    Platform(id="mame", label="街机（MAME）", cores=("mame2003_plus", "mame2003")),
)

PLATFORM_BY_ID: dict[str, Platform] = {platform.id: platform for platform in PLATFORMS}


def normalize_name(raw: str) -> str:
    """名字的比较口径：去掉**所有**空白再转小写。

    外部名录的写法很不统一（榜单写 `SEGA CD`、游戏名录写 `世嘉cd游戏`；`SFC - Sufami Turbo`
    里那个连字符两侧还有空格），所以按「去空白 + casefold」比，多一个空格少一个空格都能命中。
    """
    return "".join((raw or "").split()).casefold()


# 显示名的厂商前缀：从词表里「公司名 + 空格 + 型号」的 label 派生，长度降序避免短前缀抢先。
# 外部名录里认不出的机种名也按它补空格（`任天堂3DS` → `任天堂 3DS`）。
_COMPANY_PREFIXES: tuple[str, ...] = tuple(
    sorted(
        {platform.label.split(" ", 1)[0] for platform in PLATFORMS if " " in platform.label},
        key=len,
        reverse=True,
    )
)


def display_console_name(raw: str) -> str:
    """把外部名录的原始机种名整理成显示名：已知厂商名后补一个空格。

    只改格式，不改写公司名与型号本身；已经带空格的保持原样。
    未收录机种（3DS、Wii、PS2…）也走这里，避免下拉里出现 `任天堂3DS` 这种写法。
    """
    text = (raw or "").strip()
    for company in _COMPANY_PREFIXES:
        if text.startswith(company):
            model = text[len(company) :].lstrip()
            if model:
                return f"{company} {model}"
    return text


def _build_alias_index() -> dict[str, Platform]:
    """别名索引。`id` 与 `label` 本身也当别名收进来，为的是让「认不出的原始名」永远撞不上
    机种键：外部名录万一直接写了统一名（「任天堂 GB/GBC」）或 system key（`segaMD`）也能认出来，
    不会变成一个名字与某个机种撞车的「未收录」组。"""
    index: dict[str, Platform] = {}
    for platform in PLATFORMS:
        for raw in (*platform.aliases, platform.label, platform.id):
            key = normalize_name(raw)
            existing = index.get(key)
            if existing is not None and existing is not platform:
                raise ValueError(f"机种名冲突：{raw!r} 同时指向 {existing.id} 与 {platform.id}")
            index[key] = platform
    return index


PLATFORM_BY_ALIAS: dict[str, Platform] = _build_alias_index()

# 机种在词表里的位次：外部机种的展示顺序按它排（未收录的排到最后）
PLATFORM_ORDER: dict[str, int] = {platform.id: index for index, platform in enumerate(PLATFORMS)}


def resolve_platform(raw: str) -> Platform | None:
    """把外部名录里的机种名解析成机种；认不出返回 None（调用方回退显示原文）。"""
    return PLATFORM_BY_ALIAS.get(normalize_name(raw))


# 游戏名录 CSV 的「文件名 stem → 机种原始名」。
#
# 名录 CSV 现在只有 `中文名,英文名` 两列（首行表头），机种身份由文件名决定。这里刻意映射回旧版第一列的
# 中文写法（而不是映射成 `platform.id`）：去重键仍是 `(机种原始名, 中文, 英文)`，
# `console.raw_names` 与未收录机种的显示名（`世嘉 dc`、`索尼 PS2`）因此与旧数据完全一致。
# `ps2-jp` / `ps2-us` 必须共用 `索尼PS2`，否则两份文件之间的同款游戏不会被跨文件去重。
# 自定义 `--csv-dir` 下未登记的文件名由 search_index 回退为文件名 stem 本身。
SEARCH_CSV_CONSOLE_NAMES: dict[str, str] = {
    # 任天堂
    "nes": "任天堂FC",
    "nes-fds": "任天堂FC磁碟机",
    "snes": "任天堂SFC",
    "snes-sufami-turbo": "任天堂SFC - Sufami Turbo",
    "gb": "任天堂GB",
    "gbc": "任天堂GBC",
    "gba": "任天堂GBA",
    "nds": "任天堂NDS",
    "n64": "任天堂N64",
    "vb": "任天堂Virtual Boy",
    "3ds": "任天堂3DS",
    "wii": "任天堂Wii",
    "wiiu": "任天堂Wiiu",
    "game-watch": "任天堂GAME&WATCH",
    "pokemon-mini": "任天堂pokemon mini",
    # 世嘉
    "segaMD": "世嘉MD",
    "segaGG": "世嘉GG",
    "sega32x": "世嘉32x",
    "segaSaturn": "世嘉土星SS",
    "segaCD": "世嘉cd游戏",
    "dc": "世嘉dc",
    # 索尼
    "psx": "索尼PS1",
    "psp": "索尼PSP",
    "ps2-jp": "索尼PS2",
    "ps2-us": "索尼PS2",
    "psv": "索尼PSV",
    # 日电 / SNK / 万代
    "pce": "日电PCE",
    "pcecd": "日电pcecd",
    "ngp": "SNK公司NGPC",
    "ws": "万代WS,WSC",
    "rx78": "万代RX-78",
    # 雅达利 / 松下
    "atari2600": "雅达利2600",
    "atari5200": "雅达利5200",
    "atari7800": "雅达利7800",
    "jaguar": "雅达利Jaguar",
    "lynx": "雅达利Lynx",
    "3do": "松下3DO游戏",
}


def platform_order(platform_id: str | None) -> int:
    """机种位次；不是已收录机种（未收录）时返回词表长度，即排到最后。"""
    return PLATFORM_ORDER.get(platform_id or "", len(PLATFORMS))


# 未收录机种的统一显示名。这些机器没有 EmulatorJS system（进不了 `PLATFORMS`），
# 但外部名录里出现过；名字本身不带厂商，光靠 `display_console_name` 补不出厂商前缀。
# 键是 `normalize_name()` 的口径，值是统一显示名。
_UNMATCHED_CONSOLE_LABELS: dict[str, str] = {
    normalize_name("3DS"): "任天堂 3DS",
    normalize_name("任天堂3DS"): "任天堂 3DS",
    normalize_name("CD-I"): "飞利浦 CD-i",
    normalize_name("飞利浦CD-i"): "飞利浦 CD-i",
}


def console_label(raw: str) -> str:
    """外部名录机种的显示名：认不出的机种先查显式表，否则只补厂商名后的空格。"""
    text = (raw or "").strip()
    return _UNMATCHED_CONSOLE_LABELS.get(normalize_name(text)) or display_console_name(text)


def platform_label(platform_id: str | None, fallback: str = "") -> str:
    """机种的统一显示名；认不出机种时回退给调用方给的原文，并走未收录机种的显示名。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    if platform:
        return platform.label
    return console_label(fallback) or platform_id or ""


def playable_platforms() -> tuple[Platform, ...]:
    """本项目已收录、可上传可玩的机种（有本体扩展名白名单的那些）。"""
    return tuple(platform for platform in PLATFORMS if platform.extensions)


def normalize_extension(extension: str) -> str:
    """扩展名的比较口径：去空白、转小写、补前导点；空串返回空串。"""
    value = (extension or "").strip().lower()
    if not value:
        return ""
    return value if value.startswith(".") else f".{value}"


def playable_platforms_for_extension(extension: str) -> tuple[Platform, ...]:
    """该后缀的全部候选机种，顺序即词表顺序（候选第 1 个就是默认选中项）。

    同一后缀可以属于多个机种（Commodore 的 `.d64` / `.prg`），
    所以调用方不能假设「一个后缀只对应一个类型」。
    """
    normalized = normalize_extension(extension)
    if not normalized:
        return ()
    return tuple(
        platform
        for platform in playable_platforms()
        if normalized in {normalize_extension(ext) for ext in platform.extensions}
    )


# 多候选后缀的默认选中项：词表顺序第一个不一定是最常见的格式。
# `.chd` 在土星 / PS1 / PC-FX / 3DO 间共用，实际 PS1 镜像最多，但词表里土星排在 PS1 前。
# 这里只改「默认选中项」，不改变 `playable_platforms_for_extension()` 的候选顺序。
_EXTENSION_DEFAULT_OVERRIDES: dict[str, str] = {".chd": "psx"}


def default_playable_platform_for_extension(extension: str) -> Platform | None:
    """默认候选机种：先看覆盖表，再取词表顺序第一个；没有候选返回 None。"""
    normalized = normalize_extension(extension)
    if not normalized:
        return None
    candidates = playable_platforms_for_extension(normalized)
    override_id = _EXTENSION_DEFAULT_OVERRIDES.get(normalized)
    if override_id:
        override = next((item for item in candidates if item.id == override_id), None)
        if override is not None:
            return override
    return candidates[0] if candidates else None


def all_body_extensions() -> tuple[str, ...]:
    """全部可玩机种的本体扩展名（去重、排序），供上传 accept 与报错文案。"""
    extensions = {
        normalize_extension(ext)
        for platform in playable_platforms()
        for ext in platform.extensions
    }
    return tuple(sorted(extensions))


def bundle_platforms() -> tuple[Platform, ...]:
    """支持多文件本体的可玩机种（`bundle_extensions` 非空）。"""
    return tuple(
        platform for platform in playable_platforms() if platform.bundle_extensions
    )


def platform_bundle_extensions(platform_id: str) -> tuple[str, ...]:
    """该机种多文件本体允许出现的后缀；不支持多文件时返回空元组。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    return platform.bundle_extensions if platform else ()


def platform_bundle_entries(platform_id: str) -> tuple[str, ...]:
    """该机种多文件本体可当入口的后缀；不支持多文件时返回空元组。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    return platform.bundle_entries if platform else ()


def platform_upload_extensions(platform_id: str) -> tuple[str, ...]:
    """文件选择框 accept 用的后缀：单文件白名单 + 多文件包内白名单（去重保序）。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    if platform is None:
        return ()
    seen: list[str] = []
    for ext in (*platform.extensions, *platform.bundle_extensions):
        normalized = normalize_extension(ext)
        if normalized and normalized not in seen:
            seen.append(normalized)
    return tuple(seen)


def playable_platforms_for_bundle_extension(extension: str) -> tuple[Platform, ...]:
    """该后缀可作为多文件包内文件的候选机种，顺序即词表顺序。"""
    normalized = normalize_extension(extension)
    if not normalized:
        return ()
    return tuple(
        platform
        for platform in bundle_platforms()
        if normalized in {normalize_extension(ext) for ext in platform.bundle_extensions}
    )


def playable_platforms_for_any_extension(extension: str) -> tuple[Platform, ...]:
    """单文件或包内文件的全部候选机种，按词表顺序、按机种去重。"""
    normalized = normalize_extension(extension)
    if not normalized:
        return ()
    candidates: list[Platform] = []
    for platform in playable_platforms():
        allowed = {
            normalize_extension(ext)
            for ext in (*platform.extensions, *platform.bundle_extensions)
        }
        if normalized in allowed:
            candidates.append(platform)
    return tuple(candidates)


def all_bundle_extensions() -> tuple[str, ...]:
    """全部多文件包内后缀（去重、排序），供上传会话白名单与报错文案。"""
    extensions = {
        normalize_extension(ext)
        for platform in bundle_platforms()
        for ext in platform.bundle_extensions
    }
    return tuple(sorted(extensions))


def platform_cores(platform_id: str) -> tuple[str, ...]:
    """该机种在 EJS 里的 core 列表；不是机种时返回空元组。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    return platform.cores if platform else ()


def platform_threads(platform_id: str) -> bool:
    """该机种是否必须用线程核；不是机种或不需要线程时返回 False。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    return bool(platform.threads) if platform else False
