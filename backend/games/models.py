from datetime import datetime, timezone

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


# 游戏名上限：与 Windows 单层文件名上限、百度网盘的文件名上限一致（都是 255 个字符）
GAME_NAME_MAX_LENGTH = 255

# 卡带ID：全局唯一、只允许数字/字母/中划线/下划线（落库前统一转大写）。
# 它同时是磁盘上的目录名，所以字符集刻意为文件系统安全的那一档。
CARTRIDGE_ID_PATTERN = r"^[0-9A-Z_-]+$"
CARTRIDGE_ID_MAX_LENGTH = 64

# 游戏描述上限：一句话介绍就够，前端输入框同样按这个数限长
DESCRIPTION_MAX_LENGTH = 200

# 截图描述上限：图片栏里就显示在缩略图下方，只够一行短句
SCREENSHOT_DESCRIPTION_MAX_LENGTH = 15

# 图集描述上限：与截图描述同一档，都是缩略图下方那一行短句
GALLERY_DESCRIPTION_MAX_LENGTH = 15

# 游戏进度取值（只由用户手动设置，不会因游玩自动变更）
PROGRESS_NOT_STARTED = "not_started"
PROGRESS_IN_PROGRESS = "in_progress"
PROGRESS_COMPLETED = "completed"

# 封面类型：这盘游戏的封面被「美化」成了哪种外观（值就是封面样式 id，见
# frontend/src/constants/coverStyles.js 的 CART_STYLES / STYLE_META）。
# **可空**——空 = 没有封面类型：新建（手动上传/网络上传/搬运）一律留空，
# 只有编辑弹框里手动选、或「美化封面」时自动写入，才会落值。
# id 集合与顺序必须与前端镜像 coverStyles.js 的 STYLE_BY_GAME_TYPE 逐字一致
# （后端是权威来源，接口只认这里的取值）。
COVER_TYPES_BY_GAME_TYPE = {
    "flash": ("flash",),
    "gb": ("gb", "gbc"),
    "gba": ("gba",),
    "nes": ("fc", "nes"),
}
# 只用于中文报错文案；与前端 STYLE_META 里各样式的 label 同义
COVER_TYPE_LABELS = {
    "flash": "DISK",
    "gb": "GB",
    "gbc": "GBC",
    "gba": "GBA",
    "fc": "FC",
    "nes": "NES",
}


def cover_types_for(game_type: str) -> tuple[str, ...]:
    """该游戏类型可选的封面类型；不支持美化封面的类型返回空元组（它永远没有封面类型）。"""
    return COVER_TYPES_BY_GAME_TYPE.get(game_type, ())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Game(SQLModel, table=True):
    """一个游戏条目。同类下名称唯一、卡带ID 全局唯一；game_type 创建后不可变。

    ``crc32`` 是当前本体的摘要（换同类型本体时重算，不再作为锁定凭据）。
    卡带ID 在创建时定下，普通编辑改不动，只能走显式改名接口；它既是磁盘目录名，
    也是「同一盘卡带」的身份标识。``game_path`` / ``cover_path`` 存的是
    相对 `STORAGE_ROOT` 的路径。
    """

    __tablename__ = "games"
    __table_args__ = (
        Index("uq_games_game_type_name", "game_type", "name", unique=True),
        Index("uq_games_cartridge_id", "cartridge_id", unique=True),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=GAME_NAME_MAX_LENGTH, index=True)
    cartridge_id: str = Field(max_length=CARTRIDGE_ID_MAX_LENGTH)
    cover_type: str | None = Field(default=None, max_length=20)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    game_type: str = Field(max_length=50, index=True)
    size: int = Field(default=0)
    crc32: str = Field(default="", max_length=8)  # 本体内容摘要（8 位大写十六进制）；空 = 尚未算出
    game_path: str = Field(default="", max_length=500)
    cover_path: str | None = Field(default=None, max_length=500)
    # 攻略形态："" = 没有 / "zip"（静态站包）/ "pdf"。随上传、删除维护。
    guide_kind: str = Field(
        default="",
        max_length=10,
        sa_column_kwargs={"server_default": ""},
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class GameCloudSnapshot(SQLModel, table=True):
    """一个云端存档 = 某(用户,游戏)此刻全部本地 .sol 的整体快照。"""

    __tablename__ = "game_cloud_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    game_id: int = Field(index=True)
    # None = 顶层；非空时必须是同一 (user_id, game_id) 下的另一条快照。
    # 不加物理外键：SQLite 未开 PRAGMA foreign_keys，且老库靠 ALTER 补列，
    # 加 FK 会让新旧库结构不一致；父子完整性由 service 保证。
    parent_id: int | None = Field(default=None, index=True)
    remark: str = Field(default="", max_length=100)  # 描述上限 100 字
    created_at: datetime = Field(default_factory=_utcnow)


class GameCloudSnapshotFile(SQLModel, table=True):
    """云端快照内的单个 .sol 文件：记录还原时写回浏览器用的原始 localStorage key。"""

    __tablename__ = "game_cloud_snapshot_files"

    id: int | None = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="game_cloud_snapshots.id", index=True)
    sort_order: int = Field(default=0)
    local_key: str = Field(max_length=500)
    name: str = Field(default="", max_length=255)
    size: int = Field(default=0)
    mime: str | None = Field(default=None, max_length=200)
    file_path: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=_utcnow)


class GameScreenshot(SQLModel, table=True):
    """游戏截图：游戏播放页里截下的画面，按(用户, 游戏)隔离，只本人可见。

    展示顺序用**分数排序**：sort_order 是浮点分数，新截图追加到末尾（最大分 +
    步长），拖动重排只改被拖动那一行的分数（取相邻两分数的中值），**间隙不足时**
    才由 service 把整份重排一遍。因此不加 (user_id, game_id, sort_order) 唯一约束
    （分数允许相等/相邻，唯一约束只会碍事）。字节落在 image/{用户名}/… 下，
    file_path 存相对路径。
    """

    __tablename__ = "game_screenshots"
    __table_args__ = (
        Index("ix_game_screenshots_user_game_order", "user_id", "game_id", "sort_order"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    game_id: int = Field(index=True)  # 仅索引、无 FK：删游戏的清理由 GameService 手写
    sort_order: float = Field(default=0.0)  # 展示分数，越小越靠前（见类注释）
    description: str = Field(default="", max_length=SCREENSHOT_DESCRIPTION_MAX_LENGTH)
    file_path: str = Field(default="", max_length=500)
    size: int = Field(default=0)
    mime: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=_utcnow)


class GameGalleryImage(SQLModel, table=True):
    """游戏图集：一个游戏一套的展示图片（宣传图、说明书扫描件之类）。

    与截图相反，图集**按游戏共享**——不记上传者，任何登录用户都能看、能改。
    排序与截图同一套分数机制（sort_order 是浮点分数，见 GameScreenshot 的说明），
    所以同样不加 (game_id, sort_order) 唯一约束。字节落在
    game/{类型}/{卡带ID}/image/ 下（**游戏目录内**，类型创建后不可变），
    file_path 存相对路径。
    """

    __tablename__ = "game_gallery_images"
    __table_args__ = (
        Index("ix_game_gallery_images_game_order", "game_id", "sort_order"),
    )

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(index=True)  # 仅索引、无 FK：删游戏的清理由 GameService 手写
    sort_order: float = Field(default=0.0)  # 展示分数，越小越靠前
    description: str = Field(default="", max_length=GALLERY_DESCRIPTION_MAX_LENGTH)
    file_path: str = Field(default="", max_length=500)
    size: int = Field(default=0)
    mime: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=_utcnow)


class GameRecentPlay(SQLModel, table=True):
    """最近游玩：每个(用户, 游戏)只留一行，记录最后一次开玩时间。

    唯一约束保证重玩只刷新时间：行数天然不超过游戏总数，无需裁剪或分页。
    """

    __tablename__ = "game_recent_plays"
    __table_args__ = (UniqueConstraint("user_id", "game_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    game_id: int = Field(index=True)  # 仅索引、无 FK：删游戏的清理由 GameService 手写
    played_at: datetime = Field(default_factory=_utcnow)


class GameEmulatorSettings(SQLModel, table=True):
    """模拟器（EmulatorJS）设置：按(用户, 平台)一份，整块覆盖保存。

    payload 即引擎写在浏览器 localStorage 里那个值的 JSON 文本
    （`{controlSettings, settings, cheats}`），原样存取、不解释内容，
    进游戏前由前端写回 localStorage 交给引擎读取。
    """

    __tablename__ = "game_emulator_settings"
    __table_args__ = (UniqueConstraint("user_id", "game_type"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    game_type: str = Field(max_length=50)
    payload: str = Field(default="")
    updated_at: datetime = Field(default_factory=_utcnow)


class GameUserStat(SQLModel, table=True):
    """游玩统计：每个(用户, 游戏)只留一行——累计时长与进度。

    与游戏类型无关，任何一端播放都往同一张表累加。play_seconds 由播放页
    心跳累加（可手动改写为新基数），progress 只由用户手动设置，两者互不影响。
    """

    __tablename__ = "game_user_stats"
    __table_args__ = (UniqueConstraint("user_id", "game_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    game_id: int = Field(index=True)  # 仅索引、无 FK：删游戏的清理由 GameService 手写
    play_seconds: int = Field(default=0)  # 累计游玩秒数
    progress: str = Field(default=PROGRESS_NOT_STARTED, max_length=20)
    updated_at: datetime = Field(default_factory=_utcnow)
