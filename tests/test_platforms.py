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
    normalize_name,
    platform_label,
    platform_order,
    playable_platforms,
    resolve_platform,
)
from backend.games.service import GAME_TYPES, GAME_TYPE_LABELS

# EmulatorJS 的引擎资产（`frontend/scripts/fetch-emulatorjs.mjs` 拉到 public/ 下，不进 git），
# 机种表的权威来源就在它的 `EmulatorJS.getCores()` 里
_EJS_BUNDLE = (
    Path(__file__).resolve().parents[1]
    / "frontend/public/emulatorjs/data/emulator.min.js"
)
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


def _emulatorjs_systems() -> set[str]:
    """从 EJS 引擎里抠出 system 表（`getCores()` 返回的那个对象的键）。"""
    source = _EJS_BUNDLE.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"getCores\(\)\{let \w+=\{([^}]*)\}", source)
    if match is None:  # pragma: no cover - 引擎换了写法才会走到
        pytest.fail(f"没能在 {_EJS_BUNDLE} 里找到 getCores() 的机种表")
    return set(re.findall(r'"?([A-Za-z0-9_]+)"?\s*:\s*\[', match.group(1)))


def _frontend_game_type_labels() -> dict[str, str]:
    """从 `gameTypes.js` 的 GAME_TYPE_LIST 里抠出 slug → label。"""
    source = _FRONTEND_GAME_TYPES.read_text(encoding="utf-8")
    slugs = re.findall(r'slug:\s*"([^"]+)"', source)
    labels = re.findall(r'label:\s*"([^"]+)"', source)
    assert len(slugs) == len(labels), "GAME_TYPE_LIST 里 slug 与 label 的条数对不上"
    return dict(zip(slugs, labels))


# --------------------------------------------------------------------------
# 词表自身
# --------------------------------------------------------------------------


def test_platforms_match_emulatorjs_systems():
    """机种表逐字对应 EmulatorJS 的 system 表——引擎升级后要对一次表。"""
    if not _EJS_BUNDLE.is_file():  # pragma: no cover - 没跑过 fetch-emulatorjs 的机器
        pytest.skip("还没有拉取 EmulatorJS 资产（npm run dev / make all 时会拉）")
    assert {platform.id for platform in PLATFORMS} == _emulatorjs_systems()


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


def test_playable_platforms_are_complete():
    """可玩机种必须有扩展名白名单与默认后缀，且扩展名互不重叠（判定不能有歧义）。"""
    playable = playable_platforms()
    assert playable, "一个可玩机种都没有"
    seen: dict[str, str] = {}
    for platform in playable:
        assert platform.extensions, platform.id
        assert platform.default_extension in platform.extensions, platform.id
        for extension in platform.extensions:
            assert extension not in seen, f"{extension} 同时属于 {seen[extension]} 与 {platform.id}"
            seen[extension] = platform.id


def test_resolve_platform_ignores_case_and_whitespace():
    for raw in ("sega md", "SEGA  MD", "世嘉 md", " 世嘉MD  "):
        assert resolve_platform(raw).id == "segaMD", raw
    assert resolve_platform("不存在的机种") is None
    assert resolve_platform("") is None


def test_platform_label_falls_back_to_the_raw_name():
    assert platform_label("nes") == "任天堂 FC"
    assert platform_label(None, "任天堂Wii") == "任天堂Wii"
    assert platform_label("raw:3ds", "3DS") == "3DS"


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


def test_frontend_labels_match_the_registry():
    """前端展示层是词表的镜像（与 coverStyles 同一套约定），两边必须逐字一致。"""
    labels = _frontend_game_type_labels()
    assert set(labels) == set(GAME_TYPES)
    for game_type, label in labels.items():
        assert label == GAME_TYPE_LABELS[game_type], game_type


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
        {"id": p.id, "label": p.label, "cores": list(p.cores), "extensions": list(p.extensions)}
        for p in PLATFORMS
    ]
    assert len(json.loads(json.dumps(payload, ensure_ascii=False))) == len(PLATFORMS)
