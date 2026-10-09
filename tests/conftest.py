import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from backend import create_app
from backend.auth.service import AuthService


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
    # 数据根目录不用预先建：create_app 启动时会连同 .mounted 哨兵文件一起建出来
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
