import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from backend import create_app
from backend.auth.service import AuthService


@pytest.fixture(autouse=True)
def _hide_host_dir_env(monkeypatch):
    """把两个宿主路径变量从进程环境里摘掉，让每条用例都在受控环境下构造 Settings。

    `STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR` 是配在 `.env` 里、给 compose 用的**宿主**路径，
    只参与 mount_guard 的哨兵前缀判断；而 `Settings`（pydantic-settings）会读环境变量，
    于是 `make test` 经 Makefile 的 export 把它们带进来之后，任何构造 Settings 的用例都会
    以为数据根落在 /mnt 这类 Windows 盘路径下，判定缺哨兵而 SystemExit: 3 —— 直接跑 pytest
    全绿、走 make test 挂 4 条，就是这么来的。

    需要这两个值的用例自己构造 Settings 时显式传参（见 test_mount_guard.py）。
    """
    monkeypatch.delenv("STORAGE_HOST_DIR", raising=False)
    monkeypatch.delenv("RUNTIME_HOST_DIR", raising=False)


def login_as(client, username="alice", password="secret123"):
    response = client.post(
        "/api/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response


def register_as(client, username="alice", password="secret123"):
    response = client.post(
        "/api/register", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
def app(tmp_path):
    # 数据根目录不用预先建：create_app 启动时会建出来
    application = create_app(
        {
            "TESTING": True,
            "STORAGE_ROOT": str(tmp_path / "storage"),
        }
    )
    yield application


@pytest.fixture
def storage_root(app, tmp_path):
    """项目文件根目录：断言落盘路径时直接用。"""
    return tmp_path / "storage"


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def user(app):
    with Session(app.state.engine) as session:
        return AuthService(session).create_user("alice", "secret123")


@pytest.fixture
def logged_in(client, user):
    login_as(client)
    return client


@pytest.fixture
def do_login():
    return login_as


@pytest.fixture
def do_register():
    return register_as
