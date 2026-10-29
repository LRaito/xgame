from __future__ import annotations

import logging
import re
import tempfile
import zlib
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games import archive, importer, paths, remote
from backend.games.archive import (
    guess_asset_mime,
    normalize_guide_path,
    normalize_h5_path,
)
from backend.games.models import (
    CARTRIDGE_ID_MAX_LENGTH,
    CARTRIDGE_ID_PATTERN,
    COVER_TYPE_LABELS,
    DESCRIPTION_MAX_LENGTH,
    GAME_NAME_MAX_LENGTH,
    Game,
    GameCloudSnapshot,
    GameCloudSnapshotFile,
    GameGalleryImage,
    GameRecentPlay,
    GameScreenshot,
    GameUserStat,
    cover_types_for,
)
from backend.games.platforms import playable_platforms
from backend.games.runtime_assets import RuntimeAssets
from backend.storage.types import StorageBackend

logger = logging.getLogger(__name__)

GAME_TYPE_FLASH = "flash"
GAME_TYPE_H5 = "h5"

# 游戏类型（game_type 落库值）。顺序即 /status 与前端下拉/分组顺序。
# h5 走 ZIP 解包 + 沙箱 iframe 播放；flash 走 Ruffle；其余为 EmulatorJS。
#
# **机种那部分从 `backend/games/platforms.py` 的机种词表派生**（id 就是 EJS 的 system key，
# 也就是 game_type 的值），所以「哪些机种能上传」只需要改那张表——但 `extensions` 非空的
# 机种才会出现在这里：词表里还有 28 个 EJS 支持、本项目还没打包 core 的机种（n64/psx…），
# 它们只用来给游戏发现的外部名录「对上号」，不开放上传。
#
# flash 与 h5 **不是机种**（是载体类型），所以不来自词表、写在这里，永远排在最前。
GAME_TYPES: tuple[str, ...] = (
    GAME_TYPE_FLASH,
    GAME_TYPE_H5,
    *(platform.id for platform in playable_platforms()),
)

# 各类型允许的本体扩展名白名单（封面统一走 _COVER_EXTENSIONS）。
# 只收单文件 ROM；不开放 .bin（GB/MD/SMS 等多机种歧义）与压缩/多碟格式。
# h5 收 ZIP 压缩包，由后端解包为多文件。
_GAME_TYPE_EXTENSIONS: dict[str, frozenset[str]] = {
    GAME_TYPE_FLASH: frozenset({".swf"}),
    GAME_TYPE_H5: frozenset({".zip"}),
    **{platform.id: frozenset(platform.extensions) for platform in playable_platforms()},
}

# 网络上传时地址看不出扩展名（如网盘直链），用各类型最常用的那个后缀补上
_DEFAULT_EXTENSIONS: dict[str, str] = {
    GAME_TYPE_FLASH: ".swf",
    GAME_TYPE_H5: ".zip",
    **{platform.id: platform.default_extension for platform in playable_platforms()},
}

# 各类型的显示名，只用于后端拼中文报错文案（与 COVER_TYPE_LABELS 同一用途）。
# 前端展示层镜像在 `frontend/src/constants/gameTypes.js` 的 label 字段（可玩机种那 7 条），
# 两边必须逐字一致，由 `tests/test_platforms.py` 钉住。
GAME_TYPE_LABELS: dict[str, str] = {
    GAME_TYPE_FLASH: "Flash",
    GAME_TYPE_H5: "HTML5",
    **{platform.id: platform.label for platform in playable_platforms()},
}

_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# 最近游玩一次取多少条（列表页顶部一行 rail 的量），上限防手改 query。
RECENT_LIMIT_DEFAULT = 20
RECENT_LIMIT_MAX = 50

# 管理列表一页多少条（前端分页条每页 5 行，与 views/games/manage 的 PAGE_SIZE 一致），
# 上限防手改 query。检索那套在 search_service.py 里另有一组同款常量。
MANAGE_PAGE_SIZE_DEFAULT = 5
MANAGE_PAGE_SIZE_MAX = 100

# 搬运的卡带ID 不用手填，由本体（Flash 的 .swf / H5 的 .zip）CRC32 自动生成
_IMPORT_CARTRIDGE_PREFIX = "F-"

# 攻略的两种形态：ZIP（静态站点，查看时按需解包）与 PDF（原样存数据根、不解包）。
# 同一个游戏同时只保留一种，上传一种会删掉另一种。
GUIDE_KIND_ZIP = "zip"
GUIDE_KIND_PDF = "pdf"
# PDF 与 ZIP 一样是应用层 128MB 上限（网关已放宽到 512m，给 NDS 本体留余量）。
GUIDE_PDF_MAX_SIZE = 128 * 1024 * 1024
_GUIDE_PDF_MAGIC = b"%PDF-"
# PDF 规范允许 `%PDF-` 前有少量垃圾字节，按 1024 字节内出现即认可。
_GUIDE_PDF_HEADER_BYTES = 1024

# 两个包（H5 游戏资源包、攻略包）的入口名、上限、路径归一化与解包原语全在
# `backend/games/archive.py`；真正的解包推迟到运行时，见 `backend/games/runtime_assets.py`。


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
        # 报错文案用显示名（任天堂 FC / 世嘉 MD…），不用 `nes`/`segaMD` 这种内部键值
        raise ValidationError(
            f"该地址的文件属于「{GAME_TYPE_LABELS[detected]}」，"
            f"与所选的「{GAME_TYPE_LABELS[game_type]}」不符，请确认后重试。"
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


def _body_type_mismatch(current: str, detected: str) -> ValidationError:
    """换本体时新文件与游戏当前类型不一致的中文错误（类型创建后不可变）。"""
    current_label = GAME_TYPE_LABELS.get(current, current)
    detected_label = GAME_TYPE_LABELS.get(detected, detected)
    allowed = "、".join(sorted(_GAME_TYPE_EXTENSIONS.get(current, ())))
    suffix = f"（支持 {allowed}）" if allowed else ""
    return ValidationError(
        f"该游戏的本体类型是「{current_label}」，只能更换同一游戏类型的本体{suffix}；"
        f"上传的文件是「{detected_label}」，类型不一致，已拒绝。"
    )


# 游戏名要同时能当 Windows 文件名与百度网盘文件名（本体/封面下载下来就是「游戏名.后缀」，
# 也会被整包传到网盘），所以按两边的限制取交集校验。规则常量与包内路径校验共用，
# 放在最底层的 `backend/games/archive.py` 里。
_NAME_ILLEGAL_CHARS = archive.NAME_ILLEGAL_CHARS
_WINDOWS_RESERVED_NAMES = archive.WINDOWS_RESERVED_NAMES


_CARTRIDGE_ID_RE = re.compile(CARTRIDGE_ID_PATTERN)


def normalize_cartridge_id(raw: str) -> str:
    """卡带ID 的**比对归一**：去首尾空白 + 转大写。只归一，不校验、不抛异常。

    落库（`validate_cartridge_id`）与榜单关联（`map_for_cartridge_ids`）共用它，
    保证「库里存的大写」与「拿来比对的大写」永远是同一行代码。
    外面来的文本（榜单 CSV 的卡带 ID 列）可能有空格、小写、甚至根本不是合法卡带ID，
    所以这里**绝不能**换成 `validate_cartridge_id()`——它会 raise，把只读的榜单接口打挂。
    """
    return (raw or "").strip().upper()


def validate_cartridge_id(raw: str) -> str:
    """校验并返回卡带ID（去首尾空白、转大写）。

    卡带ID 唯一且创建后不可改，同时是磁盘上的目录名，所以字符集收得很紧：
    只允许数字、字母、中划线、下划线；小写会自动转成大写。
    """
    value = normalize_cartridge_id(raw)
    if not value:
        raise ValidationError("请填写卡带 ID。")
    if len(value) > CARTRIDGE_ID_MAX_LENGTH:
        raise ValidationError(f"卡带 ID 不能超过 {CARTRIDGE_ID_MAX_LENGTH} 个字符。")
    if not _CARTRIDGE_ID_RE.match(value):
        raise ValidationError("卡带 ID 只能包含数字、字母、中划线和下划线。")
    return value


def validate_cover_type(game_type: str, raw: str | None) -> str | None:
    """校验并返回封面类型（封面样式 id）；空值合法、返回 None。

    先判空再判类型：不支持美化封面的游戏类型收到空串是正常的（编辑弹框根本不显示
    那一行，表单照样会把空串发上来），不能因此报错。
    """
    value = (raw or "").strip().lower()
    if not value:
        return None
    allowed = cover_types_for(game_type)
    if not allowed:
        raise ValidationError("该游戏类型不支持美化封面，不能设置封面类型。")
    if value not in allowed:
        labels = "、".join(COVER_TYPE_LABELS[item] for item in allowed)
        raise ValidationError(f"封面类型只能是：{labels}。")
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


@dataclass(frozen=True)
class GameUpload:
    """一次上传的输入：文件名决定游戏类型与落盘后缀，流由调用方负责关闭。"""

    filename: str
    stream: BinaryIO
    size: int
    mime: str | None


@dataclass(frozen=True)
class _CartridgeMove:
    """改卡带ID 时要整棵搬走的一对目录（源目录不在就当没有）。"""

    source: str
    target: str


def play_path(game_type: str, game_id: int) -> str:
    """游戏的播放页路径。**这是播放路由的唯一一份实现**（`GameItem.path` 与榜单关联都走它）。

    flash 走 Ruffle 播放页、h5 走沙箱 iframe 播放页，其余平台进 EmulatorJS 通用播放页。
    """
    if game_type == GAME_TYPE_FLASH:
        return f"/games/flash/{game_id}"
    if game_type == GAME_TYPE_H5:
        return f"/games/h5/{game_id}"
    return f"/games/play/{game_id}"


@dataclass(frozen=True)
class GameLink:
    """一条「榜单行 → 平台库存游戏」的关联结果：游戏 id 与它的播放页路径。"""

    game_id: int
    path: str


@dataclass(frozen=True)
class GameItem:
    id: int
    name: str
    cartridge_id: str
    cover_type: str | None
    description: str
    game_type: str
    size: int
    crc32: str
    game_path: str
    cover_path: str | None
    created_at: datetime
    updated_at: datetime
    # ""（没有攻略）/ "zip"（静态站点）/ "pdf"
    guide_kind: str = ""

    @property
    def path(self) -> str:
        return play_path(self.game_type, self.id)


@dataclass(frozen=True)
class ManagePage:
    """管理列表的一页。字段口径与 search_service.SearchPage 一致（那边多一个 indexed）。"""

    total: int
    page: int
    page_size: int
    items: list[GameItem]


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


def _manage_order_clauses() -> tuple:
    """管理列表排序：按更新时间倒序（最近动过的排最前），id 兜底保证翻页稳定。

    与游戏中心的 `_game_order_clauses()`（类型顺序 → 名称）不同：管理页是
    「最近动过什么」的工作台视图，中心页则要保持类型分组。`updated_at` 在编辑、
    换本体/封面、传攻略、删攻略等改动时都会刷新，所以它就是管理页展示的那一列。
    """
    return (col(Game.updated_at).desc(), col(Game.id).desc())


class GameService:
    def __init__(
        self, session: Session, storage: StorageBackend, runtime_storage: StorageBackend
    ) -> None:
        self._session = session
        self._storage = storage  # 数据根：本体/封面/图集/两个 zip
        self._runtime_storage = runtime_storage  # 运行时根：H5 与攻略的解包产物
        self._assets = RuntimeAssets(storage, runtime_storage)

    def _storage_root(self) -> str | None:
        """数据根的绝对路径，只用来算 Windows 的完整路径长度（见 `archive.ensure_path_fits`）。

        `StorageBackend` 协议没有 `root` 这一项（远端实现未必要落到本地目录），所以取不到就
        返回 None、跳过长度检查——宁可少一道检查，也不要为一个可选能力把协议撑大。
        """
        root = getattr(self._storage, "root", None)
        return str(root) if root is not None else None

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

    def map_for_cartridge_ids(self, raw_ids: Sequence[str]) -> dict[str, GameLink]:
        """一次查询拿一批卡带ID 对应的库存游戏（榜单行关联用），避免逐行查。

        **入参是外面来的原始文本**（榜单 CSV 的卡带 ID 列：可能有空格、小写，也可能是根本
        不存在的编号），比对前统一走 `normalize_cartridge_id()`（去首尾空白 + 转大写），
        与落库时的大写形式对齐。**键是原样回传的入参字符串**——调用方 `links.get(原始ID)`
        就完事，不必知道这条归一规则；没命中的入参不出现在结果里。

        只认**有本体**的游戏（`game_path != ''`），与 `list_center` / `list_recent` 同口径：
        没有本体的条目点进去只会 404，不该给链接。

        不分块：榜单一个机种最多 100 行、每行最多 2 个卡带ID（见 `search_index._RANKING_ID_SPLIT`），
        也就是最多 200 个宿主参数，离 SQLite 的 999 还差一个数量级。
        """
        # 归一后的 ID -> 原样入参（可能多个入参归一到同一个 ID，都要能查到）
        wanted: dict[str, list[str]] = {}
        for raw in raw_ids:
            key = normalize_cartridge_id(raw)
            if key:
                wanted.setdefault(key, []).append(raw)
        if not wanted:
            return {}
        rows = self._session.exec(
            select(Game)
            .where(col(Game.cartridge_id).in_(list(wanted)), Game.game_path != "")
            # 卡带ID 有唯一索引，正常只会有一行；老库若缺索引（create_all 不补索引）就按 id 取第一条
            .order_by(col(Game.id))
        ).all()
        links: dict[str, GameLink] = {}
        for row in rows:
            link = GameLink(game_id=row.id, path=play_path(row.game_type, row.id))
            for raw in wanted.get(row.cartridge_id, ()):
                links[raw] = link
        return links

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
        page: int = 1,
        page_size: int = MANAGE_PAGE_SIZE_DEFAULT,
    ) -> ManagePage:
        """管理列表的一页。排序按更新时间倒序（最近改动的排最前），筛选口径不变。

        越界参数在这里收敛而不是靠 Query(ge=, le=)：参数校验失败走 FastAPI 的 422，
        会绕开本仓库统一的 {ok, message} 错误信封（同 list_recent 与 search_service 的处理）。

        页码越界**不算错误**：items 空、total 照给，页码收敛交给前端（与检索页同一口径）。
        """
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or MANAGE_PAGE_SIZE_DEFAULT), MANAGE_PAGE_SIZE_MAX))

        filters = []
        if game_type:
            filters.append(col(Game.game_type) == game_type)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(
                (col(Game.name).like(pattern)) | (col(Game.description).like(pattern))
            )

        # 总数单独查一条：带上同一套 where，否则 total 会变成全表数
        total = self._session.exec(
            select(func.count()).select_from(Game).where(*filters)
        ).one()
        rows = self._session.exec(
            select(Game)
            .where(*filters)
            .order_by(*_manage_order_clauses())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ManagePage(
            total=int(total),
            page=page,
            page_size=page_size,
            items=[self._to_item(row) for row in rows],
        )

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
        body_url: str = "",
        body_game_type: str = "",
        cover_url: str = "",
    ) -> GameItem:
        """新建游戏：本体与封面一次入库，任一步失败即整体回滚。

        卡带ID 必填、创建后不可改（只能删掉重建）；本体/封面各自可以是本地文件
        （`body`/`cover`）或网络直链（`*_url`），走直链时先下到临时目录再走同一条
        上传管线，原始文件名不落盘。

        **不接受封面类型**：新建一律留空，只有编辑弹框手动选或美化封面时才落值。
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
                )

    def _create(
        self,
        name: str,
        description: str,
        body: GameUpload,
        cover: GameUpload | None = None,
        *,
        cartridge_id: str,
    ) -> GameItem:
        """建条目并上传本体（可选封面）：类型由本体文件名判定，封面类型留空。"""
        name = validate_game_name(name)
        description = validate_description(description)
        game_type = detect_game_type(body.filename)
        self._ensure_name_free(game_type, name)
        now = datetime.now(timezone.utc)
        row = Game(
            name=name,
            cartridge_id=cartridge_id,
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
        cover_type: str | None = None,
        clear_cover: bool = False,
    ) -> GameItem:
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        if cover_type is not None:
            row.cover_type = validate_cover_type(row.game_type, cover_type)
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

    def rename_cartridge_id(self, game_id: int, cartridge_id: str) -> GameItem:
        """改卡带ID：磁盘目录与库里所有引用它的路径列一起改，一次做完。

        卡带ID 同时是磁盘目录名，所以这是一次**显式迁移**，而不是 `update()` 顺手改个字段：
        先校验、查重、算清要搬哪些目录并把行里的路径改成新值，再把目录整棵搬过去
        （中途失败按相反顺序搬回来），最后才提交。顺序是「先危险后安全」——反过来一旦目录
        搬不动，库里所有路径就都指向不存在的位置，这盘游戏彻底打不开。
        """
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        new_id = validate_cartridge_id(cartridge_id)
        if new_id == row.cartridge_id:
            # 没变就是空操作：不碰磁盘，也不刷 updated_at
            return self._to_item(row)
        self._ensure_cartridge_free(new_id, exclude_id=row.id)

        moves = self._plan_cartridge_rename(row, new_id)
        old_id = row.cartridge_id
        done = self._move_dirs_for_rename(moves)
        row.cartridge_id = new_id
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        try:
            self._session.commit()
        except IntegrityError:
            # 并发下别人刚占了这个 ID：唯一索引兜底，磁盘搬回去、行不留痕
            self._session.rollback()
            self._rollback_dirs_for_rename(done)
            raise ValidationError(f"卡带 ID「{new_id}」已经被占用，换一个吧。") from None
        self._session.refresh(row)
        # 解包产物按卡带ID 分目录，改完名旧的那份作废（下次访问自动重新解包）。
        # 数据根那棵树已经被 move_tree 搬走了，这里只管运行时根。
        self._assets.drop_tree(paths.game_dir(row.game_type, old_id))
        return self._to_item(row)

    def _plan_cartridge_rename(self, row: Game, new_id: str) -> list[_CartridgeMove]:
        """算清这次改名要搬哪些目录，并把行里所有引用旧卡带ID 的路径改成新值。

        两件事放一起做，是为了让路径长度守卫照着**真正的目标路径**算，而不是另写一份镜像逻辑。

        要搬的目录一共三类：游戏目录一棵树（本体、封面、h5、攻略、图集都在里面）、
        以及按存档与截图的 `file_path` 反推出来的 `save/{用户名}/{类型}/{卡带ID}` 与
        `image/{用户名}/{类型}/{卡带ID}`。后两类的目录名带的是**写入当时的游戏类型**
        （历史数据里可能换过类型，截图与存档目录仍留在旧类型下），所以只能从 file_path
        反推、绝不用游戏当前类型拼——与 `delete()` 同一条规矩。
        """
        old_id = row.cartridge_id
        old_dir = paths.game_dir(row.game_type, old_id)
        new_dir = paths.game_dir(row.game_type, new_id)

        moves = [_CartridgeMove(source=old_dir, target=new_dir)]
        seen = {old_dir}
        for asset in (*self._snapshot_file_rows(row.id), *self._screenshot_rows(row.id)):
            if not asset.file_path:
                continue
            parent = PurePosixPath(asset.file_path).parent
            # 目录名的最后一段就是写入当时的卡带ID；对不上说明这条路径不是我们写的，不碰
            if parent.name != old_id:
                continue
            source = parent.as_posix()
            if source in seen:
                continue
            seen.add(source)
            moves.append(
                _CartridgeMove(source=source, target=(parent.parent / new_id).as_posix())
            )

        # 本体、封面、图集：路径都在数据根的游戏目录里，只换掉那一层前缀
        for holder, attr in ((row, "game_path"), (row, "cover_path")):
            value = getattr(holder, attr)
            if value and value.startswith(f"{old_dir}/"):
                setattr(holder, attr, self._fit_renamed_path(f"{new_dir}/{value[len(old_dir) + 1:]}"))
        for asset in self._gallery_rows(row.id):
            if asset.file_path.startswith(f"{old_dir}/"):
                asset.file_path = self._fit_renamed_path(
                    f"{new_dir}/{asset.file_path[len(old_dir) + 1:]}"
                )
                self._session.add(asset)
        # 存档与截图：只换各自父目录的最后一段（那一层类型是写入当时的，不能按当前类型拼）
        for asset in (*self._snapshot_file_rows(row.id), *self._screenshot_rows(row.id)):
            path = PurePosixPath(asset.file_path)
            if not asset.file_path or path.parent.name != old_id:
                continue
            asset.file_path = self._fit_renamed_path(
                (path.parent.parent / new_id / path.name).as_posix()
            )
            self._session.add(asset)
        # 解包产物在运行时根下，按卡带ID 分目录，改完名旧的那份就作废了（下次访问重新解包），
        # 所以只对新的前缀算长度。解包产物里的深层文件没有任何表记录，长度只能保证到
        # h5/ 与 guide/ 这一层——解包那一刻会再按真实的包内路径逐条卡一遍。
        for maker in (paths.h5_dir, paths.guide_dir):
            self._fit_renamed_path(maker(row.game_type, new_id), root=self._assets.root())
        return moves

    def _fit_renamed_path(self, value: str, *, root: str | None = None) -> str:
        """改名后的路径过一遍 Windows 总长守卫，原样返回（写起来能直接赋值）。

        `root` 缺省是数据根；解包产物在运行时根下，调用方要显式传 `self._assets.root()`。
        """
        archive.ensure_path_fits(
            root if root is not None else self._storage_root(),
            value,
            where="改名后",
            hint="或把卡带 ID 改短一点",
        )
        return value

    def _move_dirs_for_rename(self, moves: list[_CartridgeMove]) -> list[_CartridgeMove]:
        """逐个搬目录；中途失败就把已搬的按相反顺序搬回去，再把异常抛出去。

        搬之前先拦一种形态：**源目录不在、目标目录却在**。这时 `move_tree` 什么都不做，
        可行里的路径照样被改成指向目标目录——这盘游戏会悄悄读上别人（或已删游戏的残留）的文件。
        源在、目标也在是允许的：目标里只可能有孤儿文件，`move_tree` 会把它挪开再删掉。
        """
        for move in moves:
            if not self._storage.dir_exists(move.source) and self._storage.dir_exists(
                move.target
            ):
                raise ValidationError(
                    f"改名被拦下：目录「{move.target}」已经存在，而「{move.source}」不在。"
                    "改名后这盘游戏会指向那个目录，先把它清理掉再试。"
                )
        done: list[_CartridgeMove] = []
        try:
            for move in moves:
                # 源目录不在（本体还没上传过，或宿主手动删过）就当没有，照常往下走：
                # 改名本身是元数据操作，拒绝并不能让文件回来
                self._storage.move_tree(move.source, move.target)
                done.append(move)
        except StorageError:
            self._rollback_dirs_for_rename(done)
            raise
        return done

    def _rollback_dirs_for_rename(self, done: list[_CartridgeMove]) -> None:
        """把已经搬过去的目录按相反顺序搬回来；单个搬不动只记日志，不掩盖原始异常。"""
        for move in reversed(done):
            try:
                self._storage.move_tree(move.target, move.source)
            except StorageError:
                logger.error(
                    "改卡带ID 回滚失败：%s 没能搬回 %s，请手工处理。", move.target, move.source
                )

    def delete(self, game_id: int) -> None:
        """删游戏：素材目录、云端存档、以及所有账号在它上面的记录一并清掉。

        游戏一删，它的存档快照就再也进不去（没有任何入口能列出已删游戏的快照），
        所以这里顺手把快照行与存档文件一起清掉，别在磁盘上留一堆够不着的孤儿目录。
        """
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        recent_rows = self._recent_rows(row.id)
        stat_rows = self._stat_rows(row.id)
        snapshot_rows = self._snapshot_rows(row.id)
        snapshot_files = self._snapshot_file_rows(row.id)
        screenshot_rows = self._screenshot_rows(row.id)
        gallery_rows = self._gallery_rows(row.id)
        # 图集就在游戏目录里，文件随这棵目录树一起没；行要单独删
        game_dir = paths.game_dir(row.game_type, row.cartridge_id)
        self._storage.remove_tree(game_dir)
        # 解包产物是派生物，跟着整棵游戏目录一起作废（两个根相同时上面那步已经删掉了，
        # 这里退化成一次 exists() 检查）
        self._assets.drop_tree(game_dir)
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
        cover_type: str = "",
    ) -> GameItem:
        """一步完成：校验类型/后缀 → 分块上传 → 更新行 → 删旧对象。

        换本体只接受与游戏当前 `game_type` 相同的本体（类型创建后不可变），成功后
        重算并覆盖 `crc32`/`size`/`game_path`；失败整体回滚，旧档不动。
        来源可以是本地文件（`upload`）或网络直链（`url`，本体要带上 `game_type`）。

        `cover_type` 只在 kind="cover" 且非空时生效——美化封面时把所选样式 id 与
        封面文件一次写进去（分两步会有「封面换了、类型没跟上」的中间态）。
        """
        if kind not in ("game", "cover"):
            raise ValidationError("无效的上传类型。")
        if not url:
            if upload is None:
                raise ValidationError("请选择要上传的文件或填写下载地址。")
            return self._upload_asset_now(
                game_id, kind=kind, upload=upload, cover_type=cover_type
            )
        if kind == "game":
            # 下载可能很慢/很大：类型不符时在下载前就拒绝
            row = self._session.get(Game, game_id)
            if row is None:
                raise NotFoundError("游戏不存在。")
            if not game_type:
                raise ValidationError("请选择游戏类型。")
            if game_type != row.game_type:
                raise _body_type_mismatch(row.game_type, game_type)
        # 下载来的文件要在整个上传期间保持可读，临时目录包住这次上传
        with tempfile.TemporaryDirectory(prefix="x-game-fetch-") as tmp:
            with ExitStack() as stack:
                if kind == "game":
                    prepared = self._remote_body(stack, Path(tmp), url, game_type)
                else:
                    prepared = self._remote_cover(stack, Path(tmp), url)
                return self._upload_asset_now(
                    game_id, kind=kind, upload=prepared, cover_type=cover_type
                )

    def _upload_asset_now(
        self, game_id: int, *, kind: str, upload: GameUpload, cover_type: str = ""
    ) -> GameItem:
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        try:
            return self._upload_asset(row, kind=kind, upload=upload, cover_type=cover_type)
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

    def _upload_asset(
        self, row: Game, *, kind: str, upload: GameUpload, cover_type: str = ""
    ) -> GameItem:
        filename = (upload.filename or "").strip()
        if not filename:
            raise ValidationError("请选择要上传的文件。")
        extension = Path(filename).suffix.lower()
        if upload.size is None or upload.size <= 0:
            raise ValidationError("文件大小无效。")
        crc32 = ""
        if kind == "game":
            # 类型创建后不可变：先按扩展名判类型，跨类型时连流都不读、旧档不动
            detected = detect_game_type(filename)
            if detected != row.game_type:
                raise _body_type_mismatch(row.game_type, detected)
            # 同类型才算摘要；它只是当前本体的记录，不再作为更换的锁
            crc32 = _crc32_stream(upload.stream)
            _rewind(upload.stream)
            if row.game_type == GAME_TYPE_H5:
                return self._upload_h5_zip(
                    row, stream=upload.stream, size=upload.size, mime=upload.mime, crc32=crc32
                )
            path = paths.body_path(row.game_type, row.cartridge_id, extension)
        elif kind == "cover":
            if extension not in _COVER_EXTENSIONS:
                raise ValidationError("封面仅支持 jpg、png、gif、webp 图片。")
            if cover_type:
                # 美化封面：样式 id 与封面文件同一次提交，校验不过就连文件都不写
                row.cover_type = validate_cover_type(row.game_type, cover_type)
            path = paths.cover_path(row.game_type, row.cartridge_id, extension)
        else:
            raise ValidationError("无效的上传类型。")
        self._storage.upload(path, upload.stream, upload.size, upload.mime)
        old = row.game_path if kind == "game" else row.cover_path
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
        # 落库成功后再删旧对象：commit 失败时旧档仍然完好，最多留下一个未被引用的新文件
        if old and old != path:
            self._delete_storage_key(old)
        return self._to_item(row)

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
        """按归一化后的包内相对路径取 H5 资源，返回 (stream, mime, size)。

        资源包在数据根、解包产物在运行时根，两边路径一一对应、没有清单表：先确保已经
        解包（首次访问才真的解），再按同一个相对路径从运行时根读。
        """
        item = self.get(game_id)
        if item.game_type != GAME_TYPE_H5:
            raise NotFoundError("游戏文件不存在。")
        path = normalize_h5_path(asset_path)
        # ensure 必须在 try 外面：解压失败（磁盘满/只读）是服务端故障，不能被吞成 404
        self._assets.ensure(archive.H5, item.game_type, item.cartridge_id)
        try:
            stream = self._runtime_storage.open_download(
                paths.h5_asset_path(item.game_type, item.cartridge_id, path)
            )
        except StorageError as exc:
            raise NotFoundError("游戏文件不存在。") from exc
        return stream, guess_asset_mime(path), stream.size

    def open_guide_asset(self, game_id: int, asset_path: str):
        """按归一化后的攻略内相对路径取静态文件，返回 (stream, mime, size)。

        与 H5 同一套：包在数据根、解包产物在运行时根，路径一一对应、没有清单表。
        攻略形态以库里的 `guide_kind` 为准——手动拷进数据根的文件不会凭空变成攻略。
        """
        item = self.get(game_id)
        if item.guide_kind != GUIDE_KIND_ZIP:
            raise NotFoundError("攻略文件不存在。")
        relpath = normalize_guide_path(asset_path)
        self._assets.ensure(archive.GUIDE, item.game_type, item.cartridge_id)
        try:
            stream = self._runtime_storage.open_download(
                paths.guide_asset_path(item.game_type, item.cartridge_id, relpath)
            )
        except StorageError as exc:
            raise NotFoundError("攻略文件不存在。") from exc
        return stream, guess_asset_mime(relpath), stream.size

    def open_guide_pdf(self, game_id: int):
        """返回攻略 PDF 的 (stream, size)；PDF 不解包，直接从数据根读。"""
        item = self.get(game_id)
        if item.guide_kind != GUIDE_KIND_PDF:
            raise NotFoundError("攻略文件不存在。")
        try:
            stream = self._storage.open_download(
                paths.guide_pdf_path(item.game_type, item.cartridge_id)
            )
        except StorageError as exc:
            raise NotFoundError("攻略文件不存在。") from exc
        return stream, stream.size

    def upload_guide(self, game_id: int, upload: GameUpload) -> GameItem:
        """保存攻略：ZIP 静态站点包（只校验、不解压）或 PDF，二者互斥。

        上传一种形态会删掉另一种，并作废运行时根里的旧解包产物。校验在写下第一个
        字节之前做完，失败磁盘零残留；删旧形态失败时把新文件也删掉再报错，避免留下
        「两种攻略并存」的脏状态。
        """
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        filename = (upload.filename or "").strip()
        if not filename:
            raise ValidationError("请选择要上传的攻略文件（ZIP 或 PDF）。")
        suffix = Path(filename).suffix.lower()
        if suffix not in (".zip", ".pdf"):
            raise ValidationError("攻略只支持 ZIP 压缩包或 PDF 文件。")
        if upload.size is None or upload.size <= 0:
            raise ValidationError("文件大小无效。")

        game_type, cartridge_id = row.game_type, row.cartridge_id
        if suffix == ".zip":
            if upload.size > archive.MAX_ZIP_SIZE:
                raise ValidationError("压缩包过大。")
            entries = archive.read_manifest(upload.stream, kind=archive.GUIDE)
            # 包内路径的深度只出现在运行时根下，所以按运行时根算 Windows 完整路径长度
            for entry in entries:
                archive.ensure_path_fits(
                    self._assets.root(),
                    paths.guide_asset_path(game_type, cartridge_id, entry.path),
                    where=archive.WHERE[archive.GUIDE],
                )
            target = paths.guide_zip_path(game_type, cartridge_id)
            obsolete = paths.guide_pdf_path(game_type, cartridge_id)
            mime = "application/zip"
            guide_kind = GUIDE_KIND_ZIP
        else:
            if upload.size > GUIDE_PDF_MAX_SIZE:
                raise ValidationError("攻略 PDF 过大。")
            _validate_pdf_header(upload.stream)
            target = paths.guide_pdf_path(game_type, cartridge_id)
            obsolete = paths.guide_zip_path(game_type, cartridge_id)
            mime = "application/pdf"
            guide_kind = GUIDE_KIND_PDF

        _rewind(upload.stream)
        self._storage.upload(target, upload.stream, upload.size, mime)
        try:
            self._storage.delete(obsolete)
        except StorageError:
            # 旧形态没删掉：新文件也删掉再报错，库里仍是旧形态、磁盘也只留旧文件
            try:
                self._storage.delete(target)
            except StorageError:
                logger.warning("回滚新攻略文件失败：%s", target, exc_info=True)
            raise
        self._assets.drop_tree(paths.guide_dir(game_type, cartridge_id))
        row.guide_kind = guide_kind
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._to_item(row)

    def delete_guide(self, game_id: int) -> GameItem:
        """删除这个游戏的攻略：文件、解包产物与库里的形态一起清掉。

        幂等：本来就没有攻略也返回成功（数据根里可能还有历史遗留文件，一并清掉）。
        文件删除失败会抛 `StorageError`，此时库里的标记保持不变，方便重试；只有确实
        有攻略时才刷新 `updated_at`，重复 DELETE 不会把游戏反复顶到管理列表最前。
        """
        row = self._session.get(Game, game_id)
        if row is None:
            raise NotFoundError("游戏不存在。")
        game_type, cartridge_id = row.game_type, row.cartridge_id
        # 两种形态都删：同一游戏正常只有一种，这里顺手清掉宿主手放的孤儿文件。
        # 直接调 storage.delete（不能用会吞错的 _delete_storage_key）：删失败就不清列。
        self._storage.delete(paths.guide_zip_path(game_type, cartridge_id))
        self._storage.delete(paths.guide_pdf_path(game_type, cartridge_id))
        self._assets.drop_tree(paths.guide_dir(game_type, cartridge_id))
        if row.guide_kind:
            row.guide_kind = ""
            row.updated_at = datetime.now(timezone.utc)
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
        return self._to_item(row)

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
        """该游戏的全部图集行——删游戏时清掉，改卡带ID 时逐行改路径。"""
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

    def _upload_h5_zip(
        self, row: Game, *, stream, size: int | None, mime: str | None, crc32: str
    ) -> GameItem:
        """只校验并保存 H5 的 zip，一个字节都不解。

        解包推迟到播放时（`RuntimeAssets.ensure`），产物落在运行时根。校验全在写下第一个
        字节之前做完，不合规的包连覆盖都不会发生；新包就位后运行时根那份旧产物作废。
        """
        if size is None or size <= 0:
            raise ValidationError("文件大小无效。")
        if size > archive.MAX_ZIP_SIZE:
            raise ValidationError("压缩包过大。")
        entries = archive.read_manifest(stream, kind=archive.H5)
        game_type = row.game_type
        cartridge_id = row.cartridge_id
        # 包内路径的深度只出现在运行时根下，所以按运行时根算 Windows 完整路径长度
        for entry in entries:
            archive.ensure_path_fits(
                self._assets.root(),
                paths.h5_asset_path(game_type, cartridge_id, entry.path),
                where=archive.WHERE[archive.H5],
            )
        zip_path = paths.h5_zip_path(game_type, cartridge_id)
        _rewind(stream)
        self._storage.upload(zip_path, stream, size, mime or "application/zip")
        # 新包已就位：运行时根的旧解包产物作废，下次播放重新解包
        self._assets.drop_tree(paths.h5_dir(game_type, cartridge_id))
        row.game_path = zip_path
        row.size = size
        row.crc32 = crc32
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        try:
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
            cover_type=row.cover_type,
            description=row.description,
            game_type=row.game_type,
            size=row.size,
            crc32=row.crc32,
            game_path=row.game_path,
            cover_path=row.cover_path,
            created_at=row.created_at,
            updated_at=row.updated_at,
            guide_kind=row.guide_kind,
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


def _validate_pdf_header(stream: BinaryIO) -> None:
    """按内容认 PDF：`%PDF-` 出现在前 1024 字节内即可（不信任文件名与 Content-Type）。

    校验只读文件头；调用方随后用 `_rewind()` 把流绕回开头再写存储。
    """
    try:
        stream.seek(0)
    except (OSError, ValueError) as exc:
        raise ValidationError("无法读取上传的 PDF 文件。") from exc
    head = stream.read(_GUIDE_PDF_HEADER_BYTES)
    if _GUIDE_PDF_MAGIC not in head:
        raise ValidationError("PDF 文件无法解析，请上传有效的 PDF 文件。")


def _open_upload(stack: ExitStack, path: Path, mime: str | None) -> GameUpload:
    """打开本地文件构造上传项，句柄交给 ExitStack 统一关闭。"""
    path = Path(path)
    handle = stack.enter_context(path.open("rb"))
    return GameUpload(filename=path.name, stream=handle, size=path.stat().st_size, mime=mime)
