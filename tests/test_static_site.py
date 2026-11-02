import pytest
from fastapi.testclient import TestClient

from backend import create_app

INDEX_HTML = b"<!doctype html><div id=app></div>"


@pytest.fixture
def dist(tmp_path):
    """一份最小的前端产物：入口、带哈希的资源、引擎目录、版本探针。"""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "ruffle").mkdir()
    (root / "emulatorjs" / "data" / "cores").mkdir(parents=True)
    (root / "emulatorjs" / "bios").mkdir()
    (root / "index.html").write_bytes(INDEX_HTML)
    (root / "emulator-host.html").write_bytes(b"<html>host</html>")
    (root / "version.txt").write_bytes(b"v1.0.0")
    (root / "assets" / "app-abc123.js").write_bytes(b"console.log(1)")
    (root / "ruffle" / "ruffle.wasm").write_bytes(b"\x00asm")
    (root / "emulatorjs" / "data" / "fceumm-wasm.data").write_bytes(b"core")
    (root / "emulatorjs" / "data" / "cores" / "melonds-wasm.data").write_bytes(b"nds-core")
    (root / "emulatorjs" / "bios" / "nds.zip").write_bytes(b"PK\x03\x04")
    (root / "media").mkdir()
    (root / "media" / "cover.png").write_bytes(b"\x89PNG")
    return root


@pytest.fixture
def site(tmp_path, dist):
    return TestClient(
        create_app({"TESTING": True, "STORAGE_ROOT": str(tmp_path / "s"), "STATIC_DIR": str(dist)})
    )


def test_serves_index_and_spa_fallback(site):
    """根路径与前端路由都回 index.html，且必须 no-cache（否则「部署完还是旧页面」）。"""
    for path in ("/", "/games", "/games/123"):
        response = site.get(path)
        assert response.status_code == 200
        assert response.content == INDEX_HTML
        assert response.headers["cache-control"] == "no-cache"


def test_serves_hashed_assets_with_immutable_cache(site):
    response = site.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["content-type"].startswith("text/javascript")


def test_engine_assets_have_explicit_mime(site):
    """MIME 必须来自显式表：Windows 上按注册表猜会把 .js 猜成 text/plain、整站白屏。"""
    wasm = site.get("/ruffle/ruffle.wasm")
    assert wasm.headers["content-type"] == "application/wasm"
    assert wasm.headers["cache-control"] == "public, max-age=31536000, immutable"

    core = site.get("/emulatorjs/data/fceumm-wasm.data")
    assert core.headers["content-type"] == "application/octet-stream"

    # 新加的 melonds core 与其它 core 一样走 immutable + octet-stream
    nds_core = site.get("/emulatorjs/data/cores/melonds-wasm.data")
    assert nds_core.status_code == 200
    assert nds_core.headers["content-type"] == "application/octet-stream"
    assert nds_core.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_nds_bios_is_no_cache(site):
    """BIOS 文件名固定、用户随时可能替换，不能跟着 /emulatorjs/ 走一年 immutable。"""
    response = site.get("/emulatorjs/bios/nds.zip")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"] == "application/zip"


def test_missing_nds_bios_is_404_not_index(site, dist):
    """BIOS 缺失时必须 404（宿主页据此提示），绝不回落 index.html。"""
    (dist / "emulatorjs" / "bios" / "nds.zip").unlink()
    response = site.get("/emulatorjs/bios/nds.zip")
    assert response.status_code == 404
    assert b"<div id=app>" not in response.content


@pytest.mark.parametrize("path", ["/assets/gone-000000.js", "/assets", "/assets/", "/ruffle"])
def test_missing_hashed_asset_is_404_not_index(site, path):
    """旧页面请求已下线的旧哈希 JS：必须 404，回落 index.html 会让报错变成
    `Unexpected token '<'`，极难排查。目录名本身（`/assets`）同样不回落。"""
    response = site.get(path)
    assert response.status_code == 404
    assert b"<div id=app>" not in response.content


def test_version_probe_is_plain_text_and_404_when_missing(site, dist):
    response = site.get("/version.txt")
    assert response.status_code == 200
    assert response.text == "v1.0.0"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith("text/plain")

    (dist / "version.txt").unlink()
    gone = site.get("/version.txt")
    assert gone.status_code == 404
    assert b"<div id=app>" not in gone.content


def test_emulator_host_is_no_cache(site):
    response = site.get("/emulator-host.html")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_other_static_files_get_no_cache_header(site):
    """其余静态文件（机壳图、封面图、Service Worker）与 nginx 一样不额外加缓存头。"""
    response = site.get("/media/cover.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "cache-control" not in response.headers


def test_api_404_stays_json(site):
    """`/api/` 下没匹配到的路径必须回 JSON，不能回落成 HTML（前端 axios 会拿到一坨 HTML）。"""
    response = site.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["ok"] is False


def test_api_routes_still_work_with_site_mounted(site):
    assert site.get("/health").text == "ok"
    assert (
        site.post("/api/register", json={"username": "alice", "password": "secret123"}).status_code
        == 200
    )
    assert site.get("/api/me").json()["data"] == {"username": "alice"}


@pytest.mark.parametrize(
    "path",
    [
        "/%2e%2e%2f%2e%2e%2fetc/passwd",
        "/assets/%2e%2e%2f%2e%2e%2findex.html",
        "/..%5c..%5cwindows%5cwin.ini",
        "/media/cover.png%00.html",
    ],
)
def test_path_traversal_is_rejected(site, path):
    """HTTP 层能拿到的越界写法（编码过的）一律拒掉，不回落到 index.html。

    裸的 `../..` 到不了服务端——httpx/浏览器会先在客户端把点段归一化掉，所以那些写法
    在下面按单元测（`_normalize` / `_resolve`）。
    """
    response = site.get(path)
    assert response.status_code == 404
    assert b"<div id=app>" not in response.content


@pytest.mark.parametrize("raw", ["../../etc/passwd", "..", "a/../../b", "a\\b", "a:b/c", "a\x00b"])
def test_normalize_rejects_illegal_paths(raw):
    """越界、反斜杠、盘符/ADS 里的冒号、NUL 一律拒掉。

    这里不像 H5 包内路径那样查 Windows 保留设备名与结尾点：静态站**只读不写**，请求里的
    名字最多命中 dist 里已有的文件，命中不了就回落 index.html，不会在磁盘上建出什么。
    """
    from backend.static_site import _normalize

    assert _normalize(raw) is None


def test_normalize_keeps_legal_paths():
    from backend.static_site import _normalize

    assert _normalize("assets/app.js") == "assets/app.js"
    assert _normalize("./media/cover.png") == "media/cover.png"
    # 前导斜杠按「站点根下的相对路径」处理（与 nginx 把 $uri 当 root 下路径一致），
    # 不是绝对路径——绝对路径才是危险的
    assert _normalize("/emulatorjs/data/x.data") == "emulatorjs/data/x.data"


def test_resolve_stays_inside_root(tmp_path, dist):
    """解析后必须仍在 dist 根之内（挡住符号链接等绕法）。"""
    from backend.static_site import _resolve

    root = dist.resolve()
    assert _resolve(root, "assets/app-abc123.js") == root / "assets" / "app-abc123.js"

    outside = tmp_path / "secret.txt"
    outside.write_text("nope")
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("本机不支持创建符号链接")
    assert _resolve(root, "link.txt") is None


def test_not_mounted_without_static_dir(client):
    """不设 STATIC_DIR（Docker 路线）时后端一条静态路由都不注册。"""
    assert client.get("/").status_code == 404
    assert client.get("/index.html").status_code == 404
    assert client.get("/version.txt").status_code == 404
    assert client.get("/health").status_code == 200
