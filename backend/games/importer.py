"""7k7k / 4399 / flash.homes 游戏搬运：解析游戏页、下载 Flash / HTML5 资源。

服务端唯一的搬运实现：给定游戏页地址，自动识别站点与资源类型（Flash SWF，
或被站点用 Ruffle 包装的「H5 版 Flash」），自包含的 HTML5 游戏则按原目录结构
镜像入口页 + JS/CSS/图片/音频；4399 上依赖在线运行时的纯联运 H5 会明确报错。
flash.homes 是 Flash 存档站，作品一律是按 sha256 存放的单个 SWF。

约定：只接受 7k7k / 4399 / flash.homes 域名下的游戏页地址（避免把服务端当成
任意 URL 代理）。下载产物写入调用方给的临时目录并返回 `ImportedGame`，由
`GameService.import_from_url` 负责落盘与建条目。
"""

from __future__ import annotations

import html as html_module
import json
import logging
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HOME_7K7K = "https://www.7k7k.com"
HOME_4399 = "https://www.4399.com"
HOME_FLASH_HOMES = "https://flash.homes"
TIMEOUT = 30
CHUNK = 64 * 1024
WORKERS = 6
MAX_FILES = 5000

# 会当作资源一并镜像的扩展名
ASSET_EXTS = {
    ".js", ".css", ".json", ".xml", ".txt", ".fnt", ".atlas",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico",
    ".mp3", ".ogg", ".wav", ".m4a", ".aac", ".mp4", ".webm",
    ".ttf", ".woff", ".woff2", ".eot",
}
HTML_EXTS = {".html", ".htm"}
# 需要读取内容、继续扫描引用的文本类型
TEXT_EXTS = {".js", ".css", ".json", ".xml", ".txt", ".svg", ".atlas"} | HTML_EXTS

_EXT_ALT = "|".join(sorted(e[1:] for e in ASSET_EXTS))
ATTR_RE = re.compile(
    r'(?:src|href|data-src|data-original|poster)\s*=\s*["\']([^"\']+)["\']', re.I
)
CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.I)
CSS_IMPORT_RE = re.compile(r"""@import\s+['"]([^'"]+)['"]""", re.I)
JS_REF_RE = re.compile(
    r"""["']([^"'\s]+\.(?:%s)(?:\?[^"'\s]*)?)["']""" % _EXT_ALT, re.I
)
SWF_RE = re.compile(r"""["']([^"'\s]+\.swf(?:\?[^"'\s]*)?)["']""", re.I)
RUFFLE_LOAD_RE = re.compile(r"""player\.load\(\s*["']([^"']+)["']""", re.I)


class DownloadError(Exception):
    """搬运流程中可预期的失败，service 会转成中文 400。"""


@dataclass
class ImportedGame:
    """一次搬运的结果：已下载到本地临时目录的游戏描述。"""

    site: str
    source_id: str
    name: str
    description: str
    kind: str  # flash | h5
    page_url: str
    body_path: Path  # flash: .swf；h5: 入口 index.html
    h5_dir: Path | None  # h5: 镜像根目录（用于打包）
    cover_path: Path | None
    width: int | None = None
    height: int | None = None


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = UA
    return session


def _get(session, url, referer=None, stream=False, retries=2):
    headers = {"Referer": referer} if referer else {}
    last = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=TIMEOUT, stream=stream)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as exc:
            # 4xx（除限流外）重试无意义，直接报错
            status = exc.response.status_code if exc.response is not None else None
            if status and 400 <= status < 500 and status != 429:
                raise DownloadError(f"请求失败: {url} (HTTP {status})") from exc
            last = exc
        except requests.RequestException as exc:
            last = exc
        if attempt < retries:
            time.sleep(0.8 * (attempt + 1))
    raise DownloadError(f"请求失败: {url} ({last})")


def fetch_text(session, url, referer=None, encoding=None) -> str:
    resp = _get(session, url, referer=referer)
    if encoding:
        resp.encoding = encoding
    elif not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return resp.text


def _size_text(num: int) -> str:
    """给报错用的易读大小（不超过一位小数，够说明问题即可）。"""
    if num >= 1024 * 1024:
        return f"{num / (1024 * 1024):.1f} MB"
    if num >= 1024:
        return f"{num / 1024:.1f} KB"
    return f"{num} 字节"


def download_file(session, url, dest, referer=None, *, max_bytes=None) -> tuple[str, int]:
    """流式下载单个文件，先写 .part 再原子替换。返回 (路径, 字节数)。

    max_bytes 给了就设大小上限：响应头声明的长度先卡一道，真下超了也立刻中断
    （不能只信 Content-Length，服务端可以不报或报假的）。
    """
    dest = str(dest)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    resp = None
    try:
        resp = _get(session, url, referer=referer, stream=True)
        declared = (resp.headers.get("Content-Length") or "").strip()
        if max_bytes and declared.isdigit() and int(declared) > max_bytes:
            raise DownloadError(
                f"文件过大（{_size_text(int(declared))}），上限 {_size_text(max_bytes)}"
            )
        written = 0
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(CHUNK):
                if not chunk:
                    continue
                written += len(chunk)
                if max_bytes and written > max_bytes:
                    raise DownloadError(f"文件过大，超过上限 {_size_text(max_bytes)}")
                fh.write(chunk)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    finally:
        if resp is not None:
            resp.close()
    return dest, os.path.getsize(dest)


# --------------------------------------------------------------------------- #
# 资源识别与 H5 镜像
# --------------------------------------------------------------------------- #
def is_ruffle_wrapper(html: str) -> bool:
    """判断页面是否是 Ruffle 播放器包装页（7k7k / 4399 的「H5 版 Flash」）。"""
    return bool(RUFFLE_LOAD_RE.search(html) or "RufflePlayer" in html)


def contains_swf(html: str) -> bool:
    return bool(SWF_RE.search(html))


def extract_swf_url(html: str, base_url: str):
    """从 Ruffle 包装页 / Flash 页面中解析出 .swf 地址（可为相对路径）。"""
    for regex in (RUFFLE_LOAD_RE, SWF_RE):
        match = regex.search(html)
        if match:
            url = match.group(1)
            if url.startswith("//"):
                url = "https:" + url
            return urljoin(base_url, url)
    return None


def _is_skippable(ref: str) -> bool:
    ref = ref.strip()
    if not ref or ref.startswith("#"):
        return True
    return ref.lower().startswith(
        ("data:", "blob:", "javascript:", "mailto:", "tel:", "about:", "chrome:")
    )


def _ref_url(ref: str, base_url: str) -> str:
    if ref.startswith("//"):
        return "https:" + ref
    return urljoin(base_url, ref)


def extract_refs(text: str, ext: str, base_url: str):
    """从 html/css/js 文本中提取待镜像的资源引用（原始字符串）。"""
    refs = []
    if ext in HTML_EXTS:
        refs += ATTR_RE.findall(text)
    if ext == ".css":
        refs += CSS_URL_RE.findall(text)
        refs += CSS_IMPORT_RE.findall(text)
    if ext in HTML_EXTS or ext == ".js":
        refs += JS_REF_RE.findall(text)
    out = []
    for ref in refs:
        if _is_skippable(ref):
            continue
        path = urlsplit(_ref_url(ref, base_url)).path
        if os.path.splitext(path)[1].lower() in ASSET_EXTS | HTML_EXTS:
            out.append(ref)
    return out


def mirror_relpath(url: str, entry_dir: str, base_host: str) -> str:
    """把远程 URL 映射为镜像目录下的相对路径。"""
    parts = urlsplit(url)
    rel = unquote(parts.path).lstrip("/")
    if parts.netloc == base_host:
        base_path = unquote(urlsplit(entry_dir).path).lstrip("/")
        if rel.startswith(base_path):
            rel = rel[len(base_path):]
    else:
        rel = f"_external/{parts.netloc}/{rel}"
    if not rel or rel.endswith("/"):
        rel += "index.html"
    return rel


def download_h5_bundle(session, entry_url, out_dir, referer) -> str:
    """镜像 HTML5 游戏：入口页 + 递归发现的 JS/CSS/图片/音频。返回入口文件路径。"""
    entry_dir = urljoin(entry_url, ".")
    base_host = urlsplit(entry_url).netloc
    entry_rel = mirror_relpath(entry_url, entry_dir, base_host)
    entry_dest = os.path.join(out_dir, entry_rel)

    seen, mirrored, external = set(), set(), {}
    queue = [entry_url]
    count = 0

    while queue:
        batch = [u for u in dict.fromkeys(queue) if u not in seen]
        queue = []
        if not batch:
            break
        seen.update(batch)
        results = {}

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {}
            for url in batch:
                if count >= MAX_FILES:
                    logger.warning("H5 镜像超过 %s 个文件，停止继续抓取: %s", MAX_FILES, entry_url)
                    break
                rel = mirror_relpath(url, entry_dir, base_host)
                if rel in mirrored:  # 同一文件的不同带参 URL，只下一次
                    continue
                mirrored.add(rel)
                dest = os.path.join(out_dir, rel)
                count += 1
                if urlsplit(url).netloc != base_host:
                    external[url] = dest
                futures[pool.submit(download_file, session, url, dest, referer)] = url
            for future in as_completed(futures):
                url = futures[future]
                try:
                    dest, _size = future.result()
                except DownloadError as exc:
                    logger.warning("跳过 H5 资源 %s: %s", url, exc)
                    continue
                results[url] = dest

        # 扫描文本文件，继续发现引用
        for url, dest in results.items():
            ext = os.path.splitext(dest)[1].lower()
            if ext not in TEXT_EXTS or os.path.getsize(dest) > 20 * 1024 * 1024:
                continue
            try:
                text = open(dest, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for ref in extract_refs(text, ext, url):
                abs_url = _ref_url(ref, url)
                if abs_url in seen:
                    continue
                if os.path.splitext(urlsplit(abs_url).path)[1].lower() in HTML_EXTS \
                        and urlsplit(abs_url).netloc != base_host:
                    continue  # 不跟着外链网页乱爬
                queue.append(abs_url)

    if external:
        _rewrite_external(out_dir, external)
    return entry_dest


def _rewrite_external(out_dir, external):
    """把文本文件里指向外部站点的绝对地址改写成本地镜像相对路径。"""
    mapping = {}
    for orig, dest in external.items():
        local = os.path.relpath(dest, out_dir).replace(os.sep, "/")
        variants = {orig}
        if orig.startswith("//"):
            variants |= {"https:" + orig, "http:" + orig}
        mapping.update({v: local for v in variants})

    for root, _dirs, files in os.walk(out_dir):
        for name in files:
            path = os.path.join(root, name)
            if os.path.splitext(name)[1].lower() not in TEXT_EXTS:
                continue
            try:
                data = open(path, "rb").read()
            except OSError:
                continue
            original = data
            for remote, local in mapping.items():
                if remote.encode() in data:
                    rel = os.path.relpath(
                        os.path.join(out_dir, local), root
                    ).replace(os.sep, "/")
                    data = data.replace(remote.encode(), rel.encode())
            if data != original:
                open(path, "wb").write(data)


# --------------------------------------------------------------------------- #
# 站点：7k7k
# --------------------------------------------------------------------------- #
def _extract_js_object(html: str, varname: str):
    """从 JS 源码里按大括号配对取出 `var varname = {...}` 的对象字面量。"""
    idx = html.find(varname)
    if idx < 0:
        return None
    start = html.find("{", idx)
    if start < 0:
        return None
    depth, quote, escaped = 0, None, False
    for pos in range(start, len(html)):
        ch = html[pos]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[start:pos + 1]
    return None


def _js_field(block: str, key: str):
    match = re.search(
        key + r'\s*:\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null)', block
    )
    if not match:
        return None
    raw = match.group(1)
    if raw.startswith('"'):
        return json.loads(raw)
    if raw in ("true", "false"):
        return raw == "true"
    if raw == "null":
        return None
    return float(raw) if "." in raw else int(raw)


def _parse_7k_game_info(html: str) -> dict:
    block = _extract_js_object(html, "var gameInfo")
    if not block:
        raise DownloadError("页面中未找到 gameInfo，可能不是可下载的游戏页")
    keys = (
        "gameType", "gameId", "gameName", "gamePath", "gamePic", "gameBpic",
        "gameDesc", "isOutlink", "outLink", "gamewidth", "gameheight",
    )
    return {key: _js_field(block, key) for key in keys}


def load_7k7k(session, target, game_id):
    play_url = f"{HOME_7K7K}/swf/{game_id}.htm"
    info, last_error, page_used = None, None, play_url
    for page_url in (play_url, f"{HOME_7K7K}/flash/{game_id}.htm"):
        try:
            info = _parse_7k_game_info(fetch_text(session, page_url))
            page_used = page_url
            break
        except DownloadError as exc:
            last_error = exc
    if info is None:
        if last_error and "404" in str(last_error):
            raise DownloadError(f"游戏 {game_id} 不存在或已下架")
        raise last_error or DownloadError("无法获取游戏信息")
    return {
        "id": str(info.get("gameId") or game_id),
        "name": info.get("gameName") or game_id,
        "page": page_used,
        "cover": info.get("gameBpic") or info.get("gamePic"),
        "desc": info.get("gameDesc"),
        "width": info.get("gamewidth"),
        "height": info.get("gameheight"),
        "game_path": info.get("gamePath"),
        "_info": info,
    }


def resolve_7k7k(session, loaded):
    info, page_url = loaded["_info"], loaded["page"]
    game_path = info.get("gamePath")
    out_link = info.get("outLink")
    if info.get("isOutlink") in (1, "1") or (not game_path and out_link):
        raise DownloadError(f"外链游戏，无法下载: {out_link or '(未提供地址)'}")
    if not game_path:
        raise DownloadError("gameInfo 中没有 gamePath，无法定位游戏资源")
    if game_path.startswith("//"):
        game_path = "https:" + game_path
    elif game_path.startswith("/"):
        game_path = HOME_7K7K + game_path
    elif not urlsplit(game_path).netloc:
        game_path = urljoin(page_url, game_path)

    if game_path.lower().split("?")[0].endswith(".swf"):
        return "flash", game_path

    html = fetch_text(session, game_path, referer=page_url)
    if is_ruffle_wrapper(html) or contains_swf(html):
        swf = extract_swf_url(html, game_path)
        if swf:
            return "flash", swf

    ext = os.path.splitext(urlsplit(game_path).path)[1].lower()
    if ext in HTML_EXTS:
        return "h5", game_path
    raise DownloadError(f"无法识别的 gamePath 类型: {game_path}")


# --------------------------------------------------------------------------- #
# 站点：4399
# --------------------------------------------------------------------------- #
FLASH_BASE_4399 = "https://s1.4399.com/4399swf"          # Flash 资源服务器
H5_BASE_4399_FALLBACK = "https://sda.4399.com/4399swf"   # H5 入口服务器
SERVERSDA_JS = "https://www.4399.com/js/serversda.js"

# 依赖 4399 在线运行时的 H5：资源由服务端动态下发，抓静态文件没有意义
ONLINE_RUNTIME_HINTS = (
    "h5mini", "h5wan.4399sj.com", "h.api.4399.com", "yc_handle.js", "页游控制层",
)


def _parse_4399_page(html: str) -> dict:
    def field(key):
        match = re.search(key + r"\s*=\s*[\"']([^\"']*)[\"']", html)
        return match.group(1) if match else None

    return {
        "path": field("_strGamePath"),
        "title": field("game_title"),
        "pic": field("_strGamePic"),
    }


def _find_4399_swf_path(html: str):
    """兼容旧页面的三种 Flash 地址提取方式。"""
    for pattern in (
        r'var\s+_strGamePath\s*=\s*"([^"]+\.swf)"',
        r'<embed[^>]+src\s*=\s*"([^"]+\.swf)"',
        r'<param\s+name="movie"\s+value\s*=\s*"([^"]+\.swf)"',
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def _get_4399_h5_base(session) -> str:
    """从 serversda.js 读取站点声明的资源服务器，失败则用默认值。"""
    try:
        js = fetch_text(session, SERVERSDA_JS, encoding="utf-8")
        match = re.search(r'webServer\s*=\s*"([^"]+)"', js)
        if match:
            base = match.group(1)
            if base.startswith("//"):
                base = "https:" + base
            return base.rstrip("/")
    except DownloadError:
        pass
    return H5_BASE_4399_FALLBACK


def _build_4399_flash_url(path: str) -> str:
    if path.startswith("//"):
        return "https:" + path
    if path.startswith("http"):
        return path
    return FLASH_BASE_4399 + path


def load_4399(session, target, game_id):
    page_url = target if target.startswith("http") else f"{HOME_4399}/flash/{game_id}.htm"
    html = fetch_text(session, page_url, encoding="gb2312")
    info = _parse_4399_page(html)
    path = info.get("path") or _find_4399_swf_path(html)
    if not path:
        raise DownloadError("页面中未找到 _strGamePath，可能不是可下载的游戏页")
    return {
        "id": game_id,
        "name": info.get("title") or game_id,
        "page": page_url,
        "cover": info.get("pic"),
        "desc": None,
        "width": None,
        "height": None,
        "game_path": path,
    }


def resolve_4399(session, loaded):
    page_url, path = loaded["page"], loaded["game_path"]
    low = path.lower().split("?")[0]
    if low.endswith(".swf"):
        return "flash", _build_4399_flash_url(path)
    if not (low.endswith(".html") or low.endswith(".htm")):
        raise DownloadError(f"无法识别的游戏资源类型: {path}")

    if path.startswith("//"):
        entry = "https:" + path
    elif path.startswith("http"):
        entry = path
    else:
        entry = _get_4399_h5_base(session) + "/" + path.lstrip("/")

    html = fetch_text(session, entry, referer=page_url)

    # 被 Ruffle 包装的「H5 版 Flash」：继续解析底层 swf
    if is_ruffle_wrapper(html) or contains_swf(html):
        swf = extract_swf_url(html, entry)
        if swf:
            return "flash", swf

    if any(hint in html for hint in ONLINE_RUNTIME_HINTS):
        raise DownloadError(
            "该 H5 游戏依赖 4399 在线运行时（资源由服务端动态下发），无法离线下载"
        )
    return "h5", entry


# --------------------------------------------------------------------------- #
# 站点：flash.homes（Flash 保存计划）
#
# 存档站的作品一律是「按 sha256 命名、放在 CDN 上」的单个 SWF；游戏页用 Astro
# 渲染，播放器组件把自己的入参（含 sha256、标题、封面文件名）原样挂在
# <astro-island ... component-url=".../PlayerStage..."> 的 props 属性里，
# 页面另有 JSON-LD 兜底（标题缺失的藏品只有 JSON-LD 里那份名称）。
# --------------------------------------------------------------------------- #
SWF_CDN_FLASH_HOMES = "https://swf.flash.homes"
SHOT_CDN_FLASH_HOMES = "https://screenshots.flash.homes"
SHA256_RE = re.compile(r"[0-9a-f]{64}", re.I)
# 形如 F8YX-1DNE-JQG9 的三段短码
FLASH_HOMES_SLUG_RE = re.compile(r"/flash/([0-9A-Za-z-]+)", re.I)
ISLAND_RE = re.compile(r"<astro-island\b[^>]*>", re.I)
PROPS_ATTR_RE = re.compile(r'\sprops="([^"]*)"')
LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
META_DESC_RE = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
# 站点为每件藏品自动生成的介绍尾巴，去掉后剩下的才是有效描述
FLASH_HOMES_DESC_TAIL = "——已归档的 Flash 作品，浏览器直接播放。"


def _unwrap_prop(value):
    """还原 Astro 序列化：标量/对象包成 [0, 值]，数组包成 [1, [...]]，可嵌套。"""
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], int):
        code, payload = value
        if code == 0:
            return _unwrap_prop(payload)
        if code == 1:
            return [_unwrap_prop(item) for item in payload]
        return payload
    if isinstance(value, dict):
        return {key: _unwrap_prop(item) for key, item in value.items()}
    return value


def _astro_props(page: str) -> dict:
    """取 PlayerStage 岛传给组件的 props。"""
    for tag in ISLAND_RE.findall(page):
        if "PlayerStage" not in tag:
            continue
        match = PROPS_ATTR_RE.search(tag)
        if not match:
            break
        try:
            raw = json.loads(html_module.unescape(match.group(1)))
        except json.JSONDecodeError as exc:
            raise DownloadError("页面播放器信息无法解析") from exc
        if not isinstance(raw, dict):
            break
        return {key: _unwrap_prop(value) for key, value in raw.items()}
    raise DownloadError("页面中未找到播放器信息，可能不是可下载的游戏页")


def _flash_homes_ld(page: str) -> dict:
    """取页面里第一个带名称的 JSON-LD 对象（CreativeWork），用于兜底标题与封面。"""
    for match in LD_JSON_RE.finditer(page):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("name"):
            return data
    return {}


def _flash_homes_cover(props: dict, ld: dict):
    """封面地址：播放器给的是文件名，JSON-LD 里则是完整地址。"""
    shot = props.get("screenshot")
    if isinstance(shot, str) and shot:
        return f"{SHOT_CDN_FLASH_HOMES}/{shot}"
    images = ld.get("image")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict) and image.get("url"):
                return str(image["url"])
    return None


def _flash_homes_desc(page: str, name: str, slug: str) -> str:
    match = META_DESC_RE.search(page)
    if not match:
        return ""
    text = html_module.unescape(match.group(1))
    if text.endswith(FLASH_HOMES_DESC_TAIL):
        text = text[: -len(FLASH_HOMES_DESC_TAIL)]
    text = text.strip()
    # 只剩游戏名/短码的「描述」没有信息量
    return "" if not text or text in (name, slug) else text


def load_flash_homes(session, target, game_id):
    page_url = f"{HOME_FLASH_HOMES}/flash/{game_id}"
    try:
        page = fetch_text(session, page_url, encoding="utf-8")
    except DownloadError as exc:
        if "404" in str(exc):
            raise DownloadError(f"游戏 {game_id} 不存在或已下架") from exc
        raise
    props = _astro_props(page)
    sha256 = props.get("sha256")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise DownloadError("页面中未找到游戏文件校验值，无法定位 SWF")
    ld = _flash_homes_ld(page)
    name = str(props.get("title") or ld.get("name") or game_id)
    ratio = props.get("stageRatio")
    ratio = ratio if isinstance(ratio, dict) else {}
    return {
        "id": game_id,
        "name": name,
        "page": page_url,
        "cover": _flash_homes_cover(props, ld),
        "desc": _flash_homes_desc(page, name, game_id),
        "width": ratio.get("width"),
        "height": ratio.get("height"),
        "swf": f"{SWF_CDN_FLASH_HOMES}/{sha256.lower()}.swf",
    }


def resolve_flash_homes(session, loaded):
    return "flash", loaded["swf"]


# --------------------------------------------------------------------------- #
# 站点识别
# --------------------------------------------------------------------------- #
def detect_site(target: str, override: str | None = None):
    if override:
        return override
    host = urlsplit(target).netloc.lower()
    if host == "7k7k.com" or host.endswith(".7k7k.com"):
        return "7k7k"
    if host == "4399.com" or host.endswith(".4399.com"):
        return "4399"
    if host == "flash.homes" or host.endswith(".flash.homes"):
        return "flash.homes"
    return None


def _flash_homes_slug(target: str) -> str:
    """flash.homes 的作品 id 是 12 位短码，页面上写作 4-4-4 的 slug。"""
    match = FLASH_HOMES_SLUG_RE.search(target)
    if match:
        slug = re.sub(r"[^0-9A-Za-z]", "", match.group(1)).upper()
        if len(slug) == 12:
            return f"{slug[:4]}-{slug[4:8]}-{slug[8:]}"
    raise DownloadError(f"无法从地址中解析出游戏 ID: {target}")


def game_id_from_arg(target: str, site: str) -> str:
    target = target.strip()
    if site == "flash.homes":
        return _flash_homes_slug(target)
    if target.isdigit():
        return target
    if site == "7k7k":
        if "h5.7k7k.com" in target and "/mb/mb2/" in target:
            raise DownloadError(
                "暂不支持 h5.7k7k.com 的第三方联运 H5 页面，请改用 "
                "https://www.7k7k.com/flash/<id>.htm 形式的游戏页"
            )
        match = re.search(r"/(?:flash|swf)/(\d+)\.htm", target)
    else:
        match = re.search(r"/flash/(\d+)(?:_\d+)?\.htm", target)
    if match:
        return match.group(1)
    match = re.search(r"(\d{4,})", target)
    if match:
        return match.group(1)
    raise DownloadError(f"无法从地址中解析出游戏 ID: {target}")


SITE_HANDLERS = {
    "7k7k": (load_7k7k, resolve_7k7k),
    "4399": (load_4399, resolve_4399),
    "flash.homes": (load_flash_homes, resolve_flash_homes),
}


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def _download_cover(session, cover_url, cover_dir: Path, referer) -> Path | None:
    if not cover_url:
        return None
    if cover_url.startswith("//"):
        cover_url = "https:" + cover_url
    ext = os.path.splitext(urlsplit(cover_url).path)[1].lower() or ".jpg"
    dest = cover_dir / ("cover" + ext)
    try:
        path, _size = download_file(session, cover_url, dest, referer)
    except DownloadError as exc:
        logger.warning("封面下载失败: %s", exc)
        return None
    return Path(path)


def build_h5_zip(source_dir: Path, dest_zip: Path) -> Path:
    """把镜像目录打包成播放用 zip：入口须为根目录 index.html。"""
    source_dir = Path(source_dir)
    if not (source_dir / "index.html").is_file():
        raise DownloadError("H5 镜像缺少入口 index.html，无法打包")
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())
    return Path(dest_zip)


def download_game(
    target: str, work_dir, session: requests.Session | None = None
) -> ImportedGame:
    """解析并下载一个 7k7k / 4399 / flash.homes 游戏到 work_dir，返回描述对象。"""
    target = (target or "").strip()
    if not target.lower().startswith(("http://", "https://")):
        raise DownloadError("请填写完整的游戏页地址（http/https）。")
    site = detect_site(target)
    if site is None:
        raise DownloadError("仅支持 7k7k、4399、flash.homes 的游戏页地址。")

    work_dir = Path(work_dir)
    body_dir = work_dir / "body"
    cover_dir = work_dir / "cover"
    body_dir.mkdir(parents=True, exist_ok=True)
    cover_dir.mkdir(parents=True, exist_ok=True)

    session = session or make_session()
    game_id = game_id_from_arg(target, site)
    loader, resolver = SITE_HANDLERS[site]
    loaded = loader(session, target, game_id)
    kind, url = resolver(session, loaded)
    cover_path = _download_cover(session, loaded.get("cover"), cover_dir, loaded["page"])

    common = dict(
        site=site,
        source_id=str(loaded["id"]),
        name=str(loaded["name"] or game_id),
        description=str(loaded.get("desc") or ""),
        page_url=loaded["page"],
        cover_path=cover_path,
        width=loaded.get("width"),
        height=loaded.get("height"),
    )

    if kind == "flash":
        dest = body_dir / "game.swf"
        download_file(session, url, dest, loaded["page"])
        return ImportedGame(kind="flash", body_path=dest, h5_dir=None, **common)

    entry = Path(download_h5_bundle(session, url, str(body_dir), loaded["page"]))
    index = body_dir / "index.html"
    if entry != index:
        if index.exists():
            raise DownloadError("镜像目录已存在 index.html，无法确定 H5 入口")
        entry.rename(index)
    return ImportedGame(kind="h5", body_path=index, h5_dir=body_dir, **common)
