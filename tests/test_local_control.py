from fastapi.testclient import TestClient

from backend import create_app
from backend.local_control import CONTROL_TOKEN_HEADER, SHUTDOWN_PATH

TOKEN = "s3cret-token"


def _app(tmp_path, **overrides):
    config = {"TESTING": True, "STORAGE_ROOT": str(tmp_path / "storage")}
    config.update(overrides)
    return create_app(config)


def _client(app, host="127.0.0.1"):
    """指定来源地址的客户端：默认的 testclient 主机名不是回环，测不到正常路径。"""
    return TestClient(app, client=(host, 51234))


def test_route_absent_by_default(tmp_path):
    """Docker 路线不设 LOCAL_CONTROL，这个接口根本不存在——一个能停服务的口子不能默认开着。"""
    client = _client(_app(tmp_path))
    assert client.post(SHUTDOWN_PATH, headers={CONTROL_TOKEN_HEADER: TOKEN}).status_code == 404


def test_rejects_non_loopback_client(tmp_path):
    """局域网里的设备发过来一律 403。"""
    app = _app(tmp_path, LOCAL_CONTROL=True, LOCAL_CONTROL_TOKEN=TOKEN)
    client = _client(app, host="192.168.1.20")
    response = client.post(SHUTDOWN_PATH, headers={CONTROL_TOKEN_HEADER: TOKEN})
    assert response.status_code == 403
    assert "本机" in response.json()["message"]


def test_rejects_wrong_token(tmp_path):
    app = _app(tmp_path, LOCAL_CONTROL=True, LOCAL_CONTROL_TOKEN=TOKEN)
    client = _client(app)
    assert client.post(SHUTDOWN_PATH, headers={CONTROL_TOKEN_HEADER: "nope"}).status_code == 403
    assert client.post(SHUTDOWN_PATH).status_code == 403


def test_missing_token_configured_means_no_route(tmp_path):
    app = _app(tmp_path, LOCAL_CONTROL=True, LOCAL_CONTROL_TOKEN=None)
    assert _client(app).post(SHUTDOWN_PATH).status_code == 404


def test_invokes_shutdown_hook(tmp_path):
    """带着对的 token 从本机来 → 调启动器挂的回调（真正让 uvicorn 退出的那一步）。"""
    app = _app(tmp_path, LOCAL_CONTROL=True, LOCAL_CONTROL_TOKEN=TOKEN)
    calls: list[str] = []
    app.state.request_shutdown = lambda: calls.append("stop")

    response = _client(app).post(SHUTDOWN_PATH, headers={CONTROL_TOKEN_HEADER: TOKEN})
    assert response.status_code == 200
    assert response.json()["data"] == {"stopping": True}
    assert calls == ["stop"]


def test_without_hook_reports_unsupported(tmp_path):
    """启动器没挂回调（比如直接用 uvicorn 命令行起的）时如实相告，而不是假装停掉了。"""
    app = _app(tmp_path, LOCAL_CONTROL=True, LOCAL_CONTROL_TOKEN=TOKEN)
    response = _client(app).post(SHUTDOWN_PATH, headers={CONTROL_TOKEN_HEADER: TOKEN})
    assert response.status_code == 501
