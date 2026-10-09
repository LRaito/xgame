import zlib
import html
import io
import itertools
import json
import zipfile
from pathlib import Path

import pytest
from sqlmodel import Session, select

from backend.errors import ValidationError
from backend.config import DB_SUBDIR
from backend.mount_guard import SENTINEL_NAME
from backend.games import importer, paths
from backend.games.models import Game, GameCloudSnapshot, GameCloudSnapshotFile, GameH5File
from backend.games.service import (
    GAME_TYPES,
    GameService,
    GameUpload,
    detect_game_type,
    normalize_guide_path,
    normalize_h5_path,
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
        yield GameService(session, app.state.storage)


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
        and p.name != SENTINEL_NAME
        # db/ 里是 SQLite 库与它的月度备份，不属于游戏素材
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
    cartridge_type: str | None = None,
):
    """按新流程建游戏：一次请求提交名称/卡带ID/描述/本体（可选封面），类型由后端识别。"""
    files = {"file": (filename, body, mime)}
    if cover is not None:
        files["cover"] = cover
    data = {
        "name": name,
        "cartridge_id": cartridge_id or _next_cartridge_id(),
        "description": description,
    }
    if cartridge_type is not None:
        data["cartridge_type"] = cartridge_type
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
    assert [item["id"] for item in tools] == ["games", "games-manage"]


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


def test_games_list_sorted_by_name_asc(game_service):
    """游戏中心与管理页的游戏列表都按游戏名称升序（与插入/更新时间无关）。"""
    # 故意打乱插入顺序；中心列表只收已传本体的游戏
    for name in ("delta", "bravo", "charlie"):
        game_service.create(
            name, "", _upload("g.swf", b"swf"), cartridge_id=_next_cartridge_id()
        )

    center = [g.name for g in game_service.list_center()]
    manage = [g.name for g in game_service.list_manage()]
    assert center == ["bravo", "charlie", "delta"]
    assert manage == ["bravo", "charlie", "delta"]


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
    found = game_service.list_manage(keyword="测试")
    assert len(found) == 1

    stream = game_service.open_asset(updated.game_path)
    try:
        assert stream.read() == b"swf!"
    finally:
        stream.close()

    game_service.delete(item.id)
    assert _files(storage_root) == set()


def test_replace_deletes_old_storage_objects(app, game_service, storage_root):
    first = game_service.create(
        "旧名", "描述", _upload("a.swf", b"old-swf"), cartridge_id="OLD-1"
    )
    assert first.game_path == "game/flash/OLD-1/game.swf"
    _unlock_body(app, first.id)

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
    assert logged_in_games.get("/api/games/manage").json()["data"] == []
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
    assert logged_in_games.get("/api/games/manage").json()["data"] == []
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
    names = [item["name"] for item in filtered.json()["data"]]
    assert names == ["Alpha"]

    typed = logged_in_games.get("/api/games/manage", params={"game_type": "flash"})
    assert typed.status_code == 200
    assert len(typed.json()["data"]) == 2


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


def test_replacing_body_switches_game_type(logged_in_games, storage_root):
    """换本体即换类型：上传另一平台的本体后类型随扩展名切换，旧目录被清掉。"""
    nes = _create_game(logged_in_games, "N", "a.nes", b"nes-body").json()["data"]
    cid = nes["cartridge_id"]
    assert nes["game_type"] == "nes"
    assert _exists(storage_root, f"game/nes/{cid}/game.nes")
    _unlock_body(logged_in_games.app, nes["id"])

    uploaded = logged_in_games.post(
        f"/api/games/manage/{nes['id']}/assets",
        data={"kind": "game"},
        files={"file": ("a.gba", b"gba-body", "application/octet-stream")},
    )
    assert uploaded.status_code == 201
    body = uploaded.json()["data"]
    assert body["game_type"] == "gba"
    assert body["game_path"] == f"game/gba/{cid}/game.gba"
    assert body["path"] == f"/games/play/{nes['id']}"
    assert not (storage_root / "game" / "nes" / cid).exists()

    # 详情接口同样返回切换后的类型
    detail = logged_in_games.get(f"/api/games/manage/{nes['id']}").json()["data"]
    assert detail["game_type"] == "gba"


def test_type_switch_keeps_cover(logged_in_games, storage_root):
    """换类型挪目录：封面跟着从旧类型目录搬到新类型目录，不会随旧目录一起被删。"""
    nes = _create_game(
        logged_in_games,
        "带封面换类型",
        "a.nes",
        b"nes-body",
        cover=("c.png", b"png-body", "image/png"),
    ).json()["data"]
    cid = nes["cartridge_id"]
    assert _exists(storage_root, f"game/nes/{cid}/cover.png")
    _unlock_body(logged_in_games.app, nes["id"])

    switched = logged_in_games.post(
        f"/api/games/manage/{nes['id']}/assets",
        data={"kind": "game"},
        files={"file": ("a.gba", b"gba-body", "application/octet-stream")},
    )
    assert switched.status_code == 201, switched.text
    body = switched.json()["data"]
    assert body["game_type"] == "gba"
    assert body["cover_path"] == f"game/gba/{cid}/cover.png"
    assert _read(storage_root, f"game/gba/{cid}/cover.png") == b"png-body"
    assert not (storage_root / "game" / "nes" / cid).exists()

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


def test_body_crc32_lock_allows_same_file(logged_in_games):
    """本体已锁定：重传同一个文件（rom 丢了补传）放行，crc32 不变。"""
    game = _create_game(logged_in_games, "锁-同文件", "a.nes", b"nes-body").json()["data"]
    again = logged_in_games.post(
        f"/api/games/manage/{game['id']}/assets",
        data={"kind": "game"},
        files={"file": ("a.nes", b"nes-body", "application/octet-stream")},
    )
    assert again.status_code == 201
    assert again.json()["data"]["crc32"] == game["crc32"]


def test_body_crc32_lock_rejects_other_file(logged_in_games, storage_root):
    """本体已锁定：换成本不一致的文件被拒，且旧本体文件没被覆盖。"""
    game = _create_game(logged_in_games, "锁-异文件", "a.nes", b"nes-body").json()["data"]
    before = _files(storage_root)

    rejected = logged_in_games.post(
        f"/api/games/manage/{game['id']}/assets",
        data={"kind": "game"},
        files={"file": ("a.nes", b"other-body", "application/octet-stream")},
    )
    assert rejected.status_code == 400
    assert "CRC32" in rejected.json()["message"]
    assert _files(storage_root) == before
    assert logged_in_games.get(f"/api/games/manage/{game['id']}").json()["data"]["crc32"] == game["crc32"]


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


def test_create_requires_cartridge_id(logged_in_games):
    """卡带ID 必填：不填直接 400，不留下条目。"""
    response = logged_in_games.post(
        "/api/games/manage",
        data={"name": "没卡带ID", "description": ""},
        files={"file": ("a.nes", b"nes-body", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "卡带" in response.json()["message"]
    assert logged_in_games.get("/api/games/manage").json()["data"] == []


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
    """卡带ID 建后不可改：PUT 带 cartridge_id 也只当普通字段忽略，想换只能删了重建。"""
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
    assert logged_in_games.get("/api/games/manage").json()["data"] == []


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


def test_failed_switch_keeps_old_asset(game_service, storage_root):
    """换类型时新本体校验失败：类型、旧本体文件都保持原样（不先毁旧档）。"""
    item = game_service.create(
        "F", "", _upload("a.swf", b"swf-body"), cartridge_id="KEEP1"
    )
    bad_zip = _make_zip({"a.js": b"no-entry"})
    with pytest.raises(Exception):
        game_service.upload_asset(item.id, kind="game", upload=_upload("bad.zip", bad_zip))

    fresh = game_service.get(item.id)
    assert fresh.game_type == "flash"
    assert fresh.game_path == "game/flash/KEEP1/game.swf"
    assert _read(storage_root, "game/flash/KEEP1/game.swf") == b"swf-body"


def test_cartridge_type_defaults_to_default(logged_in_games):
    """卡带类型始终有值：新建没传就是「默认」，中心列表与管理详情都带着它。"""
    nes = _create_game(logged_in_games, "CT 默认", "a.nes", b"nes-body").json()["data"]
    assert nes["cartridge_type"] == "default"

    center = logged_in_games.get("/api/games").json()["data"]
    assert center[0]["cartridge_type"] == "default"
    assert logged_in_games.get(f"/api/games/manage/{nes['id']}").json()["data"][
        "cartridge_type"
    ] == "default"


def test_create_accepts_cartridge_type_for_nes(logged_in_games):
    """新建时按所选本体落成的类型收卡带类型；与类型对不上就 400。"""
    ok = _create_game(
        logged_in_games, "CT 新建", "a.nes", b"nes-body", cartridge_type="us"
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["data"]["cartridge_type"] == "us"

    bad = _create_game(
        logged_in_games, "CT 新建不合法", "b.sfc", b"sfc-body", cartridge_type="us"
    )
    assert bad.status_code == 400
    assert "卡带类型" in bad.json()["message"]


def test_update_cartridge_type(logged_in_games):
    """FC NES 可设日版/美版；空值回落「默认」。"""
    nes = _create_game(logged_in_games, "CT 日版", "a.nes", b"nes-body").json()["data"]
    updated = logged_in_games.put(
        f"/api/games/manage/{nes['id']}", json={"cartridge_type": "jp"}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["cartridge_type"] == "jp"

    cleared = logged_in_games.put(
        f"/api/games/manage/{nes['id']}", json={"cartridge_type": ""}
    )
    assert cleared.json()["data"]["cartridge_type"] == "default"


def test_cartridge_type_rejects_value_not_allowed_by_type(logged_in_games):
    """只有 FC NES 区分日版/美版，其余游戏类型设这两个值一律 400。"""
    snes = _create_game(logged_in_games, "CT SNES", "a.sfc", b"sfc-body").json()["data"]
    for value in ("jp", "us", "xx"):
        rejected = logged_in_games.put(
            f"/api/games/manage/{snes['id']}", json={"cartridge_type": value}
        )
        assert rejected.status_code == 400, value
        assert "卡带类型" in rejected.json()["message"]
    # 被拒后原值不变
    detail = logged_in_games.get(f"/api/games/manage/{snes['id']}").json()["data"]
    assert detail["cartridge_type"] == "default"


def test_type_switch_resets_cartridge_type(logged_in_games, storage_root):
    """换本体换类型后，新类型不认的卡带类型回落「默认」。"""
    nes = _create_game(logged_in_games, "CT 换类型", "a.nes", b"nes-body").json()["data"]
    logged_in_games.put(
        f"/api/games/manage/{nes['id']}", json={"cartridge_type": "jp"}
    )
    _unlock_body(logged_in_games.app, nes["id"])

    switched = logged_in_games.post(
        f"/api/games/manage/{nes['id']}/assets",
        data={"kind": "game"},
        files={"file": ("a.sfc", b"sfc-body", "application/octet-stream")},
    )
    assert switched.status_code == 201, switched.text
    body = switched.json()["data"]
    assert body["game_type"] == "snes"
    assert body["cartridge_type"] == "default"


def test_init_db_adds_missing_cartridge_type_column(tmp_path):
    """老库的 games 表没有 cartridge_type：启动时补上这一列，旧行取「默认」。"""
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

    assert "cartridge_type" in {c["name"] for c in sa_inspect(engine).get_columns("games")}
    with Session(engine) as session:
        assert session.get(Game, 1).cartridge_type == "default"


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
    names = [item["name"] for item in filtered.json()["data"]]
    assert names == ["Md game"]


# ---------- H5（ZIP 解包） ----------


def _make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _unlock_body(app, game_id: int) -> None:
    """清掉本体 CRC32 锁（crc32 为空 = 未锁定）。

    换本体/换类型/换 H5 代这些路径只在未锁定时可用，本文件里凡是考这些行为的用例
    都先解锁；锁定语义本身另由 test_body_crc32_lock_* 覆盖。
    """
    with Session(app.state.engine) as session:
        row = session.get(Game, game_id)
        row.crc32 = ""
        session.add(row)
        session.commit()


def _upload_h5(logged_in_games, name="H5 demo"):
    """建一个 H5 游戏（本体是含 index.html 的最小 zip，类型由扩展名自动识别）。"""
    create = _create_game(
        logged_in_games, name, "seed.zip", _make_zip({"index.html": b"seed"})
    )
    assert create.status_code == 201
    assert create.json()["data"]["game_type"] == "h5"
    game_id = create.json()["data"]["id"]
    _unlock_body(logged_in_games.app, game_id)
    return game_id


def _h5_rows(app, game_id):
    with Session(app.state.engine) as session:
        return list(
            session.exec(
                select(GameH5File).where(GameH5File.game_id == game_id)
            ).all()
        )


def test_h5_upload_and_serve(logged_in_games, storage_root):
    """建 H5→传含 index.html 与资源的 zip→解包入库；入口与资源均可取且带沙箱安全头。"""
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    archive = _make_zip(
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
        files={"file": ("game.zip", archive, "application/zip")},
    )
    assert upload.status_code == 201
    body = upload.json()["data"]
    assert body["game_path"] == f"game/h5/{cid}/game.zip"
    assert body["size"] == len(archive)

    rows = _h5_rows(logged_in_games.app, game_id)
    assert sorted(row.path for row in rows) == ["assets/app.js", "index.html"]
    assert all(
        row.file_path == f"game/h5/{cid}/h5/{row.path}" for row in rows
    )
    assert _exists(storage_root, f"game/h5/{cid}/game.zip")

    entry = logged_in_games.get(f"/api/games/{game_id}/h5/index.html")
    assert entry.status_code == 200
    assert entry.content == b"<html>hi</html>"
    assert entry.headers["content-type"].startswith("text/html")
    assert "sandbox" in entry.headers["content-security-policy"]
    assert "allow-same-origin" not in entry.headers["content-security-policy"]
    assert entry.headers["x-content-type-options"] == "nosniff"
    assert entry.headers["access-control-allow-origin"] == "*"

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

    _unlock_body(logged_in_games.app, game_id)
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


def test_h5_reupload_replaces_whole_package(logged_in_games, storage_root):
    """重传整包替换：新内容生效，旧资源文件不残留，清单只保留新包。"""
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
    assert _exists(storage_root, f"game/h5/{cid}/h5/old.js")

    _unlock_body(logged_in_games.app, game_id)
    logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"index.html": b"v2"}), "application/zip")},
    )
    assert logged_in_games.get(f"/api/games/{game_id}/h5/index.html").content == b"v2"
    assert not _exists(storage_root, f"game/h5/{cid}/h5/old.js")
    assert sorted(row.path for row in _h5_rows(logged_in_games.app, game_id)) == [
        "index.html"
    ]


def test_h5_delete_and_type_change_cleanup(logged_in_games, storage_root):
    game_id = _upload_h5(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    # 换成主机 ROM 本体：类型离开 h5，解包清单与资源、旧本体一并清理
    switched = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.nes", b"nes-body", "application/octet-stream")},
    )
    assert switched.status_code == 201
    assert switched.json()["data"]["game_type"] == "nes"
    assert switched.json()["data"]["game_path"] == f"game/nes/{cid}/game.nes"
    assert _h5_rows(logged_in_games.app, game_id) == []
    assert not (storage_root / "game" / "h5" / cid).exists()
    assert not _exists(storage_root, f"game/nes/{cid}/game.zip")

    # 再换回 H5 并删除游戏：目录与清单全清
    logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"index.html": b"x"}), "application/zip")},
    )
    assert logged_in_games.delete(f"/api/games/manage/{game_id}").status_code == 200
    assert _files(storage_root) == set()
    assert _h5_rows(logged_in_games.app, game_id) == []


def test_replacing_swf_with_zip_switches_to_h5(logged_in_games, storage_root):
    """Flash 本体换成 zip：类型切到 h5、旧 swf 删除、解包资源可用。"""
    flash = _create_game(logged_in_games, "F", "a.swf", b"swf-body").json()["data"]
    _unlock_body(logged_in_games.app, flash["id"])
    uploaded = logged_in_games.post(
        f"/api/games/manage/{flash['id']}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", _make_zip({"index.html": b"h5"}), "application/zip")},
    )
    assert uploaded.status_code == 201
    body = uploaded.json()["data"]
    assert body["game_type"] == "h5"
    assert body["game_path"] == f"game/h5/{flash['cartridge_id']}/game.zip"
    assert body["path"] == f"/games/h5/{flash['id']}"
    assert not (storage_root / "game" / "flash" / flash["cartridge_id"]).exists()
    assert logged_in_games.get(f"/api/games/{flash['id']}/h5/index.html").content == b"h5"


def test_h5_enforces_limits(logged_in_games, storage_root, monkeypatch):
    from backend.games import service as games_service

    game_id = _upload_h5(logged_in_games)
    before = _files(storage_root)
    payload = _make_zip({"index.html": b"a", "b.js": b"b"})

    monkeypatch.setattr(games_service, "_H5_MAX_ENTRIES", 1)
    too_many = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", payload, "application/zip")},
    )
    assert too_many.status_code == 400
    assert "数量" in too_many.json()["message"]
    monkeypatch.undo()

    monkeypatch.setattr(games_service, "_H5_MAX_TOTAL_SIZE", 1)
    too_big = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("g.zip", payload, "application/zip")},
    )
    assert too_big.status_code == 400
    assert _files(storage_root) == before


def test_h5_path_helpers():
    assert normalize_h5_path("assets/app.js") == "assets/app.js"
    with pytest.raises(Exception):
        normalize_h5_path("../evil.js")
    with pytest.raises(Exception):
        normalize_h5_path("/abs.js")


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


# ---------- 攻略（整目录静态资源） ----------


def _upload_guide(client, game_id: int, files: dict[str, bytes], paths=None):
    """multipart 整目录上传：files 多个 part + 按下标对位的 paths JSON 数组。"""
    parts = [
        ("files", (name.rsplit("/", 1)[-1], data, "application/octet-stream"))
        for name, data in files.items()
    ]
    return client.post(
        f"/api/games/manage/{game_id}/guide",
        data={"paths": json.dumps(list(files) if paths is None else paths)},
        files=parts,
    )


def _guide_game(logged_in_games, name="攻略 demo"):
    """建一个最简单的游戏（攻略与游戏类型无关，用 flash 本体最省事）。"""
    create = _create_game(logged_in_games, name, "seed.swf", b"FWS")
    assert create.status_code == 201
    return create.json()["data"]["id"]


def test_guide_upload_and_serve(logged_in_games, storage_root):
    """整目录上传→按目录落盘→入口与子资源都能取到，且不带 H5 那套沙箱头。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    upload = _upload_guide(
        logged_in_games,
        game_id,
        {"index.html": b"<html>guide</html>", "assets/css/site.css": b"body{}"},
    )
    assert upload.status_code == 201
    assert upload.json()["data"]["has_guide"] is True
    assert _read(storage_root, f"game/flash/{cid}/guide/index.html") == b"<html>guide</html>"
    assert _read(storage_root, f"game/flash/{cid}/guide/assets/css/site.css") == b"body{}"

    entry = logged_in_games.get(f"/api/games/{game_id}/guide/index.html")
    assert entry.status_code == 200
    assert entry.content == b"<html>guide</html>"
    assert entry.headers["content-type"].startswith("text/html")
    assert entry.headers["cache-control"] == "no-cache, must-revalidate"
    # 攻略与 H5 不同：不隔离、不放行匿名
    assert "content-security-policy" not in entry.headers

    css = logged_in_games.get(f"/api/games/{game_id}/guide/assets/css/site.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")

    head = logged_in_games.head(f"/api/games/{game_id}/guide/index.html")
    assert head.status_code == 200
    assert head.headers["content-length"] == str(len(b"<html>guide</html>"))

    listed = logged_in_games.get("/api/games").json()["data"]
    assert [item["has_guide"] for item in listed if item["id"] == game_id] == [True]


def test_guide_requires_index(logged_in_games, storage_root):
    """没有 index.html 直接拒，且磁盘上什么都不留（连暂存目录都没有）。"""
    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)
    response = _upload_guide(logged_in_games, game_id, {"pages/1.html": b"x"})
    assert response.status_code == 400
    assert "index.html" in response.json()["message"]
    assert _files(storage_root) == before


def test_guide_entry_name_is_case_insensitive(logged_in_games, storage_root):
    """入口大小写不敏感，落盘统一成小写 index.html，入口地址才固定。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    assert _upload_guide(logged_in_games, game_id, {"INDEX.HTML": b"hi"}).status_code == 201
    assert _exists(storage_root, f"game/flash/{cid}/guide/index.html")
    assert (
        logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 200
    )


@pytest.mark.parametrize("bad_name", ["../evil.js", "/abs.js", "a/../../b.js", "a\\b.js", "a?b.js"])
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


def test_guide_rejects_mismatched_paths(logged_in_games):
    """paths 与 files 数量对不上、或 paths 不是字符串数组，都是 400。"""
    game_id = _guide_game(logged_in_games)
    short = _upload_guide(
        logged_in_games, game_id, {"index.html": b"a", "b.css": b"b"}, paths=["index.html"]
    )
    assert short.status_code == 400

    bad_json = logged_in_games.post(
        f"/api/games/manage/{game_id}/guide",
        data={"paths": "not-json"},
        files=[("files", ("index.html", b"a", "application/octet-stream"))],
    )
    assert bad_json.status_code == 400

    not_strings = logged_in_games.post(
        f"/api/games/manage/{game_id}/guide",
        data={"paths": json.dumps([1])},
        files=[("files", ("index.html", b"a", "application/octet-stream"))],
    )
    assert not_strings.status_code == 400


def test_guide_reupload_replaces_whole_tree(logged_in_games, storage_root):
    """重传就是整目录替换：这一版没有的文件在磁盘上要消失，也不留暂存目录。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(
        logged_in_games, game_id, {"index.html": b"v1", "old.css": b"old"}
    )
    again = _upload_guide(
        logged_in_games, game_id, {"index.html": b"v2", "new.css": b"new"}
    )
    assert again.status_code == 201
    assert _read(storage_root, f"game/flash/{cid}/guide/index.html") == b"v2"
    assert _exists(storage_root, f"game/flash/{cid}/guide/new.css")
    assert not _exists(storage_root, f"game/flash/{cid}/guide/old.css")
    assert not [p for p in _files(storage_root) if "/.guide-" in p]


def test_guide_requires_login(client, user, do_login):
    """攻略资源与其它业务接口一样要登录（与 H5 的免登录正好相反）。"""
    do_login(client)
    game_id = _guide_game(client)
    assert _upload_guide(client, game_id, {"index.html": b"x"}).status_code == 201
    assert client.post("/api/logout").status_code == 200
    assert client.get(f"/api/games/{game_id}/guide/index.html").status_code == 401
    assert client.head(f"/api/games/{game_id}/guide/index.html").status_code == 401
    assert (
        client.post(
            f"/api/games/manage/{game_id}/guide",
            data={"paths": json.dumps(["index.html"])},
            files=[("files", ("index.html", b"x", "application/octet-stream"))],
        ).status_code
        == 401
    )


def test_guide_missing_returns_404(logged_in_games):
    game_id = _guide_game(logged_in_games)
    assert logged_in_games.get(f"/api/games/{game_id}/guide/index.html").status_code == 404
    assert logged_in_games.get(f"/api/games/{game_id}/guide/nope.css").status_code == 404
    # 上传后子资源仍然只认实际存在的文件
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    assert logged_in_games.get(f"/api/games/{game_id}/guide/nope.css").status_code == 404


def test_guide_removed_with_game_delete(logged_in_games, storage_root):
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    assert logged_in_games.delete(f"/api/games/manage/{game_id}").status_code == 200
    assert not (Path(storage_root) / "game" / "flash" / cid).exists()


def test_guide_removed_on_game_type_switch(logged_in_games, storage_root):
    """换本体换了类型：攻略随旧类型目录一起消失（与 H5 资源同样的口径）。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    _upload_guide(logged_in_games, game_id, {"index.html": b"x"})
    _unlock_body(logged_in_games.app, game_id)
    switch = logged_in_games.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game"},
        files={"file": ("new.nes", b"NES\x1a", "application/octet-stream")},
    )
    assert switch.status_code == 201
    assert switch.json()["data"]["game_type"] == "nes"
    assert switch.json()["data"]["has_guide"] is False
    assert not (Path(storage_root) / "game" / "flash" / cid).exists()


def test_guide_has_flag_follows_disk(logged_in_games, storage_root):
    """没有清单表也没有库标记：标记完全跟磁盘走，手动删掉攻略界面立刻变。"""
    game_id = _guide_game(logged_in_games)
    cid = _cartridge_of(logged_in_games.app, game_id)
    guide_entry = Path(storage_root) / "game" / "flash" / cid / "guide" / "index.html"

    def flag():
        listed = logged_in_games.get("/api/games").json()["data"]
        return next(item["has_guide"] for item in listed if item["id"] == game_id)

    assert flag() is False
    guide_entry.parent.mkdir(parents=True, exist_ok=True)
    guide_entry.write_bytes(b"manual")
    assert flag() is True
    guide_entry.unlink()
    assert flag() is False


def test_guide_enforces_limits(logged_in_games, storage_root, monkeypatch):
    from backend.games import service as games_service

    game_id = _guide_game(logged_in_games)
    before = _files(storage_root)

    monkeypatch.setattr(games_service, "_GUIDE_MAX_FILES", 1)
    too_many = _upload_guide(
        logged_in_games, game_id, {"index.html": b"a", "b.css": b"b"}
    )
    assert too_many.status_code == 400
    assert "数量" in too_many.json()["message"]
    monkeypatch.undo()

    monkeypatch.setattr(games_service, "_GUIDE_MAX_TOTAL_SIZE", 1)
    too_big = _upload_guide(logged_in_games, game_id, {"index.html": b"a" * 64})
    assert too_big.status_code == 400
    assert _files(storage_root) == before


def test_guide_path_helpers():
    assert paths.guide_dir("flash", "AB-1") == "game/flash/AB-1/guide"
    assert paths.guide_entry_path("flash", "AB-1") == "game/flash/AB-1/guide/index.html"
    assert (
        paths.guide_asset_path("flash", "AB-1", "pages/1.html")
        == "game/flash/AB-1/guide/pages/1.html"
    )
    assert paths.guide_temp_dir("flash", "AB-1", "tok") == "game/flash/AB-1/.guide-tok"
    assert normalize_guide_path("pages/mc/1.html") == "pages/mc/1.html"
    with pytest.raises(ValidationError):
        normalize_guide_path("../evil.js")
    with pytest.raises(ValidationError):
        normalize_guide_path("/abs.js")


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
    assert len(logged_in_games.get("/api/games/manage").json()["data"]) == 1


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
    assert logged_in_games.get("/api/games/manage").json()["data"] == []


def test_import_cleans_up_when_download_fails(logged_in_games, storage_root, monkeypatch):
    def boom(url, work, session=None):
        raise importer.DownloadError("页面解析失败")

    monkeypatch.setattr(importer, "download_game", boom)
    response = logged_in_games.post(
        "/api/games/manage/import", json={"url": "https://www.7k7k.com/flash/9.htm"}
    )
    assert response.status_code == 400
    assert response.json()["message"] == "页面解析失败"
    assert logged_in_games.get("/api/games/manage").json()["data"] == []


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
    assert logged_in_games.get("/api/games/manage").json()["data"] == []




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
    assert "h5" in response.json()["message"] and "gba" in response.json()["message"]
    assert logged_in_games.get("/api/games/manage").json()["data"] == []


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
    assert logged_in_games.get("/api/games/manage").json()["data"] == []


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
    """编辑游戏时换本体走直链：类型随所选类型切换，旧目录被清理。"""
    created = _create_game(logged_in_games, "换本体", "a.nes", b"nes-body").json()["data"]
    _unlock_body(logged_in_games.app, created["id"])
    remote_files["https://cdn.test/roms/new.gba"] = b"gba-rom"

    response = logged_in_games.post(
        f"/api/games/manage/{created['id']}/assets",
        data={"kind": "game", "url": "https://cdn.test/roms/new.gba", "game_type": "gba"},
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["game_type"] == "gba"
    assert body["game_path"] == f"game/gba/{created['cartridge_id']}/game.gba"
    assert body["crc32"] == _crc32_of(b"gba-rom")
    assert not (storage_root / "game" / "nes" / created["cartridge_id"]).exists()


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
