from __future__ import annotations

import logging
import re
import tempfile
import unicodedata
import zipfile
import zlib
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games import importer, paths, remote
from backend.games.models import (
    CARTRIDGE_ID_MAX_LENGTH,
    CARTRIDGE_ID_PATTERN,
    CARTRIDGE_TYPE_DEFAULT,
    CARTRIDGE_TYPE_LABELS,
    DESCRIPTION_MAX_LENGTH,
    GAME_NAME_MAX_LENGTH,
    Game,
    GameCloudSnapshot,
    GameCloudSnapshotFile,
    GameGalleryImage,
    GameH5File,
    GameRecentPlay,
    GameScreenshot,
    GameUserStat,
    cartridge_types_for,
)
from backend.storage.types import StorageBackend

logger = logging.getLogger(__name__)

GAME_TYPE_FLASH = "flash"
GAME_TYPE_H5 = "h5"

# 游戏类型（game_type 落库值）。顺序即 /status 与前端下拉/分组顺序。
# h5 走 ZIP 解包 + 沙箱 iframe 播放；flash 走 Ruffle；其余为 EmulatorJS。
GAME_TYPES = (
    GAME_TYPE_FLASH,
    GAME_TYPE_H5,
    "nes",
    "snes",
    "gb",      # Game Boy / Game Boy Color（EJS 无独立 gbc core，共用一个）
    "gba",
    "segaMD",  # Mega Drive / Genesis
    "segaGG",  # Game Gear
    "segaMS",  # Sega Master System
)

# 各类型允许的本体扩展名白名单（封面统一走 _COVER_EXTENSIONS）。
# 只收单文件 ROM；不开放 .bin（GB/MD/SMS 等多机种歧义）与压缩/多碟格式。
# h5 收 ZIP 压缩包，由后端解包为多文件。
_GAME_TYPE_EXTENSIONS: dict[str, frozenset[str]] = {
    GAME_TYPE_FLASH: frozenset({".swf"}),
    GAME_TYPE_H5: frozenset({".zip"}),
    "nes": frozenset({".nes"}),
    "snes": frozenset({".sfc", ".smc"}),
    "gb": frozenset({".gb", ".gbc"}),
    "gba": frozenset({".gba"}),
    "segaMD": frozenset({".md", ".gen"}),
    "segaGG": frozenset({".gg"}),
    "segaMS": frozenset({".sms"}),
}

# 网络上传时地址看不出扩展名（如网盘直链），用各类型最常用的那个后缀补上
_DEFAULT_EXTENSIONS: dict[str, str] = {
    GAME_TYPE_FLASH: ".swf",
    GAME_TYPE_H5: ".zip",
    "nes": ".nes",
    "snes": ".sfc",
    "gb": ".gb",
    "gba": ".gba",
    "segaMD": ".md",
    "segaGG": ".gg",
    "segaMS": ".sms",
}

_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# 最近游玩一次取多少条（列表页顶部一行 rail 的量），上限防手改 query。
RECENT_LIMIT_DEFAULT = 20
RECENT_LIMIT_MAX = 50

# 搬运的卡带ID 不用手填，由本体（Flash 的 .swf / H5 的 .zip）CRC32 自动生成
_IMPORT_CARTRIDGE_PREFIX = "F-"

# H5 入口固定为根目录 index.html（大小写不敏感识别，落库统一小写）。
H5_ENTRY_PATH = "index.html"
_H5_ENTRY_NAMES = frozenset({"index.html", "index.htm"})

# 攻略入口固定为根目录 index.html（大小写不敏感识别，落盘统一小写）。
# 只认 index.html、不收 index.htm：攻略没有清单表做路径重写，收下它就得改名，不值得。
GUIDE_ENTRY_PATH = paths.GUIDE_ENTRY_NAME
_GUIDE_ENTRY_NAMES = frozenset({GUIDE_ENTRY_PATH})

# 攻略解包/上传上限。文件数取 1000 与 Starlette MultiPartParser.max_files 的硬上限对齐
# （超了在解析阶段就被拒，路由层拿不到），整体请求大小另由 nginx client_max_body_size 兜底。
_GUIDE_MAX_FILES = 1000
_GUIDE_MAX_FILE_SIZE = 64 * 1024 * 1024
_GUIDE_MAX_TOTAL_SIZE = 256 * 1024 * 1024

# H5 解包上限（压缩包本体上限与 nginx client_max_body_size 对齐）。
_H5_MAX_ZIP_SIZE = 128 * 1024 * 1024
_H5_MAX_ENTRIES = 2000
_H5_MAX_ENTRY_SIZE = 64 * 1024 * 1024
_H5_MAX_TOTAL_SIZE = 256 * 1024 * 1024
_H5_MAX_RATIO = 200
_H5_RATIO_MIN_SIZE = 1024 * 1024
_ASSET_MAX_PATH_LENGTH = 512
_ASSET_MAX_PATH_SEGMENTS = 32
_H5_SKIP_NAMES = frozenset({"__MACOSX", ".DS_Store"})
_ASSET_DEFAULT_MIME = "application/octet-stream"

# 静态资源（H5 解包资源、攻略）的 MIME 由该显式表决定，不依赖运行环境的 /etc/mime.types，保证可复现。
_ASSET_MIME_TYPES: dict[str, str] = {
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


def allowed_body_extensions() -> tuple[str, ...]:
    """全部允许的本体扩展名（供前端 accept 与错误提示使用，已排序）。"""
    extensions = {ext for exts in _GAME_TYPE_EXTENSIONS.values() for ext in exts}
    return tuple(sorted(extensions))


def game_type_of_extension(extension: str) -> str | None:
    """扩展名对应的游戏类型；不是已收录的本体格式时返回 None。"""
    for game_type, extensions in _GAME_TYPE_EXTENSIONS.items():
        if extension in extensions:
            return game_type
    return None


def _remote_extension(url: str) -> str:
    """取直链扩展名，并把地址不合法（非 http/https）转成领域错误。

    凡是碰 `remote` 的地方都要从这层过：不然 DownloadError 会一路冒到 router，
    那里只认 ValidationError 之类的领域错误，最后变成 500。
    """
    try:
        return remote.extension_from_url(url)
    except importer.DownloadError as exc:
        raise ValidationError(str(exc)) from exc


def _remote_body_filename(url: str, game_type: str) -> str:
    """按用户选定的类型定远程本体的文件名（这里只用到它的扩展名）。

    网络上传时类型以下拉选择为准：地址自带的扩展名能认出类型就必须与所选一致，
    不一致当场报错（选错存进去也是放不出来）；认不出（没扩展名，或不是已收录的
    格式）就用该类型的默认后缀补上。
    """
    extensions = _GAME_TYPE_EXTENSIONS.get(game_type)
    if extensions is None:
        raise ValidationError("请选择游戏类型。")
    extension = _remote_extension(url)
    detected = game_type_of_extension(extension) if extension else None
    if detected is not None and detected != game_type:
        raise ValidationError(
            f"该地址的文件属于 {detected} 类型，与所选的 {game_type} 不符，请确认后重试。"
        )
    return f"remote{extension if detected else _DEFAULT_EXTENSIONS[game_type]}"


def detect_game_type(filename: str) -> str:
    """按本体文件名判定游戏类型——类型只由本体决定，不接受手动指定。

    各类型的扩展名互不重叠（见 _GAME_TYPE_EXTENSIONS），因此判定无歧义；
    未收录的扩展名一律拒绝，并在提示里列出支持的格式。
    """
    game_type = game_type_of_extension(Path(filename or "").suffix.lower())
    if game_type is None:
        allowed = "、".join(allowed_body_extensions())
        raise ValidationError(f"无法识别的游戏文件格式，仅支持 {allowed}。")
    return game_type


# 游戏名要同时能当 Windows 文件名与百度网盘文件名（本体/封面下载下来就是「游戏名.后缀」，
# 也会被整包传到网盘），所以按两边的限制取交集校验：非法字符 \ / : * ? " < > |（全角版，
# 如 ：与 ／，不受影响）、控制字符、结尾的点、保留设备名、长度上限。
_NAME_ILLEGAL_CHARS = frozenset('\\/:*?"<>|')
# Windows 保留设备名（大小写不敏感，带扩展名同样保留，如 NUL.nes 也是设备名）
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"COM{i}" for i in range(10)}
    | {f"LPT{i}" for i in range(10)}
)


_CARTRIDGE_ID_RE = re.compile(CARTRIDGE_ID_PATTERN)


def validate_cartridge_id(raw: str) -> str:
    """校验并返回卡带ID（去首尾空白、转大写）。

    卡带ID 唯一且创建后不可改，同时是磁盘上的目录名，所以字符集收得很紧：
    只允许数字、字母、中划线、下划线；小写会自动转成大写。
    """
    value = (raw or "").strip().upper()
    if not value:
        raise ValidationError("请填写卡带 ID。")
    if len(value) > CARTRIDGE_ID_MAX_LENGTH:
        raise ValidationError(f"卡带 ID 不能超过 {CARTRIDGE_ID_MAX_LENGTH} 个字符。")
    if not _CARTRIDGE_ID_RE.match(value):
        raise ValidationError("卡带 ID 只能包含数字、字母、中划线和下划线。")
    return value


def validate_cartridge_type(game_type: str, raw: str) -> str:
    """校验并返回卡带类型；空值取「默认」（这个字段始终有值）。

    可选集合由游戏类型决定：目前只有 FC NES 区分日版/美版，其余类型只有「默认」。
    """
    value = (raw or "").strip().lower() or CARTRIDGE_TYPE_DEFAULT
    allowed = cartridge_types_for(game_type)
    if value not in allowed:
        labels = "、".join(CARTRIDGE_TYPE_LABELS[item] for item in allowed)
        raise ValidationError(f"卡带类型只能是：{labels}。")
    return value


def validate_game_name(raw: str) -> str:
    """校验并返回游戏名（去首尾空白）。不合规抛 ValidationError，消息里说清原因。"""
    name = (raw or "").strip()
    if not name:
        raise ValidationError("请填写游戏名称。")
    if len(name) > GAME_NAME_MAX_LENGTH:
        raise ValidationError(f"游戏名称不能超过 {GAME_NAME_MAX_LENGTH} 个字符。")
    illegal = sorted({ch for ch in name if ch in _NAME_ILLEGAL_CHARS})
    if illegal:
        raise ValidationError(
            f"游戏名称不能包含 {' '.join(illegal)}（Windows 与百度网盘都不允许这些字符）。"
        )
    if any(ord(ch) < 32 for ch in name):
        raise ValidationError("游戏名称不能包含换行、制表符等控制字符。")
    if name.endswith("."):
        raise ValidationError("游戏名称不能以点结尾（Windows 会丢掉结尾的点）。")
    if name.split(".", 1)[0].strip().upper() in _WINDOWS_RESERVED_NAMES:
        raise ValidationError("这是 Windows 的保留设备名，换个名字吧。")
    return name


def validate_description(raw: str) -> str:
    """校验并返回游戏描述（去首尾空白）。超长抛 ValidationError，不静默截断。"""
    description = (raw or "").strip()
    if len(description) > DESCRIPTION_MAX_LENGTH:
        raise ValidationError(f"游戏描述不能超过 {DESCRIPTION_MAX_LENGTH} 个字符。")
    return description


def sanitize_game_name(raw: str, *, fallback: str = "未命名游戏") -> str:
    """把外部来源（搬运抓到的游戏标题）尽可能弄成合法名字：换非法字符、去结尾点、截断。

    搬运不该因为站点标题里有 `/` 或 `:` 就整个失败，所以这里只做无害转换；
    真落库前仍会过 validate_game_name（转换后必然合规，除非整段被清空而回退到兜底名）。
    """
    cleaned = "".join(
        "_" if (ch in _NAME_ILLEGAL_CHARS or ord(ch) < 32) else ch for ch in (raw or "")
    )
    # 先截断再去掉结尾的空白与点：Windows 会把结尾的空格和点静默丢掉，留着会让库里的名字和导出文件名对不上
    cleaned = cleaned.strip()[:GAME_NAME_MAX_LENGTH].rstrip(" .")
    if not cleaned or cleaned.split(".", 1)[0].strip().upper() in _WINDOWS_RESERVED_NAMES:
        return fallback
    return cleaned


def guess_asset_mime(path: str) -> str:
    """按后缀返回静态资源 MIME；未知后缀一律 octet-stream。"""
    return _ASSET_MIME_TYPES.get(PurePosixPath(path).suffix.lower(), _ASSET_DEFAULT_MIME)


def normalize_h5_path(raw: str) -> str:
    """归一化压缩包内相对路径；任何歧义/越界/非法字符都拒绝。"""
    return _normalize_asset_path(raw, where="压缩包内")


def normalize_guide_path(raw: str) -> str:
    """归一化攻略文件夹内相对路径；规则与 H5 包内路径完全一致。"""
    return _normalize_asset_path(raw, where="攻略文件夹内")


def _normalize_asset_path(raw: str, *, where: str) -> str:
    """H5 包内路径与攻略内路径共用的归一化：任何歧义/越界/非法字符都拒绝。"""
    if not raw or not raw.strip():
        raise ValidationError(f"{where}含空路径。")
    text = unicodedata.normalize("NFC", raw).strip()
    if "\\" in text:
        raise ValidationError(f"{where}含非法路径（反斜杠）。")
    if any(ord(ch) < 32 for ch in text):
        raise ValidationError(f"{where}含非法路径（控制字符）。")
    if any(ch in text for ch in "?#%"):
        raise ValidationError(f"{where}含非法路径（? # %）。")
    posix = PurePosixPath(text)
    if posix.is_absolute():
        raise ValidationError(f"{where}含绝对路径。")
    parts = posix.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValidationError(f"{where}含非法路径（. 或 ..）。")
    normalized = "/".join(parts)
    if normalized != text:
        raise ValidationError(f"{where}含非法路径。")
    if len(normalized) > _ASSET_MAX_PATH_LENGTH or len(parts) > _ASSET_MAX_PATH_SEGMENTS:
        raise ValidationError(f"{where}含过长路径。")
    return normalized


def _h5_skip_entry(name: str) -> bool:
    """跳过资源里常见的系统垃圾条目（macOS 元数据、.DS_Store）。"""
    parts = PurePosixPath(name).parts
    return any(part in _H5_SKIP_NAMES for part in parts)


def _has_h5_entry(entries: list[tuple[str, zipfile.ZipInfo]]) -> bool:
    return any(path.lower() in _H5_ENTRY_NAMES for path, _ in entries)


def _strip_h5_wrapper(
    entries: list[tuple[str, zipfile.ZipInfo]],
) -> list[tuple[str, zipfile.ZipInfo]]:
    """压缩包把整个游戏套在一层目录里时剥掉该前缀。

    仅当根目录没有入口、且全部条目共享唯一顶层目录、剥掉后根目录出现入口时才剥离；
    否则原样返回（避免误剥与入口同级的 assets/ 之类目录）。
    """
    if _has_h5_entry(entries):
        return entries
    tops = {path.split("/", 1)[0] for path, _ in entries}
    if len(tops) != 1:
        return entries
    top = tops.pop()
    if not all(path.startswith(f"{top}/") for path, _ in entries):
        return entries
    stripped = [(path[len(top) + 1 :], info) for path, info in entries]
    return stripped if _has_h5_entry(stripped) else entries


def _read_zip_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[BinaryIO, int]:
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


class _SeekableStream:
    """zipfile 需要底层流具备 seekable()/readable()；部分 Python 版本的 spooled 文件没有。"""

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


@dataclass(frozen=True)
class GameUpload:
    """一次上传的输入：文件名决定游戏类型与落盘后缀，流由调用方负责关闭。"""

    filename: str
    stream: BinaryIO
    size: int
    mime: str | None


@dataclass(frozen=True)
class GuideUpload:
    """攻略里的一次上传：path 是文件夹内相对路径（前端已剥掉最外层目录名）。"""

    path: str
    stream: BinaryIO
    size: int | None


@dataclass
class _TypeSwitch:
    """一次「换本体顺带换类型」需要做的磁盘收尾：挪封面与图集 + 删旧类型目录。"""

    stale_dir: str
    cover_from: str | None
    cover_to: str
    gallery_from: str
    gallery_to: str


@dataclass(frozen=True)
class GameItem:
    id: int
    name: str
    cartridge_id: str
    cartridge_type: str
    description: str
    game_type: str
    size: int
    crc32: str
    game_path: str
    cover_path: str | None
    created_at: datetime
    updated_at: datetime
    has_guide: bool = False

    @property
    def path(self) -> str:
        # flash 走 Ruffle 播放页、h5 走沙箱 iframe 播放页，其余平台进 EmulatorJS 通用播放页
        if self.game_type == GAME_TYPE_FLASH:
            return f"/games/flash/{self.id}"
        if self.game_type == GAME_TYPE_H5:
            return f"/games/h5/{self.id}"
        return f"/games/play/{self.id}"


def _game_order_clauses() -> tuple:
    """列表排序：按 GAME_TYPES 的类型顺序分组，组内再按名称。

    类型用一个 CASE 表达式折算成 GAME_TYPES 中的序号，与 /status.game_types
    和前端下拉的顺序一致，不按类型字符串字典序（否则 segaGG 会排在 snes 之后）。
    """
    type_rank = case(
        {game_type: index for index, game_type in enumerate(GAME_TYPES)},
        value=col(Game.game_type),
        else_=len(GAME_TYPES),
    )
    return (type_rank, col(Game.name), col(Game.id))


class GameService:
    def __init__(self, session: Session, storage: StorageBackend) -> None:
        self._session = session
        self._storage = storage

    def list_center(self) -> list[GameItem]:
        rows = self._session.exec(
            select(Game)
            .where(Game.game_path != "")
            .order_by(*_game_order_clauses())
        ).all()
        return [self._to_item(row) for row in rows]

    def list_recent(self, user_id: int, *, limit: int = RECENT_LIMIT_DEFAULT) -> list[GameItem]:
        """当前用户最近玩过的游戏，按最近一次开玩时间倒序。

        只返回仍可游玩的条目（game_path != ''），与中心列表口径一致：本体被清空或
        游戏已删的记录不该出现在 rail 里。
        """
        # 越界值在这里收敛而不是靠 Query(ge=, le=)：参数校验失败走 FastAPI 的 422，
        # 会绕开本仓库统一的 {ok, message} 错误信封（同 settings_router 的处理）。
        limit = max(1, min(int(limit), RECENT_LIMIT_MAX))
        rows = self._session.exec(
            select(Game)
            .join(GameRecentPlay, GameRecentPlay.game_id == Game.id)
            .where(GameRecentPlay.user_id == user_id, Game.game_path != "")
            # 同一时刻记两条时用 id 兜底，保证顺序稳定（与 _game_order_clauses 同思路）
            .order_by(col(GameRecentPlay.played_at).desc(), col(GameRecentPlay.id).desc())
            .limit(limit)
        ).all()
        return [self._to_item(row) for row in rows]

    def mark_played(self, user_id: int, game_id: int) -> None:
        """记录一次开玩：没有则插入，已有则刷新 played_at（一个游戏只留一行）。"""
        row = self._session.get(Game, game_id)
        if row is None or not row.game_path:
            raise NotFoundError("游戏不存在。")
        try:
            self._touch_play(user_id, game_id)
        except IntegrityError:
            # 并发首写撞唯一约束（多标签同时第一次玩同一游戏）：回滚后按已有行改写
            self._session.rollback()
            self._touch_play(user_id, game_id)

    def _touch_play(self, user_id: int, game_id: int) -> None:
        row = self._session.exec(
            select(GameRecentPlay).where(
                GameRecentPlay.user_id == user_id,
                GameRecentPlay.game_id == game_id,
            )
        ).first()
        if row is None:
            row = GameRecentPlay(user_id=user_id, game_id=game_id)
        row.played_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()

    def list_manage(
        self,
        *,
        game_type: str | None = None,
        keyword: str | None = None,
    ) -> list[GameItem]:
        query = select(Game).order_by(*_game_order_clauses())
        if game_type:
            query = query.where(Game.game_type == game_type)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            query = query.where(
                (col(Game.name).like(pattern)) | (col(Game.description).like(pattern))
            )
        rows = self._session.exec(query).all()
        return [self._to_item(row) for row in rows]

    def get(self, game_id: int) -> GameItem:
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        return self._to_item(row)

    def create(
        self,
        name: str,
        description: str,
        body: GameUpload | None = None,
        cover: GameUpload | None = None,
        *,
        cartridge_id: str,
        cartridge_type: str = "",
        body_url: str = "",
        body_game_type: str = "",
        cover_url: str = "",
    ) -> GameItem:
        """新建游戏：本体与封面一次入库，任一步失败即整体回滚。

        卡带ID 必填、创建后不可改（只能删掉重建）；本体/封面各自可以是本地文件
        （`body`/`cover`）或网络直链（`*_url`），走直链时先下到临时目录再走同一条
        上传管线，原始文件名不落盘。
        """
        cartridge_id = validate_cartridge_id(cartridge_id)
        self._ensure_cartridge_free(cartridge_id)
        if not (body_url or cover_url):
            if body is None:
                raise ValidationError("请选择本体文件或填写本体下载地址。")
            return self._create(
                name,
                description,
                body,
                cover,
                cartridge_id=cartridge_id,
                cartridge_type=cartridge_type,
            )
        # 下载来的文件要在整个上传期间保持可读，所以临时目录与句柄都包住 _create
        with tempfile.TemporaryDirectory(prefix="x-game-fetch-") as tmp:
            with ExitStack() as stack:
                work = Path(tmp)
                if body is None and body_url:
                    body = self._remote_body(stack, work / "body", body_url, body_game_type)
                if cover is None and cover_url:
                    cover = self._remote_cover(stack, work / "cover", cover_url)
                if body is None:
                    raise ValidationError("请选择本体文件或填写本体下载地址。")
                return self._create(
                    name,
                    description,
                    body,
                    cover,
                    cartridge_id=cartridge_id,
                    cartridge_type=cartridge_type,
                )

    def _create(
        self,
        name: str,
        description: str,
        body: GameUpload,
        cover: GameUpload | None = None,
        *,
        cartridge_id: str,
        cartridge_type: str = "",
    ) -> GameItem:
        """建条目并上传本体（可选封面）：类型由本体文件名判定，卡带类型按该类型校验。"""
        name = validate_game_name(name)
        description = validate_description(description)
        game_type = detect_game_type(body.filename)
        cartridge_type = validate_cartridge_type(game_type, cartridge_type)
        self._ensure_name_free(game_type, name)
        now = datetime.now(timezone.utc)
        row = Game(
            name=name,
            cartridge_id=cartridge_id,
            cartridge_type=cartridge_type,
            description=description,
            game_type=game_type,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        try:
            self.upload_asset(row.id, kind="game", upload=body)
            if cover is not None:
                self.upload_asset(row.id, kind="cover", upload=cover)
        except Exception:
            # 上传中途失败不留下半成品条目（已上传对象随 delete 一并清理）
            self.delete(row.id)
            raise
        return self.get(row.id)

    def update(
        self,
        game_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        cartridge_type: str | None = None,
        clear_cover: bool = False,
    ) -> GameItem:
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        if cartridge_type is not None:
            row.cartridge_type = validate_cartridge_type(row.game_type, cartridge_type)
        if name is not None:
            name = validate_game_name(name)
            if name != row.name:
                self._ensure_name_free(row.game_type, name, exclude_id=row.id)
                row.name = name
        if description is not None:
            row.description = validate_description(description)
        if clear_cover:
            self._delete_storage_key(row.cover_path)
            row.cover_path = None
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._to_item(row)

    def delete(self, game_id: int) -> None:
        """删游戏：素材目录、云端存档、以及所有账号在它上面的记录一并清掉。

        游戏一删，它的存档快照就再也进不去（没有任何入口能列出已删游戏的快照），
        所以这里顺手把快照行与存档文件一起清掉，别在磁盘上留一堆够不着的孤儿目录。
        """
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        h5_rows = self._h5_rows(row.id)
        recent_rows = self._recent_rows(row.id)
        stat_rows = self._stat_rows(row.id)
        snapshot_rows = self._snapshot_rows(row.id)
        snapshot_files = self._snapshot_file_rows(row.id)
        screenshot_rows = self._screenshot_rows(row.id)
        gallery_rows = self._gallery_rows(row.id)
        # 图集就在游戏目录里，文件随这棵目录树一起没；行要单独删
        self._storage.remove_tree(paths.game_dir(row.game_type, row.cartridge_id))
        # 存档与截图的目录名带的是「写入当时的游戏类型」，换过类型的游戏与当前
        # game_type 不一样，所以一律从 file_path 反推目录，绝不用当前类型拼
        save_dirs: set[str] = set()
        for asset in snapshot_files:
            self._delete_storage_key(asset.file_path)
            if asset.file_path:
                save_dirs.add(str(PurePosixPath(asset.file_path).parent))
            self._session.delete(asset)
        image_dirs: set[str] = set()
        for shot in screenshot_rows:
            self._delete_storage_key(shot.file_path)
            if shot.file_path:
                image_dirs.add(str(PurePosixPath(shot.file_path).parent))
            self._session.delete(shot)
        for image in gallery_rows:
            self._session.delete(image)
        for snapshot in snapshot_rows:
            self._session.delete(snapshot)
        for asset in h5_rows:
            self._session.delete(asset)
        for recent in recent_rows:
            self._session.delete(recent)
        for stat in stat_rows:
            self._session.delete(stat)
        self._session.delete(row)
        self._session.commit()
        for directory in save_dirs | image_dirs:
            self._safe_remove_tree(directory)

    def _delete_storage_key(self, key: str | None) -> None:
        """删单个文件；失败只吞掉（多半是本来就不在了），不影响主流程。"""
        if not key:
            return
        try:
            self._storage.delete(key)
        except StorageError:
            pass

    def upload_asset(
        self,
        game_id: int,
        *,
        kind: str,
        upload: GameUpload | None = None,
        url: str = "",
        game_type: str = "",
    ) -> GameItem:
        """一步完成：按文件名定类型/后缀 → 分块上传 → 删旧对象 → 更新行。

        来源可以是本地文件（`upload`）或网络直链（`url`，本体要带上 `game_type`）；
        失败即整体回滚：切换类型时只改行状态不动对象，新本体就位后才清理旧档。
        """
        if kind not in ("game", "cover"):
            raise ValidationError("无效的上传类型。")
        if not url:
            if upload is None:
                raise ValidationError("请选择要上传的文件或填写下载地址。")
            return self._upload_asset_now(game_id, kind=kind, upload=upload)
        # 下载来的文件要在整个上传期间保持可读，临时目录包住这次上传
        with tempfile.TemporaryDirectory(prefix="x-game-fetch-") as tmp:
            with ExitStack() as stack:
                if kind == "game":
                    prepared = self._remote_body(stack, Path(tmp), url, game_type)
                else:
                    prepared = self._remote_cover(stack, Path(tmp), url)
                return self._upload_asset_now(game_id, kind=kind, upload=prepared)

    def _upload_asset_now(self, game_id: int, *, kind: str, upload: GameUpload) -> GameItem:
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        try:
            return self._upload_asset(row, kind=kind, upload=upload)
        except Exception:
            self._session.rollback()
            raise

    def _fetch_remote(
        self, stack: ExitStack, work_dir: Path, filename: str, url: str
    ) -> GameUpload:
        """下载直链并包成一次上传。

        文件名在这里只是「扩展名的载体」，一律用 `remote{后缀}` 这个名字存临时文件，
        原始文件名不落盘——地址里带什么路径分隔符都影响不到库里。
        """
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            path, _size = remote.fetch(url, work_dir / filename)
        except importer.DownloadError as exc:
            raise ValidationError(str(exc)) from exc
        return _open_upload(stack, path, None)

    def _remote_body(
        self, stack: ExitStack, work_dir: Path, url: str, game_type: str
    ) -> GameUpload:
        return self._fetch_remote(stack, work_dir, _remote_body_filename(url, game_type), url)

    def _remote_cover(self, stack: ExitStack, work_dir: Path, url: str) -> GameUpload:
        extension = _remote_extension(url)
        if extension not in _COVER_EXTENSIONS:
            allowed = "、".join(sorted(_COVER_EXTENSIONS))
            raise ValidationError(f"封面仅支持 {allowed} 图片，请填写指向图片的直链。")
        return self._fetch_remote(stack, work_dir, f"remote{extension}", url)

    def _upload_asset(self, row: Game, *, kind: str, upload: GameUpload) -> GameItem:
        filename = (upload.filename or "").strip()
        if not filename:
            raise ValidationError("请选择要上传的文件。")
        extension = Path(filename).suffix.lower()
        if upload.size is None or upload.size <= 0:
            raise ValidationError("文件大小无效。")
        crc32 = ""
        switched: _TypeSwitch | None = None
        if kind == "game":
            # crc32 锁：先算摘要再动任何文件/行，摘要不符时旧本体连覆盖都不会发生
            crc32 = _crc32_stream(upload.stream)
            _rewind(upload.stream)
            if row.crc32 and crc32 != row.crc32:
                raise ValidationError(
                    "该游戏的本体已锁定：上传的文件与首次上传的 CRC32 不一致，换本体请上传同一个文件。"
                )
            # 本体决定类型：上传新平台的文件即随之切换类型
            switched = self._switch_game_type(row, detect_game_type(filename))
            if row.game_type == GAME_TYPE_H5:
                item = self._upload_h5_zip(
                    row, stream=upload.stream, size=upload.size, mime=upload.mime, crc32=crc32
                )
                self._finish_type_switch(switched)
                return item
            path = paths.body_path(row.game_type, row.cartridge_id, extension)
        elif kind == "cover":
            if extension not in _COVER_EXTENSIONS:
                raise ValidationError("封面仅支持 jpg、png、gif、webp 图片。")
            path = paths.cover_path(row.game_type, row.cartridge_id, extension)
        else:
            raise ValidationError("无效的上传类型。")
        self._storage.upload(path, upload.stream, upload.size, upload.mime)
        old = row.game_path if kind == "game" else row.cover_path
        if old and old != path:
            self._delete_storage_key(old)
        if kind == "game":
            row.game_path = path
            row.size = upload.size
            row.crc32 = crc32
        else:
            row.cover_path = path
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        self._finish_type_switch(switched)
        return self._to_item(row)

    def _switch_game_type(self, row: Game, game_type: str) -> _TypeSwitch | None:
        """把行的类型换成 game_type，返回新本体就位后要收尾的目录搬家。

        磁盘目录带游戏类型，所以类型一变，旧目录里的封面也得跟着挪到新目录；
        但这里只改行状态与 h5 清单（事务内），真正的文件搬家交给调用方在新本体
        写成功之后做，避免上传失败先把旧档毁了。
        """
        if game_type == row.game_type:
            return None
        # 类型换了就是另一组命名空间：同名游戏若已存在，这次换本体不能落库
        self._ensure_name_free(game_type, row.name, exclude_id=row.id)
        # 下面要按「旧类型 → 新类型」改写路径，先把旧类型固定下来（行稍后就会被改）
        old_type = row.game_type
        old_dir = paths.game_dir(old_type, row.cartridge_id)
        new_dir = paths.game_dir(game_type, row.cartridge_id)
        switch = _TypeSwitch(
            stale_dir=old_dir,
            cover_from=row.cover_path,
            cover_to="",
            gallery_from=paths.gallery_dir(old_type, row.cartridge_id),
            gallery_to=paths.gallery_dir(game_type, row.cartridge_id),
        )
        if row.cover_path:
            suffix = Path(row.cover_path).suffix
            switch.cover_to = paths.cover_path(game_type, row.cartridge_id, suffix)
            row.cover_path = switch.cover_to
        # 图集在游戏目录里，随目录一起搬；行里的路径跟着换成新类型那层前缀
        for image in self._gallery_rows(row.id):
            if not image.file_path.startswith(f"{old_dir}/"):
                continue
            image.file_path = f"{new_dir}/{image.file_path[len(old_dir) + 1:]}"
            self._session.add(image)
        if row.game_type == GAME_TYPE_H5:
            for asset in self._h5_rows(row.id):
                self._session.delete(asset)
        row.game_path = ""
        row.size = 0
        row.game_type = game_type
        # 卡带类型跟着游戏类型走：新类型不认原来的值（如 NES「日版」换成 SNES）就回「默认」
        if row.cartridge_type not in cartridge_types_for(game_type):
            row.cartridge_type = CARTRIDGE_TYPE_DEFAULT
        return switch

    def _finish_type_switch(self, switch: _TypeSwitch | None) -> None:
        """新本体已就位：把封面与图集挪进新类型目录，再删掉旧类型目录。

        这一删是递归的（整个旧游戏目录），所以凡是要留下的子目录都得先搬走——
        图集就是其中之一（攻略与 H5 资源不迁，随旧目录一起清掉）。
        """
        if switch is None:
            return
        if switch.cover_from and switch.cover_to:
            self._storage.move(switch.cover_from, switch.cover_to)
        self._storage.move_tree(switch.gallery_from, switch.gallery_to)
        self._storage.remove_tree(switch.stale_dir)

    def open_asset(self, path: str):
        if not path:
            raise ValidationError("文件尚未上传。")
        return self._storage.open_download(path)

    def import_from_url(self, url: str) -> GameItem:
        """从 7k7k / 4399 / flash.homes 游戏页搬运：解析下载到临时目录，再走普通上传管线入库。

        卡带ID 不用手填，直接由本体文件的 CRC32 生成（`F-{CRC32}`）：同一个文件在哪个站
        搬都是同一盘卡带，重复搬运会撞上同一个卡带ID，正好被唯一约束挡下。
        """
        url = (url or "").strip()
        if not url:
            raise ValidationError("请填写要搬运的游戏地址。")
        with tempfile.TemporaryDirectory(prefix="x-game-import-") as tmp:
            work = Path(tmp)
            try:
                imported = importer.download_game(url, work)
            except importer.DownloadError as exc:
                raise ValidationError(str(exc)) from exc
            # 站点标题常带 `/`、`:` 这类字符，先无害化成合法游戏名再入库
            name = sanitize_game_name(imported.name or "")
            # 站点简介经常一长串，搬运不该因此失败：按上限截断（正常新建/编辑则是报错，不静默截）
            description = (imported.description or "").strip()[:DESCRIPTION_MAX_LENGTH]
            with ExitStack() as stack:
                body_path = imported.body_path
                body_mime = "application/x-shockwave-flash"
                if imported.kind == "h5":
                    # H5 镜像先打成 zip，入口校验失败在下载阶段就暴露
                    body_path = work / "game.zip"
                    body_mime = "application/zip"
                    try:
                        importer.build_h5_zip(imported.h5_dir, body_path)
                    except importer.DownloadError as exc:
                        raise ValidationError(str(exc)) from exc
                cartridge_id = self._import_cartridge_id(body_path)
                body = _open_upload(stack, body_path, body_mime)
                cover = None
                if imported.cover_path and imported.cover_path.is_file():
                    cover = _open_upload(
                        stack,
                        imported.cover_path,
                        guess_asset_mime(imported.cover_path.name),
                    )
                return self.create(
                    name, description, body, cover, cartridge_id=cartridge_id
                )

    def _import_cartridge_id(self, body_path: Path) -> str:
        """搬运的卡带ID：读一遍本体文件取 CRC32，拼成 `F-{CRC32}`（8 位大写十六进制）。

        用本体摘要而不是站点 id 或游戏名，是为了让「同一个文件」在库里天然是同一盘卡带。
        搬运的卡带ID 改不了，所以占用时给一句能说清缘由的提示，而不是让人「换一个」。
        """
        with open(body_path, "rb") as handle:
            cartridge_id = f"{_IMPORT_CARTRIDGE_PREFIX}{_crc32_stream(handle)}"
        self._ensure_cartridge_free(
            cartridge_id,
            message=f"这个游戏已经搬运过了（卡带 ID {cartridge_id} 已被占用）。",
        )
        return cartridge_id

    def open_h5_asset(self, game_id: int, asset_path: str):
        """按归一化后的包内相对路径取 H5 资源，返回 (stream, mime, size)。"""
        item = self.get(game_id)
        if item.game_type != GAME_TYPE_H5:
            raise NotFoundError("游戏文件不存在。")
        path = normalize_h5_path(asset_path)
        row = self._session.exec(
            select(GameH5File).where(
                GameH5File.game_id == game_id, GameH5File.path == path
            )
        ).first()
        if row is None:
            raise NotFoundError("游戏文件不存在。")
        return self._storage.open_download(row.file_path), row.mime or _ASSET_DEFAULT_MIME, row.size

    def open_guide_asset(self, game_id: int, asset_path: str):
        """按归一化后的攻略内相对路径取静态文件，返回 (stream, mime, size)。

        攻略目录与 URL 路径一一对应，没有清单表：归一化之后直接拼磁盘路径，
        文件不存在由存储层报错，在这里转成 404（否则 router 会当成 400 上报）。
        """
        item = self.get(game_id)
        relpath = normalize_guide_path(asset_path)
        try:
            stream = self._storage.open_download(
                paths.guide_asset_path(item.game_type, item.cartridge_id, relpath)
            )
        except StorageError as exc:
            raise NotFoundError("攻略文件不存在。") from exc
        return stream, guess_asset_mime(relpath), stream.size

    def upload_guide(self, game_id: int, uploads: list[GuideUpload]) -> GameItem:
        """整目录保存攻略：全量校验 → 写同层暂存目录 → 整体替换 guide/。

        与 H5 一样，磁盘上没有代际前缀，替换靠一次目录改名（旧目录先改名挪开、新的就位、
        再删挪开的），中途失败旧攻略还在。所有校验都在写下第一个字节之前做完，失败最多
        留下一个暂存目录，统一在 except 里删掉——磁盘零残留。
        """
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        if not uploads:
            raise ValidationError("请选择要上传的攻略文件夹。")
        if len(uploads) > _GUIDE_MAX_FILES:
            raise ValidationError(f"攻略文件数量过多，最多 {_GUIDE_MAX_FILES} 个。")

        normalized: list[tuple[str, GuideUpload]] = []
        seen: set[str] = set()
        total = 0
        has_entry = False
        for upload in uploads:
            path = normalize_guide_path(upload.path)
            if path.lower() in _GUIDE_ENTRY_NAMES:
                # 大小写不敏感识别入口，落盘统一成小写，入口地址才固定
                path = GUIDE_ENTRY_PATH
                has_entry = True
            marker = path.lower()
            if marker in seen:
                raise ValidationError("攻略内含重名文件。")
            seen.add(marker)
            if upload.size is not None:
                if upload.size > _GUIDE_MAX_FILE_SIZE:
                    raise ValidationError("攻略内单个文件过大。")
                total += upload.size
                if total > _GUIDE_MAX_TOTAL_SIZE:
                    raise ValidationError("攻略总体积过大。")
            normalized.append((path, upload))
        if not has_entry:
            raise ValidationError("攻略根目录需包含 index.html。")

        game_type = row.game_type
        cartridge_id = row.cartridge_id
        temp_dir = paths.guide_temp_dir(game_type, cartridge_id, uuid4().hex[:12])
        try:
            for path, upload in normalized:
                stored = self._storage.upload(
                    f"{temp_dir}/{path}",
                    upload.stream,
                    upload.size or 0,
                    guess_asset_mime(path),
                )
                if upload.size is not None and stored.size is not None and stored.size != upload.size:
                    raise StorageError("攻略文件写入大小不一致。")
            # 新攻略全部就位后再换目录：这一步之后磁盘上已经是新攻略
            self._storage.replace_tree(temp_dir, paths.guide_dir(game_type, cartridge_id))
        except (ValidationError, StorageError):
            self._safe_remove_tree(temp_dir)
            raise
        except Exception as exc:
            logger.warning("攻略上传失败，已清掉暂存目录 game_id=%s", game_id, exc_info=exc)
            self._safe_remove_tree(temp_dir)
            raise StorageError("攻略上传失败。") from exc

        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._to_item(row)

    def _has_guide(self, row: Game) -> bool:
        """磁盘即真相：guide/index.html 在就算这个游戏有攻略。

        攻略没有清单表、也不落库标记，判定就是一次 stat——本地磁盘一次系统调用，
        列表每行一次可忽略；换来的是「从宿主目录手动删掉攻略，界面立刻跟着变」。
        """
        try:
            self._storage.stat(paths.guide_entry_path(row.game_type, row.cartridge_id))
        except StorageError:
            return False
        return True

    def _h5_rows(self, game_id: int) -> list[GameH5File]:
        return list(
            self._session.exec(
                select(GameH5File).where(GameH5File.game_id == game_id)
            ).all()
        )

    def _recent_rows(self, game_id: int) -> list[GameRecentPlay]:
        """所有用户的该游戏最近游玩记录——删游戏时一并清掉，不留孤儿行。"""
        return list(
            self._session.exec(
                select(GameRecentPlay).where(GameRecentPlay.game_id == game_id)
            ).all()
        )

    def _stat_rows(self, game_id: int) -> list[GameUserStat]:
        """所有用户的该游戏游玩统计（时长/进度）——同样随删游戏一起清掉。"""
        return list(
            self._session.exec(
                select(GameUserStat).where(GameUserStat.game_id == game_id)
            ).all()
        )

    def _snapshot_rows(self, game_id: int) -> list[GameCloudSnapshot]:
        """该游戏的全部云端存档快照（所有账号的）——随删游戏一起清掉。"""
        return list(
            self._session.exec(
                select(GameCloudSnapshot).where(GameCloudSnapshot.game_id == game_id)
            ).all()
        )

    def _screenshot_rows(self, game_id: int) -> list[GameScreenshot]:
        """该游戏的全部截图行（所有账号的）——随删游戏一起清掉。"""
        return list(
            self._session.exec(
                select(GameScreenshot).where(GameScreenshot.game_id == game_id)
            ).all()
        )

    def _gallery_rows(self, game_id: int) -> list[GameGalleryImage]:
        """该游戏的全部图集行——删游戏时清掉，换类型时逐行改路径。"""
        return list(
            self._session.exec(
                select(GameGalleryImage).where(GameGalleryImage.game_id == game_id)
            ).all()
        )

    def _snapshot_file_rows(self, game_id: int) -> list[GameCloudSnapshotFile]:
        """上述快照里的全部存档文件行。"""
        return list(
            self._session.exec(
                select(GameCloudSnapshotFile)
                .join(
                    GameCloudSnapshot,
                    GameCloudSnapshot.id == GameCloudSnapshotFile.snapshot_id,
                )
                .where(GameCloudSnapshot.game_id == game_id)
            ).all()
        )

    def _read_h5_manifest(
        self, stream
    ) -> list[tuple[str, zipfile.ZipInfo]]:
        """只校验压缩包清单（不解压数据），返回 (归一化路径, ZipInfo) 列表。"""
        try:
            stream.seek(0)
        except (OSError, ValueError) as exc:
            raise ValidationError("无法读取上传的压缩包。") from exc
        try:
            archive = zipfile.ZipFile(_SeekableStream(stream))
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            raise ValidationError("压缩包无法解析，请上传有效的 ZIP 文件。") from exc
        entries: list[tuple[str, zipfile.ZipInfo]] = []
        total = 0
        with archive:
            for info in archive.infolist():
                if info.is_dir() or _h5_skip_entry(info.filename):
                    continue
                if info.flag_bits & 0x1:
                    raise ValidationError("压缩包包含加密文件，无法解包。")
                normalized = normalize_h5_path(info.filename)
                size = int(info.file_size)
                if size > _H5_MAX_ENTRY_SIZE:
                    raise ValidationError("压缩包内单个文件过大。")
                compressed = int(info.compress_size)
                if (
                    size > _H5_RATIO_MIN_SIZE
                    and compressed > 0
                    and size // compressed > _H5_MAX_RATIO
                ):
                    raise ValidationError("压缩包解压比例异常，已拒绝。")
                entries.append((normalized, info))
                total += size
                if len(entries) > _H5_MAX_ENTRIES:
                    raise ValidationError("压缩包内文件数量过多。")
                if total > _H5_MAX_TOTAL_SIZE:
                    raise ValidationError("压缩包解压后体积过大。")
        if not entries:
            raise ValidationError("压缩包为空。")
        entries = _strip_h5_wrapper(entries)
        seen: set[str] = set()
        result: list[tuple[str, zipfile.ZipInfo]] = []
        has_entry = False
        for path, info in entries:
            if path.lower() in _H5_ENTRY_NAMES:
                path = H5_ENTRY_PATH
                has_entry = True
            marker = path.lower()
            if marker in seen:
                raise ValidationError("压缩包内含重名文件。")
            seen.add(marker)
            result.append((path, info))
        if not has_entry:
            raise ValidationError("压缩包根目录需包含 index.html。")
        return result

    def _upload_h5_zip(
        self, row: Game, *, stream, size: int | None, mime: str | None, crc32: str
    ) -> GameItem:
        """解包并保存 H5 游戏：先整包解到暂存目录，再整体换掉 h5 目录，最后落库。

        磁盘上没有代际前缀，所以「换」是靠目录改名完成的：暂存目录与 h5 目录同层，
        替换是先把旧目录改名挪开、再把暂存目录改名就位，中途失败旧目录都还在。
        """
        if size is None or size <= 0:
            raise ValidationError("文件大小无效。")
        if size > _H5_MAX_ZIP_SIZE:
            raise ValidationError("压缩包过大。")
        entries = self._read_h5_manifest(stream)
        game_type = row.game_type
        cartridge_id = row.cartridge_id
        temp_dir = paths.h5_temp_dir(game_type, cartridge_id, uuid4().hex[:12])
        h5_dir = paths.h5_dir(game_type, cartridge_id)
        zip_path = paths.body_path(game_type, cartridge_id, ".zip")
        new_rows: list[GameH5File] = []
        try:
            try:
                stream.seek(0)
            except (OSError, ValueError) as exc:
                raise ValidationError("无法读取上传的压缩包。") from exc
            with zipfile.ZipFile(_SeekableStream(stream)) as archive:
                for path, info in entries:
                    spool, actual = _read_zip_entry(archive, info)
                    try:
                        if actual != int(info.file_size):
                            raise ValidationError("压缩包内文件大小与记录不符。")
                        asset_mime = guess_asset_mime(path)
                        stored = self._storage.upload(
                            f"{temp_dir}/{path}", spool, actual, asset_mime
                        )
                        if stored.size is not None and stored.size != actual:
                            raise StorageError("游戏资源写入大小不一致。")
                        new_rows.append(
                            GameH5File(
                                game_id=row.id,
                                path=path,
                                file_path=paths.h5_asset_path(game_type, cartridge_id, path),
                                size=actual,
                                mime=asset_mime,
                            )
                        )
                    finally:
                        spool.close()
            # 新资源全部就位后再换目录：这一步之后磁盘上已经是新包
            self._storage.replace_tree(temp_dir, h5_dir)
            stream.seek(0)
            self._storage.upload(zip_path, stream, size, mime or "application/zip")
        except (ValidationError, StorageError):
            self._safe_remove_tree(temp_dir)
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成领域错误并清掉暂存目录
            logger.warning("H5 上传失败，已清掉暂存目录 game_id=%s", row.id, exc_info=exc)
            self._safe_remove_tree(temp_dir)
            raise StorageError("游戏资源上传失败。") from exc
        try:
            for old in self._h5_rows(row.id):
                self._session.delete(old)
            # 先落旧行删除再插新行，避免 (game_id, path) 唯一约束在重传同包时冲突
            self._session.flush()
            for item in new_rows:
                self._session.add(item)
            row.game_path = zip_path
            row.size = size
            row.crc32 = crc32
            row.updated_at = datetime.now(timezone.utc)
            self._session.add(row)
            self._session.commit()
        except Exception as exc:  # noqa: BLE001 - commit 失败只回滚行，磁盘保持新包
            self._session.rollback()
            logger.warning("H5 资源落库失败 game_id=%s", row.id, exc_info=exc)
            raise StorageError("游戏资源保存失败。") from exc
        self._session.refresh(row)
        return self._to_item(row)

    def _safe_remove_tree(self, key: str) -> None:
        try:
            self._storage.remove_tree(key)
        except StorageError:
            pass

    def _ensure_name_free(self, game_type: str, name: str, *, exclude_id: int | None = None) -> None:
        """同类型下游戏名称唯一（联合唯一索引 uq_games_game_type_name 的业务侧提示）。"""
        rows = self._session.exec(
            select(Game.id).where(Game.game_type == game_type, Game.name == name)
        ).all()
        for existing_id in rows:
            if existing_id != exclude_id:
                raise ValidationError(f"同类游戏里已经有叫「{name}」的了，换个名字吧。")

    def _ensure_cartridge_free(
        self,
        cartridge_id: str,
        *,
        exclude_id: int | None = None,
        message: str | None = None,
    ) -> None:
        """卡带ID 全局唯一（唯一索引 uq_games_cartridge_id 的业务侧提示）。

        手填卡带ID 的场景才提示「换一个」；搬运的卡带ID 由本体摘要自动生成、改不了，
        所以那边传自己的 message 说清是哪个文件搬过了。
        """
        rows = self._session.exec(
            select(Game.id).where(Game.cartridge_id == cartridge_id)
        ).all()
        for existing_id in rows:
            if existing_id != exclude_id:
                raise ValidationError(
                    message or f"卡带 ID「{cartridge_id}」已经被占用，换一个吧。"
                )

    def _to_item(self, row: Game) -> GameItem:
        return GameItem(
            id=row.id,
            name=row.name,
            cartridge_id=row.cartridge_id,
            cartridge_type=row.cartridge_type,
            description=row.description,
            game_type=row.game_type,
            size=row.size,
            crc32=row.crc32,
            game_path=row.game_path,
            cover_path=row.cover_path,
            created_at=row.created_at,
            updated_at=row.updated_at,
            has_guide=self._has_guide(row),
        )


_HASH_CHUNK_SIZE = 1024 * 1024


def _crc32_stream(stream: BinaryIO) -> str:
    """分块读完上传流算 CRC32（不整读进内存），返回 8 位大写十六进制。

    调用方负责之后把流绕回开头再上传。算出来永远是满 8 位，
    所以库里存空串只可能是「尚未算出」，不会与真实摘要混淆。
    """
    value = 0
    while True:
        block = stream.read(_HASH_CHUNK_SIZE)
        if not block:
            break
        value = zlib.crc32(block, value)
    return f"{value & 0xFFFFFFFF:08X}"


def _rewind(stream: BinaryIO) -> None:
    """把上传流绕回开头：算完摘要后要原样再喂给存储层。"""
    try:
        stream.seek(0)
    except (OSError, ValueError) as exc:
        raise ValidationError("无法读取上传的文件。") from exc


def _open_upload(stack: ExitStack, path: Path, mime: str | None) -> GameUpload:
    """打开本地文件构造上传项，句柄交给 ExitStack 统一关闭。"""
    path = Path(path)
    handle = stack.enter_context(path.open("rb"))
    return GameUpload(filename=path.name, stream=handle, size=path.stat().st_size, mime=mime)
