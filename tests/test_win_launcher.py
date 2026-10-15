"""Windows「解压即用」包里启动器的纯逻辑测试。

启动器本身是打包脚本（`packaging/windows/launcher.py`），不是后端服务的一部分，
但它有两段逻辑错了会很难发现：**版本比较**（错了要么升不了级、要么反复升降级）
与**局域网地址排序**（错了用户照着打出来的地址连不上）。这两段是纯函数，直接钉住。
"""

import configparser
import importlib.util
from pathlib import Path

import pytest

LAUNCHER_PATH = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "launcher.py"


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


def _touch_zip(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"PK\x05\x06" + b"\0" * 18)  # 空 zip 的文件头，这里只关心文件名
    return path


# ---------- 版本比较 ----------


@pytest.mark.parametrize(
    ("newer", "older"),
    [
        ("v1.0.1", "v1.0.0"),
        ("v1.10.0", "v1.9.0"),  # 按数字段比，不是按字符串比
        ("v2.0", "v1.9.9"),
        ("v1.0.0.1", "v1.0.0"),
    ],
)
def test_version_key_orders_by_number(launcher, newer, older):
    assert launcher._version_key(newer) > launcher._version_key(older)


def test_version_key_treats_dirty_as_same_version(launcher):
    """`v1.0.0-dirty` 与 `v1.0.0` 是同一个版本号。

    本地改代码重新打的包会带 -dirty，不这样处理的话，同一个包会被反复判定为「有新版」。
    """
    assert launcher._version_key("v1.0.0-dirty") == launcher._version_key("v1.0.0")


# ---------- 找升级包 ----------


def test_find_update_picks_highest_newer_package(launcher, tmp_path, monkeypatch):
    root = tmp_path / "xgame"
    _write_package(root, "v1.0.0")
    monkeypatch.setattr(launcher, "ROOT", root)

    assert launcher.find_update() is None

    _touch_zip(root / "updates", "xgame_v1.0.1.zip")
    _touch_zip(root / "updates", "xgame_v1.2.0.zip")
    _touch_zip(root, "xgame_v0.9.0.zip")  # 更旧，忽略
    _touch_zip(root, "xgame_v1.0.0.zip")  # 同版本，忽略
    _touch_zip(root, "xgame_v1.0.0-dirty.zip")  # 同版本，忽略
    _touch_zip(root, "别的文件.zip")  # 名字不匹配，忽略
    (root / "updates" / "notes.txt").write_text("x", encoding="utf-8")

    found = launcher.find_update()
    assert found is not None
    assert found[1] == "v1.2.0"
    assert found[0].name == "xgame_v1.2.0.zip"


def test_find_update_looks_next_to_the_package_too(launcher, tmp_path, monkeypatch):
    """新包放在包目录旁边（很多人的习惯）也要能找到。"""
    root = tmp_path / "xgame"
    _write_package(root, "v1.0.0")
    monkeypatch.setattr(launcher, "ROOT", root)
    _touch_zip(tmp_path, "xgame_v3.1.4.zip")

    found = launcher.find_update()
    assert found is not None and found[1] == "v3.1.4"


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
    assert config.auto_update is True
    assert config.data_dir == Path("/opt/xgame/data")


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
