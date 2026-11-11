"""「游戏榜单」的 CSV 解析、构建与筛选测试。

用例不读仓库里的真实榜单 CSV：在 tmp_path 写几个机种文件作为固件，覆盖真实数据的格式边界
（UTF-8 带 BOM、CRLF、引号内的逗号、可选表头、评分、卡带 ID 分隔符）。
"""

import csv
import hashlib
import sqlite3

import pytest
from sqlmodel import Session

from backend.config import RANKING_CSV_DIR, SEARCH_CSV_DIR, Settings
from backend.games import search_index
from backend.games.models import Game
from backend.games.platforms import resolve_platform
from backend.games.ranking_flags import refresh_all_flags
from backend.games.ranking_service import GameRankingService
from backend.games.service import GameService
from backend.games.search_index import (
    RANKING_SCHEMA_VERSION,
    SCHEMA_VERSION,
    RankingCsvError,
    build_index,
)

# 游戏名录：只求 build_index 有东西可建，内容与榜单无关
_SEARCH_ROWS = [
    ("黄金太阳", "Golden Sun (USA)"),
    ("精灵宝可梦 火红", "Pokemon FireRed (USA)"),
]

_RANKING_HEADER = ["中文名", "英文名", "评分", "卡带ID"]
# 机种由文件名决定；三个机种文件覆盖跨机种排序与默认「不选类型」的展示。
_RANKING_FILES = {
    "nes": [
        ["超级马里奥兄弟", "Super Mario Bros.", "8.84316671219157", "NES-SM"],
        ["银河战士", "Metroid", "8.2", "NES-MT"],
    ],
    "gba": [
        ["精灵宝可梦 火红", "Pokemon FireRed", "8.5", "POKEMON FIRE RED"],
        ["黄金太阳", "Golden Sun", "8.1", "GSAE"],
        ["双版本示例", "Double Version Example", "7.75", "ID1;ID2"],
        ["查不到编号的游戏", "No ID Game", "7", ""],
    ],
    "gb": [
        ["塞尔达传说 不可思议的果实", "Zelda - Oracle", "8.0", "ZELDA"],
        ["分隔符示例", "Separator Example", "6.5", "A1/ A2"],
    ],
}
_RANKING_ROWS = [row for rows in _RANKING_FILES.values() for row in rows]
_RANKING_PLATFORMS = 3
# 只有表头的文件：必须被跳过，且照常算在指纹里
_EMPTY_RANKING_FILE = "pet"


def _write_csv(path, rows, *, encoding="utf-8-sig"):
    # 真实数据就是 UTF-8 带 BOM + CRLF，csv 模块负责处理引号
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerows(rows)


def _write_ranking_dir(path, files=None):
    """把 `{机种 id: 数据行}` 写成 `<id>.csv`；默认再补一个只有表头的文件。"""
    path.mkdir(parents=True, exist_ok=True)
    for platform, rows in (files if files is not None else _RANKING_FILES).items():
        _write_csv(path / f"{platform}.csv", [_RANKING_HEADER, *rows])
    _write_csv(path / f"{_EMPTY_RANKING_FILE}.csv", [_RANKING_HEADER])
    return path


def _digest(path):
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_mtime_ns


@pytest.fixture
def csv_dir(tmp_path):
    source = tmp_path / "csv"
    source.mkdir()
    _write_csv(source / "gba.csv", _SEARCH_ROWS)
    return source


@pytest.fixture
def ranking_dir(tmp_path):
    return _write_ranking_dir(tmp_path / "ranking")


@pytest.fixture
def index_path(tmp_path):
    return tmp_path / "storage" / "db" / "game.db"


def _settings(tmp_path, *, testing=False):
    return Settings(TESTING=testing, STORAGE_ROOT=str(tmp_path / "storage"))


def _meta(path, key):
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _ranking_rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT platform, console, score, zh, en, cartridge_ids "
            "FROM ranking ORDER BY platform, score DESC, id"
        ).fetchall()


# --------------------------------------------------------------------------
# CSV 解析
# --------------------------------------------------------------------------


def test_load_ranking_dir_handles_real_format(tmp_path):
    """表头 + BOM + CRLF + 引号内的逗号 + 空行 + Excel 行尾空列 + 只有表头的文件。"""
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(
        path / "gba.csv",
        [
            _RANKING_HEADER,
            ["含,逗号的名字", "Comma, Name", "8.123456", "ID1"],
            [],
            ["普通游戏", "Normal Game", "7.5", "ID2,ID3"],
            ["", "No Chinese Name", "6", "ID4", ""],
        ],
    )
    _write_csv(path / "gb.csv", [_RANKING_HEADER])
    _write_csv(path / "nes.csv", [_RANKING_HEADER, ["游戏", "Game", "9", "ID1"]])

    data = search_index._load_ranking_dir(path)

    assert data.source == "ranking"
    assert [row.zh for row in data.rows] == ["含,逗号的名字", "普通游戏", "", "游戏"]
    assert [row.en for row in data.rows] == [
        "Comma, Name",
        "Normal Game",
        "No Chinese Name",
        "Game",
    ]
    assert [row.score for row in data.rows] == [8.123456, 7.5, 6.0, 9.0]
    assert data.rows[1].cartridge_ids == ("ID2", "ID3")
    assert data.platforms == ("gba", "nes")
    assert [row.console for row in data.rows] == ["gba", "gba", "gba", "nes"]
    assert data.fingerprint


def test_load_ranking_dir_without_header(tmp_path):
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(path / "gba.csv", [["游戏", "Game", "8.5", "ID1"]])

    data = search_index._load_ranking_dir(path)

    assert len(data.rows) == 1
    assert data.rows[0].score == 8.5
    assert data.rows[0].zh == "游戏"
    assert data.rows[0].en == "Game"


def test_load_ranking_dir_allows_empty_cartridge_ids(tmp_path):
    """查不到编号的游戏：第 4 列留空或整列省掉都合法，落成空元组。"""
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(
        path / "c64.csv",
        [
            ["留空", "Empty ID", "8", ""],
            ["省掉第 4 列", "Omit Column", "7"],
        ],
    )

    data = search_index._load_ranking_dir(path)

    assert [row.cartridge_ids for row in data.rows] == [(), ()]


def test_load_ranking_dir_rejects_old_index_header(tmp_path):
    """带序号列的旧表头要明确拒绝，不能把序号当中文名静默解析。"""
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(
        path / "gba.csv",
        [["序号", "中文名", "英文名", "评分", "卡带ID"], ["1", "游戏", "Game", "8", "ID1"]],
    )

    with pytest.raises(RankingCsvError) as excinfo:
        search_index._load_ranking_dir(path)

    assert "四列" in str(excinfo.value)


@pytest.mark.parametrize(
    "rows",
    [
        [["游戏"]],  # 列数不对（少于 3 列）
        [["游戏", "Game", "8", "ID", "多余的一列"]],  # 列数不对（多于 4 列）
        [["游戏", "", "8", "ID"]],  # 缺英文名
        [["游戏", "Game", "", "ID"]],  # 缺评分
        [["游戏", "Game", "abc", "ID"]],  # 评分不是数字
        [["游戏", "Game", "-1", "ID"]],  # 评分为负
        [["游戏", "Game", "8", "A,B,C"]],  # 超过 2 个卡带 ID
    ],
)
def test_load_ranking_dir_rejects_bad_rows(tmp_path, rows):
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(path / "gba.csv", rows)

    with pytest.raises(RankingCsvError) as excinfo:
        search_index._load_ranking_dir(path)

    assert "gba.csv" in str(excinfo.value)
    assert "第" in str(excinfo.value)


def test_load_ranking_dir_reports_all_duplicate_titles(tmp_path):
    """同机种英文名重复：一次列出所有冲突行，make index 原样打印。"""
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(
        path / "gba.csv",
        [
            ["游戏", "Game", "8", "ID1"],
            ["另一个", "Game", "7", "ID2"],
            ["第三个", "Other", "6", "ID3"],
            ["第四个", "Other", "5", "ID4"],
        ],
    )

    with pytest.raises(RankingCsvError) as excinfo:
        search_index._load_ranking_dir(path)

    message = str(excinfo.value)
    assert "gba.csv 第 2 行" in message
    assert "gba.csv 第 4 行" in message
    assert "Game" in message and "Other" in message


def test_load_ranking_dir_rejects_unknown_filename(tmp_path):
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(path / "not-a-platform.csv", [["游戏", "Game", "8", "ID"]])

    with pytest.raises(RankingCsvError) as excinfo:
        search_index._load_ranking_dir(path)

    assert "机种 id" in str(excinfo.value)


@pytest.mark.parametrize("rows", [[], [_RANKING_HEADER]])
def test_load_ranking_dir_rejects_empty(tmp_path, rows):
    path = tmp_path / "ranking"
    path.mkdir()
    _write_csv(path / "gba.csv", rows)

    with pytest.raises(RankingCsvError):
        search_index._load_ranking_dir(path)


def test_load_ranking_dir_rejects_non_utf8(tmp_path):
    path = tmp_path / "ranking"
    path.mkdir()
    (path / "gba.csv").write_bytes(b"\xff\xfe1,game,8,ID\n")

    with pytest.raises(RankingCsvError):
        search_index._load_ranking_dir(path)


def test_ranking_dir_lives_outside_the_search_csv_dir():
    """榜单目录不能放进 backend/search/catalog/：那个目录会被整目录扫成游戏名录。"""
    assert RANKING_CSV_DIR.name == "rankings"
    assert SEARCH_CSV_DIR not in RANKING_CSV_DIR.parents


# --------------------------------------------------------------------------
# 构建
# --------------------------------------------------------------------------


def test_build_index_writes_ranking(csv_dir, ranking_dir, index_path):
    stats = build_index(csv_dir, index_path, ranking_dir=ranking_dir)

    assert stats.ranking_rows == len(_RANKING_ROWS)
    assert stats.ranking_consoles == _RANKING_PLATFORMS
    assert _meta(index_path, "schema_version") == SCHEMA_VERSION
    assert _meta(index_path, "ranking_schema_version") == RANKING_SCHEMA_VERSION
    assert _meta(index_path, "ranking_fingerprint") == search_index._load_ranking_dir(
        ranking_dir
    ).fingerprint
    assert _meta(index_path, "ranking_source") == "ranking"
    # _ranking_rows 按 platform 排序：gb(2) → gba(4) → nes(2)
    rows = _ranking_rows(index_path)
    assert rows[0][0] == "gb"
    assert rows[0][2] == 8.0
    assert rows[2][0] == "gba"
    assert rows[2][3] == "精灵宝可梦 火红"
    assert rows[2][4] == "Pokemon FireRed"
    assert rows[4][5] == '["ID1", "ID2"]'
    # 没编号的行落成空数组，前端显示「—」
    assert rows[5][3] == "查不到编号的游戏"
    assert rows[5][5] == "[]"


def test_ranking_table_has_auto_increment_id(csv_dir, ranking_dir, index_path):
    build_index(csv_dir, index_path, ranking_dir=ranking_dir)

    with sqlite3.connect(index_path) as conn:
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ranking'"
        ).fetchone()[0]
        ids = [
            row[0]
            for row in conn.execute("SELECT id FROM ranking ORDER BY id")
        ]
    assert "INTEGER PRIMARY KEY AUTOINCREMENT" in table_sql.upper()
    assert ids == list(range(1, len(_RANKING_ROWS) + 1))


def test_build_index_creates_ranking_score_indexes(csv_dir, ranking_dir, index_path):
    build_index(csv_dir, index_path, ranking_dir=ranking_dir)

    with sqlite3.connect(index_path) as conn:
        indexes = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA index_list('ranking')")
        }
    assert {
        "uq_ranking_platform_en",
        "idx_ranking_score",
        "idx_ranking_platform_score",
        "idx_ranking_in_library_score",
        "idx_ranking_platform_in_library_score",
    } <= set(indexes)
    assert indexes["uq_ranking_platform_en"] == 1


def test_build_index_populates_ranking_cartridges(csv_dir, ranking_dir, index_path):
    build_index(csv_dir, index_path, ranking_dir=ranking_dir)

    with sqlite3.connect(index_path) as conn:
        mapping = dict(
            conn.execute(
                "SELECT cartridge_id, ranking_id FROM ranking_cartridges"
            ).fetchall()
        )
    assert {"NES-SM", "NES-MT", "GSAE", "ID1", "ID2", "ZELDA", "A1", "A2"} <= set(
        mapping
    )
    assert mapping["ID1"] == mapping["ID2"]
    assert "查不到编号的游戏" not in mapping


def test_build_index_normalizes_mapping_keys(csv_dir, tmp_path, index_path):
    ranking_dir = tmp_path / "rank-lower"
    ranking_dir.mkdir()
    _write_csv(
        ranking_dir / "nes.csv",
        [_RANKING_HEADER, ["小写", "Lower", "8", "  abc-1  "]],
    )

    build_index(csv_dir, index_path, ranking_dir=ranking_dir, strict_ranking=True)

    with sqlite3.connect(index_path) as conn:
        assert conn.execute(
            "SELECT cartridge_id FROM ranking_cartridges"
        ).fetchall() == [("ABC-1",)]


def test_build_index_rejects_cross_row_duplicate_cartridge_id(
    csv_dir, ranking_dir, index_path, tmp_path
):
    before = _digest(index_path) if index_path.exists() else None
    bad = tmp_path / "dup-ranking"
    bad.mkdir()
    _write_csv(
        bad / "nes.csv",
        [_RANKING_HEADER, ["A", "Game A", "8", "SAME-ID"]],
    )
    _write_csv(
        bad / "gba.csv",
        [_RANKING_HEADER, ["B", "Game B", "8", "same-id"]],
    )

    with pytest.raises(RankingCsvError, match="SAME-ID"):
        build_index(csv_dir, index_path, ranking_dir=bad, strict_ranking=True)

    if before is not None:
        assert _digest(index_path) == before


def test_build_index_without_ranking_leaves_empty_table(csv_dir, index_path):
    stats = build_index(csv_dir, index_path)

    assert stats.ranking_rows == 0
    assert _ranking_rows(index_path) == []
    # 表在、版本在，但没有指纹 —— 榜单页据此显示「尚未加载」
    assert _meta(index_path, "ranking_schema_version") == RANKING_SCHEMA_VERSION
    assert _meta(index_path, "ranking_fingerprint") is None


def test_build_index_strict_ranking_keeps_old_index(csv_dir, ranking_dir, index_path, tmp_path):
    build_index(csv_dir, index_path, ranking_dir=ranking_dir)
    before = _digest(index_path)

    bad = tmp_path / "bad-ranking"
    bad.mkdir()
    _write_csv(bad / "gba.csv", [["游戏", "Game", "8", "A,B,C"]])
    with pytest.raises(RankingCsvError):
        build_index(csv_dir, index_path, ranking_dir=bad, strict_ranking=True)

    assert _digest(index_path) == before
    assert not index_path.with_name("game.db.tmp").exists()


def test_build_index_tolerates_bad_ranking_when_not_strict(csv_dir, index_path, tmp_path):
    bad = tmp_path / "bad-ranking"
    bad.mkdir()
    _write_csv(bad / "gba.csv", [["游戏", "Game", "8", "A,B,C"]])

    stats = build_index(csv_dir, index_path, ranking_dir=bad, strict_ranking=False)

    assert stats.ranking_rows == 0
    assert _ranking_rows(index_path) == []


def test_build_index_tolerates_missing_ranking_dir(csv_dir, index_path, tmp_path):
    stats = build_index(csv_dir, index_path, ranking_dir=tmp_path / "nope")

    assert stats.rows == len(_SEARCH_ROWS)
    assert stats.ranking_rows == 0


# --------------------------------------------------------------------------
# 只读接口
# --------------------------------------------------------------------------

RANKING_URL = "/api/games/search/ranking"
RANKING_CONSOLES_URL = "/api/games/search/ranking/consoles"


@pytest.fixture
def ranked(app, csv_dir, ranking_dir, index_path):
    """建好带榜单的索引（路径与 app 的 game_index_path 一致）。"""
    build_index(csv_dir, index_path, ranking_dir=ranking_dir)
    return index_path


def _get(client, url, **params):
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_ranking_requires_login(client):
    assert client.get(RANKING_URL).status_code == 401
    assert client.get(RANKING_CONSOLES_URL).status_code == 401


def test_ranking_missing_index_returns_guidance(logged_in, index_path):
    data = _get(logged_in, RANKING_CONSOLES_URL)
    assert data == {
        "indexed": False,
        "has_ranking": False,
        "consoles": [],
    }
    data = _get(logged_in, RANKING_URL)
    assert data == {
        "indexed": False,
        "has_ranking": False,
        "console": None,
        "page": 1,
        "page_size": 10,
        "total": 0,
        "matched_total": 0,
        "items": [],
    }
    # 服务端绝不代建索引
    assert not index_path.exists()


def test_ranking_without_ranking_data(app, logged_in, csv_dir, index_path):
    """只有游戏名录表的库：索引在、榜单没加载，不是错误。"""
    build_index(csv_dir, index_path)

    consoles = _get(logged_in, RANKING_CONSOLES_URL)
    assert consoles["indexed"] is True
    assert consoles["has_ranking"] is False
    assert consoles["consoles"] == []

    page = _get(logged_in, RANKING_URL)
    assert page["indexed"] is True
    assert page["has_ranking"] is False
    assert page["items"] == []
    assert page["total"] == 0 and page["matched_total"] == 0


def test_ranking_consoles(ranked, logged_in):
    data = _get(logged_in, RANKING_CONSOLES_URL)

    assert data["indexed"] is True
    assert data["has_ranking"] is True
    # 机种键 = EmulatorJS 的 system key，展示名与游戏管理/游戏名录共用一套（词表顺序：FC → GB/GBC → GBA）
    assert data["consoles"] == [
        {"platform": "nes", "label": "任天堂 FC", "playable": True},
        {"platform": "gb", "label": "任天堂 GB/GBC", "playable": True},
        {"platform": "gba", "label": "任天堂 GBA", "playable": True},
    ]
    assert "default_console" not in data


def test_ranking_without_console_returns_all_consoles(ranked, logged_in):
    """不传 console 就是跨机种榜单；页面默认不选类型，因此首次请求走的也是这条。"""
    page = _get(logged_in, RANKING_URL)

    assert page["console"] is None
    # 排序：评分全局降序；同分按 platform、机种内序号稳定排序
    assert [item["zh"] for item in page["items"]] == [
        "超级马里奥兄弟",
        "精灵宝可梦 火红",
        "银河战士",
        "黄金太阳",
        "塞尔达传说 不可思议的果实",
        "双版本示例",
        "查不到编号的游戏",
        "分隔符示例",
    ]
    assert [item["platform"] for item in page["items"]] == [
        "nes",
        "gba",
        "nes",
        "gba",
        "gb",
        "gba",
        "gba",
        "gb",
    ]
    scores = [item["score"] for item in page["items"]]
    assert scores == sorted(scores, reverse=True)
    assert page["items"][0]["en"] == "Super Mario Bros."
    assert page["items"][0]["score"] == 8.84316671219157
    assert page["items"][0]["cartridge_ids"] == ["NES-SM"]
    assert "rank" not in page["items"][0]
    assert page["page"] == 1
    assert page["page_size"] == 10
    assert page["total"] == 8
    assert page["matched_total"] == 8


def test_ranking_gba_page(ranked, logged_in):
    page = _get(logged_in, RANKING_URL, console="gba")

    scores = [item["score"] for item in page["items"]]
    assert scores == [8.5, 8.1, 7.75, 7.0]
    assert scores == sorted(scores, reverse=True)
    assert page["items"][0]["platform"] == "gba"
    assert page["items"][0]["zh"] == "精灵宝可梦 火红"
    assert page["items"][0]["en"] == "Pokemon FireRed"
    assert page["items"][0]["cartridge_ids"] == ["POKEMON FIRE RED"]
    assert page["items"][2]["cartridge_ids"] == ["ID1", "ID2"]
    # 没编号的行照常返回，只是 ID 列表为空
    assert page["items"][3]["cartridge_ids"] == []
    assert page["total"] == 4


def test_ranking_paginates_by_score(ranked, logged_in):
    first = _get(logged_in, RANKING_URL, page=1, page_size=3)
    second = _get(logged_in, RANKING_URL, page=2, page_size=3)

    assert first["page"] == 1
    assert second["page"] == 2
    assert first["page_size"] == second["page_size"] == 3
    assert first["total"] == second["total"] == 8
    assert len(first["items"]) == len(second["items"]) == 3
    assert min(item["score"] for item in first["items"]) >= max(
        item["score"] for item in second["items"]
    )


def test_ranking_page_is_clamped_to_last_page(ranked, logged_in):
    page = _get(logged_in, RANKING_URL, page=99, page_size=3)

    assert page["page"] == 3
    assert len(page["items"]) == 2


def test_ranking_keyword_filters_chinese_and_english(ranked, logged_in):
    by_en = _get(logged_in, RANKING_URL, keyword="mario")
    by_zh = _get(logged_in, RANKING_URL, keyword="马里奥")
    missing = _get(logged_in, RANKING_URL, keyword="不存在的游戏")

    assert by_en["total"] == by_en["matched_total"] == 1
    assert by_en["items"][0]["en"] == "Super Mario Bros."
    assert by_zh["total"] == by_zh["matched_total"] == 1
    assert by_zh["items"][0]["zh"] == "超级马里奥兄弟"
    assert missing["total"] == missing["matched_total"] == 0


def test_ranking_keyword_escapes_like_wildcards(ranked, logged_in):
    """关键词里的 % / _ 按字面匹配，不能当通配符把整份榜单查出来。"""
    assert _get(logged_in, RANKING_URL, keyword="%")["total"] == 0
    assert _get(logged_in, RANKING_URL, keyword="_")["total"] == 0


def test_ranking_in_library_filters_and_counts(ranked, logged_in, app):
    _make_game(app, "超级马里奥兄弟", "NES-SM")
    _sync_flags(app, ranked)

    page = _get(logged_in, RANKING_URL, in_library="true")

    assert page["total"] == 1
    assert page["matched_total"] == 8
    assert page["items"][0]["en"] == "Super Mario Bros."
    assert page["items"][0]["in_library"] is True
    assert page["items"][0]["path"] is not None

    outside = _get(logged_in, RANKING_URL, in_library="false")
    assert outside["total"] == 7
    assert all(item["in_library"] is False for item in outside["items"])


def test_ranking_keyword_and_in_library_are_combined(ranked, logged_in, app):
    _make_game(app, "超级马里奥兄弟", "NES-SM")
    _sync_flags(app, ranked)

    page = _get(logged_in, RANKING_URL, keyword="mario", in_library="true")

    assert page["matched_total"] == 1
    assert page["total"] == 1
    assert page["items"][0]["en"] == "Super Mario Bros."


def test_ranking_specific_console_and_separators(ranked, logged_in):
    # 机种由文件名决定：gb.csv → 机种键 `gb`
    page = _get(logged_in, RANKING_URL, console="gb")

    assert page["console"] == "gb"
    assert [item["zh"] for item in page["items"]] == [
        "塞尔达传说 不可思议的果实",
        "分隔符示例",
    ]
    assert [item["en"] for item in page["items"]] == [
        "Zelda - Oracle",
        "Separator Example",
    ]
    assert page["items"][1]["cartridge_ids"] == ["A1", "A2"]


def test_ranking_unknown_console_returns_empty(ranked, logged_in):
    page = _get(logged_in, RANKING_URL, console="NOPE")

    assert page["has_ranking"] is True
    assert page["console"] == "NOPE"
    assert page["items"] == []
    assert page["total"] == page["matched_total"] == 0


def test_ranking_broken_index_returns_503(logged_in, index_path):
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(b"not a database at all")

    response = logged_in.get(RANKING_URL)
    assert response.status_code == 503
    assert "make index" in response.json()["message"]


def test_ranking_stale_version_returns_503(ranked, logged_in, index_path):
    with sqlite3.connect(index_path) as conn:
        conn.execute("UPDATE meta SET value = '0' WHERE key = 'ranking_schema_version'")
        conn.commit()

    response = logged_in.get(RANKING_CONSOLES_URL)
    assert response.status_code == 503
    assert "过旧" in response.json()["message"]


def test_ranking_runtime_never_writes_the_index(ranked, logged_in, index_path):
    before = _digest(index_path)
    _get(logged_in, RANKING_CONSOLES_URL)
    _get(logged_in, RANKING_URL)
    _get(logged_in, RANKING_URL, console="gb")
    _get(logged_in, RANKING_URL, console="NOPE")
    assert _digest(index_path) == before


def test_ranking_routes_are_not_shadowed(ranked, logged_in):
    """这两条路径不能被 games_router 的 /{game_id}/… 抢走（抢走会是 422 而不是 404）。"""
    assert "items" in _get(logged_in, RANKING_URL)
    assert "consoles" in _get(logged_in, RANKING_CONSOLES_URL)


# --------------------------------------------------------------------------
# 与平台库存的关联（请求期按卡带ID 匹配）
# --------------------------------------------------------------------------


def _make_game(app, name, cartridge_id, *, game_type="nes", game_path=None):
    """往平台库存里插一行游戏（本组用例不碰真实文件，直接插行最省事）。

    默认给一个非空的本体路径；关联不区分有无本体，要测无本体关联时显式传 `game_path=""`。
    """
    with Session(app.state.engine) as session:
        row = Game(
            name=name,
            cartridge_id=cartridge_id,
            game_type=game_type,
            game_path=(
                f"game/{game_type}/{cartridge_id}/game.bin"
                if game_path is None
                else game_path
            ),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _sync_flags(app, index_path):
    refresh_all_flags(app.state.settings.database_path, index_path, strict=True)


def _delete_game(app, game_id):
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        session.delete(row)
        session.commit()


@pytest.fixture
def ranked_with(app, csv_dir, index_path, tmp_path):
    """按用例自己写的榜单行建索引（默认固件覆盖不到的写法用）。

    传入行是 `[机种原始名, 中文名, 英文名, 卡带ID]`，按机种拆成 `<id>.csv`，
    评分统一补 `8.0`。
    """

    def _build(rows):
        files: dict[str, list[list[str]]] = {}
        for console, zh, en, ids in rows:
            platform = resolve_platform(console)
            assert platform is not None, console
            files.setdefault(platform.id, []).append([zh, en, "8.0", ids])
        path = _write_ranking_dir(tmp_path / "custom-ranking", files)
        build_index(csv_dir, index_path, ranking_dir=path)
        return index_path

    return _build


def test_ranking_links_game_in_library(ranked, logged_in, app):
    """卡带ID 对上的行带上 game_id 与播放路径，没对上的行两个字段都是 null。"""
    game_id = _make_game(app, "超级马里奥兄弟", "NES-SM")

    page = _get(logged_in, RANKING_URL)

    assert page["items"][0]["game_id"] == game_id
    assert page["items"][0]["path"] == f"/games/play/{game_id}"
    # 银河战士（NES-MT）库存里没有
    assert page["items"][1]["game_id"] is None
    assert page["items"][1]["path"] is None


def test_ranking_link_uses_play_path_by_game_type(ranked, logged_in, app):
    """播放路径按游戏类型给：flash / h5 各有自己的播放页。"""
    flash_id = _make_game(app, "Flash 游戏", "NES-SM", game_type="flash")

    page = _get(logged_in, RANKING_URL)

    assert page["items"][0]["path"] == f"/games/flash/{flash_id}"


def test_ranking_links_when_second_cartridge_id_matches(ranked, logged_in, app):
    """一行两个卡带ID：任意一个命中就算关联（这里是第二个命中）。"""
    game_id = _make_game(app, "双版本示例", "ID2")

    page = _get(logged_in, RANKING_URL, console="gba")

    assert page["items"][2]["zh"] == "双版本示例"
    assert page["items"][2]["en"] == "Double Version Example"
    assert page["items"][2]["cartridge_ids"] == ["ID1", "ID2"]
    assert page["items"][2]["path"] == f"/games/play/{game_id}"


def test_ranking_link_is_case_insensitive(ranked_with, logged_in, app):
    """比对前两边都归一（去首尾空白 + 转大写）：榜单写小写也能对上库存的大写。"""
    ranked_with([["FC", "小写编号", "Lowercase ID", "nes-sm"]])
    game_id = _make_game(app, "超级马里奥兄弟", "NES-SM")

    page = _get(logged_in, RANKING_URL)

    assert page["items"][0]["path"] == f"/games/play/{game_id}"


def test_ranking_link_ignores_ids_that_are_not_valid_cartridge_ids(
    ranked_with, logged_in, app
):
    """榜单里带空格/点的原文（真实 CSV 里就有）不该报错，只是永远匹配不上。

    关联绝不能复用 `validate_cartridge_id()`——它会抛校验错，把只读的榜单接口打挂。
    """
    ranked_with([["FC", "编号带空格的游戏", "Spaced ID Game", "Part No. 7004 0894"]])
    _make_game(app, "同名字游戏", "PARTNO70040894")

    page = _get(logged_in, RANKING_URL)

    assert page["items"][0]["cartridge_ids"] == ["Part No. 7004 0894"]
    assert page["items"][0]["path"] is None


def test_ranking_links_games_without_body(ranked, logged_in, app):
    """没有本体的条目同样关联；has_body=False 供前端拦下跳转并提示先上传。"""
    _make_game(app, "本体丢了的游戏", "NES-SM", game_path="")

    item = _get(logged_in, RANKING_URL)["items"][0]

    assert item["path"] is not None
    assert item["has_body"] is False


def test_ranking_unlinks_after_game_deleted(ranked, logged_in, app):
    """关联是每请求现算的：删掉游戏后下一次请求就没有链接了（不用执行 make index）。"""
    game_id = _make_game(app, "超级马里奥兄弟", "NES-SM")
    assert _get(logged_in, RANKING_URL)["items"][0]["path"] is not None

    _delete_game(app, game_id)

    assert _get(logged_in, RANKING_URL)["items"][0]["path"] is None


def test_ranking_link_follows_cartridge_id_rename(ranked, logged_in, app):
    """改卡带ID 后关联立刻跟着新 ID 走：旧 ID 脱钩、新 ID 命中（同样是每请求现算）。"""
    game_id = _make_game(app, "超级马里奥兄弟", "NES-SM")
    assert _get(logged_in, RANKING_URL)["items"][0]["path"] is not None

    renamed = logged_in.put(
        f"/api/games/manage/{game_id}/cartridge-id", json={"cartridge_id": "NES-SM2"}
    )
    assert renamed.status_code == 200, renamed.text

    assert _get(logged_in, RANKING_URL)["items"][0]["path"] is None
    with Session(app.state.engine) as session:
        links = GameService(
            session, app.state.storage, app.state.runtime_storage
        ).map_for_cartridge_ids(["NES-SM2"])
    assert links["NES-SM2"].game_id == game_id


def test_ranking_link_counts_for_stock_ratio(ranked, logged_in, app):
    """「已入库比例」的数据契约：前端拿 path 非空的行数当分子、总行数当分母。"""
    _make_game(app, "精灵宝可梦 火红", "GSAE")
    _make_game(app, "黄金太阳", "ID1")

    items = _get(logged_in, RANKING_URL, console="gba")["items"]

    assert len(items) == 4
    assert sum(1 for item in items if item["path"]) == 2


def test_ranking_service_without_lookup_does_not_link(ranked, csv_dir, ranking_dir):
    """不注入查库存的回调 = 不关联（默认值，老的构造方式行为不变）。"""
    page = GameRankingService(ranked).get("nes")

    assert [item.cartridge_ids for item in page.items] == [("NES-SM",), ("NES-MT",)]
    assert all(item.game_id is None and item.path is None for item in page.items)


def test_ranking_attaches_links_only_for_current_page(ranked):
    """分页后只对当前页做库存关联，不再把整个机种的卡带 ID 全查一遍。"""
    calls = []

    def lookup(raw_ids):
        calls.append(list(raw_ids))
        return {}

    page = GameRankingService(ranked, cartridge_lookup=lookup).get(
        None, page=1, page_size=1
    )

    assert len(page.items) == 1
    assert sum(len(ids) for ids in calls) == 1
