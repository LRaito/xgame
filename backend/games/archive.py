"""压缩包（H5 游戏资源包、攻略包）的校验与解包原语。

H5 与 ZIP 形态的攻略的交付格式是同一套东西——一个根目录含 `index.html` 的 zip，所以规则、
上限与中文报错措辞都在这里集中一份，只按 `kind`（`H5` / `GUIDE`）取入口名与措辞。两个包都
**只上传 zip**：上传时 `read_manifest()` 只读中央目录做全量校验、一个字节都不解；
真正的解压发生在运行时（`backend/games/runtime_assets.py`）。攻略另有 PDF 形态，
原样存数据根、不解包，不经过本模块。

这是 `backend/games/` 里最底层的一个模块——`service.py` 与 `runtime_assets.py` 都依赖它，
它自己不依赖包内任何东西。共用的 Windows 文件名规则（游戏名校验与包内路径校验都按它）
因此也放在这里，由 `service.validate_game_name` 反向 import。
"""

from __future__ import annotations

import os
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

from backend.errors import ValidationError

# 两个包的种类键。取值刻意与 `paths.py` 的目录名一致（`h5` / `guide`）。
H5 = "h5"
GUIDE = "guide"

# 两个包的入口都固定为根目录 index.html（大小写不敏感识别，落盘统一小写）。
ENTRY_NAME = "index.html"
_ENTRY_NAMES: dict[str, frozenset[str]] = {
    # H5 收 index.htm：它的清单/入口地址由代码拼，收下改名不影响任何已有引用
    H5: frozenset({"index.html", "index.htm"}),
    # 攻略只认 index.html：两个包规则一致、少一个特例
    GUIDE: frozenset({ENTRY_NAME}),
}
# 中文报错里的主语与位置（「游戏资源」/「攻略」、…内）
LABELS: dict[str, str] = {H5: "游戏资源", GUIDE: "攻略"}
WHERE: dict[str, str] = {H5: "压缩包内", GUIDE: "攻略包内"}

# 解包上限。zip 本体上限与 nginx 的 client_max_body_size（128m）对齐；其余是防压缩炸弹：
# 单条、总量、条目数与压缩比（只在解压后体积够大时才看比例，避免小文件误伤）。
MAX_ZIP_SIZE = 128 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_ENTRY_SIZE = 64 * 1024 * 1024
MAX_TOTAL_SIZE = 256 * 1024 * 1024
MAX_RATIO = 200
RATIO_MIN_SIZE = 1024 * 1024

# 包内相对路径的上限（与「数据根/运行时根的绝对路径长度」是两回事，后者见 ensure_path_fits）
ASSET_MAX_PATH_LENGTH = 512
ASSET_MAX_PATH_SEGMENTS = 32

# 当前平台是不是 Windows。写成模块级变量而不是到处 os.name，是为了让测试能翻它——
# 「解压即用」的 Windows 包跑在 Windows 上，而测试跑在 Linux 上，不翻就永远测不到那条分支。
IS_WINDOWS = os.name == "nt"

# Windows 的完整路径上限是 260（MAX_PATH）。这里留出余量：写盘时同目录会先落一个
# `.{文件名}.tmp-{8位随机}` 的临时文件（比最终名字长），解包还有 `.h5-{12位}` 暂存目录。
WINDOWS_PATH_BUDGET = 240

# 游戏名要同时能当 Windows 文件名与百度网盘文件名（本体/封面下载下来就是「游戏名.后缀」，
# 也会被整包传到网盘），所以按两边的限制取交集校验：非法字符 \ / : * ? " < > |（全角版，
# 如 ：与 ／，不受影响）、控制字符、结尾的点、保留设备名、长度上限。
NAME_ILLEGAL_CHARS = frozenset('\\/:*?"<>|')
# Windows 保留设备名（大小写不敏感，带扩展名同样保留，如 NUL.nes 也是设备名）
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"COM{i}" for i in range(10)}
    | {f"LPT{i}" for i in range(10)}
)
# 包内路径用的非法字符集：与游戏名同一套，但去掉两个路径分隔符——
# `\` 由路径校验单独拒掉，`/` 是分隔符本身、每段都有。
_ASSET_ILLEGAL_CHARS = NAME_ILLEGAL_CHARS - {"/", "\\"}

# 解包后资源的 MIME 由该显式表决定，不依赖运行环境的 /etc/mime.types，保证可复现。
ASSET_MIME_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".wasm": "application/wasm",
    ".xml": "application/xml",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".txt": "text/plain; charset=utf-8",
}
ASSET_DEFAULT_MIME = "application/octet-stream"

# 包内常见的系统垃圾条目（macOS 元数据、.DS_Store），解包时直接跳过
SKIP_NAMES = frozenset({"__MACOSX", ".DS_Store"})


@dataclass(frozen=True)
class ArchiveEntry:
    """压缩包里的一条待解包文件；`path` 是归一化后的包内相对路径。"""

    path: str
    info: zipfile.ZipInfo


def guess_asset_mime(path: str) -> str:
    """按后缀返回静态资源 MIME；未知后缀一律 octet-stream。"""
    return ASSET_MIME_TYPES.get(PurePosixPath(path).suffix.lower(), ASSET_DEFAULT_MIME)


def normalize_h5_path(raw: str) -> str:
    """归一化压缩包内相对路径；任何歧义/越界/非法字符都拒绝。"""
    return _normalize_asset_path(raw, where=WHERE[H5])


def normalize_guide_path(raw: str) -> str:
    """归一化攻略包内相对路径；规则与 H5 包内路径完全一致。"""
    return _normalize_asset_path(raw, where=WHERE[GUIDE])


def _normalize_asset_path(raw: str, *, where: str) -> str:
    """H5 包内路径与攻略包内路径共用的归一化：任何歧义/越界/非法字符都拒绝。"""
    if not raw or not raw.strip():
        raise ValidationError(f"{where}含空路径。")
    text = unicodedata.normalize("NFC", raw).strip()
    if "\\" in text:
        raise ValidationError(f"{where}含非法路径（反斜杠）。")
    if any(ord(ch) < 32 for ch in text):
        raise ValidationError(f"{where}含非法路径（控制字符）。")
    if any(ch in text for ch in "?#%"):
        raise ValidationError(f"{where}含非法路径（? # %）。")
    # 与游戏名同一套 Windows 规则：ZIP 里这些字符完全合法，解到 NTFS 上却会直接抛异常
    # （`a:b.png` 会被当成数据流、`x?.png` 干脆建不出来），解包到一半失败最难排查。
    # 刻意不分平台：在 Linux 上也一并拒掉，同一个包在哪都能用。
    # 去掉两个路径分隔符：`\` 上面已经单独拒过，`/` 是包内路径的分隔符本身。
    illegal = sorted({ch for ch in text if ch in _ASSET_ILLEGAL_CHARS})
    if illegal:
        raise ValidationError(f"{where}含非法路径（{' '.join(illegal)}）。")
    posix = PurePosixPath(text)
    if posix.is_absolute():
        raise ValidationError(f"{where}含绝对路径。")
    parts = posix.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValidationError(f"{where}含非法路径（. 或 ..）。")
    normalized = "/".join(parts)
    if normalized != text:
        raise ValidationError(f"{where}含非法路径。")
    if len(normalized) > ASSET_MAX_PATH_LENGTH or len(parts) > ASSET_MAX_PATH_SEGMENTS:
        raise ValidationError(f"{where}含过长路径。")
    for part in parts:
        # Windows 会静默丢掉结尾的点和空格，留着会让「库里的名字」与「磁盘上的名字」对不上
        if part.endswith(".") or part.endswith(" "):
            raise ValidationError(f"{where}含非法路径（名字以点或空格结尾）。")
        if part.split(".", 1)[0].strip().upper() in WINDOWS_RESERVED_NAMES:
            raise ValidationError(f"{where}含 Windows 保留设备名。")
    return normalized


def ensure_path_fits(
    root: str | None, relative: str, *, where: str, hint: str = "或减少包内的目录层级"
) -> None:
    """在 Windows 上卡一下「根 + 相对路径」的总长度。

    `ASSET_MAX_PATH_LENGTH`（512）是**相对**上限，保证不了叠加根前缀之后仍在 260 以内。
    超限的后果不是一条干净的报错，而是解包写到一半失败、或者后面某次读文件莫名「找不到」，
    所以在收下之前按实际的根长度算一遍。其它平台没有这个上限，直接放行。

    包内路径的深度只出现在**运行时根**下（解包产物都在那里），所以调用方传的应当是
    运行时根；数据根只需算 zip 本体，天然更宽松。
    """
    if not IS_WINDOWS or not root:
        return
    if len(os.path.join(root, relative)) > WINDOWS_PATH_BUDGET:
        raise ValidationError(
            f"{where}存在过长的路径：Windows 下完整路径不能超过 {WINDOWS_PATH_BUDGET} 个字符，"
            f"请把数据目录放到更浅的位置（如 D:\\xgame），{hint}。"
        )


def zip_entry_name(info: zipfile.ZipInfo) -> str:
    """ZIP 条目名，尽量还原成原本的样子。

    `zipfile` 只在条目带了 UTF-8 标志位（`0x800`）时才按 UTF-8 解码，否则一律按 cp437。
    用资源管理器或老压缩工具打出来的中文包多半是 GBK 且不带那个标志位，于是解出来是一串乱码
    ——不报错，但文件名全错。这里按 cp437 把原始字节还原回来再试常见编码。
    """
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    for codec in ("gbk", "utf-8"):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return name


def _skip_entry(name: str) -> bool:
    """跳过资源里常见的系统垃圾条目（macOS 元数据、.DS_Store）。"""
    parts = PurePosixPath(name).parts
    return any(part in SKIP_NAMES for part in parts)


def _has_entry(entries: list[tuple[str, zipfile.ZipInfo]], kind: str) -> bool:
    names = _ENTRY_NAMES[kind]
    return any(path.lower() in names for path, _ in entries)


def _strip_single_wrapper(
    entries: list[tuple[str, zipfile.ZipInfo]], kind: str
) -> list[tuple[str, zipfile.ZipInfo]]:
    """压缩包把整个站点/游戏套在一层目录里时剥掉该前缀。

    仅当根目录没有入口、且全部条目共享唯一顶层目录、剥掉后根目录出现入口时才剥离；
    否则原样返回（避免误剥与入口同级的 assets/ 之类目录）。资源管理器与 macOS 的
    「压缩」都会套一层，不剥的话用户每次都得手动解压重打。
    """
    if _has_entry(entries, kind):
        return entries
    tops = {path.split("/", 1)[0] for path, _ in entries}
    if len(tops) != 1:
        return entries
    top = tops.pop()
    if not all(path.startswith(f"{top}/") for path, _ in entries):
        return entries
    stripped = [(path[len(top) + 1 :], info) for path, info in entries]
    return stripped if _has_entry(stripped, kind) else entries


def read_manifest(stream, *, kind: str) -> list[ArchiveEntry]:
    """只校验压缩包清单（不解压数据），返回归一化后的条目列表。

    上传与解压两处共用：上传时挡掉不合规的包，解压时再挡一次（数据根是用户可写的
    普通目录，宿主手改、网盘同步都可能换掉那个 zip，解压路径不能只信上传那一刻）。
    """
    label = LABELS[kind]
    where = WHERE[kind]
    try:
        stream.seek(0)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"无法读取上传的{label}压缩包。") from exc
    try:
        archive = zipfile.ZipFile(SeekableStream(stream))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise ValidationError("压缩包无法解析，请上传有效的 ZIP 文件。") from exc
    entries: list[tuple[str, zipfile.ZipInfo]] = []
    total = 0
    with archive:
        for info in archive.infolist():
            name = zip_entry_name(info)
            if info.is_dir() or _skip_entry(name):
                continue
            if info.flag_bits & 0x1:
                raise ValidationError("压缩包包含加密文件，无法解包。")
            normalized = _normalize_asset_path(name, where=where)
            size = int(info.file_size)
            if size > MAX_ENTRY_SIZE:
                raise ValidationError(f"{label}包内单个文件过大。")
            compressed = int(info.compress_size)
            if (
                size > RATIO_MIN_SIZE
                and compressed > 0
                and size // compressed > MAX_RATIO
            ):
                raise ValidationError("压缩包解压比例异常，已拒绝。")
            entries.append((normalized, info))
            total += size
            if len(entries) > MAX_ENTRIES:
                raise ValidationError(f"{label}包内文件数量过多。")
            if total > MAX_TOTAL_SIZE:
                raise ValidationError(f"{label}包解压后体积过大。")
    if not entries:
        raise ValidationError("压缩包为空。")
    entries = _strip_single_wrapper(entries, kind)
    seen: set[str] = set()
    result: list[ArchiveEntry] = []
    has_entry = False
    for path, info in entries:
        if path.lower() in _ENTRY_NAMES[kind]:
            # 大小写不敏感识别入口，落盘统一成小写，入口地址才固定
            path = ENTRY_NAME
            has_entry = True
        marker = path.lower()
        if marker in seen:
            raise ValidationError("压缩包内含重名文件。")
        seen.add(marker)
        result.append(ArchiveEntry(path=path, info=info))
    if not has_entry:
        raise ValidationError("压缩包根目录需包含 index.html。")
    return result


def read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[BinaryIO, int]:
    """把单条条目解压到 spooled 临时文件（超阈值落盘），顺带触发 CRC 校验并得到真实字节数。"""
    spool: BinaryIO = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with archive.open(info) as source:
            while True:
                block = source.read(256 * 1024)
                if not block:
                    break
                spool.write(block)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        spool.close()
        raise ValidationError("压缩包内文件损坏，无法解包。") from exc
    actual = spool.tell()
    spool.seek(0)
    return spool, actual


class SeekableStream:
    """zipfile 需要底层流具备 seekable()/readable()；spooled 文件与存储流未必显式实现。"""

    def __init__(self, raw) -> None:
        self._raw = raw

    def read(self, size: int = -1) -> bytes:
        return self._raw.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._raw.seek(offset, whence)

    def tell(self) -> int:
        return self._raw.tell()

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False
