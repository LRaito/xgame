"""Windows「解压即用」包里的纯逻辑测试：启动器、版本号脚本、运行时钉版文件、图标脚本。

启动器本身是打包脚本（`packaging/windows/launcher.py`），不是后端服务的一部分，但它有两段
逻辑错了会很难发现：**局域网地址排序**（错了用户照着打出来的地址连不上）与**包内默认配置**
（`xgame.ini` 的模板坏了等于包一启动就崩）。这些是纯函数，直接钉住。
"""

import configparser
import importlib.util
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

LAUNCHER_PATH = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "launcher.py"
UPGRADE_CMD_PATH = LAUNCHER_PATH.parent / "升级数据库.cmd"
SMOKE_WIN_PATH = LAUNCHER_PATH.parent / "smoke_win.py"
BUILD_WIN_DIST_PATH = LAUNCHER_PATH.parent / "build-win-dist.sh"


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("xgame_launcher", LAUNCHER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # 模块级只有定义，没有副作用
    return module


def _write_package(root: Path, version: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "version.txt").write_text(version, encoding="utf-8")


# ---------- 版本号脚本（Docker 路线与 Windows 包共用同一份）----------

VERSION_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "version.sh"


def _build_version() -> str:
    result = subprocess.run(  # noqa: S603 - 跑的是仓库自己的脚本
        ["bash", str(VERSION_SCRIPT)], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_version_script_output_shape():
    """版本号要能进包名、也要过前端版本探针的白名单（[0-9A-Za-z._-]，≤64 字符）。"""
    assert re.fullmatch(r"v[0-9][0-9A-Za-z._-]{0,62}", _build_version())


def test_version_script_is_stable_for_the_same_commit():
    """同一个提交反复跑要得到同一个版本号。

    后缀用的是**提交时间**而不是构建时刻——否则每次重建都会换个号，已经打开的页面
    会平白弹一次「有新版本」。
    """
    assert _build_version() == _build_version()


# ---------- 运行时钉版文件（构建环境镜像与组装脚本共用同一份）----------

RUNTIME_ENV = (
    Path(__file__).resolve().parent.parent / "packaging" / "windows" / "runtime.env"
)


def _runtime_env() -> dict[str, str]:
    """按 shell 的语义读一遍 runtime.env（文件名与 URL 是用 ${PBS_RELEASE} 拼出来的）。"""
    script = '. "$1" && printf "%s\\n" "$PBS_RELEASE" "$PBS_ASSET" "$PBS_SHA256" "$PBS_URL"'
    result = subprocess.run(  # noqa: S603 - 跑的是仓库自己的文件
        ["bash", "-c", script, "bash", str(RUNTIME_ENV)],
        capture_output=True,
        text=True,
        check=True,
    )
    keys = ("PBS_RELEASE", "PBS_ASSET", "PBS_SHA256", "PBS_URL")
    return dict(zip(keys, result.stdout.splitlines()))


def test_runtime_env_pins_one_consistent_runtime():
    """运行时钉版文件得自洽：文件名里带 release、URL 指向那个文件名、sha256 是 64 位十六进制。

    Dockerfile.build 照这些变量名把运行时下进镜像，build-win-dist.sh 照同一个文件名去镜像里取，
    名字对不上就成了「镜像里有、组装时找不到」这种很难一眼看出的失败。
    """
    env = _runtime_env()
    assert re.fullmatch(r"\d{8}", env["PBS_RELEASE"])
    assert env["PBS_RELEASE"] in env["PBS_ASSET"]
    assert env["PBS_ASSET"].endswith(".tar.gz")
    assert env["PBS_URL"].endswith(f"/{env['PBS_RELEASE']}/{env['PBS_ASSET']}")
    assert re.fullmatch(r"[0-9a-f]{64}", env["PBS_SHA256"])


# ---------- 「来自 Internet」标记 ----------


def test_still_locked_is_windows_only(launcher):
    """非 Windows 上直接返回 False：那里没有 NTFS 数据流，也不该去 stat 带冒号的路径。"""
    if os.name != "nt":
        assert launcher.still_locked() is False


# ---------- 包内版本号 ----------


def test_current_version_reads_package_file(launcher, tmp_path, monkeypatch):
    root = tmp_path / "xgame"
    monkeypatch.setattr(launcher, "ROOT", root)
    assert launcher.current_version() == "v0.0.0"  # 文件还没有时的兜底

    _write_package(root, "v9.9.9")
    assert launcher.current_version() == "v9.9.9"


# ---------- 局域网地址排序 ----------


def test_ip_rank_prefers_real_lan_addresses(launcher):
    """真实内网段排在前面，WSL/Hyper-V 的虚拟网段排最后。

    这台机器上装过 Docker/WSL 时，只问系统「出口网卡是谁」经常得到 198.18.x.x，
    用户照这个地址在手机上打是连不上的——所以要按网段排。
    """
    ranked = sorted(
        ["198.18.0.1", "172.20.5.5", "10.1.2.3", "192.168.1.7", "100.64.0.9"],
        key=launcher._ip_rank,
    )
    assert ranked == ["192.168.1.7", "10.1.2.3", "172.20.5.5", "100.64.0.9", "198.18.0.1"]


def test_usable_ip_filters_loopback_and_link_local(launcher):
    assert launcher._usable_ip("192.168.1.7")
    assert not launcher._usable_ip("127.0.0.1")
    assert not launcher._usable_ip("169.254.10.1")


# ---------- 包内默认配置 ----------


def test_ini_template_parses_to_expected_defaults(launcher, monkeypatch):
    """`xgame.ini` 由这个模板生成，模板坏了等于包一启动就崩，所以钉住解析结果。"""
    monkeypatch.setattr(launcher, "ROOT", Path("/opt/xgame"))
    parser = configparser.ConfigParser()
    parser.read_string(launcher._INI_TEMPLATE)
    config = launcher.Config(parser)

    assert config.port == 8910
    assert config.host == "0.0.0.0"
    assert config.open_browser is True
    assert config.data_dir == Path("/opt/xgame/data")
    # 运行时目录没配时跟着数据目录走（库与解包缓存都在它下面）
    assert config.runtime_dir == Path("/opt/xgame/data/runtime")


def test_runtime_dir_follows_data_dir_and_can_be_overridden(launcher, monkeypatch):
    """运行时目录默认跟着 data_dir，也可以单独配（两个根与 Docker 那条路线同一个模型）。"""
    monkeypatch.setattr(launcher, "ROOT", Path("/opt/xgame"))

    follows = launcher.Config(configparser.ConfigParser())
    assert follows.data_dir == Path("/opt/xgame/data")
    assert follows.runtime_dir == Path("/opt/xgame/data/runtime")

    parser = configparser.ConfigParser()
    parser.read_string("[xgame]\ndata_dir = /srv/xgame-data\n")
    assert launcher.Config(parser).runtime_dir == Path("/srv/xgame-data/runtime")

    parser = configparser.ConfigParser()
    parser.read_string("[xgame]\nruntime_dir = /srv/xgame-runtime\n")
    assert launcher.Config(parser).runtime_dir == Path("/srv/xgame-runtime")


def test_config_falls_back_on_bad_values(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", Path("/opt/xgame"))
    parser = configparser.ConfigParser()
    parser.read_string("[xgame]\nport = 不是数字\nopen_browser = no\n")
    config = launcher.Config(parser)

    assert config.port == 8910  # 坏值退回默认端口，而不是崩掉
    assert config.open_browser is False


# ---------- 图标（换 xgame.png 之后靠它生成 .ico）----------


@pytest.fixture
def make_icon():
    """按路径加载 packaging/windows/make_icon.py（它要 Pillow，没装就跳过）。"""
    pytest.importorskip("PIL")
    path = LAUNCHER_PATH.parent / "make_icon.py"
    spec = importlib.util.spec_from_file_location("xgame_make_icon", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _png(path: Path, size: tuple[int, int]) -> None:
    from PIL import Image

    Image.new("RGBA", size, (20, 40, 80, 255)).save(path)


def test_make_icon_builds_multi_size_ico(make_icon, tmp_path, capsys):
    from PIL import Image

    source = tmp_path / "xgame.png"
    target = tmp_path / "xgame.ico"
    _png(source, (512, 512))
    make_icon.SOURCE, make_icon.OUT = source, target

    assert make_icon.main() == 0

    ico = Image.open(target)
    assert sorted(ico.info["sizes"]) == sorted((s, s) for s in make_icon.SIZES)
    assert "已生成" in capsys.readouterr().out


def test_make_icon_center_crops_non_square(make_icon, tmp_path):
    """非正方形源图会被居中裁成正方形（图标必须是方的），而不是报错或拉变形。"""
    from PIL import Image

    source = tmp_path / "xgame.png"
    target = tmp_path / "xgame.ico"
    _png(source, (400, 200))
    make_icon.SOURCE, make_icon.OUT = source, target

    assert make_icon.main() == 0
    assert Image.open(target).info["sizes"]


def test_make_icon_warns_when_source_is_missing(make_icon, tmp_path):
    make_icon.SOURCE = tmp_path / "没有这张图.png"
    with pytest.raises(SystemExit) as excinfo:
        make_icon.main()
    assert "找不到源图" in str(excinfo.value)


# ---------- 包内数据库升级入口 ----------


def _config(launcher, tmp_path):
    parser = configparser.ConfigParser()
    parser.read_dict(
        {
            "xgame": {
                "data_dir": str(tmp_path / "data"),
                "runtime_dir": str(tmp_path / "runtime"),
            }
        }
    )
    return launcher.Config(parser)


class _FreeInstance:
    def __init__(self, _name):
        pass

    def acquire(self):
        return True


class _HeldInstance:
    def __init__(self, _name):
        pass

    def acquire(self):
        return False


def test_parse_args_maps_upgrade_db(launcher):
    assert launcher.parse_args(["--upgrade-db"])["action"] == "upgrade-db"
    assert "--upgrade-db" in launcher._USAGE


def test_main_dispatches_upgrade_db_without_winops(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "upgrade_database", lambda: 7)
    fake_winops = types.ModuleType("winops")
    fake_winops.run_action = lambda *_args: pytest.fail("升级动作不应经过 winops")
    monkeypatch.setitem(sys.modules, "winops", fake_winops)

    assert launcher.main(["--upgrade-db"]) == 7


def test_upgrade_database_refuses_when_service_holds_mutex(
    launcher, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(launcher, "load_config", lambda: _config(launcher, tmp_path))
    monkeypatch.setattr(launcher, "SingleInstance", _HeldInstance)
    monkeypatch.setattr(
        launcher, "port_in_use", lambda *_args: pytest.fail("互斥体已占用，不应再查端口")
    )

    with pytest.raises(SystemExit) as excinfo:
        launcher.upgrade_database()

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "正在运行" in out
    assert "升级数据库.cmd" in out


def test_upgrade_database_refuses_when_port_is_busy(
    launcher, tmp_path, monkeypatch, capsys
):
    config = _config(launcher, tmp_path)
    monkeypatch.setattr(launcher, "load_config", lambda: config)
    monkeypatch.setattr(launcher, "SingleInstance", _FreeInstance)
    monkeypatch.setattr(launcher, "port_in_use", lambda _host, _port: True)

    with pytest.raises(SystemExit) as excinfo:
        launcher.upgrade_database()

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert str(config.port) in out
    assert "关闭启动窗口" in out


def test_upgrade_database_passes_package_roots_and_returns_cli_code(
    launcher, tmp_path, monkeypatch
):
    config = _config(launcher, tmp_path)
    monkeypatch.setattr(launcher, "load_config", lambda: config)
    monkeypatch.setattr(launcher, "SingleInstance", _FreeInstance)
    monkeypatch.setattr(launcher, "port_in_use", lambda _host, _port: False)
    calls = []
    monkeypatch.setattr(
        launcher,
        "_upgrade_cli_main",
        lambda argv: calls.append(argv) or 1,
    )

    assert launcher.upgrade_database() == 1
    assert calls == [
        [
            "--storage-root",
            str(config.data_dir),
            "--runtime-root",
            str(config.runtime_dir),
        ]
    ]


def test_upgrade_database_wraps_unexpected_exception(
    launcher, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(launcher, "load_config", lambda: _config(launcher, tmp_path))
    monkeypatch.setattr(launcher, "SingleInstance", _FreeInstance)
    monkeypatch.setattr(launcher, "port_in_use", lambda _host, _port: False)

    def boom(_argv):
        raise RuntimeError("磁盘已满")

    monkeypatch.setattr(launcher, "_upgrade_cli_main", boom)

    with pytest.raises(SystemExit) as excinfo:
        launcher.upgrade_database()

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "升级数据库时出错" in out
    assert "磁盘已满" in out


def test_upgrade_database_warns_about_mounted_sentinel(
    launcher, tmp_path, monkeypatch, capsys
):
    config = _config(launcher, tmp_path)
    config.data_dir.mkdir(parents=True)
    (config.data_dir / ".mounted").touch()
    monkeypatch.setattr(launcher, "load_config", lambda: config)
    monkeypatch.setattr(launcher, "SingleInstance", _FreeInstance)
    monkeypatch.setattr(launcher, "port_in_use", lambda _host, _port: False)
    monkeypatch.setattr(launcher, "_upgrade_cli_main", lambda _argv: 0)

    assert launcher.upgrade_database() == 0
    out = capsys.readouterr().out
    assert ".mounted" in out
    assert "Docker/WSL" in out


def test_upgrade_cmd_is_ascii_lf_without_bom():
    raw = UPGRADE_CMD_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    text = raw.decode("ascii")
    assert "chcp 65001" in text
    assert 'cd /d "%~dp0"' in text
    assert "launcher.py" in text
    assert "--upgrade-db" in text
    assert "pause" in text


def test_smoke_requires_upgrade_cli():
    spec = importlib.util.spec_from_file_location("xgame_smoke", SMOKE_WIN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "upgrade.cli" in module.REQUIRED_MODULES


def test_build_script_ships_upgrade_tool():
    text = BUILD_WIN_DIST_PATH.read_text(encoding="utf-8")
    assert "$REPO/upgrade" in text
    assert "upgrade/versions/v1.py" in text
    assert "升级数据库.cmd" in text
