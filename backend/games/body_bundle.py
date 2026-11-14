"""多文件本体（cue+bin / m3u / 多盘）的校验、入口选择与清单生成。

单文件本体仍是一个 `game.{ext}`；这个模块只服务「一个游戏目录下放多个文件」的机种
（世嘉 CD、Amiga）。它不碰磁盘，只接收已经暂存好的文件与一个 `read_text` 回调，
返回最终布局；真正的搬文件、写清单与数据库提交在 `service.py`。

另外提供 `normalize_romset_name()`：街机 romset 必须保留集合名，这里统一做安全校验。

几条硬规则：

- `.bin` 永远不能当入口；入口只能是 m3u / cue / chd / adf / hdf。
- 入口在落盘时统一改名 `game.{ext}`，因为 EmulatorJS 把 `gameUrl` 末段当 MEMFS 文件名
  且不做 URL 解码，带空格/中文的原名会和 cue 内引用对不上。
- 多个 cue / chd / adf / hdf 且没有 m3u 时，按文件名自然排序生成 `game.m3u`。
- cue 的 `FILE` 与 m3u 的每行只能引用同一组里的 basename；不允许子目录、绝对路径、
  远程 URL 或大小写不一致。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from backend.errors import ValidationError
from backend.games import archive
from backend.games.platforms import Platform, normalize_extension

# 多文件本体的文件数上限（含自动生成的 m3u）。总大小不设上限，只受磁盘限制。
MAX_BUNDLE_FILES = 64
# 文件名留出足够余量：Windows 下还要叠加数据根与 game/{类型}/{卡带ID}/body/。
MAX_BUNDLE_NAME_LENGTH = 120
# cue / m3u 都是纯文本小文件；超过这个大小一定不是正常清单。
MAX_MANIFEST_TEXT_BYTES = 1024 * 1024

_CUE_FILE_RE = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+\S+', re.IGNORECASE)
_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
# 街机 romset 的落盘名会原样出现在播放 URL 末段，FBNeo 再拿它当集合名；
# 因此比普通文件名收得更紧：只允许 ASCII 字母数字点下划线中划线，且必须以 .zip 结尾。
_ROMSET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
_ROMSET_RESERVED_NAMES = frozenset({"guide.zip"})


@dataclass(frozen=True)
class StagedBundleFile:
    """一个已经上传完的多文件本体成员。"""

    name: str
    size: int
    upload_id: str

    @property
    def extension(self) -> str:
        return normalize_extension(PurePosixPath(self.name).suffix)


@dataclass(frozen=True)
class BodyBundle:
    """校验通过后的一份多文件本体计划。"""

    platform_id: str
    files: tuple[StagedBundleFile, ...]  # 用户上传的全部文件，按名称排序
    entry_source: StagedBundleFile | None  # None = 自动生成的 m3u
    entry_extension: str
    generated_m3u: bytes | None
    total_size: int

    @property
    def entry_name(self) -> str:
        """入口落盘名；EmulatorJS 只认这个安全名字。"""
        return f"game{self.entry_extension}"

    def final_name(self, file: StagedBundleFile) -> str:
        """成员在 body/ 下的最终文件名：入口改名，其余保留原名。"""
        if self.entry_source is not None and file.upload_id == self.entry_source.upload_id:
            return self.entry_name
        return file.name

    def final_files(self) -> tuple[tuple[str, int, StagedBundleFile | None], ...]:
        """(落盘名, 字节数, 来源文件) 列表；自动 m3u 的来源为 None。"""
        items: list[tuple[str, int, StagedBundleFile | None]] = [
            (self.final_name(file), file.size, file) for file in self.files
        ]
        if self.generated_m3u is not None:
            items.append(
                ("game.m3u", len(self.generated_m3u), None)
            )
        return tuple(items)


def normalize_bundle_name(raw: str) -> str:
    """多文件本体的单个文件名：必须是安全 basename，且不能占用清单名。"""
    text = unicodedata.normalize("NFC", str(raw or "")).strip()
    if not text:
        raise ValidationError("文件名不能为空。")
    if len(text) > MAX_BUNDLE_NAME_LENGTH:
        raise ValidationError(f"文件名过长（最多 {MAX_BUNDLE_NAME_LENGTH} 个字符）。")
    if "/" in text or "\\" in text:
        raise ValidationError("文件名不能包含路径分隔符。")
    if any(ord(ch) < 32 for ch in text):
        raise ValidationError("文件名不能包含控制字符。")
    if any(ch in text for ch in "?#%"):
        raise ValidationError("文件名不能包含 ? # %。")
    illegal = sorted({ch for ch in text if ch in archive.NAME_ILLEGAL_CHARS})
    if illegal:
        raise ValidationError(f"文件名包含非法字符：{' '.join(illegal)}。")
    if text in (".", ".."):
        raise ValidationError("文件名不合法。")
    if text.endswith(".") or text.endswith(" "):
        raise ValidationError("文件名不能以点或空格结尾。")
    if text.split(".", 1)[0].strip().upper() in archive.WINDOWS_RESERVED_NAMES:
        raise ValidationError("文件名是 Windows 保留设备名。")
    if text.casefold() == "manifest.json":
        raise ValidationError("文件名不能是 manifest.json。")
    if not PurePosixPath(text).suffix:
        raise ValidationError("文件名缺少扩展名。")
    return text


def normalize_romset_name(raw: str) -> str:
    """街机 romset 的落盘名：安全 basename + .zip + 只含 URL/集合名允许的 ASCII 字符。

    不能统一改成 `game.zip`：FBNeo 会把播放 URL 末段当 romset 名去匹配集合。
    """
    text = normalize_bundle_name(raw)
    if not text.lower().endswith(".zip"):
        raise ValidationError("街机本体必须是 .zip 格式的 ROM 集合。")
    if not _ROMSET_NAME_RE.fullmatch(text):
        raise ValidationError(
            "街机 ROM 文件名只能包含字母、数字、点、下划线和短横线；"
            "请使用 ROM 集合名（如 mslug.zip）。"
        )
    if text.casefold() in _ROMSET_RESERVED_NAMES:
        raise ValidationError(f"街机 ROM 不能使用保留文件名：{text}。")
    return text


def decode_manifest_text(payload: bytes) -> str:
    """cue / m3u 文本解码：优先 UTF-8（含 BOM），失败按 latin-1 兜底。"""
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return payload.decode("latin-1")


def parse_cue_references(text: str) -> list[str]:
    """cue 里所有 `FILE "…"` 引用的文件名；保留原始写法供校验。"""
    references: list[str] = []
    for line in text.splitlines():
        match = _CUE_FILE_RE.match(line)
        if match:
            references.append(match.group(1) or match.group(2))
    return references


def parse_m3u_references(text: str) -> list[str]:
    """m3u 的非注释行；`名字|标签` 只取竖线前的文件名。"""
    references: list[str] = []
    for line in text.splitlines():
        value = line.strip().lstrip("﻿").strip()
        if not value or value.startswith("#"):
            continue
        references.append(value.split("|", 1)[0].strip())
    return references


def _natural_key(name: str) -> tuple[object, ...]:
    """自然排序：disc2 排在 disc10 前面。"""
    parts = re.split(r"(\d+)", name.casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _index_by_name(files: tuple[StagedBundleFile, ...]) -> dict[str, StagedBundleFile]:
    return {file.name.casefold(): file for file in files}


def _resolve_reference(
    reference: str,
    *,
    files_by_key: dict[str, StagedBundleFile],
    where: str,
    allow_playlist: bool = False,
) -> StagedBundleFile:
    """把 cue / m3u 里的一行引用解析成组内文件；拒绝路径、URL 与大小写不一致。"""
    raw = (reference or "").strip()
    if not raw:
        raise ValidationError(f"{where}存在空引用。")
    if _URL_RE.match(raw):
        raise ValidationError(f"{where}不能引用远程地址：{raw}")
    if raw.startswith(("/", "\\")):
        raise ValidationError(f"{where}不能引用绝对路径：{raw}")
    normalized = raw.replace("\\", "/")
    if "/" in normalized:
        raise ValidationError(f"{where}只能引用同一层的文件名：{raw}")
    if normalized in (".", ".."):
        raise ValidationError(f"{where}引用了非法路径：{raw}")
    file = files_by_key.get(normalized.casefold())
    if file is None:
        raise ValidationError(f"{where}引用的文件不在本次上传里：{raw}")
    if file.name != normalized:
        raise ValidationError(
            f"{where}引用的大小写与上传文件名不一致：{raw}（实际是 {file.name}）"
        )
    if not allow_playlist and file.extension == ".m3u":
        raise ValidationError(f"{where}不能引用另一个 m3u：{raw}")
    return file


def _validate_references(
    text: str,
    *,
    entry: StagedBundleFile,
    files_by_key: dict[str, StagedBundleFile],
) -> None:
    if entry.extension == ".cue":
        references = parse_cue_references(text)
        if not references:
            raise ValidationError("cue 文件里没有找到任何 FILE 引用。")
        for reference in references:
            file = _resolve_reference(
                reference, files_by_key=files_by_key, where="cue"
            )
            if file.upload_id == entry.upload_id:
                raise ValidationError("cue 不能引用自身。")
        return
    if entry.extension == ".m3u":
        references = parse_m3u_references(text)
        if not references:
            raise ValidationError("m3u 文件里没有任何磁盘项。")
        seen: set[str] = set()
        for reference in references:
            file = _resolve_reference(
                reference,
                files_by_key=files_by_key,
                where="m3u",
                allow_playlist=True,
            )
            if file.upload_id == entry.upload_id:
                raise ValidationError("m3u 不能引用自身。")
            if file.extension == ".m3u":
                raise ValidationError(f"m3u 不能嵌套另一个 m3u：{reference}")
            if file.upload_id in seen:
                raise ValidationError(f"m3u 重复引用了同一文件：{reference}")
            seen.add(file.upload_id)


def _generated_playlist(discs: tuple[StagedBundleFile, ...]) -> bytes:
    lines = ["#EXTM3U", *(file.name for file in discs)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _select_entry(
    files: tuple[StagedBundleFile, ...],
    platform: Platform,
    read_text: Callable[[StagedBundleFile], bytes],
) -> tuple[StagedBundleFile | None, str, bytes | None]:
    """按 m3u > cue > chd > adf/hdf 选入口；必要时生成 m3u。"""
    by_extension: dict[str, list[StagedBundleFile]] = {}
    for file in files:
        by_extension.setdefault(file.extension, []).append(file)

    playlists = by_extension.get(".m3u", [])
    if len(playlists) > 1:
        raise ValidationError("多文件本体只能有一个 m3u。")
    if playlists:
        entry = playlists[0]
        text = decode_manifest_text(read_text(entry))
        files_by_key = _index_by_name(files)
        _validate_references(text, entry=entry, files_by_key=files_by_key)
        return entry, entry.extension, None

    cues = tuple(sorted(by_extension.get(".cue", []), key=lambda f: _natural_key(f.name)))
    if cues:
        if len(cues) == 1:
            entry = cues[0]
            text = decode_manifest_text(read_text(entry))
            _validate_references(
                text, entry=entry, files_by_key=_index_by_name(files)
            )
            return entry, entry.extension, None
        return None, ".m3u", _generated_playlist(cues)

    for extension in (".chd", ".adf", ".hdf"):
        candidates = tuple(
            sorted(by_extension.get(extension, []), key=lambda f: _natural_key(f.name))
        )
        if not candidates:
            continue
        if len(candidates) == 1:
            return candidates[0], extension, None
        return None, ".m3u", _generated_playlist(candidates)

    raise ValidationError("多文件本体缺少入口文件（cue / m3u / chd / adf / hdf）。")


def build_bundle(
    files: tuple[StagedBundleFile, ...],
    platform: Platform,
    read_text: Callable[[StagedBundleFile], bytes],
) -> BodyBundle:
    """校验一组已暂存文件，返回最终布局。任何不合规都抛中文 `ValidationError`。"""
    if not files:
        raise ValidationError("请选择要上传的文件。")
    if len(files) > MAX_BUNDLE_FILES:
        raise ValidationError(f"多文件本体最多 {MAX_BUNDLE_FILES} 个文件。")
    if not platform.bundle_extensions:
        raise ValidationError("当前游戏类型不支持多文件本体。")

    allowed = {normalize_extension(ext) for ext in platform.bundle_extensions}
    entries = {normalize_extension(ext) for ext in platform.bundle_entries}
    seen: set[str] = set()
    for file in files:
        if file.extension not in allowed:
            raise ValidationError(
                f"{platform.label} 不支持 {file.extension or '无后缀'} 文件：{file.name}"
            )
        key = file.name.casefold()
        if key in seen:
            raise ValidationError(f"文件名重复：{file.name}")
        seen.add(key)
        if file.size <= 0:
            raise ValidationError(f"文件大小无效：{file.name}")

    ordered = tuple(sorted(files, key=lambda f: _natural_key(f.name)))
    entry, entry_extension, generated = _select_entry(ordered, platform, read_text)
    if entry_extension not in entries:
        raise ValidationError("这个文件不能作为多文件本体的入口。")
    if entry is not None and entry.extension not in entries:
        raise ValidationError("这个文件不能作为多文件本体的入口。")

    # 入口是 m3u 时，里面的每个 cue 也必须是完整的（引用齐全）；
    # 入口是 cue 时重复校验一次，代价只是一次小文本读取。
    files_by_key = _index_by_name(ordered)
    for file in ordered:
        if file.extension != ".cue":
            continue
        text = decode_manifest_text(read_text(file))
        _validate_references(text, entry=file, files_by_key=files_by_key)

    final_names = {file.name.casefold() for file in ordered}
    if entry is not None:
        final_names.discard(entry.name.casefold())
    final_entry = f"game{entry_extension}".casefold()
    if final_entry in final_names:
        raise ValidationError("入口改名后会与另一个文件重名，请先改名。")

    total = sum(file.size for file in ordered) + (len(generated) if generated else 0)
    if len(ordered) + (1 if generated is not None else 0) > MAX_BUNDLE_FILES:
        raise ValidationError(f"多文件本体最多 {MAX_BUNDLE_FILES} 个文件。")

    return BodyBundle(
        platform_id=platform.id,
        files=ordered,
        entry_source=entry,
        entry_extension=entry_extension,
        generated_m3u=generated,
        total_size=total,
    )
