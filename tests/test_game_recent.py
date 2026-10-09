"""游戏中心「最近游玩」的接口测试。"""

from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.games.models import Game, GameRecentPlay

URL = "/api/games/recent"


_seq = 0


def _make_game(app, name: str, *, game_type: str = "nes", game_path: str | None = None) -> int:
    """直接插一行游戏，比走上传接口省事（本组用例不碰真实文件）。"""
    global _seq
    _seq += 1
    with Session(app.state.engine) as session:
        row = Game(
            name=name,
            cartridge_id=f"REC{_seq:04d}",
            game_type=game_type,
            # 默认给个非空本体路径：中心列表与最近游玩都只认「有本体」的游戏
            game_path=f"game/{game_type}/REC{_seq:04d}/game.nes" if game_path is None else game_path,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _set_game_path(app, game_id: int, path: str) -> None:
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        row.game_path = path
        session.add(row)
        session.commit()


def _recent_rows(app) -> list[GameRecentPlay]:
    with Session(app.state.engine) as session:
        return list(session.exec(select(GameRecentPlay)).all())


def test_recent_requires_login(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"game_id": 1}).status_code == 401


def test_recent_empty_before_first_play(logged_in):
    response = logged_in.get(URL)
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"] == []


def test_recent_roundtrip_orders_by_play_time(logged_in, app):
    first = _make_game(app, "First")
    second = _make_game(app, "Second")

    assert logged_in.post(URL, json={"game_id": first}).status_code == 200
    assert logged_in.post(URL, json={"game_id": second}).status_code == 200

    data = logged_in.get(URL).json()["data"]
    assert [item["id"] for item in data] == [second, first]
    # 载荷与中心列表同构，卡片需要的字段都在
    top = data[0]
    assert top["name"] == "Second"
    assert top["path"] == f"/games/play/{second}"
    assert top["category"] == "nes"
    assert "cover_path" in top
    assert "cartridge_id" in top
    assert "updated_at" in top


def test_recent_mark_keeps_single_row(logged_in, app):
    first = _make_game(app, "First")
    second = _make_game(app, "Second")

    logged_in.post(URL, json={"game_id": first})
    logged_in.post(URL, json={"game_id": second})
    # 重玩 first：不该多出一行，且它回到最前
    assert logged_in.post(URL, json={"game_id": first}).status_code == 200

    rows = _recent_rows(app)
    assert len(rows) == 2
    assert len({(row.user_id, row.game_id) for row in rows}) == 2
    assert [item["id"] for item in logged_in.get(URL).json()["data"]] == [first, second]


def test_recent_isolated_per_user(logged_in, app):
    game_id = _make_game(app, "Mine")
    logged_in.post(URL, json={"game_id": game_id})

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    logged_in.post("/api/logout")
    login = logged_in.post(
        "/api/login", json={"username": "bobby", "password": "secret123"}
    )
    assert login.status_code == 200, login.text

    assert logged_in.get(URL).json()["data"] == []


def test_recent_limit_clamped(logged_in, app):
    ids = [_make_game(app, f"Game{i}") for i in range(3)]
    for game_id in ids:
        logged_in.post(URL, json={"game_id": game_id})

    assert len(logged_in.get(URL, params={"limit": 2}).json()["data"]) == 2
    # 越界不报 422（那会绕开统一错误信封），而是收敛到 1 与上限
    assert len(logged_in.get(URL, params={"limit": 0}).json()["data"]) == 1
    assert len(logged_in.get(URL, params={"limit": 999}).json()["data"]) == 3


def test_recent_mark_unknown_game_404(logged_in):
    response = logged_in.post(URL, json={"game_id": 99999})
    assert response.status_code == 404
    assert response.json()["ok"] is False
    assert response.json()["message"]


def test_recent_mark_game_without_body_404(logged_in, app):
    game_id = _make_game(app, "Empty", game_path="")
    response = logged_in.post(URL, json={"game_id": game_id})
    assert response.status_code == 404
    assert _recent_rows(app) == []


def test_recent_skips_game_without_body(logged_in, app):
    game_id = _make_game(app, "Lost")
    logged_in.post(URL, json={"game_id": game_id})
    # 本体被清空后，旧记录不该再出现在 rail 里
    _set_game_path(app, game_id, "")
    assert logged_in.get(URL).json()["data"] == []


def test_recent_cleared_when_game_deleted(logged_in, app):
    game_id = _make_game(app, "Doomed")
    logged_in.post(URL, json={"game_id": game_id})
    assert logged_in.get(URL).json()["data"] != []

    deleted = logged_in.delete(f"/api/games/manage/{game_id}")
    assert deleted.status_code == 200, deleted.text

    assert logged_in.get(URL).json()["data"] == []
    assert _recent_rows(app) == []
