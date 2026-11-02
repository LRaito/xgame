from fastapi.testclient import TestClient

from backend import create_app


def _client(tmp_path, **overrides):
    config = {"TESTING": True, "STORAGE_ROOT": str(tmp_path / "storage")}
    config.update(overrides)
    return TestClient(create_app(config))


def test_rejects_oversized_body(tmp_path):
    """带 Content-Length 的超大请求体直接 413，一个字节都不读。

    Docker 路线上这道闸门由 nginx 的 client_max_body_size 把着；「解压即用」的 Windows
    包没有 nginx，就靠这个中间件（见 backend/request_limit.py）。
    """
    client = _client(tmp_path, MAX_REQUEST_BODY_BYTES=1024)
    response = client.post(
        "/api/register",
        content=b"x" * 4096,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413
    assert response.json()["ok"] is False
    assert "过大" in response.json()["message"]


def test_rejects_chunked_body(tmp_path):
    """没带 Content-Length 的写请求（分块传输）→ 411，不猜大小、边读边计数。"""
    client = _client(tmp_path, MAX_REQUEST_BODY_BYTES=1024)

    def chunks():
        yield b"x" * 16

    response = client.post("/api/register", content=chunks())
    assert response.status_code == 411
    assert "Content-Length" in response.json()["message"]


def test_allows_normal_requests(tmp_path):
    """上限之内的上传照常；GET 不受影响（本来就没有请求体）。"""
    client = _client(tmp_path, MAX_REQUEST_BODY_BYTES=4096)
    assert client.get("/health").status_code == 200
    registered = client.post(
        "/api/register", json={"username": "alice", "password": "secret123"}
    )
    assert registered.status_code == 200
