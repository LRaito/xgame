"""哨兵检查的测试：数据根与运行时根各查各自挂载点下的 `.mounted`。

宿主路径（判断用）与挂载点（查文件用）在真实部署里是两个世界，所以这里刻意把
`STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR` 设成 `/mnt/...` 这种假路径，而把 `STORAGE_ROOT` /
`RUNTIME_ROOT` 指向 `tmp_path`，这样哨兵文件落在临时目录里、可控。
"""

from pathlib import Path

import pytest

from backend import mount_guard
from backend.config import Settings
from backend.mount_guard import mount_pairs, on_windows_mount, require_mounted


@pytest.fixture(autouse=True)
def fast_guard(monkeypatch):
    """前缀固定 /mnt，等待时间归零，免得测试真的睡 5 秒。"""
    monkeypatch.setattr(mount_guard, "WINDOWS_MOUNT_PREFIX", "/mnt")
    monkeypatch.setattr(mount_guard, "RESTART_DELAY_SECONDS", 0)


def test_on_windows_mount_matches_by_path_parts():
    assert on_windows_mount(Path("/mnt/x/xgame"))
    assert not on_windows_mount(Path("/mntfoo"))
    assert not on_windows_mount(Path("/srv/xgame"))


def test_mount_pairs_dedupes_same_directory(tmp_path):
    """两个根默认指同一个目录：只剩一条，行为与只看数据根时一样。"""
    settings = Settings(TESTING=True, STORAGE_ROOT=str(tmp_path))
    assert mount_pairs(settings) == [(tmp_path, tmp_path)]


def test_mount_pairs_returns_both_roots(tmp_path):
    settings = Settings(
        TESTING=True,
        STORAGE_ROOT=str(tmp_path / "storage"),
        RUNTIME_ROOT=str(tmp_path / "runtime"),
        STORAGE_HOST_DIR="/mnt/x/xgame",
        RUNTIME_HOST_DIR="/mnt/x/xgame-runtime",
    )
    assert mount_pairs(settings) == [
        (Path("/mnt/x/xgame"), tmp_path / "storage"),
        (Path("/mnt/x/xgame-runtime"), tmp_path / "runtime"),
    ]


def test_passes_when_roots_are_not_on_windows_mount(tmp_path):
    settings = Settings(TESTING=True, STORAGE_ROOT=str(tmp_path))
    require_mounted(settings)
    # 不在那个前缀下就只是放行，不建目录也不建文件
    assert list(tmp_path.iterdir()) == []


def test_skips_when_testing(tmp_path):
    """同一份「缺哨兵」的配置：TESTING 下放行，非 TESTING 下退出。"""
    overrides = {"STORAGE_ROOT": str(tmp_path), "STORAGE_HOST_DIR": "/mnt/x/xgame"}

    with pytest.raises(SystemExit) as excinfo:
        require_mounted(Settings(TESTING=False, **overrides))
    assert excinfo.value.code == mount_guard.EXIT_CODE

    require_mounted(Settings(TESTING=True, **overrides))


def test_exits_when_storage_sentinel_missing(tmp_path, caplog):
    settings = Settings(
        TESTING=False,
        STORAGE_ROOT=str(tmp_path / "storage"),
        STORAGE_HOST_DIR="/mnt/x/xgame",
    )
    with pytest.raises(SystemExit) as excinfo:
        require_mounted(settings)

    assert excinfo.value.code == mount_guard.EXIT_CODE
    assert "/mnt/x/xgame/.mounted" in caplog.text


def test_exits_when_runtime_sentinel_missing(tmp_path, caplog):
    """数据根有哨兵、运行时根没有：照样拒绝启动（空挂载里会新建一个空 app.db）。"""
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / ".mounted").touch()

    settings = Settings(
        TESTING=False,
        STORAGE_ROOT=str(storage),
        STORAGE_HOST_DIR="/mnt/x/xgame",
        RUNTIME_ROOT=str(tmp_path / "runtime"),
        RUNTIME_HOST_DIR="/mnt/x/xgame-runtime",
    )
    with pytest.raises(SystemExit) as excinfo:
        require_mounted(settings)

    assert excinfo.value.code == mount_guard.EXIT_CODE
    assert "/mnt/x/xgame-runtime/.mounted" in caplog.text


def test_passes_when_both_sentinels_present(tmp_path):
    storage = tmp_path / "storage"
    runtime = tmp_path / "runtime"
    for root in (storage, runtime):
        root.mkdir()
        (root / ".mounted").touch()

    require_mounted(
        Settings(
            TESTING=False,
            STORAGE_ROOT=str(storage),
            STORAGE_HOST_DIR="/mnt/x/xgame",
            RUNTIME_ROOT=str(runtime),
            RUNTIME_HOST_DIR="/mnt/x/xgame-runtime",
        )
    )


def test_runtime_falls_back_to_storage_host_dir(tmp_path):
    """运行时根没给宿主路径时，判断退回 RUNTIME_ROOT（本机直跑的情形）。"""
    settings = Settings(TESTING=True, STORAGE_ROOT=str(tmp_path), RUNTIME_ROOT=str(tmp_path))
    assert mount_pairs(settings) == [(tmp_path, tmp_path)]
