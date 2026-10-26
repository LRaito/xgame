import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.games import paths
from backend.games.models import GameCloudSnapshot, GameCloudSnapshotFile
from backend.config import DB_SUBDIR


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
        # db/ 里是备份与检索索引，不属于游戏素材
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


def _create_snapshot(client, game_id: int, remark="备注"):
    data, files = _upload_form(game_id, [_sol_data(b"snapshot")], remark=remark)
    response = client.post("/api/games/saves", data=data, files=files)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _list_snapshots(client, game_id: int) -> list[dict]:
    response = client.get("/api/games/saves", params={"game_id": game_id})
    assert response.status_code == 200, response.text
    return response.json()["data"]


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


def test_cloud_snapshot_default_parent_is_null(logged_in_saves):
    """新增存档默认没有父节点：创建返回、列表、详情三处都是 null。"""
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-1")["id"]
    snapshot = _create_snapshot(client, game_id)

    assert snapshot["parent_id"] is None
    assert _list_snapshots(client, game_id)[0]["parent_id"] is None
    detail = client.get(f"/api/games/saves/{snapshot['id']}")
    assert detail.json()["data"]["parent_id"] is None


def test_cloud_snapshot_set_and_clear_parent(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-2")["id"]
    parent = _create_snapshot(client, game_id, remark="主干")
    child = _create_snapshot(client, game_id, remark="分支")

    response = client.put(
        f"/api/games/saves/{child['id']}/parent", json={"parent_id": parent["id"]}
    )
    assert response.status_code == 200
    assert response.json()["data"]["parent_id"] == parent["id"]

    listed = {item["id"]: item for item in _list_snapshots(client, game_id)}
    assert listed[child["id"]]["parent_id"] == parent["id"]
    with Session(client.app.state.engine) as session:
        assert session.get(GameCloudSnapshot, child["id"]).parent_id == parent["id"]

    # null = 设为顶层
    cleared = client.put(
        f"/api/games/saves/{child['id']}/parent", json={"parent_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["parent_id"] is None
    with Session(client.app.state.engine) as session:
        assert session.get(GameCloudSnapshot, child["id"]).parent_id is None


def test_cloud_snapshot_parent_self_rejected(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-3")["id"]
    snapshot = _create_snapshot(client, game_id)

    response = client.put(
        f"/api/games/saves/{snapshot['id']}/parent",
        json={"parent_id": snapshot["id"]},
    )
    assert response.status_code == 400
    assert "自己" in response.json()["message"]
    with Session(client.app.state.engine) as session:
        assert session.get(GameCloudSnapshot, snapshot["id"]).parent_id is None


def test_cloud_snapshot_parent_cross_game_rejected(logged_in_saves):
    client = logged_in_saves
    game_a = _make_game(client, "游戏 A", cartridge_id="TREE-4A")["id"]
    game_b = _make_game(client, "游戏 B", cartridge_id="TREE-4B")["id"]
    snapshot_a = _create_snapshot(client, game_a)
    snapshot_b = _create_snapshot(client, game_b)

    response = client.put(
        f"/api/games/saves/{snapshot_a['id']}/parent",
        json={"parent_id": snapshot_b["id"]},
    )
    assert response.status_code == 400
    assert "同一游戏" in response.json()["message"]
    with Session(client.app.state.engine) as session:
        assert session.get(GameCloudSnapshot, snapshot_a["id"]).parent_id is None


def test_cloud_snapshot_parent_cycle_rejected(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-5")["id"]
    a = _create_snapshot(client, game_id, remark="A")
    b = _create_snapshot(client, game_id, remark="B")
    c = _create_snapshot(client, game_id, remark="C")

    for child, parent in ((b, a), (c, b)):
        response = client.put(
            f"/api/games/saves/{child['id']}/parent",
            json={"parent_id": parent["id"]},
        )
        assert response.status_code == 200, response.text

    # A → C 会让 A→B→C→A 成环
    response = client.put(
        f"/api/games/saves/{a['id']}/parent", json={"parent_id": c["id"]}
    )
    assert response.status_code == 400
    assert "循环" in response.json()["message"]
    with Session(client.app.state.engine) as session:
        assert session.get(GameCloudSnapshot, a["id"]).parent_id is None


def test_cloud_snapshot_parent_user_isolation(logged_in_saves, app):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-6")["id"]
    alice_snapshot = _create_snapshot(client, game_id)

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    client.post("/api/logout")
    login = client.post(
        "/api/login", json={"username": "bobby", "password": "secret123"}
    )
    assert login.status_code == 200, login.text
    bobby_snapshot = _create_snapshot(client, game_id)

    # 改别人的快照 → 404
    response = client.put(
        f"/api/games/saves/{alice_snapshot['id']}/parent",
        json={"parent_id": bobby_snapshot["id"]},
    )
    assert response.status_code == 404
    # 把父级指向别人的快照 → 404（不暴露存在性）
    response = client.put(
        f"/api/games/saves/{bobby_snapshot['id']}/parent",
        json={"parent_id": alice_snapshot["id"]},
    )
    assert response.status_code == 404
    # 列表仍只看到自己的
    assert [item["id"] for item in _list_snapshots(client, game_id)] == [
        bobby_snapshot["id"]
    ]


def test_cloud_snapshot_parent_missing_rejected(logged_in_saves):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-7")["id"]
    snapshot = _create_snapshot(client, game_id)

    response = client.put(
        f"/api/games/saves/{snapshot['id']}/parent", json={"parent_id": 999999}
    )
    assert response.status_code == 404
    assert "不存在" in response.json()["message"]


def test_cloud_snapshot_delete_reparents_children(logged_in_saves, storage_root):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-8")["id"]
    parent = _create_snapshot(client, game_id, remark="父")
    child = _create_snapshot(client, game_id, remark="子")
    other_child = _create_snapshot(client, game_id, remark="另一个子")
    grandchild = _create_snapshot(client, game_id, remark="孙")

    for target, parent_id in (
        (child, parent["id"]),
        (other_child, parent["id"]),
        (grandchild, child["id"]),
    ):
        response = client.put(
            f"/api/games/saves/{target['id']}/parent", json={"parent_id": parent_id}
        )
        assert response.status_code == 200, response.text

    assert client.delete(f"/api/games/saves/{parent['id']}").status_code == 200

    with Session(client.app.state.engine) as session:
        assert session.get(GameCloudSnapshot, parent["id"]) is None
        # 直接子级变顶层，孙级仍挂在原来的父级下
        assert session.get(GameCloudSnapshot, child["id"]).parent_id is None
        assert session.get(GameCloudSnapshot, other_child["id"]).parent_id is None
        assert session.get(GameCloudSnapshot, grandchild["id"]).parent_id == child["id"]
        # 子级文件仍在
        assert session.get(GameCloudSnapshotFile, child["files"][0]["id"]) is not None

    download = client.get(
        f"/api/games/saves/{child['id']}/files/{child['files'][0]['id']}/download"
    )
    assert download.status_code == 200
    assert download.content == _sol_data(b"snapshot")


def test_cloud_snapshot_list_tiebreak_id_desc(logged_in_saves):
    """同一创建时间也按 id 倒序，树里的兄弟顺序稳定。"""
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-9")["id"]
    first = _create_snapshot(client, game_id)
    second = _create_snapshot(client, game_id)

    with Session(client.app.state.engine) as session:
        rows = session.exec(
            select(GameCloudSnapshot).where(GameCloudSnapshot.game_id == game_id)
        ).all()
        fixed = rows[0].created_at
        for row in rows:
            row.created_at = fixed
            session.add(row)
        session.commit()

    ids = [item["id"] for item in _list_snapshots(client, game_id)]
    assert ids == sorted([first["id"], second["id"]], reverse=True)


def test_delete_game_removes_snapshot_tree(logged_in_saves, app):
    client = logged_in_saves
    game_id = _make_game(client, cartridge_id="TREE-10")["id"]
    parent = _create_snapshot(client, game_id)
    child = _create_snapshot(client, game_id)
    client.put(
        f"/api/games/saves/{child['id']}/parent", json={"parent_id": parent["id"]}
    )

    assert client.delete(f"/api/games/manage/{game_id}").status_code == 200
    with Session(app.state.engine) as session:
        rows = session.exec(
            select(GameCloudSnapshot).where(GameCloudSnapshot.game_id == game_id)
        ).all()
        assert rows == []
