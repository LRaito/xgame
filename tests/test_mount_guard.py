"""启动时的数据根目录哨兵文件：缺了就建，不拦启动。"""

from pathlib import Path

from backend import create_app
from backend.config import Settings
from backend.mount_guard import SENTINEL_NAME, ensure_mounted, has_sentinel, sentinel_path


def _settings(storage: Path) -> Settings:
    return Settings(TESTING=True, STORAGE_ROOT=str(storage))


def test_sentinel_lives_in_storage_root(tmp_path):
    storage = tmp_path / "storage"
    assert sentinel_path(_settings(storage)) == storage / SENTINEL_NAME


def test_ensure_mounted_creates_root_and_sentinel(tmp_path):
    storage = tmp_path / "storage"
    assert not storage.exists()  # 根目录都还不存在

    path = ensure_mounted(_settings(storage))

    assert path == storage / SENTINEL_NAME
    assert path.is_file()
    assert path.read_text() == ""
    assert has_sentinel(_settings(storage)) is True


def test_ensure_mounted_keeps_existing_sentinel(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir(parents=True)
    (storage / SENTINEL_NAME).write_text("原有内容")

    ensure_mounted(_settings(storage))

    assert (storage / SENTINEL_NAME).read_text() == "原有内容"


def test_app_creates_sentinel_on_startup(tmp_path):
    """服务启动时检查一次：根目录没有哨兵文件就补上，然后照常起来。"""
    storage = tmp_path / "storage"

    app = create_app({"TESTING": True, "STORAGE_ROOT": str(storage)})

    assert (storage / SENTINEL_NAME).is_file()
    assert has_sentinel(app.state.settings) is True
