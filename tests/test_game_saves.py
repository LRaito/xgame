import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.games import paths
from backend.games.models import GameCloudSnapshot, GameCloudSnapshotFile
from backend.config import DB_SUBDIR
from backend.mount_guard import SENTINEL_NAME


@pytest.fixture
def logged_in_saves(client, user, do_login):
    do_login(client)
    return client


def _files(storage_root) -> set[str]:
    root = Path(storage_root)
    if not root.exists():
        return set()
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
        and p.name != SENTINEL_NAME
        # db/ 里是 SQLite 库与它的月度备份，不属于游戏素材
        and p.relative_to(root).parts[0] != DB_SUBDIR
    }


def _make_game(client, name="存档测试游戏", cartridge_id=None):
    """建一个 Flash 游戏（类型由本体扩展名自动识别）。"""
    response = client.post(
        "/api/games/manage",
        data={
            "name": name,
            "description": "",
            "cartridge_id": cartridge_id or f"SAVE{abs(hash(name)) % 100000}",
        },
        files={"file": ("demo.swf", b"swf-body", "application/x-shockwave-flash")},
    )
    assert response.status_code == 201
    return response.json()["data"]


def _sol_data(payload: bytes) -> bytes:
    # .sol 头部：00 bf + "TCSO" + 8 字节 0，后接业务字节
    return b"\x00\xbfTCSO" + b"\x00" * 8 + payload


def _upload_form(game_id: int, sols: list[bytes], remark="备注"):
    manifest = json.dumps(
        [
            {
                "local_key": f"http://localhost/game-assets/swf/{game_id}/slot-{i}.sol",
                "name": f"存档{i + 1}",
            }
            for i in range(len(sols))
        ]
    )
    data = {
        "game_id": str(game_id),
        "remark": remark,
        "manifest": manifest,
    }
    files = [
        ("sols", (f"slot{i}.sol", data_, "application/octet-stream"))
        for i, data_ in enumerate(sols)
    ]
    return data, files


def test_save_file_path_layout():
    """存档落盘路径：save/用户名/游戏类型/卡带ID/{uuid}.state。"""
    path = paths.save_file_path("alice", "nes", "AB-12", "deadbeef")
    assert path == "save/alice/nes/AB-12/deadbeef.state"


def test_cloud_saves_requires_login(client):
    response = client.get("/api/games/saves", params={"game_id": 1})
    assert response.status_code == 401
    body = response.json()
    assert body["ok"] is False
    assert "登录" in body["message"]


def test_cloud_saves_unknown_game(logged_in):
    """没建过这个游戏：同步存档返回「游戏不存在」。"""
    data, files = _upload_form(1, [_sol_data(b"a")])
    response = logged_in.post("/api/games/saves", data=data, files=files)
    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert "游戏不存在" in body["message"]


def test_cloud_snapshot_roundtrip(logged_in_saves, user, storage_root):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="RT-1")["id"]

    sols = [_sol_data(b"first"), _sol_data(b"second-save")]
    data, files = _upload_form(game_id, sols)
    create = client.post("/api/games/saves", data=data, files=files)
    assert create.status_code == 201
    snapshot = create.json()["data"]
    assert len(snapshot["files"]) == 2
    assert [f["name"] for f in snapshot["files"]] == ["存档1", "存档2"]

    # 落盘路径按 用户名/游戏类型/卡带ID 分目录，内容与上传一致
    prefix = f"save/{user.username}/flash/RT-1/"
    saved = sorted(k for k in _files(storage_root) if k.startswith(prefix))
    assert len(saved) == 2
    assert all(k.endswith(".state") for k in saved)
    assert sorted((Path(storage_root) / k).read_bytes() for k in saved) == sorted(sols)

    listing = client.get("/api/games/saves", params={"game_id": game_id})
    assert listing.status_code == 200
    items = listing.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == snapshot["id"]
    assert items[0]["file_count"] == 2
    assert items[0]["total_size"] == sum(len(s) for s in sols)
    assert items[0]["remark"] == "备注"

    detail = client.get(f"/api/games/saves/{snapshot['id']}")
    assert detail.status_code == 200
    files = detail.json()["data"]["files"]
    assert [f["name"] for f in files] == ["存档1", "存档2"]
    assert files[0]["local_key"].endswith("/slot-0.sol")
    assert [f["sort_order"] for f in files] == [0, 1]

    # 单文件下载内容还原
    for file_ in files:
        download = client.get(
            f"/api/games/saves/{snapshot['id']}/files/{file_['id']}/download"
        )
        assert download.status_code == 200
        assert download.content == sols[file_["sort_order"]]
        assert download.headers.get("content-type") == "application/octet-stream"

    # 删除快照 → 行与文件都清理
    delete = client.delete(f"/api/games/saves/{snapshot['id']}")
    assert delete.status_code == 200
    assert not [k for k in _files(storage_root) if k.startswith(prefix)]
    with Session(client.app.state.engine) as session:
        assert session.get(GameCloudSnapshot, snapshot["id"]) is None
        rows = session.exec(
            select(GameCloudSnapshotFile).where(
                GameCloudSnapshotFile.snapshot_id == snapshot["id"]
            )
        ).all()
        assert len(rows) == 0


def test_cloud_snapshot_update_remark(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client)["id"]
    data, files = _upload_form(game_id, [_sol_data(b"x")], remark="旧的描述")
    create = client.post("/api/games/saves", data=data, files=files)
    assert create.status_code == 201
    snapshot_id = create.json()["data"]["id"]

    update = client.put(
        f"/api/games/saves/{snapshot_id}", json={"remark": "通关前的存档"}
    )
    assert update.status_code == 200
    assert update.json()["data"]["remark"] == "通关前的存档"

    detail = client.get(f"/api/games/saves/{snapshot_id}")
    assert detail.json()["data"]["remark"] == "通关前的存档"
    listing = client.get("/api/games/saves", params={"game_id": game_id})
    assert listing.json()["data"][0]["remark"] == "通关前的存档"


def test_cloud_snapshot_remark_too_long_update(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client)["id"]
    data, files = _upload_form(game_id, [_sol_data(b"x")])
    create = client.post("/api/games/saves", data=data, files=files)
    assert create.status_code == 201
    snapshot_id = create.json()["data"]["id"]

    update = client.put(
        f"/api/games/saves/{snapshot_id}", json={"remark": "超" * 101}
    )
    assert update.status_code == 400
    assert "100" in update.json()["message"]


def test_cloud_snapshot_remark_too_long_create(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client)["id"]
    data, files = _upload_form(game_id, [_sol_data(b"x")], remark="超" * 101)
    response = client.post("/api/games/saves", data=data, files=files)
    assert response.status_code == 400
    assert "100" in response.json()["message"]


def test_cloud_saves_user_isolation(logged_in_saves, app):
    client = logged_in_saves
    game_id = _make_game(client)["id"]
    data, files = _upload_form(game_id, [_sol_data(b"alice-save")])
    create = client.post("/api/games/saves", data=data, files=files)
    assert create.status_code == 201
    snapshot_id = create.json()["data"]["id"]

    # 换 bobby 登录后看不到 alice 的云端存档
    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    client.post("/api/logout")
    login = client.post(
        "/api/login", json={"username": "bobby", "password": "secret123"}
    )
    assert login.status_code == 200, login.text

    listing = client.get("/api/games/saves", params={"game_id": game_id})
    assert listing.status_code == 200
    assert listing.json()["data"] == []

    detail = client.get(f"/api/games/saves/{snapshot_id}")
    assert detail.status_code == 404
    download = client.get(f"/api/games/saves/{snapshot_id}/files/1/download")
    assert download.status_code == 404
    update = client.put(f"/api/games/saves/{snapshot_id}", json={"remark": "劫持"})
    assert update.status_code == 404
    delete = client.delete(f"/api/games/saves/{snapshot_id}")
    assert delete.status_code == 404


def test_cloud_saves_manifest_mismatch(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client)["id"]
    data = {
        "game_id": str(game_id),
        "remark": "",
        "manifest": json.dumps(
            [{"local_key": "k1", "name": "a"}]  # 只声明 1 个
        ),
    }
    files = [
        ("sols", ("a.sol", _sol_data(b"a"), "application/octet-stream")),
        ("sols", ("b.sol", _sol_data(b"b"), "application/octet-stream")),
    ]
    response = client.post("/api/games/saves", data=data, files=files)
    assert response.status_code == 400
    assert "不一致" in response.json()["message"]


def test_cloud_snapshot_game_missing(logged_in_saves):
    client = logged_in_saves
    data, files = _upload_form(99999, [_sol_data(b"x")])
    response = client.post("/api/games/saves", data=data, files=files)
    assert response.status_code == 404
    assert "游戏不存在" in response.json()["message"]


def test_emulator_state_snapshot_keeps_extension(logged_in_saves):
    """模拟器(.state)存档快照：name 带扩展名时，列表/详情保留，下载名不再追加 .sol。"""
    client = logged_in_saves
    game_id = _make_game(client, "Emulator 游戏")["id"]
    states = [b"state-one-bytes", b"state-two-bytes"]
    manifest = json.dumps(
        [
            {"local_key": "emu|slot-0", "name": "slot-0.state"},
            {"local_key": "emu|slot-1", "name": "slot-1.state"},
        ]
    )
    data = {"game_id": str(game_id), "remark": "", "manifest": manifest}
    files = [
        ("sols", (f"slot{i}.state", body, "application/octet-stream"))
        for i, body in enumerate(states)
    ]

    create = client.post("/api/games/saves", data=data, files=files)
    assert create.status_code == 201
    snapshot = create.json()["data"]
    assert [f["name"] for f in snapshot["files"]] == ["slot-0.state", "slot-1.state"]
    assert [f["local_key"] for f in snapshot["files"]] == ["emu|slot-0", "emu|slot-1"]

    detail = client.get(f"/api/games/saves/{snapshot['id']}")
    assert detail.status_code == 200
    files_detail = detail.json()["data"]["files"]
    assert [f["name"] for f in files_detail] == ["slot-0.state", "slot-1.state"]

    # 下载名保留 .state（不再强制补 .sol），字节透传一致
    for index, file_ in enumerate(files_detail):
        download = client.get(
            f"/api/games/saves/{snapshot['id']}/files/{file_['id']}/download"
        )
        assert download.status_code == 200
        assert download.content == states[index]
        disposition = download.headers.get("content-disposition") or ""
        assert "slot-%d.state" % index in disposition
        assert ".sol" not in disposition
