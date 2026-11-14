"""多文件本体：cue+bin、m3u 多碟、多 adf 的完整入库与播放链路。"""

import json
import zlib

import pytest

from backend.errors import ValidationError
from backend.games import paths
from backend.games.body_bundle import (
    MAX_BUNDLE_FILES,
    StagedBundleFile,
    build_bundle,
    normalize_bundle_name,
)
from backend.games.platforms import PLATFORM_BY_ID


def _crc(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


def _bundle_crc(files: list[dict]) -> str:
    text = "".join(
        f"{item['name']}\t{item['size']}\t{item['crc32']}\n"
        for item in sorted(files, key=lambda item: item["name"])
    )
    return _crc(text.encode("utf-8"))


def _stage(client, filename, data, game_type=""):
    response = client.post(
        "/api/games/uploads",
        json={"filename": filename, "size": len(data), "game_type": game_type},
    )
    assert response.status_code == 200, response.text
    upload = response.json()["data"]
    offset = 0
    for index in range(upload["total_chunks"]):
        end = min(offset + upload["chunk_size"], len(data))
        put = client.put(
            f"/api/games/uploads/{upload['upload_id']}/chunks/{index}",
            content=data[offset:end],
            headers={"Content-Type": "application/octet-stream"},
        )
        assert put.status_code == 200, put.text
        offset = end
    assert client.post(f"/api/games/uploads/{upload['upload_id']}/complete").status_code == 200
    return upload["upload_id"]


def _create_bundle(client, name, cartridge_id, staged, game_type, **extra):
    data = {
        "name": name,
        "cartridge_id": cartridge_id,
        "body_game_type": game_type,
        "upload_ids": list(staged),
    }
    data.update(extra)
    return client.post("/api/games/manage", data=data)


def _replace_bundle(client, game_id, staged):
    data = {"kind": "game", "upload_ids": list(staged)}
    return client.post(f"/api/games/manage/{game_id}/assets", data=data)


@pytest.fixture
def small_chunks(monkeypatch):
    monkeypatch.setattr("backend.games.uploads.CHUNK_SIZE", 4)


CUE = b'FILE "track01.bin" BINARY\n  TRACK 01 MODE1/2352\n   INDEX 01 00:00:00\n'
BIN = b"0123456789"


def test_cue_bin_bundle_creates_game_and_plays(logged_in, storage_root, small_chunks):
    cue_id = _stage(logged_in, "game.cue", CUE, "segaCD")
    bin_id = _stage(logged_in, "track01.bin", BIN, "segaCD")

    created = _create_bundle(
        logged_in, "世嘉CD游戏", "CHUNK10", [cue_id, bin_id], "segaCD"
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["body_kind"] == "bundle"
    assert item["game_path"] == "game/segaCD/CHUNK10/body/game.cue"
    assert item["size"] == len(CUE) + len(BIN)
    expected_files = [
        {"name": "game.cue", "size": len(CUE), "crc32": _crc(CUE)},
        {"name": "track01.bin", "size": len(BIN), "crc32": _crc(BIN)},
    ]
    assert item["crc32"] == _bundle_crc(expected_files)

    body = storage_root / "game/segaCD/CHUNK10/body"
    assert (body / "game.cue").read_bytes() == CUE
    assert (body / "track01.bin").read_bytes() == BIN
    manifest = json.loads((body / "manifest.json").read_text("utf-8"))
    assert manifest["entry"] == "game.cue"
    assert manifest["files"] == expected_files

    # 暂存会话在提交后全部删掉
    assert not (storage_root / paths.upload_session_dir(cue_id)).exists()
    assert not (storage_root / paths.upload_session_dir(bin_id)).exists()

    # 播放清单与逐文件下发
    manifest_resp = logged_in.get(f"/api/games/{item['id']}/play/manifest")
    assert manifest_resp.status_code == 200, manifest_resp.text
    payload = manifest_resp.json()["data"]
    assert payload["entry"] == "game.cue"
    assert [entry["name"] for entry in payload["files"]] == [
        "game.cue",
        "track01.bin",
    ]
    assert payload["total_size"] == len(CUE) + len(BIN)

    entry_view = logged_in.get(f"/api/games/{item['id']}/play/game.cue")
    assert entry_view.status_code == 200
    assert entry_view.content == CUE
    bin_view = logged_in.get(f"/api/games/{item['id']}/play/files/track01.bin")
    assert bin_view.status_code == 200
    assert bin_view.content == BIN
    assert logged_in.head(f"/api/games/{item['id']}/play/files/track01.bin").status_code == 200
    assert logged_in.get(f"/api/games/{item['id']}/play/files/missing.bin").status_code == 404


def test_multiple_adf_generates_m3u(logged_in, storage_root, small_chunks):
    first = b"disk-one"
    second = b"disk-two!"
    one = _stage(logged_in, "disc1.adf", first, "amiga")
    two = _stage(logged_in, "disc2.adf", second, "amiga")

    created = _create_bundle(logged_in, "Amiga多盘", "CHUNK11", [two, one], "amiga")
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["game_path"] == "game/amiga/CHUNK11/body/game.m3u"

    generated = b"#EXTM3U\ndisc1.adf\ndisc2.adf\n"
    manifest = json.loads(
        (storage_root / "game/amiga/CHUNK11/body/manifest.json").read_text("utf-8")
    )
    assert manifest["entry"] == "game.m3u"
    assert [entry["name"] for entry in manifest["files"]] == [
        "disc1.adf",
        "disc2.adf",
        "game.m3u",
    ]
    assert item["size"] == len(first) + len(second) + len(generated)
    assert (storage_root / "game/amiga/CHUNK11/body/game.m3u").read_bytes() == generated

    payload = logged_in.get(f"/api/games/{item['id']}/play/manifest").json()["data"]
    assert payload["entry"] == "game.m3u"
    assert logged_in.get(f"/api/games/{item['id']}/play/files/disc2.adf").content == second


def test_cue_without_bin_is_rejected(logged_in, small_chunks):
    cue_id = _stage(logged_in, "game.cue", CUE, "segaCD")
    response = _create_bundle(logged_in, "缺分轨", "CHUNK12", [cue_id], "segaCD")
    assert response.status_code == 400
    assert "引用" in response.json()["message"]
    assert logged_in.get("/api/games/manage").json()["data"]["total"] == 0

    # 走单个 upload_id 也一样拒绝：cue 不能单独成盘
    single = logged_in.post(
        "/api/games/manage",
        data={
            "name": "单cue",
            "cartridge_id": "CHUNK13",
            "upload_id": cue_id,
            "body_game_type": "segaCD",
        },
    )
    assert single.status_code == 400
    assert "多文件" in single.json()["message"] or "引用" in single.json()["message"]


def test_single_adf_and_chd_stay_single_file(logged_in, storage_root, small_chunks):
    adf_id = _stage(logged_in, "game.adf", b"adf-body", "amiga")
    created = logged_in.post(
        "/api/games/manage",
        data={
            "name": "单盘Amiga",
            "cartridge_id": "CHUNK14",
            "upload_id": adf_id,
            "body_game_type": "amiga",
        },
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["body_kind"] == "file"
    assert item["game_path"] == "game/amiga/CHUNK14/game.adf"
    assert (storage_root / item["game_path"]).read_bytes() == b"adf-body"

    chd_id = _stage(logged_in, "game.chd", b"chd-body", "segaCD")
    created = logged_in.post(
        "/api/games/manage",
        data={
            "name": "单盘世嘉CD",
            "cartridge_id": "CHUNK15",
            "upload_id": chd_id,
            "body_game_type": "segaCD",
        },
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["body_kind"] == "file"
    assert item["game_path"] == "game/segaCD/CHUNK15/game.chd"


def test_bundle_replaces_bundle_and_cleans_old_files(
    logged_in, storage_root, small_chunks
):
    cue_id = _stage(logged_in, "game.cue", CUE, "segaCD")
    bin_id = _stage(logged_in, "track01.bin", BIN, "segaCD")
    created = _create_bundle(logged_in, "换多文件", "CHUNK16", [cue_id, bin_id], "segaCD")
    assert created.status_code == 201, created.text
    game_id = created.json()["data"]["id"]

    new_cue = b'FILE "track02.bin" BINARY\n  TRACK 01 MODE1/2352\n'
    new_bin = b"abcdefghijkl"
    new_cue_id = _stage(logged_in, "new.cue", new_cue, "segaCD")
    new_bin_id = _stage(logged_in, "track02.bin", new_bin, "segaCD")
    replaced = _replace_bundle(logged_in, game_id, [new_cue_id, new_bin_id])
    assert replaced.status_code == 201, replaced.text
    item = replaced.json()["data"]
    assert item["size"] == len(new_cue) + len(new_bin)

    body = storage_root / "game/segaCD/CHUNK16/body"
    assert (body / "game.cue").read_bytes() == new_cue
    assert (body / "track02.bin").read_bytes() == new_bin
    assert not (body / "track01.bin").exists()
    parent = body.parent
    assert [p.name for p in parent.iterdir()] == ["body"]


def test_bundle_to_single_removes_body_dir(logged_in, storage_root, small_chunks):
    # 先用单个 adf 建，再换成多 adf，随后用单个 hdf 换回单文件
    adf_id = _stage(logged_in, "game.adf", b"one", "amiga")
    created = logged_in.post(
        "/api/games/manage",
        data={
            "name": "多转单",
            "cartridge_id": "CHUNK18",
            "upload_id": adf_id,
            "body_game_type": "amiga",
        },
    )
    game_id = created.json()["data"]["id"]
    one = _stage(logged_in, "disc1.adf", b"disk1", "amiga")
    two = _stage(logged_in, "disc2.adf", b"disk2", "amiga")
    assert _replace_bundle(logged_in, game_id, [one, two]).status_code == 201
    assert (storage_root / "game/amiga/CHUNK18/body").exists()

    hdf_id = _stage(logged_in, "game.hdf", b"single-again", "amiga")
    replaced = logged_in.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game", "upload_id": hdf_id},
    )
    assert replaced.status_code == 201, replaced.text
    item = replaced.json()["data"]
    assert item["body_kind"] == "file"
    assert item["game_path"] == "game/amiga/CHUNK18/game.hdf"
    assert not (storage_root / "game/amiga/CHUNK18/body").exists()


def test_bundle_cross_type_replacement_rejected(logged_in, storage_root, small_chunks):
    cue_id = _stage(logged_in, "game.cue", CUE, "segaCD")
    bin_id = _stage(logged_in, "track01.bin", BIN, "segaCD")
    created = _create_bundle(logged_in, "跨类型", "CHUNK19", [cue_id, bin_id], "segaCD")
    game_id = created.json()["data"]["id"]
    before = created.json()["data"]

    adf_one = _stage(logged_in, "disc1.adf", b"disk1", "amiga")
    adf_two = _stage(logged_in, "disc2.adf", b"disk2", "amiga")
    response = _replace_bundle(logged_in, game_id, [adf_one, adf_two])
    assert response.status_code == 400
    after = logged_in.get(f"/api/games/manage/{game_id}").json()["data"]
    assert after["game_path"] == before["game_path"]
    assert after["crc32"] == before["crc32"]


def test_bundle_rejects_type_change_and_delete_cleans_body(
    logged_in, storage_root, small_chunks
):
    cue_id = _stage(logged_in, "game.cue", CUE, "segaCD")
    bin_id = _stage(logged_in, "track01.bin", BIN, "segaCD")
    created = _create_bundle(logged_in, "删多文件", "CHUNK20", [cue_id, bin_id], "segaCD")
    game_id = created.json()["data"]["id"]

    changed = logged_in.put(
        f"/api/games/manage/{game_id}/game-type", json={"game_type": "psx"}
    )
    assert changed.status_code == 400
    assert "多文件" in changed.json()["message"]

    assert logged_in.delete(f"/api/games/manage/{game_id}").status_code == 200
    assert not (storage_root / "game/segaCD/CHUNK20").exists()


def test_bundle_reference_validation_messages(logged_in, small_chunks):
    # cue 引用了不存在的文件
    bad_cue = _stage(
        logged_in,
        "bad.cue",
        b'FILE "missing.bin" BINARY\n  TRACK 01 MODE1/2352\n',
        "segaCD",
    )
    response = _create_bundle(logged_in, "坏引用", "CHUNK21", [bad_cue], "segaCD")
    assert response.status_code == 400
    assert "不在本次上传里" in response.json()["message"]

    # m3u 引用远程地址
    bad_m3u = _stage(
        logged_in, "bad.m3u", b"#EXTM3U\nhttp://example.com/disc.cue\n", "amiga"
    )
    response = _create_bundle(logged_in, "远程引用", "CHUNK22", [bad_m3u], "amiga")
    assert response.status_code == 400
    assert "远程" in response.json()["message"]

    # cue 引用子目录
    nested = _stage(
        logged_in,
        "nested.cue",
        b'FILE "sub/track.bin" BINARY\n  TRACK 01 MODE1/2352\n',
        "segaCD",
    )
    bin_id = _stage(logged_in, "track.bin", b"data", "segaCD")
    response = _create_bundle(logged_in, "子目录", "CHUNK23", [nested, bin_id], "segaCD")
    assert response.status_code == 400
    assert "同一层" in response.json()["message"]

    # 大小写不一致
    case_cue = _stage(
        logged_in,
        "case.cue",
        b'FILE "Track01.BIN" BINARY\n  TRACK 01 MODE1/2352\n',
        "segaCD",
    )
    lower_bin = _stage(logged_in, "track01.bin", b"data", "segaCD")
    response = _create_bundle(
        logged_in, "大小写", "CHUNK24", [case_cue, lower_bin], "segaCD"
    )
    assert response.status_code == 400
    assert "大小写" in response.json()["message"]

    # m3u 引用的 cue 自己缺分轨：入口校验通过，但 cue 也要被校验
    broken_cue = _stage(
        logged_in,
        "disc1.cue",
        b'FILE "missing.bin" BINARY\n  TRACK 01 MODE1/2352\n',
        "segaCD",
    )
    playlist = _stage(logged_in, "game.m3u", b"#EXTM3U\ndisc1.cue\n", "segaCD")
    response = _create_bundle(
        logged_in, "m3u坏cue", "CHUNK27", [playlist, broken_cue], "segaCD"
    )
    assert response.status_code == 400
    assert "不在本次上传里" in response.json()["message"]

    # 文件名重复
    one = _stage(logged_in, "same.bin", b"aaaa", "segaCD")
    two = _stage(logged_in, "same.bin", b"bbbb", "segaCD")
    cue = _stage(logged_in, "dup.cue", b'FILE "same.bin" BINARY\n', "segaCD")
    response = _create_bundle(logged_in, "重名", "CHUNK25", [cue, one, two], "segaCD")
    assert response.status_code == 400
    assert "重复" in response.json()["message"]


def test_bundle_follows_cartridge_id_rename(logged_in, storage_root, small_chunks):
    cue_id = _stage(logged_in, "game.cue", CUE, "segaCD")
    bin_id = _stage(logged_in, "track01.bin", BIN, "segaCD")
    created = _create_bundle(logged_in, "改ID", "CHUNK28", [cue_id, bin_id], "segaCD")
    game_id = created.json()["data"]["id"]

    renamed = logged_in.put(
        f"/api/games/manage/{game_id}/cartridge-id",
        json={"cartridge_id": "CHUNK29"},
    )
    assert renamed.status_code == 200, renamed.text
    item = renamed.json()["data"]
    assert item["game_path"] == "game/segaCD/CHUNK29/body/game.cue"
    assert (storage_root / "game/segaCD/CHUNK29/body/game.cue").read_bytes() == CUE
    assert (storage_root / "game/segaCD/CHUNK29/body/track01.bin").read_bytes() == BIN
    assert not (storage_root / "game/segaCD/CHUNK28").exists()


def test_bundle_missing_manifest_is_reported(logged_in, storage_root, small_chunks):
    cue_id = _stage(logged_in, "game.cue", CUE, "segaCD")
    bin_id = _stage(logged_in, "track01.bin", BIN, "segaCD")
    created = _create_bundle(logged_in, "缺清单", "CHUNK31", [cue_id, bin_id], "segaCD")
    game_id = created.json()["data"]["id"]
    (storage_root / "game/segaCD/CHUNK31/body/manifest.json").unlink()

    response = logged_in.get(f"/api/games/{game_id}/play/manifest")
    assert response.status_code == 400
    assert "清单" in response.json()["message"]
    assert logged_in.get(f"/api/games/{game_id}/play/files/track01.bin").status_code == 400


def test_network_url_rejects_bundle_only_extension(logged_in):
    response = logged_in.post(
        "/api/games/manage",
        data={
            "name": "直链cue",
            "cartridge_id": "CHUNK30",
            "body_url": "https://example.com/game.cue",
            "body_game_type": "segaCD",
        },
    )
    assert response.status_code == 400
    assert "网络直链" in response.json()["message"]


def test_bundle_rejects_duplicate_upload_ids(logged_in, small_chunks):
    adf_id = _stage(logged_in, "disc1.adf", b"disk", "amiga")
    response = _create_bundle(logged_in, "重复会话", "CHUNK26", [adf_id, adf_id], "amiga")
    assert response.status_code == 400
    assert "重复" in response.json()["message"]


def test_normalize_bundle_name_rules():
    assert normalize_bundle_name("Sonic CD (USA).cue") == "Sonic CD (USA).cue"
    for raw in (
        "../evil.bin",
        "sub/track.bin",
        "sub\\track.bin",
        "bad?.bin",
        "bad#.bin",
        "bad%.bin",
        "manifest.json",
        "CON.bin",
        "name.",
        "name ",
        "noext",
    ):
        with pytest.raises(ValidationError):
            normalize_bundle_name(raw)


def test_build_bundle_rejects_too_many_files():
    platform = PLATFORM_BY_ID["amiga"]
    files = tuple(
        StagedBundleFile(f"disc{index}.adf", 1, f"{index:032x}")
        for index in range(MAX_BUNDLE_FILES + 1)
    )
    with pytest.raises(ValidationError):
        build_bundle(files, platform, lambda _file: b"")
