"""机种词表（`backend/games/platforms.py`）的自检。

词表是「同一个平台在整个项目里只有一个身份、一个名字」的唯一来源，所以这里既钉它自己的
不变量，也钉它与三处消费方的一致性：

- **与 EmulatorJS 的 system 表逐字对应**——引擎升级（改了 `EJS_VERSION` 并重拉资产）之后
  这条会红，提醒重新对表；
- id / 别名不冲突；
- 可玩机种 = `service.GAME_TYPES` 里的机种部分，且顺序一致；
- 前端 `constants/gameTypes.js` 的 label 与词表逐字一致；
- 两份**真实** CSV 里的每一个机种名都能被解析，或明确落在「未收录」名单里——
  名录换了写法而词表没跟上时，这条会红（否则页面上会静默多出一个「未收录」机种）。
"""

import json
import re
from pathlib import Path

import pytest

from backend.config import RANKING_CSV_PATH, SEARCH_CSV_DIR
from backend.games.platforms import (
    PLATFORM_BY_ALIAS,
    PLATFORM_BY_ID,
    PLATFORMS,
    BiosSpec,
    all_bundle_extensions,
    bundle_platforms,
    default_playable_platform_for_extension,
    normalize_name,
    platform_bundle_entries,
    platform_bundle_extensions,
    platform_label,
    platform_order,
    platform_upload_extensions,
    playable_platforms,
    playable_platforms_for_bundle_extension,
    playable_platforms_for_extension,
    resolve_platform,
)
from backend.games.service import GAME_TYPES, GAME_TYPE_LABELS

# EmulatorJS 的引擎资产（`frontend/scripts/fetch-emulatorjs.mjs` 拉到 public/ 下，不进 git），
# 机种表的权威来源就在它的 `EmulatorJS.getCores()` 里
_EJS_BUNDLE = (
    Path(__file__).resolve().parents[1]
    / "frontend/public/emulatorjs/data/emulator.min.js"
)
# 前端展示层的类型注册表来自 `/api/games/status`，不再手写 label / 扩展名镜像。
# 这里只检查前端没有把映射写回去（常量文件里不应出现类型条目定义）。
_FRONTEND_GAME_TYPES = (
    Path(__file__).resolve().parents[1] / "frontend/src/constants/gameTypes.js"
)

# 外部名录里对不上任何 EmulatorJS 机种的写法：这些机种引擎不认，只能保留原文展示。
# 词表给它们补上别名之后，要从这里删掉（`test_unmatched_*` 会拦住「加了别名却忘了删」）。
_UNMATCHED_SEARCH_CONSOLES = {
    "万代RX-78",
    "世嘉dc",
    "任天堂3DS",
    "任天堂GAME&WATCH",
    "任天堂Wii",
    "任天堂Wiiu",
    "任天堂pokemon mini",
    "索尼PS2",
    "索尼PSV",
}
_UNMATCHED_RANKING_CONSOLES = {"3DS", "CD-I"}


def _emulatorjs_cores() -> dict[str, set[str]]:
    """从 EJS 引擎里抠出 system → core 集合（`getCores()` 返回的那个对象）。"""
    source = _EJS_BUNDLE.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"getCores\(\)\{let \w+=\{([^}]*)\}", source)
    if match is None:  # pragma: no cover - 引擎换了写法才会走到
        pytest.fail(f"没能在 {_EJS_BUNDLE} 里找到 getCores() 的机种表")
    pairs = re.findall(r'"?([A-Za-z0-9_]+)"?\s*:\s*\[([^\]]*)\]', match.group(1))
    return {
        key: set(re.findall(r'"([^"]+)"', cores))
        for key, cores in pairs
    }


def _emulatorjs_systems() -> set[str]:
    """从 EJS 引擎里抠出 system 表（`getCores()` 返回的那个对象的键）。"""
    return set(_emulatorjs_cores())


def _frontend_game_types_source() -> str:
    return _FRONTEND_GAME_TYPES.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 词表自身
# --------------------------------------------------------------------------


def test_platforms_match_emulatorjs_systems():
    """机种表逐字对应 EmulatorJS 的 system 表——引擎升级后要对一次表。"""
    if not _EJS_BUNDLE.is_file():  # pragma: no cover - 没跑过 fetch-emulatorjs 的机器
        pytest.skip("还没有拉取 EmulatorJS 资产（npm run dev / make all 时会拉）")
    assert {platform.id for platform in PLATFORMS} == _emulatorjs_systems()


def test_platform_cores_match_emulatorjs_systems():
    """词表声明的 core 必须是 EJS 该 system 真实支持的 core。"""
    if not _EJS_BUNDLE.is_file():  # pragma: no cover
        pytest.skip("还没有拉取 EmulatorJS 资产（npm run dev / make all 时会拉）")
    systems = _emulatorjs_cores()
    for platform in PLATFORMS:
        missing = set(platform.cores) - systems[platform.id]
        assert not missing, f"{platform.id} 声明了 EJS 不支持的 core：{sorted(missing)}"


def test_platform_ids_are_unique():
    assert len(PLATFORM_BY_ID) == len(PLATFORMS)


def test_alias_index_has_no_conflicts():
    """一个别名只能指向一个机种；`id` 与 `label` 也当别名收（见 `_build_alias_index`）。"""
    for platform in PLATFORMS:
        for raw in (*platform.aliases, platform.label, platform.id):
            assert resolve_platform(raw) is platform
    assert len(PLATFORM_BY_ALIAS) >= sum(len(platform.aliases) for platform in PLATFORMS)


def test_every_platform_declares_its_cores():
    """每个机种都要写清 EJS 用哪些 core——这是「能玩不能玩」的依据。"""
    for platform in PLATFORMS:
        assert platform.cores, platform.id
        assert platform.label, platform.id


def test_playable_platforms_declare_extensions_and_defaults():
    """可玩机种必须有扩展名白名单与默认后缀，且默认后缀在白名单内。

    扩展名允许跨机种重叠（Commodore 的 `.d64` / `.prg`），重叠时由候选集消歧，
    所以这里不再断言「扩展名互不重叠」。
    """
    playable = playable_platforms()
    assert playable, "一个可玩机种都没有"
    for platform in playable:
        assert platform.extensions, platform.id
        assert platform.default_extension in platform.extensions, platform.id


def test_bios_specs_are_well_formed():
    """BIOS 只在词表里声明一次，文件名与包内文件都必须是安全的 basename。"""
    seen: set[str] = set()
    for platform in PLATFORMS:
        spec = platform.bios
        if spec is None:
            continue
        assert platform.extensions, f"不可玩机种不该声明 BIOS：{platform.id}"
        assert spec.file == f"{platform.id}.zip", platform.id
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.zip", spec.file), spec.file
        assert spec.required_files, platform.id
        for name in spec.required_files:
            assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name), name
        assert len(set(spec.required_files)) == len(spec.required_files), platform.id
        assert spec.file not in seen, f"BIOS 包文件名重复：{spec.file}"
        seen.add(spec.file)

    assert PLATFORM_BY_ID["nds"].bios == BiosSpec(
        "nds.zip", ("bios7.bin", "bios9.bin", "firmware.bin")
    )
    assert PLATFORM_BY_ID["atari5200"].bios == BiosSpec(
        "atari5200.zip", ("5200.rom",), optional=True
    )
    assert PLATFORM_BY_ID["lynx"].bios == BiosSpec("lynx.zip", ("lynxboot.img",))
    assert PLATFORM_BY_ID["coleco"].bios == BiosSpec(
        "coleco.zip", ("colecovision.rom",)
    )
    assert PLATFORM_BY_ID["psx"].bios == BiosSpec(
        "psx.zip", ("scph5500.bin", "scph5501.bin", "scph5502.bin")
    )
    assert PLATFORM_BY_ID["segaSaturn"].bios == BiosSpec(
        "segaSaturn.zip", ("saturn_bios.bin",)
    )
    assert PLATFORM_BY_ID["pcfx"].bios == BiosSpec("pcfx.zip", ("pcfx.rom",))
    assert PLATFORM_BY_ID["3do"].bios == BiosSpec("3do.zip", ("panafz1.bin",))
    assert PLATFORM_BY_ID["segaCD"].bios == BiosSpec(
        "segaCD.zip", ("bios_CD_E.bin", "bios_CD_U.bin", "bios_CD_J.bin")
    )
    assert PLATFORM_BY_ID["amiga"].bios == BiosSpec(
        "amiga.zip", ("kick34005.A500", "kick40068.A1200"), optional=True
    )
    assert PLATFORM_BY_ID["arcade"].bios == BiosSpec(
        "arcade.zip", ("neogeo.zip", "pgm.zip"), optional=True
    )
    assert PLATFORM_BY_ID["psp"].bios is None
    assert PLATFORM_BY_ID["dos"].bios is None
    assert PLATFORM_BY_ID["n64"].bios is None
    assert PLATFORM_BY_ID["nes"].bios is None


def test_bundle_extensions_are_well_formed():
    """多文件包内后缀必须是单文件白名单的超集，入口必须是包内后缀的子集。"""
    for platform in bundle_platforms():
        assert platform.bundle_extensions, platform.id
        assert platform.bundle_entries, platform.id
        bundle = {ext.lower() for ext in platform.bundle_extensions}
        entries = {ext.lower() for ext in platform.bundle_entries}
        assert entries <= bundle, platform.id
        # 单文件能上传的后缀也必须能在多文件包里出现
        assert {ext.lower() for ext in platform.extensions} <= bundle, platform.id
        assert all(ext.startswith(".") for ext in platform.bundle_extensions), platform.id
        assert all(ext.startswith(".") for ext in platform.bundle_entries), platform.id

    assert bundle_platforms() == (
        PLATFORM_BY_ID["segaCD"],
        PLATFORM_BY_ID["amiga"],
    )
    assert platform_bundle_extensions("segaCD") == (".cue", ".bin", ".m3u", ".chd")
    assert platform_bundle_entries("segaCD") == (".m3u", ".cue", ".chd")
    assert platform_bundle_extensions("amiga") == (".adf", ".hdf", ".m3u")
    assert platform_bundle_entries("amiga") == (".m3u", ".adf", ".hdf")
    assert platform_bundle_extensions("nes") == ()
    assert platform_upload_extensions("segaCD") == (".chd", ".cue", ".bin", ".m3u")
    assert platform_upload_extensions("amiga") == (".adf", ".hdf", ".m3u")


def test_bundle_extensions_resolve_to_platforms():
    """包内后缀只用于多文件类型推断；单文件候选表保持原样。"""
    assert [p.id for p in playable_platforms_for_bundle_extension(".cue")] == ["segaCD"]
    assert [p.id for p in playable_platforms_for_bundle_extension(".bin")] == ["segaCD"]
    assert [p.id for p in playable_platforms_for_bundle_extension(".m3u")] == [
        "segaCD",
        "amiga",
    ]
    assert [p.id for p in playable_platforms_for_bundle_extension(".adf")] == ["amiga"]
    assert [p.id for p in playable_platforms_for_bundle_extension(".hdf")] == ["amiga"]
    assert playable_platforms_for_bundle_extension(".nes") == ()
    assert all_bundle_extensions() == (
        ".adf",
        ".bin",
        ".chd",
        ".cue",
        ".hdf",
        ".m3u",
    )

    # 单文件判型表不变：cue/bin 仍不开放，chd/adf/hdf 按单文件候选
    assert playable_platforms_for_extension(".cue") == ()
    assert playable_platforms_for_extension(".bin") == ()
    assert [p.id for p in playable_platforms_for_extension(".adf")] == ["amiga"]
    assert [p.id for p in playable_platforms_for_extension(".hdf")] == ["amiga"]


def test_atari5200_lynx_coleco_extensions_resolve():
    """Atari 5200 / Lynx / ColecoVision 的后缀各自唯一，不与现有词表重叠。"""
    assert [p.id for p in playable_platforms_for_extension(".a52")] == ["atari5200"]
    assert [p.id for p in playable_platforms_for_extension(".lnx")] == ["lynx"]
    assert [p.id for p in playable_platforms_for_extension(".col")] == ["coleco"]
    assert default_playable_platform_for_extension(".a52").id == "atari5200"
    assert default_playable_platform_for_extension(".lnx").id == "lynx"
    assert default_playable_platform_for_extension(".col").id == "coleco"


def test_n64_and_cd_image_extensions_resolve():
    """N64 三个后缀各自唯一；CD 镜像按候选集消歧，默认项可被覆盖。"""
    for extension in (".z64", ".n64", ".v64"):
        assert [p.id for p in playable_platforms_for_extension(extension)] == ["n64"]
    assert default_playable_platform_for_extension(".z64").id == "n64"
    assert default_playable_platform_for_extension(".n64").id == "n64"
    assert default_playable_platform_for_extension(".v64").id == "n64"

    assert [p.id for p in playable_platforms_for_extension(".pbp")] == ["psx"]
    assert [p.id for p in playable_platforms_for_extension(".iso")] == [
        "psx",
        "psp",
        "3do",
    ]
    assert [p.id for p in playable_platforms_for_extension(".chd")] == [
        "segaCD",
        "segaSaturn",
        "psx",
        "pcfx",
        "3do",
    ]
    # 候选顺序仍是词表顺序，但默认项由覆盖表指定为更常见的 PS1
    assert default_playable_platform_for_extension(".chd").id == "psx"
    assert default_playable_platform_for_extension(".iso").id == "psx"
    assert default_playable_platform_for_extension(".pbp").id == "psx"

    # 多文件 / 歧义后缀继续不开放
    assert playable_platforms_for_extension(".cue") == ()
    assert playable_platforms_for_extension(".bin") == ()


def test_psp_dos_arcade_extensions_resolve():
    """PSP 的 .cso 唯一，DOS 的 .jsdos 唯一，.zip 由 DOS / 街机共用。"""
    assert [p.id for p in playable_platforms_for_extension(".cso")] == ["psp"]
    assert [p.id for p in playable_platforms_for_extension(".jsdos")] == ["dos"]
    assert [p.id for p in playable_platforms_for_extension(".zip")] == [
        "dos",
        "arcade",
    ]
    assert default_playable_platform_for_extension(".cso").id == "psp"
    assert default_playable_platform_for_extension(".jsdos").id == "dos"


def test_threaded_platforms_match_emulatorjs():
    """`Platform.threads` 必须与 EJS 的 requiresThreads() 一致。"""
    if not _EJS_BUNDLE.is_file():  # pragma: no cover
        pytest.skip("还没有拉取 EmulatorJS 资产（npm run dev / make all 时会拉）")
    source = _EJS_BUNDLE.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"requiresThreads\(t\)\{return\[([^\]]*)\]\.includes\(t\)\}", source
    )
    if match is None:  # pragma: no cover - 引擎换了写法才会走到
        pytest.fail(f"没能在 {_EJS_BUNDLE} 里找到 requiresThreads()")
    required_cores = set(re.findall(r'"([^"]+)"', match.group(1)))
    for platform in playable_platforms():
        expected = bool(set(platform.cores) & required_cores)
        assert platform.threads == expected, platform.id
    assert PLATFORM_BY_ID["psp"].threads is True
    assert PLATFORM_BY_ID["dos"].threads is True
    assert PLATFORM_BY_ID["arcade"].threads is False


def test_extension_candidates_follow_registry_order():
    """同一后缀的候选按词表顺序给出，第 1 个就是默认选中项。"""
    assert [p.id for p in playable_platforms_for_extension(".d64")] == [
        "c64",
        "c128",
        "pet",
        "plus4",
        "vic20",
    ]
    assert [p.id for p in playable_platforms_for_extension("d64")] == [
        "c64",
        "c128",
        "pet",
        "plus4",
        "vic20",
    ]
    assert [p.id for p in playable_platforms_for_extension(".prg")] == [
        "c64",
        "c128",
        "pet",
        "plus4",
        "vic20",
    ]
    assert [p.id for p in playable_platforms_for_extension(".d71")] == ["c128"]
    assert [p.id for p in playable_platforms_for_extension(".tap")] == ["c64"]
    assert playable_platforms_for_extension(".bin") == ()
    assert default_playable_platform_for_extension(".d64").id == "c64"
    assert default_playable_platform_for_extension(".d71").id == "c128"
    assert default_playable_platform_for_extension(".bin") is None


def test_resolve_platform_ignores_case_and_whitespace():
    for raw in ("sega md", "SEGA  MD", "世嘉 md", " 世嘉MD  "):
        assert resolve_platform(raw).id == "segaMD", raw
    assert resolve_platform("不存在的机种") is None
    assert resolve_platform("") is None


def test_platform_label_falls_back_to_the_raw_name():
    assert platform_label("nes") == "任天堂 FC"
    assert platform_label(None, "3DS") == "3DS"
    assert platform_label("raw:3ds", "3DS") == "3DS"


def test_platform_label_formats_unmatched_company_names():
    """认不出的机种也按「公司名 + 空格 + 型号」显示，不能原样吐 `任天堂3DS`。"""
    assert platform_label(None, "任天堂3DS") == "任天堂 3DS"
    assert platform_label(None, "索尼PS2") == "索尼 PS2"
    assert platform_label(None, "世嘉dc") == "世嘉 dc"
    assert platform_label(None, "任天堂 Wii") == "任天堂 Wii"
    assert platform_label("raw:3ds", "任天堂3DS") == "任天堂 3DS"


# 显示名统一为「公司名 + 空格 + 型号」；没有公司名的只写型号。
# 这里只钉住「厂商名后面必须有空格」，不强制每台机器都写厂商。
_LABEL_COMPANY_PREFIXES = (
    "任天堂",
    "世嘉",
    "索尼",
    "日电",
    "万代",
    "雅达利",
    "松下",
    "SNK",
    "Commodore",
)


def test_platform_labels_use_company_space_model():
    for platform in PLATFORMS:
        label = platform.label
        assert label == label.strip(), platform.id
        assert "  " not in label, platform.id
        for company in _LABEL_COMPANY_PREFIXES:
            if label.startswith(company):
                rest = label[len(company) :]
                assert rest.startswith(" "), (
                    f"{platform.id} 的显示名「{label}」在厂商名后缺少空格"
                )


def test_unmatched_console_labels_use_company_space_model():
    """未收录机种没有词表 label，展示时也必须补厂商名后的空格。"""
    for raw in _UNMATCHED_SEARCH_CONSOLES:
        label = platform_label(None, raw)
        for company in _LABEL_COMPANY_PREFIXES:
            if label.startswith(company):
                rest = label[len(company) :]
                assert rest.startswith(" "), f"{raw!r} 的显示名「{label}」缺少空格"


def test_platform_order_puts_unknown_platforms_last():
    assert platform_order("nes") == 0
    assert platform_order("nes") < platform_order("snes")
    assert platform_order(None) == len(PLATFORMS)
    assert platform_order("raw:3ds") == len(PLATFORMS)


# --------------------------------------------------------------------------
# 与三处消费方的一致性
# --------------------------------------------------------------------------


def test_game_types_are_flash_h5_plus_playable_platforms_in_order():
    assert GAME_TYPES == ("flash", "h5", *[p.id for p in playable_platforms()])


def test_game_type_labels_match_the_registry():
    assert GAME_TYPE_LABELS["flash"] == "Flash"
    assert GAME_TYPE_LABELS["h5"] == "HTML5"
    for platform in playable_platforms():
        assert GAME_TYPE_LABELS[platform.id] == platform.label


def test_frontend_does_not_hardcode_the_type_registry():
    """前端不再保存 label / 扩展名映射：它们只从 `/api/games/status` 读取。

    机种与后缀的映射只在 `backend/games/platforms.py` 维护，避免第二份表漂移。
    """
    source = _frontend_game_types_source()
    assert "GAME_TYPE_LIST" not in source
    assert not re.search(r'slug:\s*"', source)
    assert "extensions: [" not in source


# --------------------------------------------------------------------------
# 与两份真实 CSV 的一致性
# --------------------------------------------------------------------------


def _search_csv_consoles() -> set[str]:
    import csv

    names: set[str] = set()
    for path in sorted(SEARCH_CSV_DIR.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                if row and row[0].strip():
                    names.add(row[0].strip())
    return names


def _ranking_csv_consoles() -> set[str]:
    import csv
    import io

    text = RANKING_CSV_PATH.read_text(encoding="utf-8-sig")
    names: set[str] = set()
    for index, row in enumerate(csv.reader(io.StringIO(text, newline=""))):
        row = [cell.strip() for cell in row]
        if not any(row) or (index == 0 and row[0] in {"序号", "排名"}):
            continue
        if len(row) >= 2 and row[1]:
            names.add(row[1])
    return names


def _assert_all_resolve(names: set[str], unmatched: set[str]) -> None:
    for name in sorted(names):
        platform = resolve_platform(name)
        if name in unmatched:
            assert platform is None, f"{name} 已经能解析成 {platform.id}，请从「未收录」名单里删掉"
        else:
            assert platform is not None, f"机种「{name}」没有对应词表条目，也没有列进「未收录」名单"


def test_every_search_console_name_resolves_or_is_listed_as_unmatched():
    assert _search_csv_consoles()
    _assert_all_resolve(_search_csv_consoles(), _UNMATCHED_SEARCH_CONSOLES)


def test_every_ranking_console_name_resolves_or_is_listed_as_unmatched():
    assert _ranking_csv_consoles()
    _assert_all_resolve(_ranking_csv_consoles(), _UNMATCHED_RANKING_CONSOLES)


def test_merged_search_consoles_collapse_into_one_registry_platform():
    """检索侧会把同一机种的多个原始名合并成一项，这里钉住合并后的项数。"""
    groups = {
        resolve_platform(name).id if resolve_platform(name) else f"raw:{normalize_name(name)}"
        for name in _search_csv_consoles()
    }
    assert len(groups) == 32
    # 几个典型的合并：GB 与 GBC 同属 `gb`，FC 与 FC 磁碟机同属 `nes`
    assert resolve_platform("任天堂GB").id == resolve_platform("任天堂GBC").id == "gb"
    assert resolve_platform("任天堂FC").id == resolve_platform("任天堂FC磁碟机").id == "nes"
    assert (
        resolve_platform("任天堂SFC").id
        == resolve_platform("任天堂SFC - Sufami Turbo").id
        == "snes"
    )


def test_ranking_consoles_do_not_share_a_platform():
    """榜单里一个机种一行，所以两个不同的写法不该落到同一个机种上（否则下拉会出现同名项）。"""
    groups: dict[str, list[str]] = {}
    for name in _ranking_csv_consoles():
        platform = resolve_platform(name)
        key = platform.id if platform else f"raw:{normalize_name(name)}"
        groups.setdefault(key, []).append(name)
    collisions = {key: names for key, names in groups.items() if len(names) > 1}
    assert collisions == {}


def test_registry_is_serializable_to_json():
    """词表要能原样吐给别的消费方（现在是测试用，将来若加接口也是这个形状）。"""
    payload = [
        {
            "id": p.id,
            "label": p.label,
            "cores": list(p.cores),
            "extensions": list(p.extensions),
            "bios": (
                {
                    "file": p.bios.file,
                    "required_files": list(p.bios.required_files),
                    "optional": p.bios.optional,
                }
                if p.bios
                else None
            ),
        }
        for p in PLATFORMS
    ]
    assert len(json.loads(json.dumps(payload, ensure_ascii=False))) == len(PLATFORMS)
