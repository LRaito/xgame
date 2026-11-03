"""机种词表——全项目「这是哪台机器」的唯一权威来源。

同一个平台在项目里原本有三套写法，互相看不出是同一个东西：

- **游戏管理**用 `game_type`（`nes` / `segaMD` / …，同时是磁盘目录名）；
- **游戏检索**用外部名录 CSV 第一列的中文长名（`任天堂FC`、`世嘉MD`、`任天堂GB`、`任天堂GBC` …）；
- **游戏榜单**用榜单 CSV 第 2 列的英文短名（`FC`、`MD`、`GB/GBC` …）。

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
3. **`extensions` 非空才代表本项目已收录、可上传可玩**——当前 24 个机种有；其余机种（含 EJS 支持
   但本项目还没打包 core 的 n64/psx 等）只用来给外部名录「对上号」，不开放上传。

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

    `aliases` 是外部名录里出现过的各种写法（含检索 CSV 与榜单 CSV 的实际取值），
    用于把 `console` 那一列的自由文本解析回机种；匹配时忽略大小写与所有空白。
    """

    id: str  # EmulatorJS system key
    label: str  # 统一显示名（中文）
    cores: tuple[str, ...]  # EJS 该 system 的 core，逐字取自 EJS
    aliases: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()  # 非空 = 本项目已收录可玩；值即 game_type
    default_extension: str = ""  # 网络直链看不出后缀时补的那个（只有可玩机种有）
    bios: BiosSpec | None = None  # 需要 BIOS 的机种在这里声明


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
        label="任天堂 Virtual Boy",
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
    ),
    Platform(
        id="psp",
        label="索尼 PSP",
        cores=("ppsspp",),
        aliases=("索尼PSP", "PSP"),
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
    ),
    # Commodore 五个共用 .d64 / .prg：后缀不唯一时由用户选类型，
    # 候选顺序取本表的先后，因此默认候选是 c64。
    Platform(
        id="c64",
        label="Commodore 64",
        cores=("vice_x64sc",),
        aliases=("C64",),
        extensions=(".d64", ".tap", ".crt", ".prg"),
        default_extension=".d64",
    ),
    Platform(
        id="c128",
        label="Commodore 128",
        cores=("vice_x128",),
        aliases=("C128",),
        extensions=(".d64", ".d71", ".prg"),
        default_extension=".d64",
    ),
    Platform(
        id="pet",
        label="Commodore PET",
        cores=("vice_xpet",),
        aliases=("PET",),
        extensions=(".prg", ".d64"),
        default_extension=".prg",
    ),
    Platform(
        id="plus4",
        label="Commodore Plus/4",
        cores=("vice_xplus4",),
        aliases=("PLUS/4",),
        extensions=(".prg", ".d64"),
        default_extension=".prg",
    ),
    Platform(
        id="vic20",
        label="Commodore VIC-20",
        cores=("vice_xvic",),
        aliases=("VIC-20",),
        extensions=(".prg", ".d64"),
        default_extension=".prg",
    ),
    Platform(id="amiga", label="Amiga", cores=("puae",), aliases=("AMIGA",)),
    Platform(id="dos", label="DOS", cores=("dosbox_pure",), aliases=("DOS",)),
    Platform(
        id="arcade",
        label="街机",
        cores=("fbneo", "fbalpha2012_cps1", "fbalpha2012_cps2"),
        aliases=("ARCADE",),
    ),
    # 与 arcade 重叠的另一个街机 system，只作引擎侧的兜底，没有外部名录对应
    Platform(id="mame", label="街机（MAME）", cores=("mame2003_plus", "mame2003")),
)

PLATFORM_BY_ID: dict[str, Platform] = {platform.id: platform for platform in PLATFORMS}


def normalize_name(raw: str) -> str:
    """名字的比较口径：去掉**所有**空白再转小写。

    外部名录的写法很不统一（榜单写 `SEGA CD`、检索写 `世嘉cd游戏`；`SFC - Sufami Turbo`
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


def platform_order(platform_id: str | None) -> int:
    """机种位次；不是已收录机种（未收录）时返回词表长度，即排到最后。"""
    return PLATFORM_ORDER.get(platform_id or "", len(PLATFORMS))


def platform_label(platform_id: str | None, fallback: str = "") -> str:
    """机种的统一显示名；认不出机种时回退给调用方给的原文，并补齐厂商名后的空格。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    if platform:
        return platform.label
    return display_console_name(fallback) or platform_id or ""


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


def default_playable_platform_for_extension(extension: str) -> Platform | None:
    """默认候选机种（词表顺序第一个）；没有候选返回 None。"""
    candidates = playable_platforms_for_extension(extension)
    return candidates[0] if candidates else None


def all_body_extensions() -> tuple[str, ...]:
    """全部可玩机种的本体扩展名（去重、排序），供上传 accept 与报错文案。"""
    extensions = {
        normalize_extension(ext)
        for platform in playable_platforms()
        for ext in platform.extensions
    }
    return tuple(sorted(extensions))


def platform_cores(platform_id: str) -> tuple[str, ...]:
    """该机种在 EJS 里的 core 列表；不是机种时返回空元组。"""
    platform = PLATFORM_BY_ID.get(platform_id or "")
    return platform.cores if platform else ()
