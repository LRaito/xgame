import pytest
from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.config import DB_SUBDIR
from backend.games import paths
from backend.games.models import Game, GameGalleryImage
from backend.mount_guard import SENTINEL_NAME

# 一张“长得像 PNG”的最小字节：magic 之后接任意业务字节
PNG_HEAD = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def logged_in_gallery(client, user, do_login):
    do_login(client)
    return client


def _files(storage_root) -> set[str]:
    from pathlib import Path

    root = Path(storage_root)
    if not root.exists():
        return set()
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
        and p.name != SENTINEL_NAME
        and p.relative_to(root).parts[0] != DB_SUBDIR
    }


def _make_game(
    client,
    name="图集测试游戏",
    cartridge_id="GAL1",
    filename="demo.swf",
    body=b"swf-body",
):
    """建一个游戏（类型由本体扩展名自动识别）。"""
    response = client.post(
        "/api/games/manage",
        data={"name": name, "description": "", "cartridge_id": cartridge_id},
        files={"file": (filename, body, "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _unlock_body(app, game_id: int) -> None:
    """清掉本体 CRC32 锁，让换本体/换类型这条路可用。"""
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        row.crc32 = ""
        session.add(row)
        session.commit()


def _png(payload: bytes = b"frame") -> bytes:
    return PNG_HEAD + payload


def _upload(
    client,
    game_id,
    *,
    data: bytes | None = None,
    description: str = "",
    filename: str = "gallery.png",
    content_type: str = "image/png",
):
    return client.post(
        "/api/games/gallery",
        data={"game_id": str(game_id), "description": description},
        files={"file": (filename, _png() if data is None else data, content_type)},
    )


def _move(client, image_id: int, to_index: int):
    return client.post(
        f"/api/games/gallery/{image_id}/move", json={"to_index": to_index}
    )


def test_gallery_file_path_layout():
    """图集落盘路径：game/游戏类型/卡带ID/image/{uuid}.{后缀}（没有用户名那一层）。"""
    assert (
        paths.gallery_file_path("nes", "AB-12", "deadbeef", ".png")
        == "game/nes/AB-12/image/deadbeef.png"
    )
    assert paths.gallery_dir("nes", "AB-12") == "game/nes/AB-12/image"


def test_gallery_requires_login(client):
    response = client.get("/api/games/gallery", params={"game_id": 1})
    assert response.status_code == 401
    body = response.json()
    assert body["ok"] is False
    assert "登录" in body["message"]


def test_gallery_upload_roundtrip(logged_in_gallery, storage_root):
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-1")["id"]
    data = _png(b"first-image")

    create = _upload(client, game_id, data=data)
    assert create.status_code == 201, create.text
    item = create.json()["data"]
    assert item["sort_order"] > 0
    assert item["description"] == ""
    assert item["size"] == len(data)
    # 磁盘路径是内部实现细节，不下发给前端
    assert "file_path" not in item

    # 落在游戏目录里（不是顶层 image/），且没有用户名那一层
    prefix = "game/flash/GAL-1/image/"
    saved = sorted(k for k in _files(storage_root) if k.startswith(prefix))
    assert len(saved) == 1
    assert saved[0].endswith(".png")
    assert (storage_root / saved[0]).read_bytes() == data

    listing = client.get("/api/games/gallery", params={"game_id": game_id})
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()["data"]] == [item["id"]]

    # 图片接口 inline 返回本体（不传 filename → 没有 Content-Disposition）
    image = client.get(f"/api/games/gallery/{item['id']}/image")
    assert image.status_code == 200
    assert image.content == data
    assert image.headers["content-type"] == "image/png"
    assert "content-disposition" not in image.headers


def test_gallery_accepts_common_image_formats(logged_in_gallery, storage_root):
    """格式按内容 magic 认，后缀也由内容定（不看文件名）。"""
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-8")["id"]
    cases = [
        ("a.jpg", b"\xff\xd8\xff\xe0jpeg-body", ".jpg", "image/jpeg"),
        ("b.gif", b"GIF89agif-body", ".gif", "image/gif"),
        ("c.webp", b"RIFF\x00\x00\x00\x00WEBPwebp-body", ".webp", "image/webp"),
        # 文件名说是 png，内容其实是 gif：以内容为准
        ("d.png", b"GIF89agif-body", ".gif", "image/gif"),
    ]
    for filename, data, extension, mime in cases:
        created = _upload(
            client,
            game_id,
            data=data,
            filename=filename,
            content_type="application/octet-stream",
        )
        assert created.status_code == 201, created.text
        item = created.json()["data"]
        stored = [key for key in _files(storage_root) if key.endswith(extension)]
        assert stored, f"{filename} 没按内容落成 {extension}"
        image = client.get(f"/api/games/gallery/{item['id']}/image")
        assert image.content == data
        assert image.headers["content-type"] == mime


def test_gallery_unknown_game(logged_in_gallery):
    response = _upload(logged_in_gallery, 99999)
    assert response.status_code == 404
    assert "游戏不存在" in response.json()["message"]


def test_gallery_upload_validation(logged_in_gallery, monkeypatch):
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-2")["id"]

    # 空文件
    empty = _upload(client, game_id, data=b"")
    assert empty.status_code == 400
    assert "空" in empty.json()["message"]

    # 内容认不出是什么图片（magic 不符）——文件名与 content-type 都不作数
    unknown = _upload(
        client, game_id, data=b"not-an-image", filename="pic.png", content_type="image/png"
    )
    assert unknown.status_code == 400
    assert "只支持" in unknown.json()["message"]

    # 描述超 15 字
    long_desc = _upload(client, game_id, description="超" * 16)
    assert long_desc.status_code == 400
    assert "15" in long_desc.json()["message"]

    # 超过单张上限（把上限调小，免得测试里真造 16MB 字节）
    from backend.games import images

    monkeypatch.setattr(images, "IMAGE_MAX_SIZE", 4)
    too_big = _upload(client, game_id, data=_png(b"12345"))
    assert too_big.status_code == 400
    assert "过大" in too_big.json()["message"]


def test_gallery_description_roundtrip(logged_in_gallery):
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-3")["id"]

    create = _upload(client, game_id, description="  封面  ")
    assert create.status_code == 201
    item = create.json()["data"]
    assert item["description"] == "封面"  # 首尾空白去掉

    update = client.put(
        f"/api/games/gallery/{item['id']}", json={"description": "  说明书  "}
    )
    assert update.status_code == 200
    assert update.json()["data"]["description"] == "说明书"

    too_long = client.put(
        f"/api/games/gallery/{item['id']}", json={"description": "超" * 16}
    )
    assert too_long.status_code == 400
    assert "15" in too_long.json()["message"]


def test_gallery_move_and_delete(logged_in_gallery, storage_root):
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-4")["id"]
    ids = [_upload(client, game_id).json()["data"]["id"] for _ in range(3)]

    def listed():
        rows = client.get("/api/games/gallery", params={"game_id": game_id}).json()[
            "data"
        ]
        return [row["id"] for row in rows], [row["sort_order"] for row in rows]

    order, scores = listed()
    assert order == ids
    assert scores == sorted(scores)  # 追加到末尾：分数递增

    # 把第 3 张拖到最前（下标 0）
    moved = _move(client, ids[2], 0)
    assert moved.status_code == 200
    assert [row["id"] for row in moved.json()["data"]] == [ids[2], ids[0], ids[1]]

    # 「单条更新」：一次拖动只改被拖那一行的分数（上下邻居的分数原样不动）
    before = dict(zip(*listed()))
    assert _move(client, ids[2], 2).status_code == 200
    after = dict(zip(*listed()))
    changed = [key for key in after if after[key] != before[key]]
    assert changed == [ids[2]]

    # 拖到原位＝不动；越界的位置拒绝
    assert _move(client, ids[2], 2).status_code == 200
    assert _move(client, ids[0], 3).status_code == 400
    assert _move(client, ids[0], -1).status_code == 400

    # 删除：行与文件一起消失，剩下的顺序不变
    assert client.delete(f"/api/games/gallery/{ids[0]}").status_code == 200
    assert listed()[0] == [ids[1], ids[2]]
    remaining = [k for k in _files(storage_root) if "/image/" in k]
    assert len(remaining) == 2


def test_gallery_move_renumbers_when_gap_runs_out(logged_in_gallery):
    """反复往同一处插：分数间隙切没了以后由后端整份重排，顺序始终正确。"""
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-7")["id"]
    ids = [_upload(client, game_id).json()["data"]["id"] for _ in range(3)]

    expected = list(ids)
    for _ in range(40):
        tail = expected[-1]
        tail_index = expected.index(tail)
        assert _move(client, tail, 1).status_code == 200
        expected.pop(tail_index)
        expected.insert(1, tail)

        rows = client.get("/api/games/gallery", params={"game_id": game_id}).json()[
            "data"
        ]
        assert [row["id"] for row in rows] == expected
        scores = [row["sort_order"] for row in rows]
        assert scores == sorted(scores)
        assert len(set(scores)) == len(scores)  # 分数互不相同 → 顺序稳定


def test_gallery_is_shared_across_users(logged_in_gallery, app, storage_root):
    """图集按游戏共享：换个账号照样看得见、也改得动（与截图的按账号隔离相反）。"""
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-5")["id"]
    item = _upload(client, game_id, description="alice 传的图").json()["data"]

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    client.post("/api/logout")
    assert (
        client.post(
            "/api/login", json={"username": "bobby", "password": "secret123"}
        ).status_code
        == 200
    )

    # bobby 看得见这张图，也能取图、改描述、拖动、删除
    listing = client.get("/api/games/gallery", params={"game_id": game_id})
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()["data"]] == [item["id"]]
    assert client.get(f"/api/games/gallery/{item['id']}/image").status_code == 200
    updated = client.put(
        f"/api/games/gallery/{item['id']}", json={"description": "bobby 改的"}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["description"] == "bobby 改的"
    assert client.delete(f"/api/games/gallery/{item['id']}").status_code == 200
    assert [k for k in _files(storage_root) if "/image/" in k] == []


def test_type_switch_migrates_gallery(logged_in_gallery, app, storage_root):
    """换本体换类型：图集跟着目录搬到新类型目录，行里的路径一并更新。"""
    client = logged_in_gallery
    game = _make_game(
        client, name="带图集换类型", cartridge_id="GAL-9", filename="a.nes", body=b"nes-body"
    )
    game_id = game["id"]
    assert game["game_type"] == "nes"
    created = [_upload(client, game_id, description=f"图{i}") for i in range(2)]
    ids = [row.json()["data"]["id"] for row in created]
    assert all(row.status_code == 201 for row in created)
    assert len([k for k in _files(storage_root) if k.startswith("game/nes/GAL-9/image/")]) == 2

    _unlock_body(app, game_id)
    switched = client.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("a.gba", b"gba-body", "application/octet-stream")},
    )
    assert switched.status_code == 201, switched.text
    assert switched.json()["data"]["game_type"] == "gba"

    # 图片整目录搬到了新类型目录，旧类型目录整个没了
    moved = sorted(k for k in _files(storage_root) if "/image/" in k)
    assert len(moved) == 2
    assert all(k.startswith("game/gba/GAL-9/image/") for k in moved)
    assert not (storage_root / "game" / "nes" / "GAL-9").exists()

    # 行里的路径跟着换，取图照旧 200、顺序与内容都不变
    with Session(app.state.engine) as session:
        rows = session.exec(
            select(GameGalleryImage).where(GameGalleryImage.game_id == game_id)
        ).all()
        assert all(row.file_path.startswith("game/gba/GAL-9/image/") for row in rows)
    listing = client.get("/api/games/gallery", params={"game_id": game_id})
    assert [row["id"] for row in listing.json()["data"]] == ids
    image = client.get(f"/api/games/gallery/{ids[0]}/image")
    assert image.status_code == 200
    assert image.content == _png()


def test_delete_game_clears_gallery(logged_in_gallery, app, storage_root):
    client = logged_in_gallery
    game_id = _make_game(client, cartridge_id="GAL-6")["id"]
    ids = [_upload(client, game_id).json()["data"]["id"] for _ in range(2)]

    assert client.delete(f"/api/games/manage/{game_id}").status_code == 200

    # 图集行与磁盘文件都随游戏一起清掉，不留够不着的孤儿目录
    assert [k for k in _files(storage_root) if "/image/" in k] == []
    with Session(app.state.engine) as session:
        rows = session.exec(
            select(GameGalleryImage).where(GameGalleryImage.id.in_(ids))
        ).all()
        assert rows == []
