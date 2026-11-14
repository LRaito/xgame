"""用户级快捷键配置接口测试。"""

from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.shortcuts.models import UserShortcut

URL = "/api/user-shortcuts"


def test_shortcuts_require_login(client):
    assert client.get(URL).status_code == 401
    assert client.put(f"{URL}/play.sync_cloud", json={"binding": "Backquote"}).status_code == 401
    assert client.delete(f"{URL}/play.sync_cloud").status_code == 401


def test_shortcuts_empty_initially(logged_in):
    response = logged_in.get(URL)
    assert response.status_code == 200
    assert response.json()["data"]["overrides"] == []


def test_shortcut_roundtrip(logged_in):
    saved = logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "Ctrl+Shift+KeyS"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"] == {
        "action_id": "play.sync_cloud",
        "binding": "Ctrl+Shift+KeyS",
    }
    listed = logged_in.get(URL).json()["data"]["overrides"]
    assert listed == [{"action_id": "play.sync_cloud", "binding": "Ctrl+Shift+KeyS"}]


def test_shortcut_normalizes_modifier_order(logged_in):
    saved = logged_in.put(f"{URL}/play.screenshot", json={"binding": "Shift+Ctrl+KeyS"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["binding"] == "Ctrl+Shift+KeyS"


def test_shortcut_clear_is_empty_string(logged_in):
    logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "Backquote"})
    cleared = logged_in.put(f"{URL}/play.sync_cloud", json={"binding": ""})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["binding"] == ""
    assert logged_in.get(URL).json()["data"]["overrides"] == [
        {"action_id": "play.sync_cloud", "binding": ""}
    ]


def test_shortcut_reset_removes_override(logged_in, app):
    logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "Backquote"})
    reset = logged_in.delete(f"{URL}/play.sync_cloud")
    assert reset.status_code == 200
    assert logged_in.get(URL).json()["data"]["overrides"] == []
    with Session(app.state.engine) as session:
        assert session.exec(select(UserShortcut)).all() == []


def test_shortcut_reset_is_idempotent(logged_in):
    assert logged_in.delete(f"{URL}/play.sync_cloud").status_code == 200


def test_shortcut_rejects_unknown_key(logged_in):
    response = logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "CapsLock"})
    assert response.status_code == 400
    assert response.json()["message"] == "该键暂不支持设置，请换一个键。"


def test_shortcut_rejects_reserved_binding(logged_in):
    response = logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "Ctrl+KeyW"})
    assert response.status_code == 400
    assert "占用" in response.json()["message"]

    bare_tab = logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "Tab"})
    assert bare_tab.status_code == 400
    assert "切换焦点" in bare_tab.json()["message"]

    escape = logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "Ctrl+Escape"})
    assert escape.status_code == 400
    assert "取消" in escape.json()["message"]


def test_shortcut_rejects_bad_modifier(logged_in):
    for binding in ("Hyper+KeyS", "Ctrl+Ctrl+KeyS"):
        response = logged_in.put(f"{URL}/play.sync_cloud", json={"binding": binding})
        assert response.status_code == 400, binding


def test_shortcut_rejects_bad_action_id(logged_in):
    response = logged_in.put(f"{URL}/BadAction", json={"binding": "KeyS"})
    assert response.status_code == 400
    assert response.json()["message"] == "快捷键标识不合法。"


def test_shortcut_isolated_per_user(logged_in, app):
    logged_in.put(f"{URL}/play.sync_cloud", json={"binding": "Backquote"})

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    logged_in.post("/api/logout")
    login = logged_in.post(
        "/api/login", json={"username": "bobby", "password": "secret123"}
    )
    assert login.status_code == 200, login.text

    assert logged_in.get(URL).json()["data"]["overrides"] == []
