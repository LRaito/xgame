from pathlib import Path

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
    # 数据根目录不用预先建：create_app 启动时会建出来。
    # 刻意**不设** RUNTIME_ROOT：这时运行时根退回数据根，两个 LocalStorage 指向同一棵树，
    # 与 Docker 默认之外的另外两条路线（本机直跑、Windows 包的 data_dir 未改）一致。
    application = create_app(
        {
            "TESTING": True,
            "STORAGE_ROOT": str(tmp_path / "storage"),
        }
    )
    yield application


@pytest.fixture
def split_app(tmp_path):
    """两个根分开的 app：数据根 tmp/storage、运行时根 tmp/runtime（Docker 的形态）。

    解包产物的失效、清理与「同根时不重复出错」两类行为都要在这一组里再验一遍。
    """
    application = create_app(
        {
            "TESTING": True,
            "STORAGE_ROOT": str(tmp_path / "storage"),
            "RUNTIME_ROOT": str(tmp_path / "runtime"),
        }
    )
    yield application


@pytest.fixture
def storage_root(app, tmp_path):
    """项目文件根目录：断言落盘路径时直接用。"""
    return tmp_path / "storage"


@pytest.fixture
def runtime_root(app):
    """运行时根目录（H5/攻略的解包产物、SQLite 库）。不配 RUNTIME_ROOT 时就是数据根。"""
    return Path(app.state.settings.runtime_root)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def split_client(split_app):
    return TestClient(split_app)


@pytest.fixture
def user(app):
    with Session(app.state.engine) as session:
        return AuthService(session).create_user("alice", "secret123")


@pytest.fixture
def logged_in(client, user):
    login_as(client)
    return client


@pytest.fixture
def split_logged_in(split_client, split_app):
    """两个根分开的 app 上建号并登录（只给新用例用，现有用例继续走 logged_in）。"""
    with Session(split_app.state.engine) as session:
        AuthService(session).create_user("alice", "secret123")
    login_as(split_client)
    return split_client


@pytest.fixture
def do_login():
    return login_as


@pytest.fixture
def do_register():
    return register_as
