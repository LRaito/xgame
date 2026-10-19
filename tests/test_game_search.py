"""「游戏检索」的索引构建与只读接口测试。

用例不读真实名录（4MB / 37 个文件，慢且脆）：在 tmp_path 写几行小 CSV 固件，覆盖真实数据的
格式边界——UTF-8 带 BOM、CRLF、字段内含逗号要引号、中文为空、整串都是标签、重复三元组。
"""

import hashlib
import os
import sqlite3

import pytest

from backend import create_app
from backend.games import search_index
from backend.games.search_index import IndexBuildError, build_index, ensure_game_index
from backend.games.search_service import GameSearchService
from backend.games.search_text import fts_query, index_text, strip_tags

SEARCH_URL = "/api/games/search"
CONSOLES_URL = "/api/games/search/consoles"

# 一行一个元组：(机种, 中文, 英文)。刻意混入各种边界。
_ROWS = [
    ("任天堂FC", "超级马里奥兄弟", "Super Mario Bros. (Japan) (Rev 1)"),
    ("任天堂FC", "马里奥医生", "Dr. Mario (USA)"),
    ("任天堂FC", "塞尔达传说", "Zelda no Densetsu (Japan)"),
    ("任天堂FC", "蝙蝠侠与罗宾的冒险", "Batman & Robin (USA, Europe)"),
    ("任天堂SFC", "超级马里奥世界", "Super Mario World (Europe)"),
    ("任天堂SFC", "最终幻想6", "Final Fantasy VI (USA)"),
    ("任天堂SFC", "", "Rendering Ranger R2 (Japan)"),
    ("索尼PS2", "[PS2]", "Alfa Romeo Racing Italiano (USA)"),
    ("索尼PS2", "含,逗号的,名字", "Comma, Test (USA)"),
    # 三元组与上面第 1 行完全相同 —— 应当被去重
    ("任天堂FC", "超级马里奥兄弟", "Super Mario Bros. (Japan) (Rev 1)"),
    # 机种与中文相同、英文不同 —— 必须保留（同款游戏的不同地区版本）
    ("任天堂FC", "超级马里奥兄弟", "Super Mario Bros. (USA)"),
    # 机种与英文相同、中文不同 —— 同样必须保留
    ("任天堂FC", "超级马里奥兄弟2", "Super Mario Bros. (USA)"),
]

# 造重复行的两个不同源文件：三元组一致的跨文件也要合并
_DUP_ACROSS_FILES = ("世嘉MD", "索尼克", "Sonic the Hedgehog (USA)")

# 落库行数：_ROWS 12 行里有 1 行完全重复 → 11，再加跨文件重复但只该留一条的索尼克 → 12
_EXPECTED_ROWS = 12
# 机种按 id 排 = 源文件的读取顺序（文件名排序），不是 CSV 里出现的顺序
_EXPECTED_CONSOLES = ["世嘉MD", "任天堂FC", "任天堂SFC", "索尼PS2"]


def _write_csv(path, rows):
    # 真实名录就是 UTF-8 带 BOM + CRLF，csv 模块负责处理引号
    import csv

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerows(rows)


@pytest.fixture
def csv_dir(tmp_path):
    source = tmp_path / "csv"
    source.mkdir()
    _write_csv(source / "任天堂FC.csv", _ROWS)
    _write_csv(source / "世嘉MD.csv", [_DUP_ACROSS_FILES])
    _write_csv(source / "世嘉MD 另一版.csv", [_DUP_ACROSS_FILES])
    return source


@pytest.fixture
def index_path(tmp_path):
    """建好的索引库路径（与 app 的 STORAGE_ROOT/db/game.db 一致）。"""
    return tmp_path / "storage" / "db" / "game.db"


@pytest.fixture
def built(app, csv_dir, index_path):
    stats = build_index(csv_dir, index_path)
    return stats


def _search(client, **params):
    response = client.get(SEARCH_URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _names(data):
    return [(item["console"], item["zh"], item["en"]) for item in data["items"]]


def _digest(path):
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_mtime_ns


# --------------------------------------------------------------------------
# 文本规则
# --------------------------------------------------------------------------


def test_strip_tags():
    assert strip_tags("Final Fantasy VII (Europe) (Disc 1)") == "Final Fantasy VII"
    assert strip_tags("蝙蝠侠与罗宾的冒险 (美版, 欧版) (Beta)") == "蝙蝠侠与罗宾的冒险"
    assert strip_tags("Mario (USA)") == "Mario"
    assert strip_tags("Super Mario World") == "Super Mario World"
    # 整串都是标签时保留原串：名录里有 38 行中文名本身就是 [PS2]
    assert strip_tags("[PS2]") == "[PS2]"
    assert strip_tags("(Japan)") == "(Japan)"
    assert strip_tags("") == ""


def test_index_text():
    assert index_text("超级马里奥3D世界") == "超 级 马 里 奥 3D 世 界"
    # 全角字母归一：名录里有 ＴＩＭＥ ＡＮＤ ＴＩＤＥ 这种写法
    assert index_text("ＴＩＭＥ") == "TIME"
    # 结尾标签不进索引
    assert index_text("超级马里奥 (日版)") == "超 级 马 里 奥"


def test_fts_query_edges():
    assert fts_query("") is None
    assert fts_query("   ") is None
    assert fts_query(None) is None
    assert fts_query("*") is None
    # 引号必须转义，否则构造出非法 FTS 语法直接抛异常
    assert fts_query('a"b') == '"a""b"'
    assert fts_query('"') == '""""'
    # 词间 AND、词内短语；尾随 * 是前缀
    assert fts_query("mario*") == '"mario"*'
    assert fts_query("final fantasy") == '"final" AND "fantasy"'


# --------------------------------------------------------------------------
# 构建
# --------------------------------------------------------------------------


def test_build_index_stats_and_schema(csv_dir, index_path):
    stats = build_index(csv_dir, index_path)

    # 12 行固件里有 1 行文件内重复 + 1 行跨文件重复 → 12 行
    assert stats.rows == _EXPECTED_ROWS
    assert stats.consoles == len(_EXPECTED_CONSOLES)
    assert stats.path == index_path
    assert index_path.is_file()

    # 不留 journal 系伴随文件（os.replace 只换主库，留了就是隐患）
    for suffix in ("-wal", "-shm", "-journal", ".tmp"):
        assert not index_path.with_name(index_path.name + suffix).exists()

    with sqlite3.connect(index_path) as conn:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        assert meta["schema_version"] == "1"
        assert meta["rows"] == str(stats.rows)
        assert meta["consoles"] == str(len(_EXPECTED_CONSOLES))
        assert meta["built_at"]
        # contentless FTS 表能 MATCH
        assert conn.execute(
            "SELECT count(*) FROM game_fts WHERE game_fts MATCH ?", ('"马 里 奥"',)
        ).fetchone()[0] > 0


def test_build_index_is_idempotent_and_overwrites(csv_dir, index_path):
    first = build_index(csv_dir, index_path)
    second = build_index(csv_dir, index_path)
    assert (first.rows, first.consoles) == (second.rows, second.consoles)

    # 换成更小的源，再跑一次必须整库换掉（不是往里追加）
    smaller = csv_dir.parent / "small"
    smaller.mkdir()
    _write_csv(smaller / "小.csv", [("任天堂FC", "只有一个", "Only One")])
    third = build_index(smaller, index_path)
    assert third.rows == 1
    with sqlite3.connect(index_path) as conn:
        assert conn.execute("SELECT count(*) FROM game").fetchone()[0] == 1


def test_build_index_rejects_bad_row(tmp_path):
    source = tmp_path / "bad"
    source.mkdir()
    (source / "坏.csv").write_text("机种,只有两列\n", encoding="utf-8")
    with pytest.raises(IndexBuildError, match="三列|3 列"):
        build_index(source, tmp_path / "db" / "game.db")


def test_build_index_rejects_empty_dir(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    with pytest.raises(IndexBuildError):
        build_index(source, tmp_path / "db" / "game.db")


def test_build_index_reports_unwritable_target(csv_dir, tmp_path):
    """写不进去时要给 IndexBuildError（中文可操作提示），不能甩 sqlite3/OSError 的 traceback。

    目标目录不可写时 sqlite3 报的是 `unable to open database file` 而不是 PermissionError，
    这条用例正是钉住那个转换。
    """
    target_dir = tmp_path / "readonly"
    target_dir.mkdir()
    os.chmod(target_dir, 0o555)
    try:
        with pytest.raises(IndexBuildError, match="写入权限|make index"):
            build_index(csv_dir, target_dir / "game.db")
        assert not (target_dir / "game.db").exists()
        assert not (target_dir / "game.db.tmp").exists()
    finally:
        os.chmod(target_dir, 0o755)


# --------------------------------------------------------------------------
# 启动时自动补建
# --------------------------------------------------------------------------


def _settings(tmp_path, *, testing=False):
    from backend.config import Settings

    return Settings(TESTING=testing, STORAGE_ROOT=str(tmp_path / "storage"))


def test_ensure_game_index_builds_when_missing(csv_dir, tmp_path):
    # ranking_csv=None：这一组用例只关心检索索引，不读仓库里的真实榜单 CSV
    stats = ensure_game_index(_settings(tmp_path), csv_dir=csv_dir, ranking_csv=None)

    assert stats is not None
    assert stats.rows == _EXPECTED_ROWS
    assert (tmp_path / "storage" / "db" / "game.db").is_file()


def test_ensure_game_index_skips_when_present(csv_dir, tmp_path):
    """已有索引就跳过：不重建、不覆盖（内容与 mtime 都不变）。"""
    ensure_game_index(_settings(tmp_path), csv_dir=csv_dir, ranking_csv=None)
    index_path = tmp_path / "storage" / "db" / "game.db"
    before = _digest(index_path)

    assert ensure_game_index(_settings(tmp_path), csv_dir=csv_dir, ranking_csv=None) is None
    assert _digest(index_path) == before


def test_ensure_game_index_skips_when_testing(tmp_path):
    """测试环境不自动建：否则每个用例都要白建一次 5 万行的索引。"""
    assert ensure_game_index(_settings(tmp_path, testing=True), csv_dir=tmp_path) is None
    assert not (tmp_path / "storage" / "db" / "game.db").exists()


def test_ensure_game_index_tolerates_missing_csv(tmp_path):
    """名录被人删掉/挪走时跳过并记一条日志，不建文件、不抛异常。"""
    assert ensure_game_index(_settings(tmp_path), csv_dir=tmp_path / "nope") is None
    assert not (tmp_path / "storage" / "db" / "game.db").exists()


def test_ensure_game_index_tolerates_broken_csv(tmp_path):
    """名录坏了也不能拦住服务启动（best-effort）。"""
    source = tmp_path / "bad"
    source.mkdir()
    (source / "坏.csv").write_text("只有两列\n", encoding="utf-8")

    assert ensure_game_index(_settings(tmp_path), csv_dir=source, ranking_csv=None) is None
    assert not (tmp_path / "storage" / "db" / "game.db").exists()


def test_app_startup_builds_missing_index(monkeypatch, csv_dir, tmp_path):
    """接线：create_app() 起来时确实会自检并补建。"""
    monkeypatch.setattr(search_index, "SEARCH_CSV_DIR", csv_dir)
    # 榜单单独测（见 test_game_ranking.py），这里指到一个不存在的文件，避免依赖仓库里的真实榜单
    monkeypatch.setattr(search_index, "RANKING_CSV_PATH", tmp_path / "ranking.csv")

    create_app({"TESTING": False, "STORAGE_ROOT": str(tmp_path / "storage")})

    index_path = tmp_path / "storage" / "db" / "game.db"
    assert index_path.is_file()
    with sqlite3.connect(index_path) as conn:
        assert conn.execute("SELECT count(*) FROM game").fetchone()[0] == _EXPECTED_ROWS


# --------------------------------------------------------------------------
# 去重口径
# --------------------------------------------------------------------------


def test_dedupe_only_exact_triples(built, logged_in):
    data = _search(logged_in, page_size=100)
    rows = _names(data)

    # 三元组完全一致的（同文件内 1 行 + 跨文件 1 行）各只留一条
    mario_jp = [r for r in rows if r[2] == "Super Mario Bros. (Japan) (Rev 1)"]
    assert len(mario_jp) == 1
    sonic = [r for r in rows if r[2] == "Sonic the Hedgehog (USA)"]
    assert len(sonic) == 1

    # 只英文或只中文相同的必须都留着
    same_en = [r for r in rows if r[2] == "Super Mario Bros. (USA)"]
    assert len(same_en) == 2  # 中文不同
    same_zh = [r for r in rows if r[1] == "超级马里奥兄弟"]
    assert len(same_zh) == 2  # 英文不同（日版 / 美版）

    assert data["total"] == _EXPECTED_ROWS


# --------------------------------------------------------------------------
# 检索
# --------------------------------------------------------------------------


def test_search_requires_login(client):
    assert client.get(SEARCH_URL).status_code == 401
    assert client.get(CONSOLES_URL).status_code == 401


def test_search_by_chinese_substring(built, logged_in):
    data = _search(logged_in, q="马里奥")
    assert data["indexed"] is True
    assert data["total"] >= 3
    assert all("马里奥" in item["zh"] for item in data["items"])


def test_normalization_invariant(built, logged_in):
    """归一化不变量：中文名中间取两个相邻汉字当查询，必命中该行。

    这一条同时抓「建库时漏了 index_text()」与「查询时漏了 index_text()」。窗口只能取
    「相邻且都是汉字」的，而且要从**剥掉结尾标签后**的主标题里取。
    """
    for zh_name in ("超级马里奥兄弟", "蝙蝠侠与罗宾的冒险", "最终幻想6"):
        base = strip_tags(zh_name)
        window = base[2:4]
        data = _search(logged_in, q=window, page_size=100)
        assert any(item["zh"] == zh_name for item in data["items"]), (
            f"查询 {window!r} 没命中 {zh_name!r}"
        )


def test_search_english_case_and_prefix(built, logged_in):
    lower = _search(logged_in, q="mario")
    upper = _search(logged_in, q="MARIO")
    assert lower["total"] == upper["total"] > 0
    assert _search(logged_in, q="mario*")["total"] >= lower["total"]
    assert _search(logged_in, q="不存在的名字xyz")["total"] == 0


def test_trailing_tags_not_indexed(built, logged_in):
    """结尾的地区/语言标签不进索引，展示仍是原文。"""
    assert _search(logged_in, q="japan")["total"] == 0
    assert _search(logged_in, q="日版")["total"] == 0

    # 但主标题搜得到，而且返回的 en 仍是带标签的原文
    data = _search(logged_in, q="Super Mario Bros")
    assert data["total"] > 0
    assert any("(Japan)" in item["en"] for item in data["items"])
    # 整串都是标签的行不会因此消失
    assert _search(logged_in, q="Alfa Romeo")["total"] == 1
    assert _search(logged_in, q="PS2")["total"] >= 1


def test_search_quotes_do_not_break(logged_in):
    for q in ['a"b', '"', "*", "mario AND", "马 里"]:
        response = logged_in.get(SEARCH_URL, params={"q": q})
        assert response.status_code == 200, f"{q!r} -> {response.text}"


def test_console_filter(built, logged_in):
    consoles = logged_in.get(CONSOLES_URL).json()["data"]
    assert consoles["indexed"] is True
    assert [c["name"] for c in consoles["consoles"]] == _EXPECTED_CONSOLES

    fc_id = next(c["id"] for c in consoles["consoles"] if c["name"] == "任天堂FC")
    all_rows = _search(logged_in, page_size=100)
    fc_rows = _search(logged_in, console_id=fc_id, page_size=100)
    assert 0 < fc_rows["total"] < all_rows["total"]
    assert all(item["console"] == "任天堂FC" for item in fc_rows["items"])

    # 关键词 + 机种过滤可以叠加
    assert _search(logged_in, q="mario", console_id=fc_id)["total"] > 0


def test_pagination_is_stable(built, logged_in):
    """翻完整页：并集 = 全集且无重复。抓 ORDER BY 少了 g.id tiebreaker 的坑。"""
    page_size = 3
    total = _search(logged_in, page_size=page_size)["total"]
    seen: list[int] = []
    for page in range(1, total // page_size + 2):
        data = _search(logged_in, page=page, page_size=page_size)
        seen += [item["id"] for item in data["items"]]
    assert len(seen) == total
    assert len(set(seen)) == total


def test_pagination_clamps_params(built, logged_in):
    # 越界不返回 422（那会绕开统一错误信封），由 service 收敛
    data = _search(logged_in, page=0, page_size=100000)
    assert data["page"] == 1
    assert data["page_size"] == 100
    # 越界页返回空列表而不是报错
    assert _search(logged_in, page=9999)["items"] == []


def test_empty_query_lists_everything(built, logged_in):
    data = _search(logged_in, q="", page_size=100)
    assert data["indexed"] is True
    assert data["total"] == _EXPECTED_ROWS


# --------------------------------------------------------------------------
# 索引缺失 / 损坏
# --------------------------------------------------------------------------


def test_missing_index_returns_guidance_and_creates_nothing(app, logged_in, index_path):
    data = _search(logged_in)
    assert data == {"indexed": False, "total": 0, "page": 1, "page_size": 10, "items": []}
    assert logged_in.get(CONSOLES_URL).json()["data"] == {"indexed": False, "consoles": []}
    # 服务端绝不代建索引
    assert not index_path.exists()


def test_broken_index_returns_503(app, logged_in, index_path):
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(b"not a database at all")
    response = logged_in.get(SEARCH_URL)
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert "make index" in body["message"]


def test_stale_schema_version_returns_503(app, logged_in, built, index_path):
    with sqlite3.connect(index_path) as conn:
        conn.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
        conn.commit()
    response = logged_in.get(SEARCH_URL)
    assert response.status_code == 503
    assert "过旧" in response.json()["message"]


# --------------------------------------------------------------------------
# 「只有 make index 写这个库」
# --------------------------------------------------------------------------


def _touch_every_route(client):
    """把这一功能的读写路径都打一遍。"""
    client.get(SEARCH_URL)
    client.get(SEARCH_URL, params={"q": "马里奥"})
    client.get(SEARCH_URL, params={"q": "mario", "page": 2, "page_size": 1})
    client.get(SEARCH_URL, params={"console_id": 1})
    client.get(SEARCH_URL, params={"page": -5, "page_size": 999999})
    client.get(SEARCH_URL, params={"q": "a" * 500})
    client.get(SEARCH_URL, params={"q": '"quoted" AND *'})
    client.get(CONSOLES_URL)


def test_runtime_never_writes_the_index(built, logged_in, index_path):
    """跑完所有只读路径后，库文件逐字节与 mtime 都不变。"""
    before = _digest(index_path)
    _touch_every_route(logged_in)
    assert _digest(index_path) == before


def test_runtime_works_without_write_permission(built, logged_in, index_path):
    """运行期连写权限都不需要：库文件与被改成只读的目录都能正常工作。"""
    os.chmod(index_path, 0o444)
    os.chmod(index_path.parent, 0o555)
    try:
        _touch_every_route(logged_in)
        data = _search(logged_in, q="mario")
        assert data["indexed"] is True
        assert data["total"] > 0
    finally:
        os.chmod(index_path.parent, 0o755)


def test_service_rejects_writes_to_a_read_only_index(built, index_path):
    """service 的连接是 mode=ro + query_only，写语句在这里就该失败。"""
    service = GameSearchService(index_path)
    with service._connect() as conn:
        with pytest.raises(sqlite3.Error):
            conn.execute("DELETE FROM game")


def test_routes_are_not_shadowed(built, logged_in):
    """这两条路径不能被 games_router 的 /{game_id}/… 抢走（抢走会是 422 而不是 404）。"""
    data = _search(logged_in)
    assert "items" in data and "total" in data
    consoles = logged_in.get(CONSOLES_URL).json()["data"]
    assert "consoles" in consoles
