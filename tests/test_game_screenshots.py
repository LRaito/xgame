import pytest
from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.config import DB_SUBDIR
from backend.games import images, paths
from backend.games.models import GameScreenshot
from backend.mount_guard import SENTINEL_NAME

# 一张“长得像 PNG”的最小字节：magic 之后接任意业务字节
PNG_HEAD = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def logged_in_screenshots(client, user, do_login):
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


def _make_game(client, name="截图测试游戏", cartridge_id="SHOT1"):
    """建一个 Flash 游戏（类型由本体扩展名自动识别）。"""
    response = client.post(
        "/api/games/manage",
        data={"name": name, "description": "", "cartridge_id": cartridge_id},
        files={"file": ("demo.swf", b"swf-body", "application/x-shockwave-flash")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _png(payload: bytes = b"frame") -> bytes:
    return PNG_HEAD + payload


def _upload(
    client,
    game_id,
    *,
    data: bytes | None = None,
    description: str = "",
    filename: str = "screenshot.png",
    content_type: str = "image/png",
):
    return client.post(
        "/api/games/screenshots",
        data={"game_id": str(game_id), "description": description},
        files={"file": (filename, _png() if data is None else data, content_type)},
    )


def _move(client, screenshot_id: int, to_index: int):
    return client.post(
        f"/api/games/screenshots/{screenshot_id}/move", json={"to_index": to_index}
    )


def test_screenshot_file_path_layout():
    """截图落盘路径：image/用户名/游戏类型/卡带ID/{uuid}.{后缀}。"""
    assert (
        paths.screenshot_file_path("alice", "nes", "AB-12", "deadbeef", ".png")
        == "image/alice/nes/AB-12/deadbeef.png"
    )
    assert (
        paths.screenshot_file_path("alice", "nes", "AB-12", "deadbeef", "jpg")
        == "image/alice/nes/AB-12/deadbeef.jpg"
    )


def test_screenshots_require_login(client):
    response = client.get("/api/games/screenshots", params={"game_id": 1})
    assert response.status_code == 401
    body = response.json()
    assert body["ok"] is False
    assert "登录" in body["message"]


def test_screenshot_upload_roundtrip(logged_in_screenshots, user, storage_root):
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-1")["id"]
    data = _png(b"first-frame")

    create = _upload(client, game_id, data=data)
    assert create.status_code == 201, create.text
    item = create.json()["data"]
    assert item["sort_order"] > 0
    assert item["description"] == ""
    assert item["size"] == len(data)

    # 落盘路径按 用户名/游戏类型/卡带ID 分目录，内容与上传一致
    prefix = f"image/{user.username}/flash/SHOT-1/"
    saved = sorted(k for k in _files(storage_root) if k.startswith(prefix))
    assert len(saved) == 1
    assert saved[0].endswith(".png")
    assert (storage_root / saved[0]).read_bytes() == data

    listing = client.get("/api/games/screenshots", params={"game_id": game_id})
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()["data"]] == [item["id"]]

    # 图片接口 inline 返回本体（不传 filename → 没有 Content-Disposition）
    image = client.get(f"/api/games/screenshots/{item['id']}/image")
    assert image.status_code == 200
    assert image.content == data
    assert image.headers["content-type"] == "image/png"
    assert "content-disposition" not in image.headers


def test_screenshot_accepts_common_image_formats(
    logged_in_screenshots, storage_root
):
    """图库里手动上传的图：格式按内容 magic 认，后缀也由内容定（不看文件名）。"""
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-8")["id"]
    cases = [
        ("a.jpg", b"\xff\xd8\xff\xe0jpeg-body", ".jpg", "image/jpeg"),
        ("b.gif", b"GIF89agif-body", ".gif", "image/gif"),
        ("c.webp", b"RIFF\x00\x00\x00\x00WEBPwebp-body", ".webp", "image/webp"),
        # 文件名说是 png，内容其实是 gif：以内容为准
        ("d.png", b"GIF89agif-body", ".gif", "image/gif"),
    ]
    for filename, data, extension, mime in cases:
        created = _upload(
            client, game_id, data=data, filename=filename, content_type="application/octet-stream"
        )
        assert created.status_code == 201, created.text
        item = created.json()["data"]
        stored = [key for key in _files(storage_root) if key.endswith(extension)]
        assert stored, f"{filename} 没按内容落成 {extension}"
        image = client.get(f"/api/games/screenshots/{item['id']}/image")
        assert image.content == data
        assert image.headers["content-type"] == mime


def test_screenshot_unknown_game(logged_in_screenshots):
    response = _upload(logged_in_screenshots, 99999)
    assert response.status_code == 404
    assert "游戏不存在" in response.json()["message"]


def test_screenshot_upload_validation(logged_in_screenshots, monkeypatch):
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-2")["id"]

    # 空文件
    empty = _upload(client, game_id, data=b"")
    assert empty.status_code == 400
    assert "空" in empty.json()["message"]

    # 内容认不出是什么图片（magic 不符）——文件名与 content-type 都不作数
    unknown = _upload(
        client, game_id, data=b"not-an-image", filename="shot.png", content_type="image/png"
    )
    assert unknown.status_code == 400
    assert "只支持" in unknown.json()["message"]

    # 描述超 15 字
    long_desc = _upload(client, game_id, description="超" * 16)
    assert long_desc.status_code == 400
    assert "15" in long_desc.json()["message"]

    # 超过单张上限（把上限调小，免得测试里真造 16MB 字节）
    monkeypatch.setattr(images, "IMAGE_MAX_SIZE", 4)
    too_big = _upload(client, game_id, data=_png(b"12345"))
    assert too_big.status_code == 400
    assert "过大" in too_big.json()["message"]


def test_screenshot_description_roundtrip(logged_in_screenshots):
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-3")["id"]

    create = _upload(client, game_id, description="  开局  ")
    assert create.status_code == 201
    item = create.json()["data"]
    assert item["description"] == "开局"  # 首尾空白去掉

    update = client.put(
        f"/api/games/screenshots/{item['id']}", json={"description": "  BOSS 战  "}
    )
    assert update.status_code == 200
    assert update.json()["data"]["description"] == "BOSS 战"

    too_long = client.put(
        f"/api/games/screenshots/{item['id']}", json={"description": "超" * 16}
    )
    assert too_long.status_code == 400
    assert "15" in too_long.json()["message"]


def test_screenshot_move_and_delete(logged_in_screenshots, storage_root):
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-4")["id"]
    ids = [_upload(client, game_id).json()["data"]["id"] for _ in range(3)]

    def listed():
        rows = client.get(
            "/api/games/screenshots", params={"game_id": game_id}
        ).json()["data"]
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

    # 删除：行与文件一起消失，剩下的顺序不变（分数排序不需要重排）
    assert client.delete(f"/api/games/screenshots/{ids[0]}").status_code == 200
    assert listed()[0] == [ids[1], ids[2]]
    remaining = [k for k in _files(storage_root) if k.startswith("image/")]
    assert len(remaining) == 2


def test_screenshot_move_renumbers_when_gap_runs_out(logged_in_screenshots, app):
    """反复往同一处插：分数间隙切没了以后由后端整份重排，顺序始终正确。"""
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-7")["id"]
    ids = [_upload(client, game_id).json()["data"]["id"] for _ in range(3)]

    expected = list(ids)
    for _ in range(40):
        # 轮流把末尾那张拖到中间（下标 1）：来回切，每次都往同一条缝里挤
        tail = expected[-1]
        tail_index = expected.index(tail)
        assert _move(client, tail, 1).status_code == 200
        expected.pop(tail_index)
        expected.insert(1, tail)

        rows = client.get(
            "/api/games/screenshots", params={"game_id": game_id}
        ).json()["data"]
        assert [row["id"] for row in rows] == expected
        scores = [row["sort_order"] for row in rows]
        assert scores == sorted(scores)
        assert len(set(scores)) == len(scores)  # 分数互不相同 → 顺序稳定


def test_screenshots_are_isolated_per_user(logged_in_screenshots, app):
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-5")["id"]
    item = _upload(client, game_id, description="alice 的图").json()["data"]

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    client.post("/api/logout")
    assert (
        client.post(
            "/api/login", json={"username": "bobby", "password": "secret123"}
        ).status_code
        == 200
    )

    # bobby 看不到、也动不了 alice 的截图
    listing = client.get("/api/games/screenshots", params={"game_id": game_id})
    assert listing.status_code == 200
    assert listing.json()["data"] == []
    assert client.get(f"/api/games/screenshots/{item['id']}/image").status_code == 404
    assert (
        client.put(
            f"/api/games/screenshots/{item['id']}", json={"description": "劫持"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/games/screenshots/{item['id']}/move", json={"direction": "up"}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/games/screenshots/{item['id']}").status_code == 404


def test_delete_game_clears_screenshots(logged_in_screenshots, app, storage_root):
    client = logged_in_screenshots
    game_id = _make_game(client, cartridge_id="SHOT-6")["id"]
    ids = [_upload(client, game_id).json()["data"]["id"] for _ in range(2)]

    assert client.delete(f"/api/games/manage/{game_id}").status_code == 200

    # 截图行与磁盘文件都随游戏一起清掉，不留够不着的孤儿目录
    assert not [k for k in _files(storage_root) if k.startswith("image/")]
    with Session(app.state.engine) as session:
        rows = session.exec(
            select(GameScreenshot).where(GameScreenshot.id.in_(ids))
        ).all()
        assert rows == []
