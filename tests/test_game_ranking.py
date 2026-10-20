"""「游戏榜单」的 CSV 解析、构建与启动就地补载测试。

用例不读仓库里的真实榜单 CSV：在 tmp_path 写几行小 CSV 固件，覆盖真实数据的格式边界
（UTF-8 带 BOM、CRLF、引号内的逗号、可选表头、机种大小写、卡带 ID 分隔符）。
"""

import csv
import hashlib
import os
import sqlite3

import pytest
from sqlmodel import Session

from backend import create_app
from backend.config import RANKING_CSV_PATH, SEARCH_CSV_DIR, Settings
from backend.games import search_index
from backend.games.models import Game
from backend.games.ranking_service import GameRankingService, _pick_default
from backend.games.service import GameService
from backend.games.search_index import (
    RANKING_SCHEMA_VERSION,
    SCHEMA_VERSION,
    RankingCsvError,
    build_index,
    ensure_game_index,
    ensure_ranking_loaded,
)

# 检索名录：只求 build_index 有东西可建，内容与榜单无关
_SEARCH_ROWS = [
    ("任天堂GBA", "黄金太阳", "Golden Sun (USA)"),
    ("任天堂GBA", "精灵宝可梦 火红", "Pokemon FireRed (USA)"),
]

_RANKING_HEADER = ["序号", "机种名称", "游戏名称", "游戏卡带ID"]
# FC 排在最前是为了测「默认机种是 FC」——页面打开时不选也是它
_RANKING_ROWS = [
    ["1", "FC", "超级马里奥兄弟", "NES-SM"],
    ["2", "FC", "银河战士", "NES-MT"],
    ["1", "GBA", "精灵宝可梦 火红", "POKEMON FIRE RED"],
    ["2", "GBA", "黄金太阳", "GSAE"],
    ["3", "GBA", "双版本示例", "ID1;ID2"],
    ["4", "GBA", "查不到编号的游戏", ""],
    ["1", "GBC", "塞尔达传说 不可思议的果实", "ZELDA"],
    ["2", "GBC", "分隔符示例", "A1/ A2"],
]
# 归一后的机种：FC→nes、GBA→gba、GBC→gb（同一个机种，所以序号各自独立）
_RANKING_PLATFORMS = 3


def _write_csv(path, rows, *, encoding="utf-8-sig"):
    # 真实数据就是 UTF-8 带 BOM + CRLF，csv 模块负责处理引号
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerows(rows)


def _digest(path):
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_mtime_ns


@pytest.fixture
def csv_dir(tmp_path):
    source = tmp_path / "csv"
    source.mkdir()
    _write_csv(source / "任天堂GBA.csv", _SEARCH_ROWS)
    return source


@pytest.fixture
def ranking_csv(tmp_path):
    path = tmp_path / "ranking" / "ranking.csv"
    path.parent.mkdir()
    _write_csv(path, [_RANKING_HEADER, *_RANKING_ROWS])
    return path


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
            "SELECT console, rank, title, cartridge_ids FROM ranking ORDER BY console, rank"
        ).fetchall()


# --------------------------------------------------------------------------
# CSV 解析
# --------------------------------------------------------------------------


def test_parse_ranking_csv_handles_real_format(tmp_path):
    """表头 + BOM + CRLF + 引号内的逗号 + 空行 + Excel 行尾空列。"""
    path = tmp_path / "ranking.csv"
    _write_csv(
        path,
        [
            _RANKING_HEADER,
            ["1", "GBA", "含,逗号的名字", "ID1"],
            [],
            ["2", "GBA", "普通游戏", "ID2,ID3"],
            ["1", "gbc", "小写机种", "ID4", ""],
        ],
    )

    data = search_index._load_ranking_csv(path)

    assert data.source == "ranking.csv"
    assert data.fingerprint == hashlib.sha256(path.read_bytes()).hexdigest()
    assert [row.title for row in data.rows] == ["含,逗号的名字", "普通游戏", "小写机种"]
    assert data.rows[1].cartridge_ids == ("ID2", "ID3")
    # 机种经词表归一：`GBA` 与 `gbc` 分别落到机种键 `gba` 与 `gb`（`gbc` 是 `gb` 的别名），
    # 原文照旧留在行上（rows[*].console）供溯源
    assert data.platforms == ("gba", "gb")
    assert [row.console for row in data.rows] == ["GBA", "GBA", "gbc"]


def test_parse_ranking_csv_without_header(tmp_path):
    path = tmp_path / "ranking.csv"
    _write_csv(path, [["1", "GBA", "游戏", "ID1"]])

    data = search_index._load_ranking_csv(path)

    assert len(data.rows) == 1
    assert data.rows[0].rank == 1


def test_parse_ranking_csv_allows_empty_cartridge_ids(tmp_path):
    """查不到编号的游戏：第 4 列留空或整列省掉都合法，落成空元组。"""
    path = tmp_path / "ranking.csv"
    _write_csv(path, [["1", "C64", "留空", ""], ["2", "C64", "省掉第 4 列"]])

    data = search_index._load_ranking_csv(path)

    assert [row.cartridge_ids for row in data.rows] == [(), ()]


@pytest.mark.parametrize(
    "rows",
    [
        [["1", "GBA"]],  # 列数不对（少于 3 列）
        [["1", "GBA", "游戏", "ID", "多余的一列"]],  # 列数不对（多于 4 列）
        [["x", "GBA", "游戏", "ID"]],  # 序号不是整数
        [["0", "GBA", "游戏", "ID"]],  # 序号不是正整数
        [["1", "GBA", "", "ID"]],  # 缺游戏名
        [["1", "", "游戏", "ID"]],  # 缺机种
        [["1", "GBA", "游戏", "A,B,C"]],  # 超过 2 个卡带 ID
        [["1", "GBA", "游戏", "ID"], ["1", "gba", "另一个", "ID2"]],  # 同机种序号重复
    ],
)
def test_parse_ranking_csv_rejects_bad_rows(tmp_path, rows):
    path = tmp_path / "ranking.csv"
    _write_csv(path, rows)

    with pytest.raises(RankingCsvError) as excinfo:
        search_index._load_ranking_csv(path)

    assert "ranking.csv" in str(excinfo.value)
    assert "第" in str(excinfo.value)


@pytest.mark.parametrize("rows", [[], [_RANKING_HEADER]])
def test_parse_ranking_csv_rejects_empty(tmp_path, rows):
    path = tmp_path / "ranking.csv"
    _write_csv(path, rows)

    with pytest.raises(RankingCsvError):
        search_index._load_ranking_csv(path)


def test_parse_ranking_csv_rejects_non_utf8(tmp_path):
    path = tmp_path / "ranking.csv"
    path.write_bytes(b"\xff\xfe1,GBA,game,ID\n")

    with pytest.raises(RankingCsvError):
        search_index._load_ranking_csv(path)


def test_ranking_csv_lives_outside_the_search_csv_dir():
    """榜单 CSV 不能放进 backend/search/csv/：那个目录会被整目录扫成检索索引。"""
    assert RANKING_CSV_PATH.parent.name == "ranking"
    assert SEARCH_CSV_DIR not in RANKING_CSV_PATH.parents


# --------------------------------------------------------------------------
# 构建
# --------------------------------------------------------------------------


def test_build_index_writes_ranking(csv_dir, ranking_csv, index_path):
    stats = build_index(csv_dir, index_path, ranking_csv=ranking_csv)

    assert stats.ranking_rows == len(_RANKING_ROWS)
    assert stats.ranking_consoles == _RANKING_PLATFORMS
    assert _meta(index_path, "schema_version") == SCHEMA_VERSION
    assert _meta(index_path, "ranking_schema_version") == RANKING_SCHEMA_VERSION
    assert _meta(index_path, "ranking_fingerprint") == hashlib.sha256(
        ranking_csv.read_bytes()
    ).hexdigest()
    assert _meta(index_path, "ranking_source") == "ranking.csv"
    # _ranking_rows 按 console 原文排序：FC(2) → GBA(4) → GBC(2)
    rows = _ranking_rows(index_path)
    assert rows[0][0] == "FC"
    assert rows[2][0] == "GBA"
    assert rows[2][2] == "精灵宝可梦 火红"
    assert rows[4][3] == '["ID1", "ID2"]'
    # 没编号的行落成空数组，前端显示「—」
    assert rows[5][2] == "查不到编号的游戏"
    assert rows[5][3] == "[]"


def test_build_index_without_ranking_leaves_empty_table(csv_dir, index_path):
    stats = build_index(csv_dir, index_path)

    assert stats.ranking_rows == 0
    assert _ranking_rows(index_path) == []
    # 表在、版本在，但没有指纹 —— 榜单页据此显示「尚未加载」
    assert _meta(index_path, "ranking_schema_version") == RANKING_SCHEMA_VERSION
    assert _meta(index_path, "ranking_fingerprint") is None


def test_build_index_strict_ranking_keeps_old_index(csv_dir, ranking_csv, index_path, tmp_path):
    build_index(csv_dir, index_path, ranking_csv=ranking_csv)
    before = _digest(index_path)

    bad = tmp_path / "bad-ranking.csv"
    _write_csv(bad, [["1", "GBA", "游戏", "A,B,C"]])
    with pytest.raises(RankingCsvError):
        build_index(csv_dir, index_path, ranking_csv=bad, strict_ranking=True)

    assert _digest(index_path) == before
    assert not index_path.with_name("game.db.tmp").exists()


def test_build_index_tolerates_bad_ranking_when_not_strict(csv_dir, index_path, tmp_path):
    bad = tmp_path / "bad-ranking.csv"
    _write_csv(bad, [["1", "GBA", "游戏", "A,B,C"]])

    stats = build_index(csv_dir, index_path, ranking_csv=bad, strict_ranking=False)

    assert stats.ranking_rows == 0
    assert _ranking_rows(index_path) == []


def test_build_index_tolerates_missing_ranking_csv(csv_dir, index_path, tmp_path):
    stats = build_index(csv_dir, index_path, ranking_csv=tmp_path / "nope.csv")

    assert stats.rows == len(_SEARCH_ROWS)
    assert stats.ranking_rows == 0


# --------------------------------------------------------------------------
# 启动就地补载
# --------------------------------------------------------------------------


def test_ensure_ranking_loaded_into_search_only_index(csv_dir, ranking_csv, index_path):
    build_index(csv_dir, index_path)  # 先造一个只有检索表的库

    stats = ensure_ranking_loaded(index_path, ranking_csv)

    assert stats is not None
    assert stats.rows == len(_RANKING_ROWS)
    assert len(_ranking_rows(index_path)) == len(_RANKING_ROWS)
    # 检索表一点没动，检索版本也没变
    assert _meta(index_path, "schema_version") == SCHEMA_VERSION


def test_ensure_ranking_loaded_is_idempotent(csv_dir, ranking_csv, index_path):
    """指纹一致时连读写连接都不打开：库文件逐字节与 mtime 都不变。"""
    build_index(csv_dir, index_path)
    ensure_ranking_loaded(index_path, ranking_csv)
    before = _digest(index_path)

    stats = ensure_ranking_loaded(index_path, ranking_csv)

    assert stats is not None
    assert _digest(index_path) == before


def test_ensure_ranking_loaded_reloads_when_content_changes(csv_dir, ranking_csv, index_path):
    """内容变了但 size + mtime 被人为保留，也要按 SHA-256 重新加载。"""
    build_index(csv_dir, index_path)
    ensure_ranking_loaded(index_path, ranking_csv)
    stat = ranking_csv.stat()

    _write_csv(ranking_csv, [_RANKING_HEADER, ["1", "GBA", "换了一个名字", "ID9"]])
    os.utime(ranking_csv, (stat.st_atime, stat.st_mtime))

    ensure_ranking_loaded(index_path, ranking_csv)

    assert _ranking_rows(index_path) == [("GBA", 1, "换了一个名字", '["ID9"]')]


def test_ensure_ranking_loaded_keeps_existing_when_csv_missing(csv_dir, ranking_csv, index_path):
    build_index(csv_dir, index_path)
    ensure_ranking_loaded(index_path, ranking_csv)
    ranking_csv.unlink()

    assert ensure_ranking_loaded(index_path, ranking_csv) is None
    assert len(_ranking_rows(index_path)) == len(_RANKING_ROWS)


def test_ensure_ranking_loaded_returns_none_when_db_missing(ranking_csv, tmp_path):
    assert ensure_ranking_loaded(tmp_path / "nope" / "game.db", ranking_csv) is None


def test_ensure_ranking_loaded_degrades_without_write_permission(csv_dir, ranking_csv, index_path):
    """库文件/目录只读时只记 warning、不抛，库里原来的榜单保持可用。"""
    build_index(csv_dir, index_path)
    os.chmod(index_path, 0o444)
    os.chmod(index_path.parent, 0o555)
    try:
        assert ensure_ranking_loaded(index_path, ranking_csv) is None
    finally:
        os.chmod(index_path.parent, 0o755)


def test_ensure_game_index_loads_ranking_into_existing_index(csv_dir, ranking_csv, tmp_path):
    settings = _settings(tmp_path)
    build_index(csv_dir, settings.game_index_path)  # 先造一个只有检索表的库

    assert ensure_game_index(settings, csv_dir=csv_dir, ranking_csv=ranking_csv) is None

    assert len(_ranking_rows(settings.game_index_path)) == len(_RANKING_ROWS)


def test_ensure_game_index_skips_ranking_when_testing(csv_dir, ranking_csv, tmp_path):
    settings = _settings(tmp_path, testing=True)

    assert ensure_game_index(settings, csv_dir=csv_dir, ranking_csv=ranking_csv) is None
    assert not settings.game_index_path.exists()


def test_app_startup_loads_ranking(monkeypatch, csv_dir, ranking_csv, tmp_path):
    """接线：create_app() 起来时会把榜单 CSV 加载进 game.db。"""
    monkeypatch.setattr(search_index, "SEARCH_CSV_DIR", csv_dir)
    monkeypatch.setattr(search_index, "RANKING_CSV_PATH", ranking_csv)

    create_app({"TESTING": False, "STORAGE_ROOT": str(tmp_path / "storage")})

    index_path = tmp_path / "storage" / "db" / "game.db"
    with sqlite3.connect(index_path) as conn:
        assert conn.execute("SELECT count(*) FROM game").fetchone()[0] == len(_SEARCH_ROWS)
    assert len(_ranking_rows(index_path)) == len(_RANKING_ROWS)


# --------------------------------------------------------------------------
# 只读接口
# --------------------------------------------------------------------------

RANKING_URL = "/api/games/search/ranking"
RANKING_CONSOLES_URL = "/api/games/search/ranking/consoles"


@pytest.fixture
def ranked(app, csv_dir, ranking_csv, index_path):
    """建好带榜单的索引（路径与 app 的 game_index_path 一致）。"""
    build_index(csv_dir, index_path, ranking_csv=ranking_csv)
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
        "default_console": None,
    }
    data = _get(logged_in, RANKING_URL)
    assert data == {"indexed": False, "has_ranking": False, "console": None, "items": []}
    # 服务端绝不代建索引
    assert not index_path.exists()


def test_ranking_without_ranking_data(app, logged_in, csv_dir, index_path):
    """只有检索表的库：索引在、榜单没加载，不是错误。"""
    build_index(csv_dir, index_path)

    consoles = _get(logged_in, RANKING_CONSOLES_URL)
    assert consoles["indexed"] is True
    assert consoles["has_ranking"] is False
    assert consoles["consoles"] == []

    page = _get(logged_in, RANKING_URL)
    assert page["indexed"] is True
    assert page["has_ranking"] is False
    assert page["items"] == []


def test_ranking_consoles_and_default(ranked, logged_in):
    data = _get(logged_in, RANKING_CONSOLES_URL)

    assert data["indexed"] is True
    assert data["has_ranking"] is True
    # 机种键 = EmulatorJS 的 system key，展示名与游戏管理/检索共用一套（词表顺序：FC → GB/GBC → GBA）
    assert data["consoles"] == [
        {"platform": "nes", "label": "任天堂 FC", "playable": True},
        {"platform": "gb", "label": "任天堂 GB/GBC", "playable": True},
        {"platform": "gba", "label": "任天堂 GBA", "playable": True},
    ]
    assert data["default_console"] == "nes"


def test_ranking_defaults_to_fc(ranked, logged_in):
    """页面打开时不选机种就是 FC。"""
    page = _get(logged_in, RANKING_URL)

    assert page["console"] == "nes"
    assert [item["rank"] for item in page["items"]] == [1, 2]
    assert page["items"][0]["title"] == "超级马里奥兄弟"
    assert page["items"][0]["cartridge_ids"] == ["NES-SM"]


def test_ranking_gba_page(ranked, logged_in):
    page = _get(logged_in, RANKING_URL, console="gba")

    assert [item["rank"] for item in page["items"]] == [1, 2, 3, 4]
    assert page["items"][0]["title"] == "精灵宝可梦 火红"
    assert page["items"][0]["cartridge_ids"] == ["POKEMON FIRE RED"]
    assert page["items"][2]["cartridge_ids"] == ["ID1", "ID2"]
    # 没编号的行照常返回，只是 ID 列表为空
    assert page["items"][3]["cartridge_ids"] == []


def test_ranking_specific_console_and_separators(ranked, logged_in):
    # CSV 里写的是 `GBC`，归一后的机种键是 `gb`（与 `GB` 同一个机种）
    page = _get(logged_in, RANKING_URL, console="gb")

    assert page["console"] == "gb"
    assert [item["title"] for item in page["items"]] == [
        "塞尔达传说 不可思议的果实",
        "分隔符示例",
    ]
    assert page["items"][1]["cartridge_ids"] == ["A1", "A2"]


def test_ranking_unknown_console_returns_empty(ranked, logged_in):
    page = _get(logged_in, RANKING_URL, console="NOPE")

    assert page["has_ranking"] is True
    assert page["console"] == "NOPE"
    assert page["items"] == []


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

    默认给一个非空的本体路径：关联只认「有本体」的游戏（与游戏中心列表同口径），
    要测「没本体就不链」时显式传 `game_path=""`。
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


def _delete_game(app, game_id):
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        session.delete(row)
        session.commit()


@pytest.fixture
def ranked_with(app, csv_dir, index_path, tmp_path):
    """按用例自己写的榜单行建索引（默认固件覆盖不到的写法用）。"""

    def _build(rows):
        path = tmp_path / "custom-ranking" / "ranking.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_csv(path, [_RANKING_HEADER, *rows])
        build_index(csv_dir, index_path, ranking_csv=path)
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

    assert page["items"][2]["title"] == "双版本示例"
    assert page["items"][2]["cartridge_ids"] == ["ID1", "ID2"]
    assert page["items"][2]["path"] == f"/games/play/{game_id}"


def test_ranking_link_is_case_insensitive(ranked_with, logged_in, app):
    """比对前两边都归一（去首尾空白 + 转大写）：榜单写小写也能对上库存的大写。"""
    ranked_with([["1", "FC", "小写编号", "nes-sm"]])
    game_id = _make_game(app, "超级马里奥兄弟", "NES-SM")

    page = _get(logged_in, RANKING_URL)

    assert page["items"][0]["path"] == f"/games/play/{game_id}"


def test_ranking_link_ignores_ids_that_are_not_valid_cartridge_ids(
    ranked_with, logged_in, app
):
    """榜单里带空格/点的原文（真实 CSV 里就有）不该报错，只是永远匹配不上。

    关联绝不能复用 `validate_cartridge_id()`——它会抛校验错，把只读的榜单接口打挂。
    """
    ranked_with([["1", "FC", "编号带空格的游戏", "Part No. 7004 0894"]])
    _make_game(app, "同名字游戏", "PARTNO70040894")

    page = _get(logged_in, RANKING_URL)

    assert page["items"][0]["cartridge_ids"] == ["Part No. 7004 0894"]
    assert page["items"][0]["path"] is None


def test_ranking_skips_games_without_body(ranked, logged_in, app):
    """没有本体的条目不给链接（点进去只会 404，与游戏中心列表同口径）。"""
    _make_game(app, "本体丢了的游戏", "NES-SM", game_path="")

    page = _get(logged_in, RANKING_URL)

    assert page["items"][0]["path"] is None


def test_ranking_unlinks_after_game_deleted(ranked, logged_in, app):
    """关联是每请求现算的：删掉游戏后下一次请求就没有链接了（不用重建索引）。"""
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
        links = GameService(session, app.state.storage).map_for_cartridge_ids(["NES-SM2"])
    assert links["NES-SM2"].game_id == game_id


def test_ranking_link_counts_for_stock_ratio(ranked, logged_in, app):
    """「已入库比例」的数据契约：前端拿 path 非空的行数当分子、总行数当分母。"""
    _make_game(app, "精灵宝可梦 火红", "GSAE")
    _make_game(app, "黄金太阳", "ID1")

    items = _get(logged_in, RANKING_URL, console="gba")["items"]

    assert len(items) == 4
    assert sum(1 for item in items if item["path"]) == 2


def test_ranking_service_without_lookup_does_not_link(ranked, csv_dir, ranking_csv):
    """不注入查库存的回调 = 不关联（默认值，老的构造方式行为不变）。"""
    page = GameRankingService(ranked).get("nes")

    assert [item.cartridge_ids for item in page.items] == [("NES-SM",), ("NES-MT",)]
    assert all(item.game_id is None and item.path is None for item in page.items)


def test_pick_default_console_prefers_fc_then_registry_order():
    """默认机种按统一机种键挑：有 FC 就选它，否则取词表里最靠前的（未收录的排最后）。"""
    assert _pick_default(["gb", "gba", "nes"]) == "nes"
    assert _pick_default(["gb", "gba"]) == "gb"  # 词表里 GB/GBC 在 GBA 前
    assert _pick_default(["snes", "nes"]) == "nes"  # 词表里 FC 在 SFC 前
    assert _pick_default(["raw:3ds", "snes"]) == "snes"  # 未收录的抢不到默认位
    assert _pick_default([]) is None
