import io

import pytest

from backend.errors import StorageError, ValidationError
from backend.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path / "root")


def _stream(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


def test_upload_creates_parent_dirs_and_reads_back(storage):
    stored = storage.upload("game/nes/AB-12/game.nes", _stream(b"rom"), 3, None)
    assert stored.key == "game/nes/AB-12/game.nes"
    assert stored.size == 3
    assert stored.mime == "application/octet-stream"

    stream = storage.open_download("game/nes/AB-12/game.nes")
    try:
        assert stream.read() == b"rom"
        assert stream.size == 3
    finally:
        stream.close()
    assert storage.stat("game/nes/AB-12/game.nes").size == 3


def test_upload_overwrites_and_leaves_no_temp_file(storage, tmp_path):
    storage.upload("a/b.bin", _stream(b"old"), 3, None)
    storage.upload("a/b.bin", _stream(b"new-data"), 8, None)
    assert storage.stat("a/b.bin").size == 8
    names = sorted(p.name for p in (tmp_path / "root" / "a").iterdir())
    assert names == ["b.bin"]  # 临时文件写完后已改名，不留残渣


def test_mime_guessed_from_extension(storage):
    """磁盘上只存字节，不存元数据：上传时的 mime 只回给调用方，读取时按后缀现猜。"""
    stored = storage.upload("cover.png", _stream(b"png"), 3, None)
    assert stored.mime == "image/png"
    assert storage.upload("x.bin", _stream(b"x"), 1, "application/x-custom").mime == (
        "application/x-custom"
    )
    assert storage.open_download("cover.png").mime == "image/png"
    assert storage.open_download("x.bin").mime == "application/octet-stream"


def test_delete_is_idempotent(storage):
    storage.upload("a.bin", _stream(b"x"), 1, None)
    storage.delete("a.bin")
    storage.delete("a.bin")  # 再删一次不该报错
    with pytest.raises(StorageError):
        storage.stat("a.bin")
    with pytest.raises(StorageError):
        storage.open_download("a.bin")


def test_move_file(storage):
    storage.upload("game/nes/AB/game.nes", _stream(b"rom"), 3, None)
    assert storage.move("game/nes/AB/cover.png", "game/gba/AB/cover.png") is False
    assert storage.move("game/nes/AB/game.nes", "game/gba/AB/game.nes") is True
    assert not (storage.root / "game" / "nes" / "AB" / "game.nes").exists()
    assert storage.stat("game/gba/AB/game.nes").size == 3


def test_move_tree_moves_whole_directory(storage):
    """整目录搬迁（图集随游戏类型换目录）：嵌套子目录一起走，源目录不再留下。"""
    storage.upload("game/nes/AB/image/a.png", _stream(b"a"), 1, None)
    storage.upload("game/nes/AB/image/sub/b.png", _stream(b"b"), 1, None)

    assert storage.move_tree("game/nes/AB/image", "game/gba/AB/image") is True

    assert storage.stat("game/gba/AB/image/a.png").size == 1
    assert storage.stat("game/gba/AB/image/sub/b.png").size == 1
    assert not (storage.root / "game" / "nes" / "AB" / "image").exists()


def test_move_tree_is_noop_for_missing_source(storage):
    assert storage.move_tree("game/nes/AB/image", "game/gba/AB/image") is False
    assert not (storage.root / "game" / "gba").exists()


def test_move_tree_replaces_existing_target_and_handles_same_path(storage):
    storage.upload("game/nes/AB/image/old.png", _stream(b"old"), 3, None)
    storage.upload("game/gba/AB/image/new.png", _stream(b"new"), 3, None)

    # 目标已有内容：replace 语义（以源为准），不留 .old- 残渣
    assert storage.move_tree("game/nes/AB/image", "game/gba/AB/image") is True
    assert [p.name for p in (storage.root / "game" / "gba" / "AB" / "image").iterdir()] == [
        "old.png"
    ]
    assert storage.stat("game/gba/AB/image/old.png").size == 3

    # 源与目标同一个路径：什么也不做，目录还在
    assert storage.move_tree("game/gba/AB/image", "game/gba/AB/image") is True
    assert storage.stat("game/gba/AB/image/old.png").size == 3


def test_remove_tree_is_recursive_and_idempotent(storage):
    storage.upload("game/nes/AB/game.nes", _stream(b"rom"), 3, None)
    storage.upload("game/nes/AB/h5/index.html", _stream(b"<html>"), 6, None)
    storage.remove_tree("game/nes/AB")
    assert not (storage.root / "game" / "nes" / "AB").exists()
    storage.remove_tree("game/nes/AB")  # 不存在也不报错
    storage.remove_tree("game")  # 上层目录一并清掉


def test_replace_tree_swaps_directories(storage):
    storage.upload("game/h5/AB/h5/index.html", _stream(b"old"), 3, None)
    storage.upload("game/h5/AB/.h5-tmp/index.html", _stream(b"new"), 3, None)

    storage.replace_tree("game/h5/AB/.h5-tmp", "game/h5/AB/h5")

    stream = storage.open_download("game/h5/AB/h5/index.html")
    try:
        assert stream.read() == b"new"
    finally:
        stream.close()
    # 暂存目录被搬走，旧内容不残留
    assert not (storage.root / "game" / "h5" / "AB" / ".h5-tmp").exists()
    assert [p.name for p in (storage.root / "game" / "h5" / "AB").iterdir()] == ["h5"]


def test_replace_tree_requires_source(storage):
    with pytest.raises(StorageError):
        storage.replace_tree("missing-dir", "target-dir")


def test_replace_tree_moves_into_place_when_target_absent(storage):
    storage.upload("tmp/x.txt", _stream(b"fresh"), 5, None)
    storage.replace_tree("tmp", "final")
    assert storage.stat("final/x.txt").size == 5


@pytest.mark.parametrize(
    "bad", ["", "   ", "/etc/passwd", "../escape", "a/../../b", "a\\b", ".."]
)
def test_paths_outside_root_are_rejected(storage, bad):
    with pytest.raises(ValidationError):
        storage.upload(bad, _stream(b"x"), 1, None)
    with pytest.raises(ValidationError):
        storage.delete(bad)
    with pytest.raises(ValidationError):
        storage.stat(bad)
    with pytest.raises(ValidationError):
        storage.open_download(bad)
    with pytest.raises(ValidationError):
        storage.remove_tree(bad)


def test_constructor_creates_root(tmp_path):
    root = tmp_path / "deep" / "storage"
    LocalStorage(root)
    assert root.is_dir()
