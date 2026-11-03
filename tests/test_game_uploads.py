import io
import os
import time
import zipfile
import zlib

import pytest
from fastapi.testclient import TestClient

from backend.games import paths
from backend.games.uploads import BodyUploadService, CHUNK_SIZE, SINGLE_FILE_MAX


def _init(client, filename="game.nes", size=8, game_type=""):
    response = client.post(
        "/api/games/uploads",
        json={"filename": filename, "size": size, "game_type": game_type},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _put(client, upload_id, index, data):
    response = client.put(
        f"/api/games/uploads/{upload_id}/chunks/{index}",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _complete(client, upload_id):
    return client.post(f"/api/games/uploads/{upload_id}/complete")


def _crc32(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


def _zip_with_entry(entry: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(entry, data)
    return buffer.getvalue()


@pytest.fixture
def small_chunks(monkeypatch):
    monkeypatch.setattr("backend.games.uploads.CHUNK_SIZE", 4)


def test_chunked_upload_creates_game_in_order(logged_in, storage_root, small_chunks):
    data = b"abcdefgh"
    upload = _init(logged_in, "demo.nes", len(data))
    assert upload["chunk_size"] == 4
    assert upload["total_chunks"] == 2

    _put(logged_in, upload["upload_id"], 1, data[4:])
    _put(logged_in, upload["upload_id"], 0, data[:4])
    completed = _complete(logged_in, upload["upload_id"])
    assert completed.status_code == 200, completed.text

    created = logged_in.post(
        "/api/games/manage",
        data={
            "name": "分片游戏",
            "cartridge_id": "CHUNK01",
            "upload_id": upload["upload_id"],
        },
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["game_path"] == "game/nes/CHUNK01/game.nes"
    assert item["size"] == len(data)
    assert item["crc32"] == _crc32(data)
    assert (storage_root / item["game_path"]).read_bytes() == data
    # 提交后暂存目录应被删掉
    assert not (storage_root / paths.upload_session_dir(upload["upload_id"])).exists()


def test_chunked_upload_creates_game_with_cover(logged_in, storage_root, small_chunks):
    data = b"abcdefgh"
    upload = _init(logged_in, "cover.nes", len(data))
    _put(logged_in, upload["upload_id"], 0, data[:4])
    _put(logged_in, upload["upload_id"], 1, data[4:])
    assert _complete(logged_in, upload["upload_id"]).status_code == 200

    created = logged_in.post(
        "/api/games/manage",
        data={
            "name": "带封面",
            "cartridge_id": "CHUNK07",
            "upload_id": upload["upload_id"],
        },
        files={"cover": ("cover.png", b"png-bytes", "image/png")},
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["cover_path"] == "game/nes/CHUNK07/cover.png"
    assert (storage_root / item["cover_path"]).read_bytes() == b"png-bytes"
    assert (storage_root / item["game_path"]).read_bytes() == data


def test_chunked_upload_replaces_body(logged_in, storage_root, small_chunks):
    old = b"old-body"
    created = logged_in.post(
        "/api/games/manage",
        data={"name": "换本体", "cartridge_id": "CHUNK02"},
        files={"file": ("demo.nes", old, "application/octet-stream")},
    )
    assert created.status_code == 201, created.text
    game_id = created.json()["data"]["id"]

    new = b"new-body"
    upload = _init(logged_in, "demo.nes", len(new))
    _put(logged_in, upload["upload_id"], 0, new[:4])
    _put(logged_in, upload["upload_id"], 1, new[4:])
    assert _complete(logged_in, upload["upload_id"]).status_code == 200

    replaced = logged_in.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game", "upload_id": upload["upload_id"]},
    )
    assert replaced.status_code == 201, replaced.text
    item = replaced.json()["data"]
    assert item["size"] == len(new)
    assert item["crc32"] == _crc32(new)
    assert (storage_root / item["game_path"]).read_bytes() == new
    assert not (storage_root / paths.upload_session_dir(upload["upload_id"])).exists()


def test_chunked_upload_rejects_missing_chunk(logged_in, storage_root, small_chunks):
    upload = _init(logged_in, "demo.nes", 8)
    _put(logged_in, upload["upload_id"], 0, b"abcd")
    response = _complete(logged_in, upload["upload_id"])
    assert response.status_code == 400
    assert "分片" in response.json()["message"]
    assert (storage_root / paths.upload_session_dir(upload["upload_id"])).exists()


def test_chunked_upload_rejects_wrong_size(logged_in, small_chunks):
    upload = _init(logged_in, "demo.nes", 8)
    response = logged_in.put(
        f"/api/games/uploads/{upload['upload_id']}/chunks/0",
        content=b"abc",
        headers={"Content-Type": "application/octet-stream", "Content-Length": "3"},
    )
    assert response.status_code == 400
    assert "大小" in response.json()["message"]


def test_chunked_upload_rejects_bad_index(logged_in, small_chunks):
    upload = _init(logged_in, "demo.nes", 8)
    response = logged_in.put(
        f"/api/games/uploads/{upload['upload_id']}/chunks/2",
        content=b"abcd",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 400
    assert "序号" in response.json()["message"]


def test_chunked_upload_is_isolated_between_users(app, logged_in, small_chunks):
    upload = _init(logged_in, "demo.nes", 8)
    other = TestClient(app)
    response = other.post(
        "/api/register", json={"username": "bob", "password": "secret123"}
    )
    assert response.status_code == 200, response.text

    response = other.put(
        f"/api/games/uploads/{upload['upload_id']}/chunks/0",
        content=b"abcd",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 404
    assert other.post(f"/api/games/uploads/{upload['upload_id']}/complete").status_code == 404
    assert other.delete(f"/api/games/uploads/{upload['upload_id']}").status_code == 404


def test_chunked_upload_discard_is_idempotent(logged_in, storage_root, small_chunks):
    upload = _init(logged_in, "demo.nes", 8)
    url = f"/api/games/uploads/{upload['upload_id']}"
    assert logged_in.delete(url).status_code == 200
    assert logged_in.delete(url).status_code == 200
    assert not (storage_root / paths.upload_session_dir(upload["upload_id"])).exists()


def test_chunk_put_without_content_length_is_allowed(logged_in, small_chunks):
    upload = _init(logged_in, "demo.nes", 8)
    response = logged_in.put(
        f"/api/games/uploads/{upload['upload_id']}/chunks/0",
        content=iter([b"ab", b"cd"]),
    )
    assert response.status_code == 200, response.text
    _put(logged_in, upload["upload_id"], 1, b"efgh")
    assert _complete(logged_in, upload["upload_id"]).status_code == 200


def test_create_rejects_file_and_upload_id(logged_in, small_chunks):
    upload = _init(logged_in, "demo.nes", 4)
    _put(logged_in, upload["upload_id"], 0, b"abcd")
    assert _complete(logged_in, upload["upload_id"]).status_code == 200
    response = logged_in.post(
        "/api/games/manage",
        data={
            "name": "两种来源",
            "cartridge_id": "CHUNK03",
            "upload_id": upload["upload_id"],
        },
        files={"file": ("demo.nes", b"abcd", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "一种" in response.json()["message"]


def test_single_file_upload_over_threshold_is_rejected(logged_in, monkeypatch):
    monkeypatch.setattr("backend.games.service.SINGLE_FILE_MAX", 4)
    response = logged_in.post(
        "/api/games/manage",
        data={"name": "超限", "cartridge_id": "CHUNK04"},
        files={"file": ("demo.nes", b"abcde", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "分片上传" in response.json()["message"]


def test_chunked_upload_rejects_cross_type_replacement(logged_in, small_chunks):
    created = logged_in.post(
        "/api/games/manage",
        data={"name": "Nes游戏", "cartridge_id": "CHUNK05"},
        files={"file": ("demo.nes", b"nes-body", "application/octet-stream")},
    )
    assert created.status_code == 201, created.text
    game_id = created.json()["data"]["id"]
    before = created.json()["data"]

    upload = _init(logged_in, "demo.gb", 6)
    _put(logged_in, upload["upload_id"], 0, b"gb-g")
    _put(logged_in, upload["upload_id"], 1, b"b!")
    assert _complete(logged_in, upload["upload_id"]).status_code == 200

    response = logged_in.post(
        f"/api/games/manage/{game_id}/assets",
        data={"kind": "game", "upload_id": upload["upload_id"]},
    )
    assert response.status_code == 400
    after = logged_in.get(f"/api/games/manage/{game_id}").json()["data"]
    assert after["game_path"] == before["game_path"]
    assert after["crc32"] == before["crc32"]


def test_chunked_h5_upload_and_commit(logged_in, storage_root, small_chunks):
    data = _zip_with_entry("index.html", b"<h1>hi</h1>")
    upload = _init(logged_in, "demo.zip", len(data))
    offset = 0
    for index in range(upload["total_chunks"]):
        end = min(offset + upload["chunk_size"], len(data))
        _put(logged_in, upload["upload_id"], index, data[offset:end])
        offset = end
    assert _complete(logged_in, upload["upload_id"]).status_code == 200

    created = logged_in.post(
        "/api/games/manage",
        data={
            "name": "分片 H5",
            "cartridge_id": "CHUNK06",
            "upload_id": upload["upload_id"],
        },
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["game_type"] == "h5"
    assert item["game_path"] == "game/h5/CHUNK06/game.zip"
    assert item["crc32"] == _crc32(data)
    assert (storage_root / item["game_path"]).read_bytes() == data


def test_cleanup_stale_uploads(app, logged_in, storage_root, small_chunks):
    old = _init(logged_in, "old.nes", 4)
    fresh = _init(logged_in, "fresh.nes", 4)
    old_path = storage_root / paths.upload_meta_path(old["upload_id"])
    os.utime(old_path, (time.time() - 1000, time.time() - 1000))

    removed = BodyUploadService.cleanup_stale(app.state.storage, max_age_seconds=10)
    assert removed == 1
    assert not (storage_root / paths.upload_session_dir(old["upload_id"])).exists()
    assert (storage_root / paths.upload_session_dir(fresh["upload_id"])).exists()


def test_status_exposes_upload_limits(logged_in):
    payload = logged_in.get("/api/games/status").json()["data"]
    assert payload["upload"]["single_file_max_bytes"] == SINGLE_FILE_MAX
    assert payload["upload"]["chunk_size_bytes"] == CHUNK_SIZE
