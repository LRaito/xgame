"""游戏中心「游玩时长与进度」的接口测试。"""

from sqlmodel import Session, select

from backend.auth.models import User
from backend.auth.service import AuthService
from backend.games.models import Game, GameUserStat

STATS_URL = "/api/games/stats"


_seq = 0


def _make_game(app, name: str, *, game_path: str | None = None) -> int:
    """直接插一行游戏，比走上传接口省事（本组用例不碰真实文件）。"""
    global _seq
    _seq += 1
    with Session(app.state.engine) as session:
        row = Game(
            name=name,
            cartridge_id=f"STAT{_seq:04d}",
            game_type="nes",
            # 默认给个非空本体路径：中心列表与统计接口都只认「有本体」的游戏
            game_path=f"game/nes/STAT{_seq:04d}/game.nes" if game_path is None else game_path,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _user_id(client) -> int:
    with Session(client.app.state.engine) as session:
        return session.exec(
            select(User).where(User.username == "alice")
        ).first().id


def _stat_row(app, user_id: int, game_id: int) -> GameUserStat | None:
    with Session(app.state.engine) as session:
        return session.exec(
            select(GameUserStat).where(
                GameUserStat.user_id == user_id,
                GameUserStat.game_id == game_id,
            )
        ).first()


def test_stats_requires_login(client):
    assert client.post(f"{STATS_URL}/playtime", json={"game_id": 1, "seconds": 10}).status_code == 401
    assert client.put(f"{STATS_URL}/1/playtime", json={"hours": 1}).status_code == 401
    assert client.put(f"{STATS_URL}/1/progress", json={"progress": "completed"}).status_code == 401


def test_playtime_accumulates(logged_in, app):
    game_id = _make_game(app, "Acc")

    first = logged_in.post(f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 30})
    assert first.status_code == 200, first.text
    assert first.json()["data"]["play_seconds"] == 30

    second = logged_in.post(f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 45})
    assert second.json()["data"]["play_seconds"] == 75

    row = _stat_row(app, _user_id(logged_in), game_id)
    assert row is not None and row.play_seconds == 75


def test_playtime_add_is_clamped_per_call(logged_in, app):
    """单次上报的秒数要在 service 里收敛：不能让一次请求把时长顶上天。"""
    game_id = _make_game(app, "Clamp")

    response = logged_in.post(f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 99999})
    assert response.status_code == 200
    assert response.json()["data"]["play_seconds"] == 300

    # 负数与零都不改变总数
    assert logged_in.post(
        f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": -50}
    ).json()["data"]["play_seconds"] == 300

    # 小数秒数由 service 取整，不能因为 Pydantic 声明类型就 422 绕开错误信封
    fractional = logged_in.post(
        f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 12.7}
    )
    assert fractional.status_code == 200
    assert fractional.json()["data"]["play_seconds"] == 313


def test_playtime_manual_set_then_keep_accumulating(logged_in, app):
    """手动设时长 = 设为新基数，之后照常在其上累加。"""
    game_id = _make_game(app, "Manual")

    response = logged_in.put(f"{STATS_URL}/{game_id}/playtime", json={"hours": 10})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["play_seconds"] == 36000

    # 再手动改成 1.5 小时是覆盖
    assert logged_in.put(
        f"{STATS_URL}/{game_id}/playtime", json={"hours": 1.5}
    ).json()["data"]["play_seconds"] == 5400

    # 之后继续玩会从 5400 往上加（单次上报受 PLAYTIME_ADD_MAX 收敛，用两次凑）
    assert logged_in.post(
        f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 300}
    ).json()["data"]["play_seconds"] == 5700
    assert logged_in.post(
        f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 300}
    ).json()["data"]["play_seconds"] == 6000


def test_playtime_manual_set_rejects_out_of_range(logged_in, app):
    game_id = _make_game(app, "Range")

    for hours in (-1, 100001):
        response = logged_in.put(f"{STATS_URL}/{game_id}/playtime", json={"hours": hours})
        assert response.status_code == 400, hours
        assert response.json()["ok"] is False
        assert response.json()["message"]


def test_progress_roundtrip_and_validation(logged_in, app):
    game_id = _make_game(app, "Progress")

    for value in ("in_progress", "completed", "not_started"):
        response = logged_in.put(f"{STATS_URL}/{game_id}/progress", json={"progress": value})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["progress"] == value

    bad = logged_in.put(f"{STATS_URL}/{game_id}/progress", json={"progress": "烂尾"})
    assert bad.status_code == 400
    assert bad.json()["message"]

    # 非法值不能把已存的进度冲掉
    assert _stat_row(app, _user_id(logged_in), game_id).progress == "not_started"


def test_stats_unknown_game_returns_404(logged_in):
    assert logged_in.post(f"{STATS_URL}/playtime", json={"game_id": 999, "seconds": 10}).status_code == 404
    assert logged_in.put(f"{STATS_URL}/999/progress", json={"progress": "completed"}).status_code == 404


def test_center_list_carries_stats(logged_in, app):
    plain = _make_game(app, "Plain")
    played = _make_game(app, "Played")

    # 时长走手动设置（单次上报的秒数有上限，凑不出 2 小时）
    logged_in.put(f"{STATS_URL}/{played}/playtime", json={"hours": 2})
    logged_in.put(f"{STATS_URL}/{played}/progress", json={"progress": "completed"})
    logged_in.post("/api/games/recent", json={"game_id": played})

    rows = {item["id"]: item for item in logged_in.get("/api/games").json()["data"]}
    assert rows[plain]["play_seconds"] == 0
    assert rows[plain]["progress"] == "not_started"
    assert rows[played]["play_seconds"] == 7200
    assert rows[played]["progress"] == "completed"

    # 最近游玩载荷与中心列表同构，rail 卡片也能直接显示
    recent = {item["id"]: item for item in logged_in.get("/api/games/recent").json()["data"]}
    assert recent[played]["play_seconds"] == 7200
    assert recent[played]["progress"] == "completed"


def test_delete_game_clears_stats(logged_in, app):
    game_id = _make_game(app, "Doomed")
    logged_in.post(f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 60})
    logged_in.put(f"{STATS_URL}/{game_id}/progress", json={"progress": "in_progress"})
    assert _stat_row(app, _user_id(logged_in), game_id) is not None

    assert logged_in.delete(f"/api/games/manage/{game_id}").status_code == 200

    with Session(app.state.engine) as session:
        assert list(session.exec(select(GameUserStat)).all()) == []


def test_stats_isolated_per_user(logged_in, app, do_login):
    game_id = _make_game(app, "Shared")
    logged_in.post(f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 120})
    logged_in.put(f"{STATS_URL}/{game_id}/progress", json={"progress": "completed"})

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bob", "secret123")
    do_login(client=logged_in, username="bob", password="secret123")

    # 另一个账号看到的是默认值，不是 alice 的数据
    rows = {item["id"]: item for item in logged_in.get("/api/games").json()["data"]}
    assert rows[game_id]["play_seconds"] == 0
    assert rows[game_id]["progress"] == "not_started"

    # 各自写各自的行
    logged_in.post(f"{STATS_URL}/playtime", json={"game_id": game_id, "seconds": 30})
    with Session(app.state.engine) as session:
        stat_rows = list(session.exec(select(GameUserStat)).all())
    assert sorted(row.play_seconds for row in stat_rows) == [30, 120]
