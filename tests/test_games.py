import zlib
import html
import io
import itertools
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, select

from backend.auth.service import AuthService
from backend.errors import StorageError, ValidationError
from backend.config import DB_SUBDIR
from backend.games import importer, paths
from backend.games import archive as games_archive
from backend.games.models import (
    Game,
    GameCloudSnapshot,
    GameCloudSnapshotFile,
    GameGalleryImage,
    GameScreenshot,
)
from backend.games.service import (
    GAME_TYPES,
    GameItem,
    GameService,
    GameUpload,
    detect_game_type,
    normalize_cartridge_id,
    play_path,
    sanitize_game_name,
    validate_cartridge_id,
    validate_game_name,
)

_cartridge_seq = itertools.count(1)


def _next_cartridge_id() -> str:
    """自动补一个合法且互不重复的卡带ID（卡带ID 必填，免得每条用例都写一遍）。"""
    return f"CART{next(_cartridge_seq):04d}"


@pytest.fixture
def game_service(app):
    with Session(app.state.engine) as session:
        yield GameService(session, app.state.storage, app.state.runtime_storage)


@pytest.fixture
def logged_in_games(client, user, do_login):
    do_login(client)
    return client


def _files(storage_root) -> set[str]:
    """磁盘上现有的全部文件（相对路径），用来断言「有没有留下垃圾」。"""
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


def _read(storage_root, rel: str) -> bytes:
    return (Path(storage_root) / rel).read_bytes()


def _exists(storage_root, rel: str) -> bool:
    return (Path(storage_root) / rel).is_file()


def _cartridge_of(app, game_id: int) -> str:
    with Session(app.state.engine) as session:
        return session.get(Game, game_id).cartridge_id


def _stream(data: bytes):
    return io.BytesIO(data)


def _upload(filename: str, data: bytes = b"body", mime: str | None = None) -> GameUpload:
    """构造一次上传输入（service 层直接调用用）。"""
    return GameUpload(filename=filename, stream=_stream(data), size=len(data), mime=mime)


def _create_game(
    client,
    name: str,
    filename: str,
    body: bytes = b"body",
    mime: str = "application/octet-stream",
    cover: tuple[str, bytes, str] | None = None,
    cartridge_id: str | None = None,
    description: str = "",
    cover_type: str | None = None,
):
    """按新流程建游戏：一次请求提交名称/卡带ID/描述/本体（可选封面），类型由后端识别。

    `cover_type` 只是给「新建不接受这个字段」的用例硬塞用的，正常调用别传。
    """
    files = {"file": (filename, body, mime)}
    if cover is not None:
        files["cover"] = cover
    data = {
        "name": name,
        "cartridge_id": cartridge_id or _next_cartridge_id(),
        "description": description,
    }
    if cover_type is not None:
        data["cover_type"] = cover_type
    return client.post("/api/games/manage", data=data, files=files)


def test_detect_game_type_by_extension():
    """类型只由本体扩展名判定；未收录的格式直接拒绝。"""
    assert detect_game_type("demo.swf") == "flash"
    assert detect_game_type("demo.ZIP") == "h5"
    assert detect_game_type("demo.nes") == "nes"
    assert detect_game_type("demo.sfc") == "snes"
    assert detect_game_type("demo.smc") == "snes"
    assert detect_game_type("demo.gb") == "gb"
    assert detect_game_type("demo.gbc") == "gb"
    assert detect_game_type("demo.gba") == "gba"
    assert detect_game_type("demo.md") == "segaMD"
    assert detect_game_type("demo.gen") == "segaMD"
    assert detect_game_type("demo.gg") == "segaGG"
    assert detect_game_type("demo.sms") == "segaMS"
    with pytest.raises(Exception):
        detect_game_type("demo.txt")
    with pytest.raises(Exception):
        detect_game_type("demo")


def test_games_list_requires_login(client):
    """未登录不能查看游戏中心列表。"""
    assert client.get("/api/games").status_code == 401


def test_logout_revokes_game_access(client, user, do_login):
    """端到端：登录后建游戏，登出即失去一切游戏接口（含列表/状态/封面/本体）。"""
    do_login(client)

    create = _create_game(
        client,
        "Guest demo",
        "g.swf",
        b"swf-body",
        "application/x-shockwave-flash",
        cover=("c.png", b"png-body", "image/png"),
    )
    assert create.status_code == 201
    assert create.json()["data"]["game_type"] == "flash"
    game_id = create.json()["data"]["id"]

    assert client.post("/api/logout").status_code == 200

    assert client.get("/api/games/status").status_code == 401
    assert client.get("/api/games").status_code == 401
    assert client.get(f"/api/games/{game_id}/play").status_code == 401
    assert client.get(f"/api/games/{game_id}/cover").status_code == 401

    # 管理入口与云端存档同样需要登录
    assert client.get(f"/api/games/manage/{game_id}").status_code == 401
    assert client.get("/api/games/manage").status_code == 401
    assert _create_game(client, "x", "g.swf", b"1").status_code == 401
    assert (
        client.get("/api/games/saves", params={"game_id": game_id}).status_code == 401
    )


def test_tools_requires_login(client, user, do_login):
    """工具注册表需登录；登录后返回全部工具卡片。"""
    assert client.get("/api/tools").status_code == 401

    do_login(client)
    response = client.get("/api/tools")
    assert response.status_code == 200
    tools = response.json()["data"]
    assert [item["id"] for item in tools] == ["games", "games-manage", "games-discover"]


def test_games_status(logged_in):
    response = logged_in.get("/api/games/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["game_types"] == list(GAME_TYPES)


def test_games_list_empty(logged_in):
    response = logged_in.get("/api/games")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"] == []


def test_games_list_orders(game_service):
    """游戏中心按名称升序；管理页按更新时间倒序（最近动过的排最前）。"""
    # 故意打乱插入顺序；中心列表只收已传本体的游戏
    for name in ("delta", "bravo", "charlie"):
        game_service.create(
            name, "", _upload("g.swf", b"swf"), cartridge_id=_next_cartridge_id()
        )

    center = [g.name for g in game_service.list_center()]
    manage = [g.name for g in game_service.list_manage().items]
    assert center == ["bravo", "charlie", "delta"]
    # 后建的排最前；同一微秒内建成时按 id 兜底，结果一致
    assert manage == ["charlie", "bravo", "delta"]


def test_asset_paths_follow_cartridge_id():
    """素材路径：游戏类型 / 卡带ID 分目录，文件名固定为 game、cover。"""
    assert paths.body_path("nes", "AB-12", ".nes") == "game/nes/AB-12/game.nes"
    assert paths.cover_path("nes", "AB-12", "png") == "game/nes/AB-12/cover.png"
    assert (
        paths.h5_asset_path("h5", "AB-12", "assets/app.js")
        == "game/h5/AB-12/h5/assets/app.js"
    )
    assert (
        paths.save_file_path("alice", "nes", "AB-12", "deadbeef")
        == "save/alice/nes/AB-12/deadbeef.state"
    )


def test_game_crud_flow(game_service, storage_root):
    item = game_service.create(
        "测试游戏", "描述", _upload("任意文件名.swf", b"swf!"), cartridge_id="AB-12"
    )
    assert item.id is not None
    assert item.cartridge_id == "AB-12"
    assert item.game_type == "flash"
    assert item.path == f"/games/flash/{item.id}"
    assert item.game_path == "game/flash/AB-12/game.swf"
    assert item.size == 4
    assert _read(storage_root, "game/flash/AB-12/game.swf") == b"swf!"

    updated = game_service.upload_asset(
        item.id, kind="game", upload=_upload("再次上传.swf", b"swf!")
    )
    assert updated.game_path == "game/flash/AB-12/game.swf"

    with_cover = game_service.upload_asset(
        item.id, kind="cover", upload=_upload("cover.jpg", b"jpg", "image/jpeg")
    )
    assert with_cover.cover_path == "game/flash/AB-12/cover.jpg"

    center = game_service.list_center()
    assert len(center) == 1
    found = game_service.list_manage(keyword="测试").items
    assert len(found) == 1

    stream = game_service.open_asset(updated.game_path)
    try:
        assert stream.read() == b"swf!"
    finally:
        stream.close()

    game_service.delete(item.id)
    assert _files(storage_root) == set()


def test_replace_deletes_old_storage_objects(game_service, storage_root):
    first = game_service.create(
        "旧名", "描述", _upload("a.swf", b"old-swf"), cartridge_id="OLD-1"
    )
    assert first.game_path == "game/flash/OLD-1/game.swf"

    # 本体路径固定为 game.swf；再次上传覆盖同一文件，不再产生旧路径
    game_service.update(first.id, name="新名")
    second = game_service.upload_asset(
        first.id, kind="game", upload=_upload("b.swf", b"new-swf")
    )
    assert second.game_path == first.game_path
    assert _read(storage_root, "game/flash/OLD-1/game.swf") == b"new-swf"

    cover1 = game_service.upload_asset(
        first.id, kind="cover", upload=_upload("c.jpg", b"jpg")
    )
    game_service.upload_asset(first.id, kind="cover", upload=_upload("d.png", b"png"))
    assert cover1.cover_path is not None and not _exists(storage_root, cover1.cover_path)

    game_service.update(first.id, clear_cover=True)
    assert _exists(storage_root, "game/flash/OLD-1/game.swf")


def test_manage_api_flow(logged_in_games):
    create = _create_game(
        logged_in_games,
        "Flash _demo",
        "Flash_demo.swf",
        b"swf!!",
        "application/x-shockwave-flash",
    )
    assert create.status_code == 201
    assert create.json()["data"]["game_path"] != ""
    game_id = create.json()["data"]["id"]
    cartridge_id = create.json()["data"]["cartridge_id"]
    assert create.json()["data"]["game_path"] == f"game/flash/{cartridge_id}/game.swf"

    cover = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "cover"},
        files={"file": ("cover.png", b"png!", "image/png")},
    )
    assert cover.status_code == 201

    listing = logged_in_games.get("/api/games")
    assert listing.status_code == 200
    games = listing.json()["data"]
    assert len(games) == 1
    assert games[0]["category"] == "flash"
    assert games[0]["path"] == f"/games/flash/{game_id}"

    play = logged_in_games.get(f"/api/games/{game_id}/play")
    assert play.status_code == 200
    assert play.content == b"swf!!"
    assert play.headers.get("content-type") == "application/x-shockwave-flash"

    cover_download = logged_in_games.get(f"/api/games/{game_id}/cover")
    assert cover_download.status_code == 200
    assert cover_download.content == b"png!"

    delete = logged_in_games.delete(f"/api/games/manage/{game_id}")
    assert delete.status_code == 200

    with Session(logged_in_games.app.state.engine) as session:
        assert session.get(Game, game_id) is None


def test_manage_api_rejects_unknown_body_format(logged_in_games, storage_root):
    """本体扩展名不在白名单内：整个创建请求 400，且不留下条目与对象。"""
    response = _create_game(logged_in_games, "X", "a.txt", b"1", "text/plain")
    assert response.status_code == 400
    message = response.json()["message"]
    assert ".swf" in message.lower() and ".nes" in message
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []
    assert _files(storage_root) == set()


def test_create_rolls_back_when_cover_invalid(logged_in_games, storage_root):
    """封面校验失败：整体回滚，条目与已上传的本体对象都不留。"""
    response = _create_game(
        logged_in_games,
        "X",
        "a.swf",
        b"swf-body",
        cover=("cover.txt", b"not-image", "text/plain"),
    )
    assert response.status_code == 400
    assert "封面" in response.json()["message"]
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []
    assert _files(storage_root) == set()


def test_delete_game_removes_cloud_saves(logged_in_games, storage_root):
    """删游戏连带清掉云端存档：快照行、存档文件、以及存档目录都不留。"""
    created = _create_game(
        logged_in_games, "带存档删除", "a.nes", b"nes-body", cartridge_id="DEL-1"
    ).json()["data"]
    game_id = created["id"]

    manifest = json.dumps(
        [{"local_key": "x_emusave:%d:state1" % game_id, "name": "save.state"}]
    )
    saved = logged_in_games.post(
        "/api/games/saves",
        data={"game_id": str(game_id), "remark": "删前", "manifest": manifest},
        files={"sols": ("save.state", b"STATEBYTES", "application/octet-stream")},
    )
    assert saved.status_code == 201, saved.text
    saved_dir = storage_root / "save" / "alice" / "nes" / "DEL-1"
    assert saved_dir.is_dir() and list(saved_dir.iterdir())

    assert logged_in_games.delete(f"/api/games/manage/{game_id}").status_code == 200

    assert not (storage_root / "game" / "nes" / "DEL-1").exists()
    assert not saved_dir.exists()  # 目录本身也收掉，不留空壳
    with Session(logged_in_games.app.state.engine) as session:
        assert session.get(Game, game_id) is None
        assert session.exec(
            select(GameCloudSnapshot).where(GameCloudSnapshot.game_id == game_id)
        ).all() == []
        assert session.exec(select(GameCloudSnapshotFile)).all() == []


def test_delete_keeps_other_games_saves(logged_in_games, storage_root):
    """删一个游戏不碰别的游戏的存档。"""
    keep = _create_game(
        logged_in_games, "保留", "a.nes", b"nes-body", cartridge_id="KEEP9"
    ).json()["data"]
    drop = _create_game(
        logged_in_games, "删掉", "b.nes", b"nes-body", cartridge_id="DROP9"
    ).json()["data"]

    for item in (keep, drop):
        manifest = json.dumps(
            [{"local_key": "k%d" % item["id"], "name": "save.state"}]
        )
        assert (
            logged_in_games.post(
                "/api/games/saves",
                data={"game_id": str(item["id"]), "remark": "", "manifest": manifest},
                files={"sols": ("save.state", b"bytes", "application/octet-stream")},
            ).status_code
            == 201
        )

    assert logged_in_games.delete(f"/api/games/manage/{drop['id']}").status_code == 200

    assert not (storage_root / "save" / "alice" / "nes" / "DROP9").exists()
    kept_dir = storage_root / "save" / "alice" / "nes" / "KEEP9"
    assert kept_dir.is_dir() and list(kept_dir.iterdir())
    assert logged_in_games.get(
        "/api/games/saves", params={"game_id": keep["id"]}
    ).json()["data"]


def test_manage_search_and_filter(logged_in_games):
    _create_game(logged_in_games, "Alpha", "a.swf", b"first")
    _create_game(logged_in_games, "Beta", "b.swf", b"second")

    filtered = logged_in_games.get("/api/games/manage", params={"q": "Alpha"})
    assert filtered.status_code == 200
    names = [item["name"] for item in filtered.json()["data"]["items"]]
    assert names == ["Alpha"]

    typed = logged_in_games.get("/api/games/manage", params={"game_type": "flash"})
    assert typed.status_code == 200
    assert len(typed.json()["data"]["items"]) == 2


def test_manage_list_is_paged(logged_in_games):
    """管理列表服务端分页：默认每页 5 条，载荷是 {total, page, page_size, items}。"""
    for name in ("n06", "n02", "n09", "n04", "n01", "n08", "n03", "n10", "n05", "n07"):
        _create_game(logged_in_games, name, "a.swf")

    first = logged_in_games.get("/api/games/manage").json()["data"]
    assert set(first) == {"total", "page", "page_size", "items"}
    assert (first["total"], first["page"], first["page_size"]) == (10, 1, 5)
    # 更新时间倒序 = 建库顺序的逆序
    assert [item["name"] for item in first["items"]] == ["n07", "n05", "n10", "n03", "n08"]

    second = logged_in_games.get("/api/games/manage", params={"page": 2}).json()["data"]
    assert [item["name"] for item in second["items"]] == ["n01", "n04", "n09", "n02", "n06"]
    assert second["total"] == 10


def test_manage_list_sorted_by_updated_at_desc(logged_in_games):
    """排序按更新时间倒序，与类型、名称都无关；改过的游戏回到最前面。"""
    first = _create_game(logged_in_games, "zeta", "z.nes").json()["data"]
    _create_game(logged_in_games, "alpha", "a.swf")

    data = logged_in_games.get("/api/games/manage").json()["data"]
    assert [item["name"] for item in data["items"]] == ["alpha", "zeta"]

    # 编辑先建的那条：它的 updated_at 被刷新，于是排到最前（类型顺序、名称都不参与）
    logged_in_games.put(
        f"/api/games/manage/{first['id']}", json={"description": "改过"}
    )
    data = logged_in_games.get("/api/games/manage").json()["data"]
    assert [item["name"] for item in data["items"]] == ["zeta", "alpha"]


def test_manage_pagination_params_are_clamped(logged_in_games):
    """越界参数在 service 里收敛成合法值，返回 200 而不是 422（422 会绕开统一错误信封）。"""
    _create_game(logged_in_games, "A", "a.swf")

    zero = logged_in_games.get("/api/games/manage", params={"page": 0})
    assert zero.status_code == 200
    assert zero.json()["data"]["page"] == 1

    negative = logged_in_games.get("/api/games/manage", params={"page": -5})
    assert negative.json()["data"]["page"] == 1

    # page_size=0 与「没传」同义（`page_size or 默认值`），回落默认的 5；负数才收敛到 1
    zero_size = logged_in_games.get("/api/games/manage", params={"page_size": 0})
    assert zero_size.json()["data"]["page_size"] == 5

    negative_size = logged_in_games.get("/api/games/manage", params={"page_size": -3})
    assert negative_size.json()["data"]["page_size"] == 1

    huge = logged_in_games.get("/api/games/manage", params={"page_size": 100000})
    assert huge.status_code == 200
    assert huge.json()["data"]["page_size"] == 100


def test_manage_page_beyond_range_returns_empty_items(logged_in_games):
    """页码越界不是错误：items 空、total 照给（与检索页同一口径），页码收敛交给前端。"""
    for name in ("a", "b", "c"):
        _create_game(logged_in_games, name, "a.swf")

    data = logged_in_games.get("/api/games/manage", params={"page": 99}).json()["data"]
    assert data["items"] == []
    assert (data["total"], data["page"]) == (3, 99)


def test_manage_filter_combines_with_pagination(logged_in_games):
    """筛选与分页组合：total 是筛选后的总数，不是全表总数。"""
    for name in ("n1", "n2", "n3", "n4", "n5"):
        _create_game(logged_in_games, name, "a.swf")
    _create_game(logged_in_games, "rom", "r.nes")

    typed = logged_in_games.get(
        "/api/games/manage", params={"game_type": "flash", "page": 2, "page_size": 2}
    ).json()["data"]
    assert (typed["total"], typed["page"], typed["page_size"]) == (5, 2, 2)
    # 管理页按更新时间倒序（后建的排最前），所以第 2 页是 n3、n2
    assert [item["name"] for item in typed["items"]] == ["n3", "n2"]

    searched = logged_in_games.get(
        "/api/games/manage", params={"q": "n", "page_size": 3}
    ).json()["data"]
    assert searched["total"] == 5
    assert [item["name"] for item in searched["items"]] == ["n5", "n4", "n3"]


@pytest.mark.parametrize(
    "game_type,extension",
    [
        ("nes", ".nes"),
        ("snes", ".sfc"),
        ("snes", ".smc"),
        ("gb", ".gb"),
        ("gb", ".gbc"),
        ("gba", ".gba"),
        ("segaMD", ".md"),
        ("segaMD", ".gen"),
        ("segaGG", ".gg"),
        ("segaMS", ".sms"),
    ],
)
def test_emulator_types_upload_and_play(logged_in_games, game_type, extension):
    """各主机平台：上传本体即按扩展名定类型，中心 path 走通用播放路由，本体 octet-stream 下发。"""
    create = _create_game(logged_in_games, "平台测试", f"demo{extension}", b"rom-body")
    assert create.status_code == 201
    assert create.json()["data"]["game_type"] == game_type
    assert create.json()["data"]["game_path"].endswith(f"/game{extension}")
    game_id = create.json()["data"]["id"]

    listing = logged_in_games.get("/api/games")
    games = listing.json()["data"]
    assert len(games) == 1
    assert games[0]["category"] == game_type
    assert games[0]["path"] == f"/games/play/{game_id}"

    play = logged_in_games.get(f"/api/games/{game_id}/play")
    assert play.status_code == 200
    assert play.content == b"rom-body"
    assert play.headers.get("content-type") == "application/octet-stream"


def test_replacing_body_cross_type_rejected(logged_in_games, storage_root):
    """换本体只接受同一游戏类型：跨类型直接 400，旧本体与库值都不动。"""
    nes = _create_game(logged_in_games, "N", "a.nes", b"nes-body").json()["data"]
    cid = nes["cartridge_id"]
    before = logged_in_games.get(f"/api/games/manage/{nes['id']}").json()["data"]
    before_files = _files(storage_root)

    rejected = logged_in_games.post(
        f"/api/games/manage/{nes['id']}/assets",
        data={"kind": "game"},
        files={"file": ("a.gba", b"gba-body", "application/octet-stream")},
    )
    assert rejected.status_code == 400
    message = rejected.json()["message"]
    assert "任天堂 FC" in message
    assert "任天堂 GBA" in message
    assert _files(storage_root) == before_files

    after = logged_in_games.get(f"/api/games/manage/{nes['id']}").json()["data"]
    for key in ("game_type", "game_path", "size", "crc32", "updated_at"):
        assert after[key] == before[key]
    assert after["game_path"] == f"game/nes/{cid}/game.nes"
    play = logged_in_games.get(f"/api/games/{nes['id']}/play")
    assert play.status_code == 200
    assert play.content == b"nes-body"


def test_replacing_body_keeps_cover(logged_in_games, storage_root):
    """同类型换本体：封面留在原目录，内容不变。"""
    nes = _create_game(
        logged_in_games,
        "带封面换本体",
        "a.nes",
        b"nes-body",
        cover=("c.png", b"png-body", "image/png"),
    ).json()["data"]
    cid = nes["cartridge_id"]
    assert _exists(storage_root, f"game/nes/{cid}/cover.png")

    replaced = logged_in_games.post(
        f"/api/games/manage/{nes['id']}/assets",
        data={"kind": "game"},
        files={"file": ("b.nes", b"new-nes-body", "application/octet-stream")},
    )
    assert replaced.status_code == 201, replaced.text
    body = replaced.json()["data"]
    assert body["game_type"] == "nes"
    assert body["cover_path"] == f"game/nes/{cid}/cover.png"
    assert _read(storage_root, f"game/nes/{cid}/cover.png") == b"png-body"

    cover = logged_in_games.get(f"/api/games/{nes['id']}/cover")
    assert cover.status_code == 200
    assert cover.content == b"png-body"


def test_body_crc32_recorded_on_upload(logged_in_games):
    """上传本体时就算好 crc32 落库，管理详情里能看到。"""
    created = _create_game(logged_in_games, "记 crc32", "a.nes", b"nes-body")
    assert created.status_code == 201
    body = created.json()["data"]
    assert body["crc32"] == f"{zlib.crc32(b'nes-body') & 0xFFFFFFFF:08X}"
    detail = logged_in_games.get(f"/api/games/manage/{body['id']}").json()["data"]
    assert detail["crc32"] == body["crc32"]


def test_body_reupload_updates_crc32_and_size(logged_in_games, storage_root):
    """同类型换本体：任意新内容都接受，crc32/size 一起更新。"""
    game = _create_game(logged_in_games, "换内容", "a.nes", b"nes-body").json()["data"]
    new_body = b"nes-body-v2-longer"
    replaced = logged_in_games.post(
        f"/api/games/manage/{game['id']}/assets",
        data={"kind": "game"},
        files={"file": ("a.nes", new_body, "application/octet-stream")},
    )
    assert replaced.status_code == 201, replaced.text
    body = replaced.json()["data"]
    assert body["game_path"] == game["game_path"]
    assert body["crc32"] == _crc32_of(new_body)
    assert body["size"] == len(new_body)
    assert _read(storage_root, body["game_path"]) == new_body
    detail = logged_in_games.get(f"/api/games/manage/{game['id']}").json()["data"]
    assert detail["crc32"] == _crc32_of(new_body)


@pytest.mark.parametrize(
    "game_type,first,second,new_body",
    [
        ("gb", "a.gb", "b.gbc", b"gbc-body"),
        ("snes", "a.sfc", "b.smc", b"smc-body"),
        ("segaMD", "a.md", "b.gen", b"gen-body"),
    ],
)
def test_body_reupload_same_type_changes_extension(
    logged_in_games, storage_root, game_type, first, second, new_body
):
    """同一游戏类型内可换后缀：新文件就位、旧后缀文件删掉、crc32 更新。"""
    game = _create_game(logged_in_games, f"换后缀 {game_type}", first, b"old-body").json()[
        "data"
    ]
    cid = game["cartridge_id"]
    replaced = logged_in_games.post(
        f"/api/games/manage/{game['id']}/assets",
        data={"kind": "game"},
        files={"file": (second, new_body, "application/octet-stream")},
    )
    assert replaced.status_code == 201, replaced.text
    body = replaced.json()["data"]
    new_path = f"game/{game_type}/{cid}/game{Path(second).suffix}"
    assert body["game_type"] == game_type
    assert body["game_path"] == new_path
    assert body["crc32"] == _crc32_of(new_body)
    assert _read(storage_root, new_path) == new_body
    assert not _exists(storage_root, f"game/{game_type}/{cid}/game{Path(first).suffix}")


@pytest.mark.parametrize(
    "first,second,current_label,new_label,new_body",
    [
        ("a.nes", "b.gba", "任天堂 FC", "任天堂 GBA", b"gba-body"),
        ("a.gb", "b.nes", "任天堂 GB/GBC", "任天堂 FC", b"nes-body"),
        ("a.swf", "b.zip", "Flash", "HTML5", b"zip-body"),
        ("a.zip", "b.nes", "HTML5", "任天堂 FC", b"nes-body"),
    ],
)
def test_body_reupload_cross_type_rejected(
    logged_in_games,
    storage_root,
    first,
    second,
    current_label,
    new_label,
    new_body,
):
    """跨类型换本体 400：旧文件、库字段、播放内容全部不动。"""
    seed = _make_zip({"index.html": b"seed"}) if first == "a.zip" else b"old-body"
    if second == "b.zip":
        new_body = _make_zip({"index.html": b"new"})
    game = _create_game(logged_in_games, f"跨类型 {first}", first, seed).json()["data"]
    before = logged_in_games.get(f"/api/games/manage/{game['id']}").json()["data"]
    before_files = _files(storage_root)

    rejected = logged_in_games.post(
        f"/api/games/manage/{game['id']}/assets",
        data={"kind": "game"},
        files={"file": (second, new_body, "application/octet-stream")},
    )
    assert rejected.status_code == 400
    message = rejected.json()["message"]
    assert current_label in message
    assert new_label in message
    assert _files(storage_root) == before_files

    after = logged_in_games.get(f"/api/games/manage/{game['id']}").json()["data"]
    for key in ("game_type", "game_path", "size", "crc32", "updated_at"):
        assert after[key] == before[key]
    play = logged_in_games.get(f"/api/games/{game['id']}/play")
    assert play.status_code == 200
    assert play.content == seed


def test_body_reupload_unknown_extension_rejected(logged_in_games, storage_root):
    """未收录后缀仍是 400，旧档不动。"""
    game = _create_game(logged_in_games, "未知后缀", "a.nes", b"nes-body").json()["data"]
    before_files = _files(storage_root)
    rejected = logged_in_games.post(
        f"/api/games/manage/{game['id']}/assets",
        data={"kind": "game"},
        files={"file": ("b.txt", b"text-body", "text/plain")},
    )
    assert rejected.status_code == 400
    assert "无法识别" in rejected.json()["message"]
    assert _files(storage_root) == before_files


@pytest.mark.parametrize(
    "name",
    [
        "魂斗罗/30条命",  # Windows 与百度网盘的非法字符
        "魂斗罗:特别版",
        '双截龙"复仇"',
        "超级玛丽?",  # 半角问号非法（全角的 ？ 合法，见下面的接受用例）
        "超级玛丽.",
        "NUL",
        "con.nes",  # 保留设备名带扩展名同样保留，且大小写不敏感
        "COM1",
        "   ",
        "带\n换行的名字",
        "字" * 256,
    ],
)
def test_validate_game_name_rejects(name):
    with pytest.raises(ValidationError):
        validate_game_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "魔塔V1.1",  # 中间的点没问题，结尾的才不行
        "超级玛丽.世界",
        "魂斗罗（30 条命）",  # 全角括号
        "ＦＣ 版：合法",  # 全角冒号不是 Windows 的非法字符
        "Contra - Hard Corps",
        "  去空白后合法  ",
    ],
)
def test_validate_game_name_accepts(name):
    assert validate_game_name(name) == name.strip()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("abc", "ABC"),          # 小写自动转大写
        ("ab-12_c", "AB-12_C"),  # 中划线、下划线、数字都合法
        ("  a1  ", "A1"),        # 去首尾空白
    ],
)
def test_validate_cartridge_id_normalizes(raw, expected):
    assert validate_cartridge_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "中文", "a b", "a/b", "A.B", "A" * 65])
def test_validate_cartridge_id_rejects(raw):
    with pytest.raises(ValidationError):
        validate_cartridge_id(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [("abc", "ABC"), ("  ab-1  ", "AB-1"), ("", ""), (None, "")],
)
def test_normalize_cartridge_id_only_normalizes(raw, expected):
    """归一只做「去首尾空白 + 转大写」，**不校验**——榜单 CSV 里带空格/点的原文也要能过。"""
    assert normalize_cartridge_id(raw) == expected


@pytest.mark.parametrize(
    "game_type,expected",
    [
        ("flash", "/games/flash/7"),
        ("h5", "/games/h5/7"),
        ("nes", "/games/play/7"),
        ("gba", "/games/play/7"),
    ],
)
def test_play_path_matches_game_item_path(game_type, expected):
    """播放路径只有一份实现：模块级 play_path() 与 GameItem.path 必须一致。"""
    assert play_path(game_type, 7) == expected
    item = GameItem(
        id=7,
        name="游戏",
        cartridge_id="A1",
        cover_type=None,
        description="",
        game_type=game_type,
        size=0,
        crc32="",
        game_path="game/x/A1/game.bin",
        cover_path=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert item.path == expected


def test_map_for_cartridge_ids_normalizes_and_keeps_raw_keys(game_service):
    """键是**原样回传的入参**（调用方不必知道归一规则），未命中的入参不出现。"""
    game_service.create(
        "超级马里奥兄弟", "", _upload("a.nes", b"nes-body"), cartridge_id="NES-SM"
    )

    links = game_service.map_for_cartridge_ids([" nes-sm ", "nes-sm", "NOPE", ""])

    assert set(links) == {" nes-sm ", "nes-sm"}
    assert links[" nes-sm "].game_id == links["nes-sm"].game_id
    assert links["nes-sm"].path == f"/games/play/{links['nes-sm'].game_id}"


def test_map_for_cartridge_ids_skips_games_without_body(game_service, app):
    """没有本体的条目不给链接（与游戏中心列表同口径）。"""
    with Session(app.state.engine) as session:
        session.add(
            Game(name="本体丢了", cartridge_id="NES-SM", game_type="nes", game_path="")
        )
        session.commit()

    assert game_service.map_for_cartridge_ids(["NES-SM"]) == {}


def test_map_for_cartridge_ids_without_ids_does_not_query(game_service):
    assert game_service.map_for_cartridge_ids([]) == {}
    assert game_service.map_for_cartridge_ids(["", "   "]) == {}


def test_create_requires_cartridge_id(logged_in_games):
    """卡带ID 必填：不填直接 400，不留下条目。"""
    response = logged_in_games.post(
        "/api/games/manage",
        data={"name": "没卡带ID", "description": ""},
        files={"file": ("a.nes", b"nes-body", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "卡带" in response.json()["message"]
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []


def test_cartridge_id_is_uppercased_and_used_as_directory(logged_in_games, storage_root):
    created = _create_game(
        logged_in_games, "小写卡带ID", "a.nes", b"nes-body", cartridge_id="ab-12"
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["cartridge_id"] == "AB-12"
    assert data["game_path"] == "game/nes/AB-12/game.nes"
    assert _exists(storage_root, "game/nes/AB-12/game.nes")


def test_cartridge_id_must_be_unique(logged_in_games):
    """卡带ID 全局唯一，且跨游戏类型也不允许重复。"""
    assert _create_game(
        logged_in_games, "甲", "a.nes", b"x", cartridge_id="DUP-1"
    ).status_code == 201
    same_type = _create_game(
        logged_in_games, "乙", "b.nes", b"y", cartridge_id="dup-1"
    )
    assert same_type.status_code == 400
    assert "DUP-1" in same_type.json()["message"]

    other_type = _create_game(
        logged_in_games, "丙", "c.swf", b"z", cartridge_id="DUP-1"
    )
    assert other_type.status_code == 400


def test_cartridge_id_cannot_be_changed(logged_in_games):
    """普通编辑改不动卡带ID：PUT 带 cartridge_id 也只当普通字段忽略（改名是另一个接口）。"""
    created = _create_game(
        logged_in_games, "不可改", "a.nes", b"x", cartridge_id="FIXED1"
    ).json()["data"]
    updated = logged_in_games.put(
        f"/api/games/manage/{created['id']}",
        json={"name": "改名", "cartridge_id": "OTHER1"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["cartridge_id"] == "FIXED1"
    assert updated.json()["data"]["game_path"] == "game/nes/FIXED1/game.nes"


# ---------------------------------------------------------------- 改卡带ID

_PNG_HEAD = b"\x89PNG\r\n\x1a\n"


def _rename(client, game_id: int, new_id: str):
    return client.put(
        f"/api/games/manage/{game_id}/cartridge-id", json={"cartridge_id": new_id}
    )


def _upload_save(client, game_id: int, payload: bytes = b"save") -> None:
    manifest = json.dumps([{"local_key": "k", "name": "save.state"}])
    response = client.post(
        "/api/games/saves",
        data={"game_id": str(game_id), "remark": "备注", "manifest": manifest},
        files=[("sols", ("save.state", payload, "application/octet-stream"))],
    )
    assert response.status_code == 201, response.text


def _upload_image(client, endpoint: str, game_id: int, payload: bytes = b"frame"):
    return client.post(
        endpoint,
        data={"game_id": str(game_id), "description": ""},
        files={"file": ("pic.png", _PNG_HEAD + payload, "image/png")},
    )


def _dir_files(storage_root, prefix: str) -> list[str]:
    """某个目录前缀下现有的文件（存档与截图的文件名是 uuid，只能按目录断言）。"""
    return sorted(path for path in _files(storage_root) if path.startswith(prefix))


def _path_rows(app, game_id: int) -> list[str]:
    """该游戏在库里存了磁盘路径的全部列值（games 的两列 + 三张子表）。"""
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        values = [row.game_path, row.cover_path]
        for model in (GameGalleryImage, GameScreenshot):
            values += [
                item.file_path
                for item in session.exec(
                    select(model).where(model.game_id == game_id)
                ).all()
            ]
        values += [
            item.file_path
            for item in session.exec(
                select(GameCloudSnapshotFile)
                .join(
                    GameCloudSnapshot,
                    GameCloudSnapshot.id == GameCloudSnapshotFile.snapshot_id,
                )
                .where(GameCloudSnapshot.game_id == game_id)
            ).all()
        ]
    return [value for value in values if value]


def test_rename_cartridge_id_moves_dirs_and_rewrites_paths(
    logged_in_games, app, storage_root
):
    """改名 = 搬目录 + 改库里所有引用它的路径列：素材、图集、存档、截图一个都不能落下。"""
    created = _create_game(
        logged_in_games,
        "改名主用例",
        "a.nes",
        b"nes-body",
        cover=("cover.png", _PNG_HEAD + b"c", "image/png"),
        cartridge_id="OLD-1",
    ).json()["data"]
    game_id = created["id"]
    _upload_image(logged_in_games, "/api/games/gallery", game_id)
    _upload_image(logged_in_games, "/api/games/screenshots", game_id)
    _upload_save(logged_in_games, game_id)

    before_files = _files(storage_root)
    assert any(path.startswith("game/nes/OLD-1/") for path in before_files)
    assert any(path.startswith("save/alice/nes/OLD-1/") for path in before_files)
    assert any(path.startswith("image/alice/nes/OLD-1/") for path in before_files)

    response = _rename(logged_in_games, game_id, "new-2")
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    # 提交值自动转大写
    assert body["cartridge_id"] == "NEW-2"
    assert body["game_path"] == "game/nes/NEW-2/game.nes"
    assert body["cover_path"] == "game/nes/NEW-2/cover.png"
    assert body["updated_at"] != created["updated_at"]

    # 磁盘：新目录在、旧目录一个不剩
    assert _exists(storage_root, "game/nes/NEW-2/game.nes")
    assert _exists(storage_root, "game/nes/NEW-2/cover.png")
    assert not any("OLD-1" in path for path in _files(storage_root))
    assert not any("OLD-1" in path for path in _path_rows(app, game_id))

    # 库里每一行都指向新路径
    assert _path_rows(app, game_id) == [
        "game/nes/NEW-2/game.nes",
        "game/nes/NEW-2/cover.png",
        "game/nes/NEW-2/image/" + Path(_path_rows(app, game_id)[2]).name,
        "image/alice/nes/NEW-2/" + Path(_path_rows(app, game_id)[3]).name,
        "save/alice/nes/NEW-2/" + Path(_path_rows(app, game_id)[4]).name,
    ]

    # 功能照旧：本体、封面、图集、截图、存档都还读得到
    assert logged_in_games.get(f"/api/games/{game_id}/play").status_code == 200
    assert logged_in_games.get(f"/api/games/{game_id}/cover").status_code == 200
    gallery = logged_in_games.get(
        "/api/games/gallery", params={"game_id": game_id}
    ).json()["data"]
    assert (
        logged_in_games.get(f"/api/games/gallery/{gallery[0]['id']}/image").status_code
        == 200
    )
    shots = logged_in_games.get(
        "/api/games/screenshots", params={"game_id": game_id}
    ).json()["data"]
    assert (
        logged_in_games.get(
            f"/api/games/screenshots/{shots[0]['id']}/image"
        ).status_code
        == 200
    )
    saves = logged_in_games.get(
        "/api/games/saves", params={"game_id": game_id}
    ).json()["data"]
    assert (
        logged_in_games.get(f"/api/games/saves/{saves[0]['id']}").status_code == 200
    )


def test_rename_cartridge_id_moves_historical_type_dirs(
    logged_in_games, app, storage_root
):
    """存档与截图的目录名带的是写入当时的类型，改名要按 file_path 反推、不能按当前类型拼。"""
    created = _create_game(
        logged_in_games, "换过类型", "a.nes", b"nes-body", cartridge_id="HIST-1"
    ).json()["data"]
    game_id = created["id"]
    _upload_image(logged_in_games, "/api/games/screenshots", game_id)
    _upload_save(logged_in_games, game_id)

    # 直接造出「历史版本换过类型」的状态：库与游戏目录改到 gba，存档/截图仍留在 nes 下
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        row.game_type = "gba"
        row.game_path = "game/gba/HIST-1/game.gba"
        session.add(row)
        session.commit()
    old_dir = Path(storage_root) / "game" / "nes" / "HIST-1"
    new_dir = Path(storage_root) / "game" / "gba" / "HIST-1"
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    old_dir.rename(new_dir)
    (new_dir / "game.nes").rename(new_dir / "game.gba")
    assert _exists(storage_root, "game/gba/HIST-1/game.gba")
    assert _dir_files(storage_root, "save/alice/nes/HIST-1/")

    assert _rename(logged_in_games, game_id, "HIST-2").status_code == 200

    assert _exists(storage_root, "game/gba/HIST-2/game.gba")
    assert _dir_files(storage_root, "save/alice/nes/HIST-2/")
    assert not any("HIST-1" in path for path in _files(storage_root))
    paths_now = _path_rows(app, game_id)
    assert "save/alice/nes/HIST-2/" in " ".join(paths_now)
    assert "image/alice/nes/HIST-2/" in " ".join(paths_now)
    # 没有谁被按「当前类型 gba」错误地拼成 save/alice/gba/…
    assert "alice/gba" not in " ".join(paths_now)


def test_rename_cartridge_id_moves_other_users_dirs(
    logged_in_games, app, storage_root
):
    """存档与截图按账号隔离，改名要把每个账号的目录都搬走。"""
    client = logged_in_games
    created = _create_game(client, "多人", "a.nes", b"nes-body", cartridge_id="MULTI-1")
    game_id = created.json()["data"]["id"]
    _upload_save(client, game_id)
    _upload_image(client, "/api/games/screenshots", game_id)

    with Session(app.state.engine) as session:
        AuthService(session).create_user("bobby", "secret123")
    assert client.post("/api/logout").status_code == 200
    assert (
        client.post(
            "/api/login", json={"username": "bobby", "password": "secret123"}
        ).status_code
        == 200
    )
    _upload_save(client, game_id, b"bobby-save")
    _upload_image(client, "/api/games/screenshots", game_id, b"bobby-frame")

    assert _rename(client, game_id, "MULTI-2").status_code == 200

    for user in ("alice", "bobby"):
        assert _dir_files(storage_root, f"save/{user}/nes/MULTI-2/")
        assert _dir_files(storage_root, f"image/{user}/nes/MULTI-2/")
    assert not any("MULTI-1" in path for path in _files(storage_root))


def test_rename_cartridge_id_invalidates_runtime_extraction(
    logged_in_games, app, storage_root, runtime_root
):
    """H5 的 zip 跟着目录搬家，运行时根那份解包产物作废（下次访问自动重解）。"""
    game_id = _upload_h5(logged_in_games, name="改名 H5")
    old_id = _cartridge_of(app, game_id)
    package = _make_zip({"index.html": b"<html>hi</html>", "assets/app.js": b"js"})
    assert (
        logged_in_games.post(
            f"/api/games/manage/{game_id}/assets",
            data={"kind": "game"},
            files={"file": ("game.zip", package, "application/zip")},
        ).status_code
        == 201
    )
    # 先访问一次，让运行时根产生解包产物
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    assert _exists(runtime_root, f"game/h5/{old_id}/h5/index.html")

    response = _rename(logged_in_games, game_id, "H5-NEW")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["game_path"] == "game/h5/H5-NEW/game.zip"
    assert not any(old_id in path for path in _files(storage_root))
    assert not any(old_id in path for path in _files(runtime_root))
    # 新目录下重新解包，入口与子资源照常取得到
    assert (
        logged_in_games.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    )
    assert (
        logged_in_games.get(f"/api/games/{game_id}/h5/assets/app.js").status_code == 200
    )
    assert _exists(runtime_root, "game/h5/H5-NEW/h5/index.html")


def test_rename_cartridge_id_rejects_duplicate(logged_in_games, app, storage_root):
    """新 ID 被别的游戏占了：400，且磁盘与库都不留痕。"""
    first = _create_game(
        logged_in_games, "甲", "a.nes", b"x", cartridge_id="DUP-A"
    ).json()["data"]
    second = _create_game(
        logged_in_games, "乙", "b.nes", b"y", cartridge_id="DUP-B"
    ).json()["data"]
    before_files = _files(storage_root)

    response = _rename(logged_in_games, second["id"], "DUP-A")
    assert response.status_code == 400
    assert "DUP-A" in response.json()["message"]
    assert _files(storage_root) == before_files
    kept = logged_in_games.get(f"/api/games/manage/{second['id']}").json()["data"]
    assert kept["cartridge_id"] == "DUP-B"
    assert kept["game_path"] == "game/nes/DUP-B/game.nes"
    assert first["cartridge_id"] == "DUP-A"


@pytest.mark.parametrize("raw", ["", "   ", "a b", "a/b", "A.B", "中", "A" * 65])
def test_rename_cartridge_id_rejects_illegal(logged_in_games, storage_root, raw):
    created = _create_game(
        logged_in_games, "非法", "a.nes", b"x", cartridge_id="LEGAL-1"
    ).json()["data"]
    before_files = _files(storage_root)

    response = _rename(logged_in_games, created["id"], raw)
    assert response.status_code == 400
    assert response.json()["message"]
    assert _files(storage_root) == before_files


def test_rename_cartridge_id_unknown_game(logged_in_games):
    response = _rename(logged_in_games, 999, "WHATEVER")
    assert response.status_code == 404
    assert "游戏不存在" in response.json()["message"]


def test_rename_cartridge_id_same_value_is_noop(logged_in_games, storage_root):
    """新旧相同（含只差大小写）：200 空操作，磁盘与 updated_at 都不动。"""
    created = _create_game(
        logged_in_games, "没变", "a.nes", b"x", cartridge_id="SAME-1"
    ).json()["data"]
    before_files = _files(storage_root)

    response = _rename(logged_in_games, created["id"], "same-1")
    assert response.status_code == 200
    assert response.json()["data"]["cartridge_id"] == "SAME-1"
    assert response.json()["data"]["updated_at"] == created["updated_at"]
    assert _files(storage_root) == before_files


def test_rename_cartridge_id_rejects_existing_target_dir(
    logged_in_games, app, storage_root
):
    """源目录不在、目标目录却在：拦下，免得这盘游戏悄悄指向别人的目录。"""
    created = _create_game(
        logged_in_games, "撞目录", "a.nes", b"x", cartridge_id="CLASH-1"
    ).json()["data"]
    game_id = created["id"]
    storage = app.state.storage
    storage.upload("game/nes/CLASH-2/game.nes", _stream(b"someone-else"), 13, None)
    storage.remove_tree("game/nes/CLASH-1")

    response = _rename(logged_in_games, game_id, "CLASH-2")
    assert response.status_code == 400
    assert "game/nes/CLASH-2" in response.json()["message"]
    # 那个陌生目录没被 move_tree 顺手删掉，行也原封不动
    assert _read(storage_root, "game/nes/CLASH-2/game.nes") == b"someone-else"
    assert (
        logged_in_games.get(f"/api/games/manage/{game_id}").json()["data"][
            "cartridge_id"
        ]
        == "CLASH-1"
    )


def test_rename_cartridge_id_tolerates_missing_source_dir(
    logged_in_games, app, storage_root
):
    """本体目录不在了（宿主手删 / 换过类型还没补本体）也照常改名，只是不搬文件。"""
    created = _create_game(
        logged_in_games, "没目录", "a.nes", b"x", cartridge_id="GONE-1"
    ).json()["data"]
    game_id = created["id"]
    app.state.storage.remove_tree("game/nes/GONE-1")

    response = _rename(logged_in_games, game_id, "GONE-2")
    assert response.status_code == 200
    assert response.json()["data"]["game_path"] == "game/nes/GONE-2/game.nes"
    assert not _exists(storage_root, "game/nes/GONE-2/game.nes")


def test_rename_cartridge_id_rolls_back_when_move_fails(
    logged_in_games, app, storage_root, monkeypatch
):
    """搬第二个目录时失败：第一个要搬回去，库里的路径一个字节都不能变。"""
    from backend.games import service as games_service
    from backend.storage.local import LocalStorage

    created = _create_game(
        logged_in_games, "搬不动", "a.nes", b"x", cartridge_id="FAIL-1"
    ).json()["data"]
    game_id = created["id"]
    _upload_save(logged_in_games, game_id)
    before_files = _files(storage_root)

    original = LocalStorage.move_tree
    calls = {"n": 0}

    def flaky(self, source_key, target_key):
        calls["n"] += 1
        if calls["n"] == 2:
            raise games_service.StorageError("磁盘炸了")
        return original(self, source_key, target_key)

    monkeypatch.setattr(LocalStorage, "move_tree", flaky)
    with Session(app.state.engine) as session:
        service = GameService(session, app.state.storage, app.state.runtime_storage)
        with pytest.raises(games_service.StorageError):
            service.rename_cartridge_id(game_id, "FAIL-2")

    # 两次正向搬（游戏目录、存档目录，第二次炸）+ 一次回滚搬回
    assert calls["n"] == 3
    assert _files(storage_root) == before_files
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        assert row.cartridge_id == "FAIL-1"
        assert row.game_path == "game/nes/FAIL-1/game.nes"


def test_rename_cartridge_id_rejects_path_too_long_on_windows(
    logged_in_games, storage_root, monkeypatch
):
    """Windows 上改名后总长越界要在动手之前报错，磁盘一个字节都不动。"""
    created = _create_game(
        logged_in_games, "太长", "a.nes", b"x", cartridge_id="LEN-1"
    ).json()["data"]
    before_files = _files(storage_root)

    # 卡带 ID 最长 64，光靠它顶不破 240，所以把预算压到「数据根 + 一段新路径」之下
    monkeypatch.setattr(games_archive, "IS_WINDOWS", True)
    monkeypatch.setattr(games_archive, "WINDOWS_PATH_BUDGET", 80)
    response = _rename(logged_in_games, created["id"], "L" * 64)
    assert response.status_code == 400
    assert "过长的路径" in response.json()["message"]
    assert "卡带 ID 改短" in response.json()["message"]
    assert _files(storage_root) == before_files


def test_rename_cartridge_id_keeps_crc32_and_cover_type(
    logged_in_games, storage_root
):
    """改名不碰本体内容：CRC32 与封面类型都原样保留，之后仍可换同类型新本体。"""
    created = _create_game(
        logged_in_games,
        "改名保摘要",
        "a.nes",
        b"locked-body",
        cover=("cover.png", _PNG_HEAD + b"c", "image/png"),
        cartridge_id="LOCK-1",
    ).json()["data"]
    game_id = created["id"]
    assert (
        logged_in_games.put(
            f"/api/games/manage/{game_id}", json={"cover_type": "nes"}
        ).status_code
        == 200
    )
    original = logged_in_games.get(f"/api/games/manage/{game_id}").json()["data"]
    assert original["crc32"]

    assert _rename(logged_in_games, game_id, "LOCK-2").status_code == 200
    after = logged_in_games.get(f"/api/games/manage/{game_id}").json()["data"]
    assert after["crc32"] == original["crc32"]
    assert after["cover_type"] == "nes"

    # 同类型换任意新内容：改名后的新目录落盘，摘要跟着更新
    replacement = b"replaced-body"
    updated = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("new.nes", replacement, "application/octet-stream")},
    )
    assert updated.status_code == 201, updated.text
    body = updated.json()["data"]
    assert body["game_path"] == "game/nes/LOCK-2/game.nes"
    assert body["crc32"] == _crc32_of(replacement)
    assert _read(storage_root, "game/nes/LOCK-2/game.nes") == replacement
    assert body["cover_type"] == "nes"


def test_sanitize_game_name_for_import():
    """搬运来的标题只做无害化，不整单失败。"""
    assert sanitize_game_name("魂斗罗 / 30 条命:特别版.") == "魂斗罗 _ 30 条命_特别版"
    assert sanitize_game_name("  ") == "未命名游戏"
    assert sanitize_game_name("NUL") == "未命名游戏"
    assert len(sanitize_game_name("字" * 300)) == 255


def test_create_rejects_illegal_game_name(logged_in_games):
    response = _create_game(logged_in_games, "魂斗罗/30条命", "a.nes", b"nes-body")
    assert response.status_code == 400
    assert "/" in response.json()["message"]
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []


def test_description_length_limit(logged_in_games):
    """描述前后端都限 200 字：正好 200 可以入库，201 字新建与编辑都拒绝。"""
    ok = _create_game(logged_in_games, "长描述", "a.nes", b"x", description="字" * 200)
    assert ok.status_code == 201
    item = ok.json()["data"]
    assert item["description"] == "字" * 200

    too_long = _create_game(
        logged_in_games, "超长描述", "b.nes", b"y", description="字" * 201
    )
    assert too_long.status_code == 400
    assert "200" in too_long.json()["message"]

    edited = logged_in_games.put(
        f"/api/games/manage/{item['id']}", json={"description": "字" * 201}
    )
    assert edited.status_code == 400
    kept = logged_in_games.get(f"/api/games/manage/{item['id']}").json()["data"]
    assert kept["description"] == "字" * 200


def test_rename_rejects_illegal_game_name(logged_in_games):
    first = _create_game(logged_in_games, "合法名字", "a.nes", b"x").json()["data"]
    renamed = logged_in_games.put(
        f"/api/games/manage/{first['id']}", json={"name": "新名字. "}
    )
    assert renamed.status_code == 400
    assert logged_in_games.get(f"/api/games/manage/{first['id']}").json()["data"][
        "name"
    ] == "合法名字"


def test_duplicate_name_in_same_type_rejected(logged_in_games):
    """同类型下名称唯一；不同类型可以重名。"""
    assert _create_game(logged_in_games, "重名", "a.nes", b"x").status_code == 201
    dup = _create_game(logged_in_games, "重名", "b.nes", b"y")
    assert dup.status_code == 400
    assert "重名" in dup.json()["message"]
    # 换一个类型仍可用同一个名字
    assert _create_game(logged_in_games, "重名", "c.swf", b"z").status_code == 201


def test_rename_to_existing_name_rejected(logged_in_games):
    first = _create_game(logged_in_games, "甲", "a.nes", b"x").json()["data"]
    _create_game(logged_in_games, "乙", "b.nes", b"y")

    renamed = logged_in_games.put(
        f"/api/games/manage/{first['id']}", json={"name": "乙"}
    )
    assert renamed.status_code == 400
    assert "乙" in renamed.json()["message"]
    # 改成自己的名字（没变）不该报错
    same = logged_in_games.put(f"/api/games/manage/{first['id']}", json={"name": "甲"})
    assert same.status_code == 200


def test_failed_same_type_upload_keeps_old_asset(game_service, storage_root):
    """同类型换本体但新文件校验失败：类型、旧本体与库值都保持原样。"""
    good_zip = _make_zip({"index.html": b"old"})
    item = game_service.create(
        "H", "", _upload("a.zip", good_zip), cartridge_id="KEEP1"
    )
    before = game_service.get(item.id)
    bad_zip = _make_zip({"a.js": b"no-entry"})
    with pytest.raises(Exception):
        game_service.upload_asset(item.id, kind="game", upload=_upload("bad.zip", bad_zip))

    fresh = game_service.get(item.id)
    assert fresh.game_type == "h5"
    assert fresh.game_path == "game/h5/KEEP1/game.zip"
    assert fresh.crc32 == before.crc32
    assert fresh.size == before.size
    assert _read(storage_root, "game/h5/KEEP1/game.zip") == good_zip


def test_create_leaves_cover_type_empty(logged_in_games):
    """新建一律没有封面类型（表单里硬塞也当没给）：只有编辑与美化封面才写它。"""
    nes = _create_game(logged_in_games, "CT 空", "a.nes", b"nes-body").json()["data"]
    assert nes["cover_type"] is None

    sneaky = _create_game(
        logged_in_games, "CT 硬塞", "b.gb", b"gb-body", cover_type="gb"
    )
    assert sneaky.status_code == 201, sneaky.text
    assert sneaky.json()["data"]["cover_type"] is None

    center = logged_in_games.get("/api/games").json()["data"]
    assert [item["cover_type"] for item in center] == [None, None]
    detail = logged_in_games.get(f"/api/games/manage/{nes['id']}").json()["data"]
    assert detail["cover_type"] is None


def test_update_cover_type(logged_in_games):
    """编辑弹框可随时改封面类型；空串清空；该游戏类型不认的值 400 且原值不变。"""
    nes = _create_game(logged_in_games, "CT 改", "a.nes", b"nes-body").json()["data"]
    updated = logged_in_games.put(
        f"/api/games/manage/{nes['id']}", json={"cover_type": "fc"}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["cover_type"] == "fc"

    rejected = logged_in_games.put(
        f"/api/games/manage/{nes['id']}", json={"cover_type": "gb"}
    )
    assert rejected.status_code == 400
    assert "封面类型" in rejected.json()["message"]
    detail = logged_in_games.get(f"/api/games/manage/{nes['id']}").json()["data"]
    assert detail["cover_type"] == "fc"

    cleared = logged_in_games.put(
        f"/api/games/manage/{nes['id']}", json={"cover_type": ""}
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["cover_type"] is None


def test_cover_type_rejects_for_unsupported_type(logged_in_games):
    """不支持美化封面的类型（snes）永远没有封面类型：设值 400、空值照收。"""
    snes = _create_game(logged_in_games, "CT SNES", "a.sfc", b"sfc-body").json()["data"]
    for value in ("gb", "fc", "xx"):
        rejected = logged_in_games.put(
            f"/api/games/manage/{snes['id']}", json={"cover_type": value}
        )
        assert rejected.status_code == 400, value
        assert "封面类型" in rejected.json()["message"]
    # 空值合法：编辑弹框对这类游戏根本不显示那一行，表单照样会把空串发上来
    blank = logged_in_games.put(
        f"/api/games/manage/{snes['id']}", json={"cover_type": ""}
    )
    assert blank.status_code == 200
    assert blank.json()["data"]["cover_type"] is None


def test_body_replacement_keeps_cover_type(logged_in_games, storage_root):
    """同类型换后缀（.gb→.gbc）不碰封面类型，旧后缀本体被删掉。"""
    gb = _create_game(logged_in_games, "CT 换后缀", "a.gb", b"gb-body").json()["data"]
    cid = gb["cartridge_id"]
    logged_in_games.put(f"/api/games/manage/{gb['id']}", json={"cover_type": "gbc"})

    replaced = logged_in_games.post(
        f"/api/games/manage/{gb['id']}/assets",
        data={"kind": "game"},
        files={"file": ("b.gbc", b"gbc-body", "application/octet-stream")},
    )
    assert replaced.status_code == 201, replaced.text
    body = replaced.json()["data"]
    assert body["game_type"] == "gb"
    assert body["game_path"] == f"game/gb/{cid}/game.gbc"
    assert body["cover_type"] == "gbc"
    assert not _exists(storage_root, f"game/gb/{cid}/game.gb")


def test_assets_writes_cover_type_with_cover(logged_in_games, storage_root):
    """美化封面：样式 id 与封面文件在同一次 assets 调用里写进去。"""
    gb = _create_game(
        logged_in_games,
        "CT 美化",
        "a.gb",
        b"gb-body",
        cover=("cover.png", b"old-cover", "image/png"),
    ).json()["data"]

    saved = logged_in_games.post(
        f"/api/games/manage/{gb['id']}/assets",
        data={"kind": "cover", "cover_type": "gbc"},
        files={"file": ("cover.png", b"new-cover", "image/png")},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["data"]["cover_type"] == "gbc"
    assert _read(storage_root, saved.json()["data"]["cover_path"]) == b"new-cover"


def test_assets_rejects_bad_cover_type(logged_in_games, storage_root):
    """样式 id 非法时整次调用失败：封面文件也不换，不留半截状态。"""
    gb = _create_game(
        logged_in_games,
        "CT 美化失败",
        "a.gb",
        b"gb-body",
        cover=("cover.png", b"old-cover", "image/png"),
    ).json()["data"]

    rejected = logged_in_games.post(
        f"/api/games/manage/{gb['id']}/assets",
        data={"kind": "cover", "cover_type": "zzz"},
        files={"file": ("cover.png", b"new-cover", "image/png")},
    )
    assert rejected.status_code == 400
    assert "封面类型" in rejected.json()["message"]

    detail = logged_in_games.get(f"/api/games/manage/{gb['id']}").json()["data"]
    assert detail["cover_type"] is None
    assert _read(storage_root, detail["cover_path"]) == b"old-cover"


def test_assets_ignores_cover_type_for_game_kind(logged_in_games):
    """换本体（kind=game）不认这个字段，封面类型不会被顺带写进去。"""
    gb = _create_game(logged_in_games, "CT 本体", "a.gb", b"gb-body").json()["data"]

    uploaded = logged_in_games.post(
        f"/api/games/manage/{gb['id']}/assets",
        data={"kind": "game", "cover_type": "gbc"},
        files={"file": ("b.gb", b"gb-body-2", "application/octet-stream")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["data"]["cover_type"] is None


def test_init_db_adds_missing_cover_type_column(tmp_path):
    """老库的 games 表没有 cover_type：启动时补上这一列，旧行是空（可空列）。"""
    from sqlalchemy import inspect as sa_inspect
    from sqlmodel import create_engine

    from backend.database import init_db

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE games ("
            "id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, "
            "cartridge_id VARCHAR(64) NOT NULL, description VARCHAR(200) NOT NULL, "
            "game_type VARCHAR(50) NOT NULL, size INTEGER NOT NULL, "
            "crc32 VARCHAR(8) NOT NULL, game_path VARCHAR(500) NOT NULL, "
            "cover_path VARCHAR(500), created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL)"
        )
        conn.exec_driver_sql(
            "INSERT INTO games (id, name, cartridge_id, description, game_type, size, "
            "crc32, game_path, created_at, updated_at) VALUES "
            "(1, '老游戏', 'OLD1', '', 'nes', 0, '', '', "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )

    init_db(engine)

    columns = {c["name"]: c for c in sa_inspect(engine).get_columns("games")}
    assert "cover_type" in columns
    assert columns["cover_type"]["nullable"] is True
    with Session(engine) as session:
        assert session.get(Game, 1).cover_type is None


def test_init_db_adds_missing_guide_kind_column(tmp_path):
    """老库的 games 表没有 guide_kind：启动时补上非空列，旧行是空串（不回填磁盘）。"""
    from sqlalchemy import inspect as sa_inspect
    from sqlmodel import create_engine

    from backend.database import init_db

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE games ("
            "id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, "
            "cartridge_id VARCHAR(64) NOT NULL, description VARCHAR(200) NOT NULL, "
            "game_type VARCHAR(50) NOT NULL, size INTEGER NOT NULL, "
            "crc32 VARCHAR(8) NOT NULL, game_path VARCHAR(500) NOT NULL, "
            "cover_path VARCHAR(500), created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL)"
        )
        conn.exec_driver_sql(
            "INSERT INTO games (id, name, cartridge_id, description, game_type, size, "
            "crc32, game_path, created_at, updated_at) VALUES "
            "(1, '老游戏', 'OLD1', '', 'nes', 0, '', '', "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )

    init_db(engine)

    columns = {c["name"]: c for c in sa_inspect(engine).get_columns("games")}
    assert "guide_kind" in columns
    assert columns["guide_kind"]["nullable"] is False
    with Session(engine) as session:
        assert session.get(Game, 1).guide_kind == ""


def test_init_db_adds_missing_snapshot_parent_column_and_index(tmp_path):
    """老库的 game_cloud_snapshots 表没有 parent_id：启动时补可空列与索引。"""
    from sqlalchemy import inspect as sa_inspect
    from sqlmodel import create_engine

    from backend.database import init_db

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE game_cloud_snapshots ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "game_id INTEGER NOT NULL, remark VARCHAR(100) NOT NULL, "
            "created_at DATETIME NOT NULL)"
        )

    init_db(engine)

    columns = {
        c["name"]: c for c in sa_inspect(engine).get_columns("game_cloud_snapshots")
    }
    assert "parent_id" in columns
    assert columns["parent_id"]["nullable"] is True

    indexes = sa_inspect(engine).get_indexes("game_cloud_snapshots")
    assert any(index["column_names"] == ["parent_id"] for index in indexes)


def test_update_ignores_manual_game_type(logged_in_games):
    """类型不接受手动指定：PUT 带 game_type 也只当普通字段忽略，类型不变。"""
    created = _create_game(logged_in_games, "F", "a.swf", b"swf-body").json()["data"]
    updated = logged_in_games.put(
        f"/api/games/manage/{created['id']}",
        json={"name": "改名", "game_type": "nes"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "改名"
    assert updated.json()["data"]["game_type"] == "flash"


def test_manage_filter_emulator_type(logged_in_games):
    _create_game(logged_in_games, "Md game", "a.md", b"md-body")
    _create_game(logged_in_games, "Nes game", "b.nes", b"nes-body")
    filtered = logged_in_games.get(
        "/api/games/manage", params={"game_type": "segaMD"}
    )
    assert filtered.status_code == 200
    names = [item["name"] for item in filtered.json()["data"]["items"]]
    assert names == ["Md game"]


# ---------- H5（ZIP 解包） ----------


def _make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _upload_h5(logged_in_games, name="H5 demo"):
    """建一个 H5 游戏（本体是含 index.html 的最小 zip，类型由扩展名自动识别）。"""
    create = _create_game(
        logged_in_games, name, "seed.zip", _make_zip({"index.html": b"seed"})
    )
    assert create.status_code == 201
    assert create.json()["data"]["game_type"] == "h5"
    return create.json()["data"]["id"]


def test_h5_upload_and_serve(logged_in_games, storage_root, runtime_root):
    """建 H5→传含 index.html 与资源的 zip→只存 zip；首次访问才解包，入口与资源均可取。"""
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    package = _make_zip(
        {
            "index.html": b"<html>hi</html>",
            "assets/app.js": b"console.log(1)",
            "__MACOSX/._index.html": b"junk",
            ".DS_Store": b"junk",
        }
    )
    upload = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("game.zip", package, "application/zip")},
    )
    assert upload.status_code == 201
    body = upload.json()["data"]
    assert body["game_path"] == f"game/h5/{cid}/game.zip"
    assert body["size"] == len(package)

    # 上传只落 zip：数据根里没有解包产物，运行时根也还是空的
    assert _exists(storage_root, f"game/h5/{cid}/game.zip")
    assert not _exists(storage_root, f"game/h5/{cid}/h5/index.html")
    assert not _exists(runtime_root, f"game/h5/{cid}/h5/index.html")

    entry = logged_in_games.get(f"/api/games/{game_id}/h5/index.html")
    assert entry.status_code == 200
    assert entry.content == b"<html>hi</html>"
    assert entry.headers["content-type"].startswith("text/html")
    assert "sandbox" in entry.headers["content-security-policy"]
    assert "allow-same-origin" not in entry.headers["content-security-policy"]
    assert entry.headers["x-content-type-options"] == "nosniff"
    assert entry.headers["access-control-allow-origin"] == "*"

    # 首次访问之后才有解包产物，垃圾条目被跳过
    assert _exists(runtime_root, f"game/h5/{cid}/h5/index.html")
    assert _exists(runtime_root, f"game/h5/{cid}/h5/assets/app.js")
    assert not _exists(runtime_root, f"game/h5/{cid}/h5/.DS_Store")
    assert not any("__MACOSX" in path for path in _files(runtime_root))

    asset = logged_in_games.get(f"/api/games/{game_id}/h5/assets/app.js")
    assert asset.status_code == 200
    assert asset.content == b"console.log(1)"
    assert asset.headers["content-type"].startswith("text/javascript")

    listing = logged_in_games.get("/api/games").json()["data"]
    assert listing[0]["category"] == "h5"
    assert listing[0]["path"] == f"/games/h5/{game_id}"

    head = logged_in_games.head(f"/api/games/{game_id}/h5/index.html")
    assert head.status_code == 200
    assert head.headers["content-length"] == str(len(b"<html>hi</html>"))


def test_h5_second_request_does_not_reextract(logged_in_games, runtime_root):
    """已经解包过就只读：再访问两次，解包产物的 mtime 一个纳秒都不动。"""
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"index.html": b"v1"}), "application/zip")},
    )
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    entry = Path(runtime_root) / f"game/h5/{cid}/h5/index.html"
    stamp = entry.stat().st_mtime_ns

    for _ in range(2):
        assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    assert entry.stat().st_mtime_ns == stamp


def test_h5_concurrent_requests_extract_once(logged_in_games, app, runtime_root):
    """并发打同一盘 H5：进程内的锁让解包只发生一次，暂存目录不留残留。"""
    from concurrent.futures import ThreadPoolExecutor

    game_id = _upload_h5(logged_in_games, name="并发 H5")
    cid = _cartridge_of(app, game_id)
    logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={
            "file": (
                "g.zip",
                _make_zip({"index.html": b"hi", "a/b.js": b"js"}),
                "application/zip",
            )
        },
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: logged_in_games.get(f"/api/games/{game_id}/h5/index.html"),
                range(8),
            )
        )
    assert [response.status_code for response in results] == [200] * 8
    assert not any(".h5-" in path for path in _files(runtime_root))
    assert _exists(runtime_root, f"game/h5/{cid}/h5/index.html")


def test_h5_corrupt_zip_in_data_root_fails_at_extract(logged_in_games, storage_root, runtime_root):
    """宿主手改坏了数据根里的 zip：解包那一刻报 400，运行时根不留残留。"""
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    (Path(storage_root) / f"game/h5/{cid}/game.zip").write_bytes(b"not a zip")

    response = logged_in_games.get(f"/api/games/{game_id}/h5/index.html")
    assert response.status_code == 400
    assert response.json()["message"]
    assert not any(".h5-" in path for path in _files(runtime_root))
    assert not _exists(runtime_root, f"game/h5/{cid}/h5/index.html")


def test_h5_zip_missing_in_data_root_returns_404(logged_in_games, storage_root):
    """宿主手删了数据根里的 zip：404（解包产物也没有来源）。"""
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    (Path(storage_root) / f"game/h5/{cid}/game.zip").unlink()

    response = logged_in_games.get(f"/api/games/{game_id}/h5/index.html")
    assert response.status_code == 404
    assert "不存在" in response.json()["message"]


def test_h5_assets_stay_open_while_rest_requires_login(client, user, do_login):
    """H5 资源接口是唯一免登录业务接口（沙箱 iframe 拿不到 cookie），其余游戏接口 401。"""
    do_login(client)
    game_id = _upload_h5(client)
    client.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"index.html": b"ok"}), "application/zip")},
    )
    assert client.post("/api/logout").status_code == 200

    assert client.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    assert client.get(f"/api/games/{game_id}/play").status_code == 401
    assert client.get(f"/api/games/{game_id}/cover").status_code == 401
    assert client.get("/api/games").status_code == 401
    assert client.get(f"/api/games/manage/{game_id}").status_code == 401


def test_h5_rejects_zip_without_entry(logged_in_games, storage_root):
    game_id = _upload_h5(logged_in_games)
    before = _files(storage_root)
    response = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"a.js": b"x"}), "application/zip")},
    )
    assert response.status_code == 400
    assert "index.html" in response.json()["message"]
    assert _files(storage_root) == before  # 失败不留新文件


@pytest.mark.parametrize("bad_name", ["../evil.js", "/abs.js", "a/../../b.js", "a\\b.js"])
def test_h5_rejects_zip_slip(logged_in_games, storage_root, bad_name):
    game_id = _upload_h5(logged_in_games)
    before = _files(storage_root)
    response = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={
            "file": (
                "g.zip",
                _make_zip({"index.html": b"ok", bad_name: b"evil"}),
                "application/zip",
            )
        },
    )
    assert response.status_code == 400
    assert _files(storage_root) == before


@pytest.mark.parametrize(
    "bad_name",
    [
        "a:b.png",  # NTFS 上会被当成数据流
        "x?.png",
        "star*.png",
        'quote".png',
        "less<.png",
        "pipe|.png",
        "trailing./a.png",  # Windows 静默丢掉结尾的点
        "trailing /a.png",  # 结尾空格同理
        "sub/NUL.png",  # 保留设备名（带扩展名也算）
        "sub/com1.txt",
    ],
)
def test_h5_rejects_windows_illegal_entry_names(logged_in_games, storage_root, bad_name):
    """ZIP 里合法、NTFS 上非法的条目名要在收下之前就拒掉。

    这些名字在 Linux 上能正常落盘，在 Windows 上却会解包到一半抛异常——所以刻意不分平台，
    两边用同一套规则拒。
    """
    game_id = _upload_h5(logged_in_games)
    before = _files(storage_root)
    response = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={
            "file": (
                "g.zip",
                _make_zip({"index.html": b"ok", bad_name: b"x"}),
                "application/zip",
            )
        },
    )
    assert response.status_code == 400
    assert _files(storage_root) == before


class _RawFilename(str):
    """把「原始字节」当文件名交给 zipfile。

    `zipfile` 写包时会先试 `filename.encode("ascii")`：成功就当普通名字写出去、不置
    UTF-8 标志位（0x800），失败才改用 UTF-8 并置上标志位。这里让 ascii 那一步直接返回
    我们想要的 GBK 字节，就造出了「老工具打的包」——名字是 GBK、且不带标志位。
    """

    def __new__(cls, text: str, raw: bytes):
        instance = super().__new__(cls, text)
        instance._raw = raw
        return instance

    def encode(self, encoding="utf-8", errors="strict"):
        if encoding == "ascii":
            return self._raw
        return super().encode(encoding, errors)


def _make_legacy_gbk_zip(files: dict[str, bytes]) -> bytes:
    """造一个「老压缩工具打的中文包」：条目名是 GBK 字节、且不带 UTF-8 标志位。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(zipfile.ZipInfo(_RawFilename(name, name.encode("gbk"))), data)
    return buffer.getvalue()


def test_h5_decodes_gbk_entry_names(logged_in_games, storage_root, runtime_root):
    """不带 UTF-8 标志位的中文条目名按 GBK 还原，而不是解出一串 cp437 乱码。"""
    payload = _make_legacy_gbk_zip({"index.html": b"ok", "素材/图.png": b"png"})
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    response = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", payload, "application/zip")},
    )
    assert response.status_code == 201, response.text
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    assert _exists(runtime_root, f"game/h5/{cid}/h5/index.html")
    assert _exists(runtime_root, f"game/h5/{cid}/h5/素材/图.png")


def test_h5_rejects_paths_too_long_for_windows(
    logged_in_games, storage_root, monkeypatch
):
    """Windows 上「运行时根 + 相对路径」越界要在收下之前报错（其它平台不受影响）。

    深度只出现在运行时根（解包产物都在那里），所以长度是按运行时根算的。
    """
    game_id = _upload_h5(logged_in_games)
    # 相对路径本身合法（约 380 字符、19 段，都没到 512 / 32 的上限），
    # 但叠加运行时根前缀后在 Windows 上必然超过 240
    deep = "/".join(["d" * 20] * 18 + ["a.js"])
    payload = _make_zip({"index.html": b"ok", deep: b"x"})

    # Linux 上不检查：同样的包能收下
    ok = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", payload, "application/zip")},
    )
    assert ok.status_code == 201, ok.text
    assert _exists(storage_root, f"game/h5/{_cartridge_of(logged_in_games.app, game_id)}/game.zip")

    monkeypatch.setattr(games_archive, "IS_WINDOWS", True)
    rejected = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", payload, "application/zip")},
    )
    assert rejected.status_code == 400
    assert "过长" in rejected.json()["message"]


def test_h5_rejects_duplicate_paths_case_insensitive(logged_in_games, storage_root):
    game_id = _upload_h5(logged_in_games)
    before = _files(storage_root)
    response = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={
            "file": (
                "g.zip",
                _make_zip({"index.html": b"a", "Index.html": b"b"}),
                "application/zip",
            )
        },
    )
    assert response.status_code == 400
    assert "重名" in response.json()["message"]
    assert _files(storage_root) == before


def test_h5_strips_single_wrapper_dir(logged_in_games):
    """整个游戏套在一层目录里时自动剥掉前缀；根已有入口时 assets/ 不被误剥。"""
    game_id = _upload_h5(logged_in_games)
    wrapped = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={
            "file": (
                "g.zip",
                _make_zip({"game/index.html": b"wrapped", "game/a.js": b"js"}),
                "application/zip",
            )
        },
    )
    assert wrapped.status_code == 201
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").content == b"wrapped"
    assert logged_in_games.get(f"/api/games/{game_id}/h5/a.js").content == b"js"

    flat = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={
            "file": (
                "g.zip",
                _make_zip({"index.html": b"flat", "assets/a.js": b"nested"}),
                "application/zip",
            )
        },
    )
    assert flat.status_code == 201
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").content == b"flat"
    assert logged_in_games.get(f"/api/games/{game_id}/h5/assets/a.js").content == b"nested"


def test_h5_reupload_replaces_whole_package(logged_in_games, storage_root, runtime_root):
    """重传整包替换：新内容生效，旧解包产物作废，数据根里只留最新的 zip。"""
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={
            "file": (
                "g.zip",
                _make_zip({"index.html": b"v1", "old.js": b"old"}),
                "application/zip",
            )
        },
    )
    assert logged_in_games.get(f"/api/games/{game_id}/h5/old.js").content == b"old"
    assert _exists(runtime_root, f"game/h5/{cid}/h5/old.js")

    logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"index.html": b"v2"}), "application/zip")},
    )
    # 重传那一刻旧解包产物就被作废了（不必等到下次访问）
    assert not _exists(runtime_root, f"game/h5/{cid}/h5/old.js")
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").content == b"v2"
    assert logged_in_games.get(f"/api/games/{game_id}/h5/old.js").status_code == 404
    assert _exists(storage_root, f"game/h5/{cid}/game.zip")


def test_h5_cleanup_on_delete(logged_in_games, storage_root, runtime_root):
    """H5 解包产物按需生成；删除游戏时两个根都清空。"""
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    # 先访问一次，让运行时根产生解包产物
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    assert _exists(runtime_root, f"game/h5/{cid}/h5/index.html")

    assert logged_in_games.delete(f"/api/games/manage/{game_id}").status_code == 200
    assert _files(storage_root) == set()
    assert _files(runtime_root) == set()


def test_h5_enforces_limits(logged_in_games, storage_root, monkeypatch):
    game_id = _upload_h5(logged_in_games)
    before = _files(storage_root)
    payload = _make_zip({"index.html": b"a", "b.js": b"b"})

    monkeypatch.setattr(games_archive, "MAX_ENTRIES", 1)
    too_many = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", payload, "application/zip")},
    )
    assert too_many.status_code == 400
    assert "数量" in too_many.json()["message"]
    monkeypatch.undo()

    monkeypatch.setattr(games_archive, "MAX_TOTAL_SIZE", 1)
    too_big = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", payload, "application/zip")},
    )
    assert too_big.status_code == 400
    assert _files(storage_root) == before


def test_h5_path_helpers():
    assert games_archive.normalize_h5_path("assets/app.js") == "assets/app.js"
    with pytest.raises(Exception):
        games_archive.normalize_h5_path("../evil.js")
    with pytest.raises(Exception):
        games_archive.normalize_h5_path("/abs.js")


def test_h5_missing_asset_returns_404(logged_in_games):
    game_id = _upload_h5(logged_in_games)
    logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"index.html": b"x"}), "application/zip")},
    )
    assert logged_in_games.get(f"/api/games/{game_id}/h5/nope.js").status_code == 404
    # 非 h5 游戏不提供 h5 资源
    flash = _create_game(logged_in_games, "F", "a.swf", b"swf-body").json()["data"]
    assert logged_in_games.get(f"/api/games/{flash['id']}/h5/index.html").status_code == 404


# ---------- 攻略（ZIP 静态站 / PDF） ----------


def _upload_guide_zip(client, game_id: int, payload: bytes, filename="guide.zip"):
    """上传攻略 zip（multipart 里只有一个 file 字段）。"""
    return client.post(
        f"/api/games/manage/{game_id}/guide",
        files={"file": (filename, payload, "application/zip")},
    )


def _upload_guide(client, game_id: int, files: dict[str, bytes]):
    """把 {包内路径: 内容} 打成一个 zip 上传（最常用的写法）。"""
    return _upload_guide_zip(client, game_id, _make_zip(files))


_PDF_BODY = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def _upload_guide_pdf(client, game_id: int, payload=_PDF_BODY, filename="guide.pdf"):
    """上传攻略 PDF（multipart 里只有一个 file 字段）。"""
    return client.post(
        f"/api/games/manage/{game_id}/guide",
        files={"file": (filename, payload, "application/pdf")},
    )


def _guide_kind_of(app, game_id: int) -> str:
    """直接读库里 games.guide_kind，确认攻略状态确实落库。"""
    with Session(app.state.engine) as session:
        return session.get(Game, game_id).guide_kind


def _guide_game(logged_in_games, name="攻略 demo"):
    """建一个最简单的游戏（攻略与游戏类型无关，用 flash 本体最省事）。"""
    create = _create_game(logged_in_games, name, "seed.swf", b"FWS")
    assert create.status_code == 201
    return create.json()["data"]["id"]


def test_guide_upload_and_serve(logged_in_games, storage_root, runtime_root):
    """上传 zip→数据根只落 guide.zip；查看时才解包，入口与子资源都能取到。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    upload = _upload_guide(
        logged_in_games,
        game_id,
        {"index.html": b"<html>guide</html>", "assets/css/site.css": b"body{}"},
    )
    assert upload.status_code == 201
    assert upload.json()["data"]["has_guide"] is True
    assert upload.json()["data"]["guide_kind"] == "zip"
    # 上传只落 zip：两个根里都还没有解包产物
    assert _exists(storage_root, f"game/flash/{cid}/guide.zip")
    assert not _exists(storage_root, f"game/flash/{cid}/guide/index.html")
    assert not _exists(runtime_root, f"game/flash/{cid}/guide/index.html")

    entry = logged_in_games.get(f"/api/games/{game_id}/guide/index.html")
    assert entry.status_code == 200
    assert entry.content == b"<html>guide</html>"
    assert entry.headers["content-type"].startswith("text/html")
    assert entry.headers["cache-control"] == "no-cache, must-revalidate"
    # 攻略与 H5 不同：不隔离、不放行匿名
    assert "content-security-policy" not in entry.headers
    # 查看之后运行时根才有解包产物
    assert _exists(runtime_root, f"game/flash/{cid}/guide/index.html")
    assert _exists(runtime_root, f"game/flash/{cid}/guide/assets/css/site.css")

    css = logged_in_games.get(f"/api/games/{game_id}/guide/assets/css/site.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")

    head = logged_in_games.head(f"/api/games/{game_id}/guide/index.html")
    assert head.status_code == 200
    assert head.headers["content-length"] == str(len(b"<html>guide</html>"))

    listed = logged_in_games.get("/api/games").json()["data"]
    assert [item["has_guide"] for item in listed if item["id"] == game_id] == [True]


def test_guide_second_view_does_not_reextract(logged_in_games, runtime_root):
    """已经解包过就只读：再看两次，解包产物的 mtime 一个纳秒都不动。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"v1"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
    entry = Path(runtime_root) / f"game/flash/{cid}/guide/index.html"
    stamp = entry.stat().st_mtime_ns

    for _ in range(2):
        assert (
            logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
        )
    assert entry.stat().st_mtime_ns == stamp


def test_guide_wrapper_dir_stripped(logged_in_games, runtime_root):
    """整包套一层目录（右键压缩的常态）自动剥掉，解包后入口仍在根目录。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    upload = _upload_guide(
        logged_in_games,
        game_id,
        {"myguide/index.html": b"wrapped", "myguide/pages/1.html": b"p1"},
    )
    assert upload.status_code == 201, upload.text
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").content == b"wrapped"
    assert _exists(runtime_root, f"game/flash/{cid}/guide/pages/1.html")


def test_guide_requires_file(logged_in_games, storage_root):
    """不带 file 字段直接 400，磁盘什么都不留。"""
    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)
    response = logged_in_games.post(f"/api/games/manage/{game_id}/guide")
    assert response.status_code == 400
    assert "ZIP" in response.json()["message"]
    assert _files(storage_root) == before


def test_guide_rejects_unsupported_extension(logged_in_games, storage_root):
    """攻略只收 ZIP 与 PDF：扩展名不对就 400，连内容都不看。"""
    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)
    response = _upload_guide_zip(
        logged_in_games, game_id, _make_zip({"index.html": b"x"}), filename="guide.rar"
    )
    assert response.status_code == 400
    assert "ZIP" in response.json()["message"]
    assert "PDF" in response.json()["message"]
    assert _files(storage_root) == before


def test_guide_requires_index(logged_in_games, storage_root, runtime_root):
    """包里没有 index.html 直接拒，且两个根都零残留。"""
    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)
    before_runtime = _files(runtime_root)
    response = _upload_guide(logged_in_games, game_id, {"pages/1.html": b"x"})
    assert response.status_code == 400
    assert "index.html" in response.json()["message"]
    assert _files(storage_root) == before
    assert _files(runtime_root) == before_runtime


def test_guide_entry_name_is_case_insensitive(logged_in_games, runtime_root):
    """入口大小写不敏感，解包后统一落成小写 index.html，入口地址才固定。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    assert _upload_guide(logged_in_games, game_id, {"INDEX.HTML": b"hi"}).status_code == 201
    assert (
        logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
    )
    assert _exists(runtime_root, f"game/flash/{cid}/guide/index.html")


def test_guide_rejects_index_htm(logged_in_games):
    """攻略只认 index.html（H5 那个 index.htm 的例外不跟着来）。"""
    game_id = _guide_game(logged_in_games)
    response = _upload_guide(logged_in_games, game_id, {"index.htm": b"hi"})
    assert response.status_code == 400
    assert "index.html" in response.json()["message"]


@pytest.mark.parametrize(
    "bad_name", ["../evil.js", "/abs.js", "a/../../b.js", "a\\b.js", "a?b.js"]
)
def test_guide_rejects_bad_paths(logged_in_games, storage_root, bad_name):
    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)
    response = _upload_guide(
        logged_in_games, game_id, {"index.html": b"ok", bad_name: b"evil"}
    )
    assert response.status_code == 400
    assert _files(storage_root) == before


def test_guide_rejects_duplicate_paths_case_insensitive(logged_in_games):
    game_id = _guide_game(logged_in_games)
    response = _upload_guide(
        logged_in_games, game_id, {"index.html": b"a", "Index.html": b"b"}
    )
    assert response.status_code == 400
    assert "重名" in response.json()["message"]


def test_guide_reupload_replaces_whole_package(
    logged_in_games, storage_root, runtime_root
):
    """重传就是整包替换：旧解包产物作废、这一版没有的文件消失、不留暂存目录。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"v1", "old.css": b"old"})
    assert (
        logged_in_games.get(f"/api/games/{game_id}/guide/old.css").status_code == 200
    )
    assert _exists(runtime_root, f"game/flash/{cid}/guide/old.css")

    again = _upload_guide(
        logged_in_games, game_id, {"index.html": b"v2", "new.css": b"new"}
    )
    assert again.status_code == 201
    # 重传那一刻旧解包产物就作废了（不必等到下次查看）
    assert not _exists(runtime_root, f"game/flash/{cid}/guide/old.css")
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").content == b"v2"
    assert _exists(runtime_root, f"game/flash/{cid}/guide/new.css")
    assert logged_in_games.get(f"/api/games/{game_id}/guide/old.css").status_code == 404
    assert not [p for p in _files(runtime_root) if "/.guide-" in p]
    assert _exists(storage_root, f"game/flash/{cid}/guide.zip")


def test_guide_upload_pdf_and_serve(logged_in_games, storage_root, runtime_root):
    """PDF 攻略：数据根只落 guide.pdf、运行时根不留解包产物；GET 返回内联 PDF。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)

    upload = _upload_guide_pdf(logged_in_games, game_id)
    assert upload.status_code == 201
    data = upload.json()["data"]
    assert data["has_guide"] is True
    assert data["guide_kind"] == "pdf"
    assert _exists(storage_root, f"game/flash/{cid}/guide.pdf")
    assert not _exists(storage_root, f"game/flash/{cid}/guide.zip")
    assert not (Path(runtime_root) / "game" / "flash" / cid / "guide").exists()

    response = logged_in_games.get(f"/api/games/{game_id}/guide.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == _PDF_BODY

    head = logged_in_games.head(f"/api/games/{game_id}/guide.pdf")
    assert head.status_code == 200
    assert head.headers["content-type"] == "application/pdf"
    assert head.headers["content-length"] == str(len(_PDF_BODY))
    # PDF 不解包：查看后运行时根仍然干净，ZIP 入口也不存在
    assert not (Path(runtime_root) / "game" / "flash" / cid / "guide").exists()
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 404


def test_guide_pdf_replaces_zip_and_zip_replaces_pdf(
    logged_in_games, storage_root, runtime_root
):
    """一份攻略只有一种形态：传 PDF 删 zip 与其解包产物，再传 zip 删 PDF。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"zip"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
    assert _exists(runtime_root, f"game/flash/{cid}/guide/index.html")

    pdf = _upload_guide_pdf(logged_in_games, game_id)
    assert pdf.status_code == 201
    assert pdf.json()["data"]["guide_kind"] == "pdf"
    assert not _exists(storage_root, f"game/flash/{cid}/guide.zip")
    assert not (Path(runtime_root) / "game" / "flash" / cid / "guide").exists()
    assert logged_in_games.get(f"/api/games/{game_id}/guide.pdf").status_code == 200

    again = _upload_guide(logged_in_games, game_id, {"index.html": b"zip2"})
    assert again.status_code == 201
    assert again.json()["data"]["guide_kind"] == "zip"
    assert not _exists(storage_root, f"game/flash/{cid}/guide.pdf")
    assert logged_in_games.get(f"/api/games/{game_id}/guide.pdf").status_code == 404
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").content == b"zip2"


def test_guide_pdf_rejects_invalid_content(logged_in_games, storage_root):
    """文件名是 .pdf 但内容不是 PDF：400 且磁盘零残留。"""
    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)
    response = _upload_guide_pdf(logged_in_games, game_id, payload=b"not a pdf")
    assert response.status_code == 400
    assert "PDF" in response.json()["message"]
    assert _files(storage_root) == before


def test_guide_pdf_requires_login(client, user, do_login):
    """PDF 攻略与 ZIP 攻略一样要登录。"""
    do_login(client)
    game_id = _guide_game(client)
    assert _upload_guide_pdf(client, game_id).status_code == 201
    assert client.post("/api/logout").status_code == 200
    assert client.get(f"/api/games/{game_id}/guide.pdf").status_code == 401
    assert client.head(f"/api/games/{game_id}/guide.pdf").status_code == 401
    assert _upload_guide_pdf(client, game_id).status_code == 401


def test_guide_pdf_missing_returns_404(logged_in_games):
    """没有 PDF 攻略时（包括只有 ZIP 攻略）读 /guide.pdf 一律 404。"""
    game_id = _guide_game(logged_in_games)
    assert logged_in_games.get(f"/api/games/{game_id}/guide.pdf").status_code == 404
    assert logged_in_games.head(f"/api/games/{game_id}/guide.pdf").status_code == 404
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide.pdf").status_code == 404


def test_guide_delete_zip_removes_files_and_state(
    logged_in_games, storage_root, runtime_root
):
    """删除 ZIP 攻略：数据根文件、运行时解包产物、库里的形态一起清掉。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"x", "a.css": b"a"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
    assert _exists(runtime_root, f"game/flash/{cid}/guide/index.html")

    response = logged_in_games.delete(f"/api/games/manage/{game_id}/guide")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["has_guide"] is False
    assert data["guide_kind"] == ""
    assert _guide_kind_of(logged_in_games.app, game_id) == ""
    assert not _exists(storage_root, f"game/flash/{cid}/guide.zip")
    assert not (Path(runtime_root) / "game" / "flash" / cid / "guide").exists()
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 404
    # 删攻略不影响本体
    assert logged_in_games.get(f"/api/games/{game_id}/play").status_code == 200


def test_guide_delete_pdf(logged_in_games, storage_root):
    """删除 PDF 攻略：guide.pdf 消失、读取 404、库里形态清空。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    assert _upload_guide_pdf(logged_in_games, game_id).status_code == 201

    response = logged_in_games.delete(f"/api/games/manage/{game_id}/guide")
    assert response.status_code == 200
    assert response.json()["data"]["guide_kind"] == ""
    assert not _exists(storage_root, f"game/flash/{cid}/guide.pdf")
    assert logged_in_games.get(f"/api/games/{game_id}/guide.pdf").status_code == 404
    assert _guide_kind_of(logged_in_games.app, game_id) == ""


def test_guide_delete_without_guide_is_idempotent(logged_in_games):
    """没有攻略时 DELETE 仍返回 200；重复删除不再刷新 updated_at。"""
    game_id = _guide_game(logged_in_games)
    assert logged_in_games.delete(f"/api/games/manage/{game_id}/guide").status_code == 200

    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    assert logged_in_games.delete(f"/api/games/manage/{game_id}/guide").status_code == 200
    stamp = logged_in_games.get(f"/api/games/manage/{game_id}").json()["data"]["updated_at"]
    again = logged_in_games.delete(f"/api/games/manage/{game_id}/guide")
    assert again.status_code == 200
    assert again.json()["data"]["has_guide"] is False
    latest = logged_in_games.get(f"/api/games/manage/{game_id}").json()["data"]["updated_at"]
    assert latest == stamp


def test_guide_delete_requires_login(client, user, do_login):
    """删除攻略与其它管理接口一样要登录。"""
    do_login(client)
    game_id = _guide_game(client)
    assert _upload_guide(client, game_id, {"index.html": b"x"}).status_code == 201
    assert client.post("/api/logout").status_code == 200
    assert client.delete(f"/api/games/manage/{game_id}/guide").status_code == 401


def test_guide_delete_missing_game_returns_404(logged_in_games):
    assert logged_in_games.delete("/api/games/manage/999999/guide").status_code == 404


def test_guide_kind_survives_cartridge_rename(logged_in_games, storage_root):
    """改卡带ID 只搬目录，攻略形态保留，文件跟着到新目录、仍可打开。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    assert _upload_guide_pdf(logged_in_games, game_id).status_code == 201

    assert _rename(logged_in_games, game_id, "RENAMED-1").status_code == 200
    assert _guide_kind_of(logged_in_games.app, game_id) == "pdf"
    assert _exists(storage_root, "game/flash/RENAMED-1/guide.pdf")
    assert not _exists(storage_root, f"game/flash/{cid}/guide.pdf")
    assert logged_in_games.get(f"/api/games/{game_id}/guide.pdf").status_code == 200


def test_guide_delete_with_split_roots(split_logged_in, split_app):
    """数据根与运行时根分开时，删除攻略把两边的产物都清掉。"""
    storage = Path(split_app.state.settings.STORAGE_ROOT)
    runtime = Path(split_app.state.settings.runtime_root)
    game_id = _guide_game(split_logged_in)
    cid = _cartridge_of(split_app, game_id)
    _upload_guide(split_logged_in, game_id, {"index.html": b"x"})
    assert split_logged_in.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
    assert _exists(storage, f"game/flash/{cid}/guide.zip")
    assert _exists(runtime, f"game/flash/{cid}/guide/index.html")

    assert split_logged_in.delete(f"/api/games/manage/{game_id}/guide").status_code == 200
    assert not _exists(storage, f"game/flash/{cid}/guide.zip")
    assert not (runtime / "game" / "flash" / cid / "guide").exists()


def test_guide_delete_keeps_state_when_file_delete_fails(logged_in_games, monkeypatch):
    """文件删不掉时返回 500，且库里的形态保持原样，方便重试。"""
    game_id = _guide_game(logged_in_games)
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})

    def fail(_key):
        raise StorageError("删除文件失败，请检查存储目录权限。")

    monkeypatch.setattr(logged_in_games.app.state.storage, "delete", fail)
    response = logged_in_games.delete(f"/api/games/manage/{game_id}/guide")
    assert response.status_code == 500
    assert _guide_kind_of(logged_in_games.app, game_id) == "zip"


def test_game_lists_do_not_stat_guide_files(logged_in_games, monkeypatch):
    """攻略形态来自库：列表接口不再对攻略文件做 stat。"""
    game_id = _guide_game(logged_in_games)
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})

    def boom(*_args, **_kwargs):
        raise AssertionError("列表不应 stat 攻略文件")

    monkeypatch.setattr(logged_in_games.app.state.storage, "stat", boom)
    assert logged_in_games.get("/api/games").status_code == 200
    assert logged_in_games.get("/api/games/manage").status_code == 200
    assert logged_in_games.get(f"/api/games/manage/{game_id}").status_code == 200


def test_guide_requires_login(client, user, do_login):
    """攻略资源与其它业务接口一样要登录（与 H5 的免登录正好相反）。"""
    do_login(client)
    game_id = _guide_game(client)
    assert _upload_guide(client, game_id, {"index.html": b"x"}).status_code == 201
    assert client.post("/api/logout").status_code == 200
    assert client.get(f"/api/games/{game_id}/guide/index.html").status_code == 401
    assert client.head(f"/api/games/{game_id}/guide/index.html").status_code == 401
    assert (
        _upload_guide_zip(client, game_id, _make_zip({"index.html": b"x"})).status_code
        == 401
    )


def test_guide_missing_returns_404(logged_in_games):
    game_id = _guide_game(logged_in_games)
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 404
    assert logged_in_games.get(f"/api/games/{game_id}/guide/nope.css").status_code == 404
    # 上传后子资源仍然只认实际存在的文件
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide/nope.css").status_code == 404


def test_guide_removed_with_game_delete(logged_in_games, storage_root, runtime_root):
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
    assert logged_in_games.delete(f"/api/games/manage/{game_id}").status_code == 200
    assert not (Path(storage_root) / "game" / "flash" / cid).exists()
    assert not (Path(runtime_root) / "game" / "flash" / cid).exists()


def test_guide_kept_on_body_replacement(logged_in_games, storage_root):
    """同类型换本体不影响攻略包与它的解包产物。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200

    replaced = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("new.swf", b"FWS-new", "application/octet-stream")},
    )
    assert replaced.status_code == 201, replaced.text
    body = replaced.json()["data"]
    assert body["game_type"] == "flash"
    assert body["has_guide"] is True
    assert body["guide_kind"] == "zip"
    assert _exists(storage_root, f"game/flash/{cid}/guide.zip")
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200


def test_guide_state_comes_from_database(logged_in_games, storage_root):
    """攻略形态以库里的 games.guide_kind 为准，不再每次列表 stat 磁盘。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    game_dir = Path(storage_root) / "game" / "flash" / cid
    guide_zip = game_dir / "guide.zip"
    guide_pdf = game_dir / "guide.pdf"

    def state():
        listed = logged_in_games.get("/api/games").json()["data"]
        item = next(item for item in listed if item["id"] == game_id)
        return item["has_guide"], item["guide_kind"]

    # 没有攻略时，宿主手动放进文件也不会被当成攻略
    assert state() == (False, "")
    game_dir.mkdir(parents=True, exist_ok=True)
    guide_pdf.write_bytes(_PDF_BODY)
    assert state() == (False, "")
    assert logged_in_games.get(f"/api/games/{game_id}/guide.pdf").status_code == 404

    # 正常上传后由库记录形态；宿主删掉文件也不会改变库里的状态（打开时才 404）
    assert _upload_guide(logged_in_games, game_id, {"index.html": b"x"}).status_code == 201
    assert state() == (True, "zip")
    assert _guide_kind_of(logged_in_games.app, game_id) == "zip"
    guide_zip.unlink()
    assert state() == (True, "zip")
    assert _guide_kind_of(logged_in_games.app, game_id) == "zip"
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 404

    # 删除攻略会同时清掉库里的形态
    assert logged_in_games.delete(f"/api/games/manage/{game_id}/guide").status_code == 200
    assert state() == (False, "")
    assert _guide_kind_of(logged_in_games.app, game_id) == ""


def test_guide_enforces_limits(logged_in_games, storage_root, monkeypatch):
    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)

    monkeypatch.setattr(games_archive, "MAX_ENTRIES", 1)
    too_many = _upload_guide(
        logged_in_games, game_id, {"index.html": b"a", "b.css": b"b"}
    )
    assert too_many.status_code == 400
    assert "数量" in too_many.json()["message"]
    monkeypatch.undo()

    monkeypatch.setattr(games_archive, "MAX_TOTAL_SIZE", 1)
    too_big = _upload_guide(logged_in_games, game_id, {"index.html": b"a" * 64})
    assert too_big.status_code == 400
    assert _files(storage_root) == before


def test_guide_path_helpers():
    assert paths.guide_dir("flash", "AB-1") == "game/flash/AB-1/guide"
    assert paths.guide_zip_path("flash", "AB-1") == "game/flash/AB-1/guide.zip"
    assert paths.guide_pdf_path("flash", "AB-1") == "game/flash/AB-1/guide.pdf"
    assert paths.guide_entry_path("flash", "AB-1") == "game/flash/AB-1/guide/index.html"
    assert (
        paths.guide_asset_path("flash", "AB-1", "pages/1.html")
        == "game/flash/AB-1/guide/pages/1.html"
    )
    assert paths.guide_temp_dir("flash", "AB-1", "tok") == "game/flash/AB-1/.guide-tok"
    assert paths.h5_zip_path("h5", "AB-1") == "game/h5/AB-1/game.zip"
    assert paths.h5_entry_path("h5", "AB-1") == "game/h5/AB-1/h5/index.html"
    assert games_archive.normalize_guide_path("pages/mc/1.html") == "pages/mc/1.html"
    with pytest.raises(ValidationError):
        games_archive.normalize_guide_path("../evil.js")
    with pytest.raises(ValidationError):
        games_archive.normalize_guide_path("/abs.js")


# ---------- 两个根分开（RUNTIME_ROOT 与 STORAGE_ROOT 不同） ----------


def test_h5_extraction_goes_to_runtime_root_only(split_logged_in, split_app):
    """两个根分开时：数据根只放 zip，解包产物只出现在运行时根。"""
    storage = Path(split_app.state.settings.STORAGE_ROOT)
    runtime = Path(split_app.state.settings.runtime_root)
    assert storage != runtime

    game_id = _upload_h5(split_logged_in)
    cid = _cartridge_of(split_app, game_id)
    assert _exists(storage, f"game/h5/{cid}/game.zip")
    assert not (runtime / "game" / "h5" / cid).exists()

    assert split_logged_in.get(f"/api/games/{game_id}/h5/index.html").status_code == 200
    assert _exists(runtime, f"game/h5/{cid}/h5/index.html")
    assert not _exists(storage, f"game/h5/{cid}/h5/index.html")


@pytest.mark.parametrize("kind", ["h5", "guide"])
@pytest.mark.parametrize("action", ["delete", "reupload", "rename"])
def test_runtime_cleanup_with_split_roots(split_logged_in, split_app, kind, action):
    """两个根分开时，删游戏 / 重传资源 / 改卡带ID 都要把运行时根的产物作废。"""
    runtime = Path(split_app.state.settings.runtime_root)
    storage = Path(split_app.state.settings.STORAGE_ROOT)

    game_id = _upload_h5(split_logged_in, name=f"清理 {kind} {action}")
    cid = _cartridge_of(split_app, game_id)
    if kind == "guide":
        assert (
            _upload_guide(split_logged_in, game_id, {"index.html": b"x"}).status_code == 201
        )
        url = f"/api/games/{game_id}/guide/index.html"
        sub = "guide/index.html"
    else:
        url = f"/api/games/{game_id}/h5/index.html"
        sub = "h5/index.html"
    assert split_logged_in.get(url).status_code == 200
    assert _exists(runtime, f"game/h5/{cid}/{sub}")

    if action == "delete":
        assert split_logged_in.delete(f"/api/games/manage/{game_id}").status_code == 200
    elif action == "reupload":
        if kind == "guide":
            assert (
                _upload_guide(split_logged_in, game_id, {"index.html": b"y"}).status_code
                == 201
            )
        else:
            reuploaded = split_logged_in.post(
                f"/api/games/manage/{game_id}/assets",
                data={"kind": "game"},
                files={
                    "file": (
                        "new.zip",
                        _make_zip({"index.html": b"y"}),
                        "application/zip",
                    )
                },
            )
            assert reuploaded.status_code == 201
    else:
        assert _rename(split_logged_in, game_id, "RENAMED-1").status_code == 200

    if action == "reupload":
        # 旧解包产物立即作废；数据根的原始文件仍保留
        assert not _exists(runtime, f"game/h5/{cid}/{sub}")
        assert (storage / "game" / "h5" / cid).exists()
    else:
        assert not (runtime / "game" / "h5" / cid).exists()
        assert not (storage / "game" / "h5" / cid).exists()


# ---------- 搬运（7k7k / 4399） ----------


def test_importer_site_and_id_parsing():
    assert importer.detect_site("https://www.7k7k.com/flash/205829.htm") == "7k7k"
    assert importer.detect_site("https://www.4399.com/flash/1172_1.htm") == "4399"
    assert importer.detect_site("https://flash.homes/flash/F8YX-1DNE-JQG9") == "flash.homes"
    assert importer.detect_site("https://example.com/game") is None
    assert importer.detect_site("https://evil.com/?x=7k7k") is None
    assert importer.detect_site("https://evil.com/flash.homes/flash/F8YX-1DNE-JQG9") is None
    assert importer.game_id_from_arg("https://www.7k7k.com/flash/205829.htm", "7k7k") == "205829"
    assert importer.game_id_from_arg("https://www.4399.com/flash/1172_1.htm", "4399") == "1172"
    assert (
        importer.game_id_from_arg("https://flash.homes/flash/F8YX-1DNE-JQG9", "flash.homes")
        == "F8YX-1DNE-JQG9"
    )
    # 下载页地址、连写不带横线的短码都能归一化成页面 slug
    assert (
        importer.game_id_from_arg(
            "https://flash.homes/flash/F8YX-1DNE-JQG9/download", "flash.homes"
        )
        == "F8YX-1DNE-JQG9"
    )
    assert (
        importer.game_id_from_arg("https://flash.homes/flash/f8yx1dnejqg9", "flash.homes")
        == "F8YX-1DNE-JQG9"
    )
    with pytest.raises(importer.DownloadError):
        importer.game_id_from_arg("https://flash.homes/flash", "flash.homes")


def test_importer_swf_extraction():
    html = '<script>player.load("//s1.7k7k.com/a/b.swf")</script>'
    assert importer.is_ruffle_wrapper(html)
    assert importer.contains_swf(html)
    assert (
        importer.extract_swf_url(html, "https://www.7k7k.com/flash/1.htm")
        == "https://s1.7k7k.com/a/b.swf"
    )


def test_build_h5_zip(tmp_path):
    source = tmp_path / "body"
    (source / "assets").mkdir(parents=True)
    (source / "index.html").write_bytes(b"<html></html>")
    (source / "assets" / "app.js").write_bytes(b"js")
    dest = importer.build_h5_zip(source, tmp_path / "game.zip")
    with zipfile.ZipFile(dest) as archive:
        assert set(archive.namelist()) == {"index.html", "assets/app.js"}


# ---------- 搬运（flash.homes） ----------

FLASH_HOMES_SHA = "7a3dd0b6ae95e090811434fb451c9ca4961d417b63ff54b029b22caf0d1060d2"
FLASH_HOMES_SHOT = "2762d5d5a25b77da6619463dae4ea8e7f04f5f43310b69de5f14be17c857f007.webp"
FLASH_HOMES_SLUG = "F8YX-1DNE-JQG9"


def _flash_homes_page(*, title="金庸群侠传2贺岁版", player=True, ld=True, sha256=FLASH_HOMES_SHA):
    """仿 flash.homes 游戏页：播放器岛（props 被 HTML 转义）+ JSON-LD + meta 描述。"""
    props = {
        "id": [0, FLASH_HOMES_SLUG.replace("-", "")],
        "sha256": [0, sha256],
        "downloadHref": [0, f"/flash/{FLASH_HOMES_SLUG}/download"],
        "title": [0, title],
        "screenshot": [0, FLASH_HOMES_SHOT],
        "size": [0, 27662600],
        "stageRatio": [0, {"width": [0, 600], "height": [0, 480]}],
    }
    island = (
        '<astro-island uid="tTfWj" component-url="/_astro/PlayerStage.DrevgfuS.js" '
        'renderer-url="/_astro/client.DFmf6I1t.js" props="{}" ssr client="only">'
        "</astro-island>"
    ).format(html.escape(json.dumps(props, ensure_ascii=False)))
    ld_json = (
        '<script type="application/ld+json">{"@context":"https://schema.org",'
        '"@type":"CreativeWork","name":"金庸群侠传2贺岁版","image":[{"@type":"ImageObject",'
        f'"url":"https://screenshots.flash.homes/{FLASH_HOMES_SHOT}"}}]}}</script>'
    )
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<title>金庸群侠传2贺岁版 · Flash 保存计划</title>"
        '<meta name="description" content="金庸群侠传2贺岁版——已归档的 Flash 作品，浏览器直接播放。">'
        + (ld_json if ld else "")
        + "</head><body>"
        + (island if player else "<p>没有播放器</p>")
        + "</body></html>"
    )


def test_flash_homes_page_parsing(monkeypatch):
    monkeypatch.setattr(
        importer, "fetch_text", lambda session, url, referer=None, encoding=None: _flash_homes_page()
    )
    loaded = importer.load_flash_homes(None, f"https://flash.homes/flash/{FLASH_HOMES_SLUG}", FLASH_HOMES_SLUG)
    assert loaded["name"] == "金庸群侠传2贺岁版"
    assert loaded["page"] == f"https://flash.homes/flash/{FLASH_HOMES_SLUG}"
    assert loaded["cover"] == f"https://screenshots.flash.homes/{FLASH_HOMES_SHOT}"
    assert (loaded["width"], loaded["height"]) == (600, 480)
    # 站点自动生成的介绍尾巴去掉后没有剩余信息，desc 为空
    assert loaded["desc"] == ""
    assert importer.resolve_flash_homes(None, loaded) == (
        "flash",
        f"https://swf.flash.homes/{FLASH_HOMES_SHA}.swf",
    )


def test_flash_homes_page_without_player(monkeypatch):
    monkeypatch.setattr(
        importer, "fetch_text", lambda session, url, referer=None, encoding=None: _flash_homes_page(player=False)
    )
    with pytest.raises(importer.DownloadError):
        importer.load_flash_homes(None, "https://flash.homes/flash/X", FLASH_HOMES_SLUG)

    # 校验值不是 sha256 同样拒绝（避免拼出无效的 CDN 地址）
    monkeypatch.setattr(
        importer,
        "fetch_text",
        lambda session, url, referer=None, encoding=None: _flash_homes_page(sha256="not-a-hash"),
    )
    with pytest.raises(importer.DownloadError):
        importer.load_flash_homes(None, "https://flash.homes/flash/X", FLASH_HOMES_SLUG)


def test_flash_homes_missing_game(monkeypatch):
    def not_found(session, url, referer=None, encoding=None):
        raise importer.DownloadError(f"请求失败: {url} (HTTP 404)")

    monkeypatch.setattr(importer, "fetch_text", not_found)
    with pytest.raises(importer.DownloadError, match="不存在或已下架"):
        importer.load_flash_homes(None, "https://flash.homes/flash/X", FLASH_HOMES_SLUG)


def test_download_flash_homes_game(tmp_path, monkeypatch):
    monkeypatch.setattr(
        importer, "fetch_text", lambda session, url, referer=None, encoding=None: _flash_homes_page()
    )
    seen = {}

    def fake_download(session, url, dest, referer=None):
        seen["url"] = url
        seen["referer"] = referer
        Path(dest).write_bytes(b"swf-body")
        return str(dest), 8

    monkeypatch.setattr(importer, "download_file", fake_download)
    imported = importer.download_game(f"https://flash.homes/flash/{FLASH_HOMES_SLUG}", tmp_path)
    assert imported.kind == "flash"
    assert imported.site == "flash.homes"
    assert imported.source_id == FLASH_HOMES_SLUG
    assert imported.name == "金庸群侠传2贺岁版"
    assert imported.body_path.read_bytes() == b"swf-body"
    # 本体与封面都从 CDN 直取，并带上游戏页作 Referer
    assert seen["url"] == f"https://swf.flash.homes/{FLASH_HOMES_SHA}.swf"
    assert seen["referer"] == f"https://flash.homes/flash/{FLASH_HOMES_SLUG}"
    assert imported.cover_path is not None and imported.cover_path.suffix == ".webp"


def _fake_import(dest_dir, *, kind, name="搬运游戏", cover=False):
    work = Path(dest_dir)
    body = work / "body"
    body.mkdir(parents=True, exist_ok=True)
    cover_path = None
    if cover:
        cover_dir = work / "cover"
        cover_dir.mkdir(parents=True, exist_ok=True)
        cover_path = cover_dir / "cover.png"
        cover_path.write_bytes(b"cover-body")
    if kind == "flash":
        body_path = body / "game.swf"
        body_path.write_bytes(b"swf-body")
        h5_dir = None
    else:
        body_path = body / "index.html"
        body_path.write_bytes(b"<html>h5</html>")
        (body / "app.js").write_bytes(b"js")
        h5_dir = body
    return importer.ImportedGame(
        site="7k7k",
        source_id="1",
        name=name,
        description="来源描述",
        kind=kind,
        page_url="https://www.7k7k.com/flash/1.htm",
        body_path=body_path,
        h5_dir=h5_dir,
        cover_path=cover_path,
    )


def test_import_game_flash(logged_in_games, monkeypatch):
    monkeypatch.setattr(
        importer, "download_game", lambda url, work, session=None: _fake_import(work, kind="flash", cover=True)
    )
    response = logged_in_games.post(
        "/api/games/manage/import", json={"url": "https://www.7k7k.com/flash/1.htm"}
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["game_type"] == "flash"
    assert data["name"] == "搬运游戏"
    # 卡带ID 不用手填，取本体 CRC32 拼成 F-{CRC32}
    assert data["crc32"] == f"{zlib.crc32(b'swf-body') & 0xFFFFFFFF:08X}"
    assert data["cartridge_id"] == f"F-{data['crc32']}"
    assert data["game_path"] == f"game/flash/{data['cartridge_id']}/game.swf"
    assert data["cover_path"] == f"game/flash/{data['cartridge_id']}/cover.png"
    play = logged_in_games.get(f"/api/games/{data['id']}/play")
    assert play.content == b"swf-body"


def test_import_game_h5(logged_in_games, monkeypatch):
    monkeypatch.setattr(
        importer, "download_game", lambda url, work, session=None: _fake_import(work, kind="h5")
    )
    response = logged_in_games.post(
        "/api/games/manage/import", json={"url": "https://www.4399.com/flash/2.htm"}
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["game_type"] == "h5"
    # H5 取的是打包后 zip 的摘要，卡带ID 与落库的 crc32 始终一致
    assert data["cartridge_id"] == f"F-{data['crc32']}"
    assert data["game_path"] == f"game/h5/{data['cartridge_id']}/game.zip"
    assert logged_in_games.get(f"/api/games/{data['id']}/h5/index.html").content == b"<html>h5</html>"
    assert logged_in_games.get(f"/api/games/{data['id']}/h5/app.js").content == b"js"


def test_import_same_file_twice_rejected(logged_in_games, monkeypatch):
    """同一个本体文件只能搬一次：卡带ID 由 CRC32 生成，第二次搬进来正好撞上。"""
    monkeypatch.setattr(
        importer, "download_game", lambda url, work, session=None: _fake_import(work, kind="flash")
    )
    payload = {"url": "https://www.7k7k.com/flash/1.htm"}
    assert logged_in_games.post("/api/games/manage/import", json=payload).status_code == 201
    again = logged_in_games.post("/api/games/manage/import", json=payload)
    assert again.status_code == 400
    assert "搬运过" in again.json()["message"]
    # 第二次不该再建出条目
    assert len(logged_in_games.get("/api/games/manage").json()["data"]["items"]) == 1


def test_import_sanitizes_illegal_title(logged_in_games, monkeypatch):
    """站点标题带 `/`、`:`、结尾点号：无害化后入库，不该整个搬运失败。"""
    monkeypatch.setattr(
        importer,
        "download_game",
        lambda url, work, session=None: _fake_import(
            work, kind="flash", name="魂斗罗 / 30 条命:特别版."
        ),
    )
    response = logged_in_games.post(
        "/api/games/manage/import", json={"url": "https://www.7k7k.com/flash/1.htm"}
    )
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "魂斗罗 _ 30 条命_特别版"


def test_import_rejects_unknown_site(logged_in_games, storage_root):
    response = logged_in_games.post(
        "/api/games/manage/import", json={"url": "https://example.com/game"}
    )
    assert response.status_code == 400
    # 同时不应留下半成品条目
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []


def test_import_cleans_up_when_download_fails(logged_in_games, storage_root, monkeypatch):
    def boom(url, work, session=None):
        raise importer.DownloadError("页面解析失败")

    monkeypatch.setattr(importer, "download_game", boom)
    response = logged_in_games.post(
        "/api/games/manage/import", json={"url": "https://www.7k7k.com/flash/9.htm"}
    )
    assert response.status_code == 400
    assert response.json()["message"] == "页面解析失败"
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []


def test_import_requires_login(client):
    response = client.post(
        "/api/games/manage/import", json={"url": "https://www.7k7k.com/flash/1.htm"}
    )
    assert response.status_code == 401


def test_import_h5_packaging_failure_cleans_up(logged_in_games, monkeypatch):
    """H5 镜像缺入口导致打包失败：转成 400 且不留下半成品条目。"""
    def broken(dest_dir, *, kind, name="搬运游戏", cover=False):
        work = Path(dest_dir)
        body = work / "body"
        body.mkdir(parents=True, exist_ok=True)
        (body / "main.js").write_bytes(b"js")  # 没有 index.html
        return importer.ImportedGame(
            site="4399",
            source_id="2",
            name=name,
            description="",
            kind="h5",
            page_url="https://www.4399.com/flash/2.htm",
            body_path=body / "main.js",
            h5_dir=body,
            cover_path=None,
        )

    monkeypatch.setattr(
        importer,
        "download_game",
        lambda url, work, session=None: broken(work, kind="h5"),
    )
    response = logged_in_games.post(
        "/api/games/manage/import", json={"url": "https://www.4399.com/flash/2.htm"}
    )
    assert response.status_code == 400
    assert "index.html" in response.json()["message"]
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []




# --------------------------------------------------------------------------- #
# 网络上传：本体/封面都可以走直链（下载在服务端，先落临时文件再走普通上传管线）
# --------------------------------------------------------------------------- #
@pytest.fixture
def remote_files(monkeypatch):
    """把真正的下载换成内存字节表：键是完整地址，值是文件内容。

    只替换 `importer.download_file`，所以地址校验、扩展名判定、类型比对
    这些真实逻辑全都照跑。
    """
    files: dict[str, bytes] = {}

    def fake_download(session, url, dest, referer=None, *, max_bytes=None):
        if url not in files:
            raise importer.DownloadError(f"请求失败: {url} (HTTP 404)")
        data = files[url]
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        return str(dest), len(data)

    monkeypatch.setattr(importer, "download_file", fake_download)
    return files


def _crc32_of(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


def _create_from_url(client, name, url, game_type, **extra):
    extra.setdefault("cartridge_id", _next_cartridge_id())
    return client.post(
        "/api/games/manage",
        data={
            "name": name,
            "description": "",
            "body_url": url,
            "body_game_type": game_type,
            **extra,
        },
    )


def test_default_extensions_cover_every_game_type():
    """每个类型都要有默认后缀，且必须是该类型自己的合法扩展名。"""
    from backend.games.service import _DEFAULT_EXTENSIONS, _GAME_TYPE_EXTENSIONS

    assert set(_DEFAULT_EXTENSIONS) == set(GAME_TYPES)
    for game_type, extension in _DEFAULT_EXTENSIONS.items():
        assert extension in _GAME_TYPE_EXTENSIONS[game_type]


def test_create_game_from_body_url(logged_in_games, storage_root, remote_files):
    """网络上传本体：按所选类型入库，内容与 crc32 与本地文件上传一致。"""
    remote_files["https://cdn.test/roms/demo.gba"] = b"gba-rom"
    response = _create_from_url(
        logged_in_games, "网络本体", "https://cdn.test/roms/demo.gba", "gba"
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["game_type"] == "gba"
    assert body["game_path"] == f"game/gba/{body['cartridge_id']}/game.gba"
    assert body["size"] == len(b"gba-rom")
    assert body["crc32"] == _crc32_of(b"gba-rom")
    assert _read(storage_root, body["game_path"]) == b"gba-rom"


def test_create_game_from_body_url_without_extension_uses_type_default(
    logged_in_games, remote_files
):
    """地址看不出扩展名（网盘直链）：用所选类型的默认后缀。"""
    remote_files["https://pan.test/download?id=5"] = b"rom-bytes"
    response = _create_from_url(
        logged_in_games, "无后缀直链", "https://pan.test/download?id=5", "gba"
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["game_type"] == "gba"
    assert body["game_path"] == f"game/gba/{body['cartridge_id']}/game.gba"


def test_create_game_from_body_url_unknown_extension_uses_type_default(
    logged_in_games, remote_files
):
    """地址后缀不是已收录格式（如 .bin）：也退回所选类型的默认后缀。"""
    remote_files["https://cdn.test/roms/dump.bin"] = b"rom-bytes"
    response = _create_from_url(
        logged_in_games, "bin 直链", "https://cdn.test/roms/dump.bin", "segaMD"
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["game_path"].endswith("/game.md")


def test_create_game_from_body_url_type_mismatch_rejected(logged_in_games, remote_files):
    """地址能认出类型且与所选不一致：当场 400，不落任何条目与对象。"""
    remote_files["https://cdn.test/demo.zip"] = b"zip-bytes"
    response = _create_from_url(
        logged_in_games, "选错类型", "https://cdn.test/demo.zip", "gba"
    )
    assert response.status_code == 400
    # 报错文案用统一显示名（HTML5 / 任天堂 GBA），不甩 nes / segaMD 这种内部键值
    message = response.json()["message"]
    assert "HTML5" in message and "任天堂 GBA" in message
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []


def test_create_game_from_body_url_requires_game_type(logged_in_games, remote_files):
    """没选类型就提交：直接拒绝，不去下载。"""
    response = _create_from_url(
        logged_in_games, "缺类型", "https://cdn.test/whatever.gba", ""
    )
    assert response.status_code == 400
    assert "游戏类型" in response.json()["message"]


def test_create_game_from_body_url_rejects_download_failure(
    logged_in_games, storage_root, remote_files
):
    """下载失败转成中文 400，且不留下半成品条目或文件。"""
    response = _create_from_url(
        logged_in_games, "下不下来", "https://cdn.test/missing.nes", "nes"
    )
    assert response.status_code == 400
    assert "请求失败" in response.json()["message"]
    assert _files(storage_root) == set()
    assert logged_in_games.get("/api/games/manage").json()["data"]["items"] == []


def test_create_game_from_body_url_rejects_non_http(logged_in_games):
    """只接受 http/https，别的协议一律拒绝（服务端不做任意 URL 代理）。"""
    for url in ("file:///etc/passwd", "ftp://cdn.test/a.nes", "不是地址"):
        response = _create_from_url(logged_in_games, f"协议 {url}", url, "nes")
        assert response.status_code == 400, url
        assert "http" in response.json()["message"]


def test_create_game_with_cover_url_only(logged_in_games, storage_root, remote_files):
    """封面走直链、本体仍走本地文件：两者可以混用。"""
    remote_files["https://cdn.test/pic/cover.png"] = b"png-bytes"
    response = logged_in_games.post(
        "/api/games/manage",
        data={
            "name": "混合来源",
            "description": "",
            "cartridge_id": "MIX-1",
            "cover_url": "https://cdn.test/pic/cover.png",
        },
        files={"file": ("a.nes", b"nes-body", "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["game_type"] == "nes"
    assert body["cover_path"] == "game/nes/MIX-1/cover.png"
    assert _read(storage_root, body["cover_path"]) == b"png-bytes"


def test_create_game_with_cover_url_must_be_image(logged_in_games, remote_files):
    """封面直链的扩展名不是图片格式：400，且提示支持的格式。"""
    remote_files["https://cdn.test/cover.txt"] = b"not-an-image"
    response = logged_in_games.post(
        "/api/games/manage",
        data={
            "name": "封面不对",
            "description": "",
            "cartridge_id": "BAD-1",
            "cover_url": "https://cdn.test/cover.txt",
        },
        files={"file": ("a.nes", b"nes-body", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "png" in response.json()["message"]


def test_create_game_requires_body_or_url(logged_in_games):
    """本体既没给文件也没给地址：400 而不是崩。"""
    response = logged_in_games.post(
        "/api/games/manage",
        data={"name": "空手", "description": "", "cartridge_id": "EMPTY1"},
    )
    assert response.status_code == 400
    assert "本体" in response.json()["message"]


def test_upload_body_from_url_on_edit(logged_in_games, storage_root, remote_files):
    """编辑时换本体走直链：只接受同类型，成功后更新 crc32。"""
    created = _create_game(logged_in_games, "换本体", "a.nes", b"nes-body").json()["data"]
    remote_files["https://cdn.test/roms/new.nes"] = b"nes-rom-v2"

    response = logged_in_games.post(
        f"/api/games/manage/{created['id']}/assets",
        data={"kind": "game", "url": "https://cdn.test/roms/new.nes", "game_type": "nes"},
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["game_type"] == "nes"
    assert body["game_path"] == f"game/nes/{created['cartridge_id']}/game.nes"
    assert body["crc32"] == _crc32_of(b"nes-rom-v2")
    assert _read(storage_root, body["game_path"]) == b"nes-rom-v2"


def test_upload_body_from_url_on_edit_rejects_cross_type(
    logged_in_games, storage_root, remote_files
):
    """直链换本体也必须同类型：下载前就拒绝，存储与库都不动。"""
    created = _create_game(
        logged_in_games, "换本体跨类型", "a.nes", b"nes-body"
    ).json()["data"]
    before_files = _files(storage_root)
    remote_files["https://cdn.test/roms/new.gba"] = b"gba-rom"

    response = logged_in_games.post(
        f"/api/games/manage/{created['id']}/assets",
        data={"kind": "game", "url": "https://cdn.test/roms/new.gba", "game_type": "gba"},
    )
    assert response.status_code == 400
    message = response.json()["message"]
    assert "任天堂 FC" in message
    assert "任天堂 GBA" in message
    assert _files(storage_root) == before_files
    detail = logged_in_games.get(f"/api/games/manage/{created['id']}").json()["data"]
    assert detail["game_type"] == "nes"
    assert detail["crc32"] == created["crc32"]


def test_upload_body_from_url_on_edit_no_extension(
    logged_in_games, storage_root, remote_files
):
    """无后缀直链按当前类型的默认后缀落盘。"""
    created = _create_game(
        logged_in_games, "换本体无后缀", "a.nes", b"nes-body"
    ).json()["data"]
    remote_files["https://cdn.test/roms/download?id=1"] = b"nes-rom-download"

    response = logged_in_games.post(
        f"/api/games/manage/{created['id']}/assets",
        data={
            "kind": "game",
            "url": "https://cdn.test/roms/download?id=1",
            "game_type": "nes",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["game_path"] == f"game/nes/{created['cartridge_id']}/game.nes"
    assert _read(storage_root, body["game_path"]) == b"nes-rom-download"


def test_upload_cover_from_url_on_edit(logged_in_games, storage_root, remote_files):
    """编辑游戏时换封面走直链。"""
    created = _create_game(logged_in_games, "换封面", "a.nes", b"nes-body").json()["data"]
    remote_files["https://cdn.test/pic/new.webp"] = b"webp-bytes"

    response = logged_in_games.post(
        f"/api/games/manage/{created['id']}/assets",
        data={"kind": "cover", "url": "https://cdn.test/pic/new.webp"},
    )
    assert response.status_code == 201, response.text
    cover_path = response.json()["data"]["cover_path"]
    assert cover_path == f"game/nes/{created['cartridge_id']}/cover.webp"
    assert _read(storage_root, cover_path) == b"webp-bytes"


def test_upload_asset_url_requires_kind(logged_in_games, remote_files):
    """kind 不合法时不去下载，直接 400。"""
    created = _create_game(logged_in_games, "kind 不对", "a.nes", b"nes-body").json()["data"]
    response = logged_in_games.post(
        f"/api/games/manage/{created['id']}/assets",
        data={"kind": "wallpaper", "url": "https://cdn.test/a.png"},
    )
    assert response.status_code == 400
    assert "上传类型" in response.json()["message"]


class _StubResponse:
    """够用的假响应：headers + 一次性 iter_content。"""

    def __init__(self, body: bytes, headers: dict | None = None) -> None:
        self.body = body
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, size: int):
        yield self.body

    def close(self) -> None:
        self.closed = True


class _StubSession:
    def __init__(self, response: _StubResponse) -> None:
        self.response = response

    def get(self, url, **kwargs) -> _StubResponse:
        return self.response


def test_download_file_enforces_max_bytes(tmp_path):
    """边下边卡大小上限：超限即中断，连 .part 一起清掉。"""
    session = _StubSession(_StubResponse(b"x" * 10))
    with pytest.raises(importer.DownloadError):
        importer.download_file(session, "https://x.test/a.nes", tmp_path / "a.nes", max_bytes=4)
    assert list(tmp_path.iterdir()) == []


def test_download_file_rejects_declared_oversize_before_writing(tmp_path):
    """响应头声明的长度就超限时，连写都不写。"""
    response = _StubResponse(b"x" * 2, headers={"Content-Length": "999999999"})
    session = _StubSession(response)
    with pytest.raises(importer.DownloadError):
        importer.download_file(session, "https://x.test/a.nes", tmp_path / "a.nes", max_bytes=1024)
    assert list(tmp_path.iterdir()) == []
    assert response.closed  # 连接要放掉，别把 socket 挂着


def test_download_file_without_limit_is_unchanged(tmp_path):
    """不给上限时行为与从前一致：正常落盘，没留 .part。"""
    session = _StubSession(_StubResponse(b"payload"))
    path, size = importer.download_file(session, "https://x.test/a.nes", tmp_path / "a.nes")
    assert Path(path).read_bytes() == b"payload"
    assert size == 7
    assert [p.name for p in tmp_path.iterdir()] == ["a.nes"]


def test_init_db_drops_removed_tables(tmp_path):
    """老库里遗留的 game_h5_files 表：启动时清掉（清单表已经没有任何代码读写）。"""
    from sqlalchemy import inspect as sa_inspect
    from sqlmodel import create_engine

    from backend.database import init_db

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE game_h5_files ("
            "id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL, path VARCHAR(512) NOT NULL, "
            "file_path VARCHAR(700) NOT NULL, size INTEGER NOT NULL, "
            "mime VARCHAR(200), created_at DATETIME NOT NULL)"
        )

    init_db(engine)

    assert not sa_inspect(engine).has_table("game_h5_files")
