"""模拟器设置（键位等）按用户云同步的接口测试。"""

from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.games.models import GameEmulatorSettings

URL = "/api/games/emulator-settings"


def sample_settings() -> dict:
    """引擎 localStorage 里那块设置的最小合法形状。"""
    return {
        "controlSettings": {"0": {"0": {"value": "x", "value2": "BUTTON_2"}}},
        "settings": {"save-state-location": "browser"},
        "cheats": [],
    }


def test_settings_requires_login(client):
    assert client.get(URL, params={"game_type": "gba"}).status_code == 401
    saved = client.put(URL, json={"game_type": "gba", "settings": sample_settings()})
    assert saved.status_code == 401


def test_settings_empty_before_first_save(logged_in):
    response = logged_in.get(URL, params={"game_type": "gba"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["game_type"] == "gba"
    assert data["settings"] is None


def test_settings_roundtrip(logged_in):
    settings = sample_settings()
    saved = logged_in.put(URL, json={"game_type": "gba", "settings": settings})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["settings"] == settings

    fetched = logged_in.get(URL, params={"game_type": "gba"})
    assert fetched.status_code == 200
    assert fetched.json()["data"]["settings"] == settings


def test_settings_save_overwrites_same_row(logged_in, app):
    logged_in.put(URL, json={"game_type": "gba", "settings": sample_settings()})
    changed = sample_settings()
    changed["controlSettings"] = {"0": {"1": {"value": "z", "value2": "BUTTON_1"}}}
    saved = logged_in.put(URL, json={"game_type": "gba", "settings": changed})
    assert saved.status_code == 200
    assert saved.json()["data"]["settings"] == changed

    with Session(app.state.engine) as session:
        rows = session.exec(select(GameEmulatorSettings)).all()
    assert len(rows) == 1


def test_settings_isolated_per_game_type(logged_in):
    logged_in.put(URL, json={"game_type": "gba", "settings": sample_settings()})
    other = logged_in.get(URL, params={"game_type": "nes"})
    assert other.status_code == 200
    assert other.json()["data"]["settings"] is None


def test_settings_isolated_per_user(logged_in, app):
    logged_in.put(URL, json={"game_type": "gba", "settings": sample_settings()})

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    logged_in.post("/api/logout")
    login = logged_in.post(
        "/api/login", json={"username": "bobby", "password": "secret123"}
    )
    assert login.status_code == 200, login.text

    fetched = logged_in.get(URL, params={"game_type": "gba"})
    assert fetched.status_code == 200
    assert fetched.json()["data"]["settings"] is None


def test_settings_rejects_non_emulator_type(logged_in):
    response = logged_in.put(
        URL, json={"game_type": "flash", "settings": sample_settings()}
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False

    listed = logged_in.get(URL, params={"game_type": "flash"})
    assert listed.status_code == 400


def test_settings_rejects_invalid_payload(logged_in):
    for bad in (
        "not-an-object",
        {"controlSettings": {}, "settings": {}},  # 缺 cheats
        {"controlSettings": [], "settings": {}, "cheats": []},  # 类型不对
    ):
        response = logged_in.put(URL, json={"game_type": "gba", "settings": bad})
        assert response.status_code == 400, bad
        assert response.json()["ok"] is False


def test_settings_rejects_oversized_payload(logged_in):
    bloated = sample_settings()
    bloated["settings"] = {"huge": "x" * (64 * 1024)}
    response = logged_in.put(URL, json={"game_type": "gba", "settings": bloated})
    assert response.status_code == 400
    assert response.json()["ok"] is False
