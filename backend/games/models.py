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

# 卡带类型（卡带版本）：目前只有 FC NES 区分日版/美版，其余类型只有「默认」。
# 「默认」是真实值而不是空值——每个游戏始终有且只有一个卡带类型。
CARTRIDGE_TYPE_DEFAULT = "default"
CARTRIDGE_TYPE_JP = "jp"
CARTRIDGE_TYPE_US = "us"
CARTRIDGE_TYPE_LABELS = {
    CARTRIDGE_TYPE_JP: "日版",
    CARTRIDGE_TYPE_US: "美版",
    CARTRIDGE_TYPE_DEFAULT: "默认",
}
# 各游戏类型可选的卡带类型，顺序即展示顺序（前端 constants/cartridgeTypes.js 与此同步）
CARTRIDGE_TYPES_BY_GAME_TYPE = {
    "nes": (CARTRIDGE_TYPE_JP, CARTRIDGE_TYPE_US, CARTRIDGE_TYPE_DEFAULT),
}


def cartridge_types_for(game_type: str) -> tuple[str, ...]:
    """该游戏类型可选的卡带类型；没收录的类型只有「默认」。"""
    return CARTRIDGE_TYPES_BY_GAME_TYPE.get(game_type, (CARTRIDGE_TYPE_DEFAULT,))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Game(SQLModel, table=True):
    """一个游戏条目。同类下名称唯一、卡带ID 全局唯一；crc32 锁住本体（锁定后只能换回同一个文件）。

    卡带ID 在创建时定下、之后不可修改（只能删掉重建），既是磁盘目录名，
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
    cartridge_type: str = Field(default=CARTRIDGE_TYPE_DEFAULT, max_length=20)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    game_type: str = Field(max_length=50, index=True)
    size: int = Field(default=0)
    crc32: str = Field(default="", max_length=8)  # 本体内容摘要（8 位大写十六进制）；空 = 尚未算出
    game_path: str = Field(default="", max_length=500)
    cover_path: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class GameH5File(SQLModel, table=True):
    """H5 游戏解包后的单文件清单：path 为归一化后的包内相对路径。"""

    __tablename__ = "game_h5_files"
    __table_args__ = (UniqueConstraint("game_id", "path"),)

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(index=True)
    path: str = Field(max_length=512)
    file_path: str = Field(max_length=700)
    size: int = Field(default=0)
    mime: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=_utcnow)


class GameCloudSnapshot(SQLModel, table=True):
    """一个云端存档 = 某(用户,游戏)此刻全部本地 .sol 的整体快照。"""

    __tablename__ = "game_cloud_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    game_id: int = Field(index=True)
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
    game/{类型}/{卡带ID}/image/ 下（**游戏目录内**，换类型时随目录迁移），
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
