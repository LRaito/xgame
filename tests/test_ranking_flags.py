"""榜单/库存双向标记的同步测试。"""

import sqlite3
from pathlib import Path

from sqlmodel import Session, select

from backend.games.ranking_flags import (
    FlagSyncError,
    read_ranking_ids,
    refresh_all_flags,
    refresh_ranking_flags,
)
from backend.games.search_index import build_index
from backend.games.service import GameService

_HEADER = ["中文名", "英文名", "评分", "卡带ID"]


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    path.write_text(
        "\n".join(",".join(row) for row in rows) + "\n", encoding="utf-8-sig"
    )


def _build(app, tmp_path: Path, ranking_rows: list[list[str]]) -> Path:
    source = tmp_path / "search"
    source.mkdir()
    _write_csv(source / "nes.csv", [["中文名", "英文名"], ["测试", "Test"]])
    ranking = tmp_path / "rank"
    ranking.mkdir()
    _write_csv(ranking / "nes.csv", [_HEADER, *ranking_rows])
    target = app.state.settings.game_index_path
    build_index(source, target, ranking_dir=ranking, strict_ranking=True)
    return target


def _game_flags(app, cartridge_id: str) -> bool:
    from backend.games.models import Game

    with Session(app.state.engine) as session:
        row = session.exec(select(Game).where(Game.cartridge_id == cartridge_id)).one()
        return row.in_ranking


def _ranking_flag(path: Path, cartridge_id: str) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT r.in_library FROM ranking_cartridges rc "
            "JOIN ranking r ON r.id = rc.ranking_id WHERE rc.cartridge_id = ?",
            (cartridge_id,),
        ).fetchone()
        return row[0]


def test_refresh_all_flags_marks_both_tables(app, tmp_path):
    from backend.games.models import Game

    index = _build(
        app,
        tmp_path,
        [
            ["A", "Game A", "8", "ABC-1"],
            ["B", "Game B", "7", "ID1;ID2"],
            ["C", "Game C", "6", "XYZ"],
        ],
    )
    with Session(app.state.engine) as session:
        session.add(Game(name="甲", cartridge_id="ABC-1", game_type="nes"))
        session.add(Game(name="乙", cartridge_id="ID1", game_type="nes"))
        session.commit()
        updated_at = session.exec(select(Game).where(Game.cartridge_id == "ABC-1")).one().updated_at

    stats = refresh_all_flags(app.state.settings.database_path, index, strict=True)

    assert stats is not None
    assert _game_flags(app, "ABC-1") is True
    assert _game_flags(app, "ID1") is True
    assert _ranking_flag(index, "ABC-1") == 1
    assert _ranking_flag(index, "ID1") == 1
    assert _ranking_flag(index, "XYZ") == 0
    with Session(app.state.engine) as session:
        row = session.exec(select(Game).where(Game.cartridge_id == "ABC-1")).one()
        assert row.updated_at == updated_at  # 全量对账不改排序字段


def test_shared_ranking_row_stays_in_library_while_any_id_exists(app, tmp_path):
    from backend.games.models import Game

    index = _build(
        app,
        tmp_path,
        [["B", "Game B", "7", "ID1;ID2"]],
    )
    with Session(app.state.engine) as session:
        session.add(Game(name="一号", cartridge_id="ID1", game_type="nes"))
        session.add(Game(name="二号", cartridge_id="ID2", game_type="nes"))
        session.commit()
    refresh_all_flags(app.state.settings.database_path, index, strict=True)
    assert _ranking_flag(index, "ID1") == 1

    with Session(app.state.engine) as session:
        row = session.exec(select(Game).where(Game.cartridge_id == "ID1")).one()
        session.delete(row)
        session.commit()
    refresh_ranking_flags(
        app.state.settings.database_path, index, ["ID1"]
    )
    assert _ranking_flag(index, "ID2") == 1  # 同一行的另一个 ID 还在

    with Session(app.state.engine) as session:
        row = session.exec(select(Game).where(Game.cartridge_id == "ID2")).one()
        session.delete(row)
        session.commit()
    refresh_ranking_flags(
        app.state.settings.database_path, index, ["ID2"]
    )
    assert _ranking_flag(index, "ID2") == 0


def test_service_create_rename_delete_updates_flags(app, tmp_path):
    index = _build(
        app,
        tmp_path,
        [
            ["A", "Game A", "8", "ABC-1"],
            ["B", "Game B", "7", "ID1;ID2"],
        ],
    )
    service = GameService(
        Session(app.state.engine),
        app.state.storage,
        app.state.runtime_storage,
        game_index_path=index,
        database_path=app.state.settings.database_path,
    )

    created = service.create(
        "命中游戏", "", cartridge_id="ABC-1", body_game_type="nes"
    )
    assert created.in_ranking is True
    assert _ranking_flag(index, "ABC-1") == 1

    renamed = service.rename_cartridge_id(created.id, "ID1")
    assert renamed.in_ranking is True
    assert _ranking_flag(index, "ABC-1") == 0
    assert _ranking_flag(index, "ID1") == 1

    renamed = service.rename_cartridge_id(created.id, "NOPE")
    assert renamed.in_ranking is False
    assert _ranking_flag(index, "ID1") == 0

    service.delete(created.id)
    assert _ranking_flag(index, "ID1") == 0


def test_read_ranking_ids_normalizes_and_reports_missing_mapping(app, tmp_path):
    index = _build(app, tmp_path, [["A", "Game A", "8", "ABC-1"]])

    assert read_ranking_ids(index, ["  abc-1 "]) == {"ABC-1": 1}
    assert read_ranking_ids(index, ["NOPE"]) == {}

    index.unlink()
    assert read_ranking_ids(index, ["ABC-1"]) == {}


def test_api_create_rename_delete_updates_flags(app, logged_in, tmp_path):
    """生产依赖装配也传了两个库路径：API 增删改同样维护标记。"""
    index = _build(
        app,
        tmp_path,
        [
            ["A", "Game A", "8", "ABC-1"],
            ["B", "Game B", "7", "ID1;ID2"],
        ],
    )

    created = logged_in.post(
        "/api/games/manage",
        data={
            "name": "API 游戏",
            "cartridge_id": "ABC-1",
            "description": "",
            "body_game_type": "nes",
        },
    )
    assert created.status_code == 201, created.text
    game_id = created.json()["data"]["id"]
    assert created.json()["data"]["in_ranking"] is True
    assert _ranking_flag(index, "ABC-1") == 1

    renamed = logged_in.put(
        f"/api/games/manage/{game_id}/cartridge-id",
        json={"cartridge_id": "ID1"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["in_ranking"] is True
    assert _ranking_flag(index, "ABC-1") == 0
    assert _ranking_flag(index, "ID1") == 1

    assert logged_in.delete(f"/api/games/manage/{game_id}").status_code == 200
    assert _ranking_flag(index, "ID1") == 0


def test_refresh_all_flags_strict_rejects_missing_app_column(app, tmp_path):
    index = _build(app, tmp_path, [["A", "Game A", "8", "ABC-1"]])
    # 模拟还没跑 make upgrade 的老库：直接删掉列做不到，用另一个空库代替
    old_db = tmp_path / "old.db"
    with sqlite3.connect(old_db) as conn:
        conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE system_config (id INTEGER PRIMARY KEY)")
        conn.commit()

    try:
        refresh_all_flags(old_db, index, strict=True)
    except FlagSyncError as exc:
        assert "make upgrade" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("缺少 in_ranking 列时必须报错")
