"""游戏素材与存档在项目文件根目录下的相对路径约定。

根目录即 `STORAGE_ROOT`，路径分隔符一律用 `/`，SQLite 里存的就是这些相对路径。
目录名一律用「游戏类型键 + 卡带ID」——卡带ID 创建后不可改，所以改游戏名不会
挪动任何文件，磁盘上永远是人能直接看懂、能直接拷走的普通目录：

    game/{game_type}/{卡带ID}/game.{后缀}           本体
    game/{game_type}/{卡带ID}/cover.{后缀}          封面
    game/{game_type}/{卡带ID}/h5/{包内相对路径}      H5 解包资源
    game/{game_type}/{卡带ID}/guide/{文件夹内相对路径} 攻略静态资源（入口固定 index.html）
    game/{game_type}/{卡带ID}/image/{uuid}.{后缀}   图集（全站共享，随游戏类型迁移）
    save/{用户名}/{game_type}/{卡带ID}/{uuid}.state 云端存档文件
    image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀} 游戏截图（按账号隔离；播放页截的是 .png）
"""

from backend.errors import ValidationError

GAME_DIR = "game"
SAVE_DIR = "save"
IMAGE_DIR = "image"

H5_DIR_NAME = "h5"
GUIDE_DIR_NAME = "guide"
GUIDE_ENTRY_NAME = "index.html"
# 图集目录：虽与顶层截图目录同名（都是 image），但它挂在游戏目录下、按游戏共享，
# 与 image/{用户名}/… 那套按账号隔离的截图是两回事，取值刻意复用以保持目录可读。
GALLERY_DIR_NAME = "image"
BODY_STEM = "game"
COVER_STEM = "cover"
SAVE_EXTENSION = ".state"
SCREENSHOT_EXTENSION = ".png"  # 播放页截图固定 PNG；图库里手动上传的还可能是 jpg/webp/gif


def normalize_extension(extension: str) -> str:
    """把扩展名统一成带点的小写形式（如 `.nes`）。"""
    value = (extension or "").strip().lower()
    if not value:
        raise ValidationError("缺少文件扩展名。")
    return value if value.startswith(".") else f".{value}"


def game_dir(game_type: str, cartridge_id: str) -> str:
    """一个游戏的全部素材所在目录。"""
    return f"{GAME_DIR}/{game_type}/{cartridge_id}"


def body_path(game_type: str, cartridge_id: str, extension: str) -> str:
    return f"{game_dir(game_type, cartridge_id)}/{BODY_STEM}{normalize_extension(extension)}"


def cover_path(game_type: str, cartridge_id: str, extension: str) -> str:
    return f"{game_dir(game_type, cartridge_id)}/{COVER_STEM}{normalize_extension(extension)}"


def h5_dir(game_type: str, cartridge_id: str) -> str:
    return f"{game_dir(game_type, cartridge_id)}/{H5_DIR_NAME}"


def h5_asset_path(game_type: str, cartridge_id: str, relpath: str) -> str:
    return f"{h5_dir(game_type, cartridge_id)}/{relpath}"


def h5_temp_dir(game_type: str, cartridge_id: str, token: str) -> str:
    """解包暂存目录：与最终 h5 目录同层，替换时才能用改名做到原子。"""
    return f"{game_dir(game_type, cartridge_id)}/.h5-{token}"


def guide_dir(game_type: str, cartridge_id: str) -> str:
    return f"{game_dir(game_type, cartridge_id)}/{GUIDE_DIR_NAME}"


def guide_entry_path(game_type: str, cartridge_id: str) -> str:
    """攻略入口文件：它存在就算这个游戏有攻略。"""
    return f"{guide_dir(game_type, cartridge_id)}/{GUIDE_ENTRY_NAME}"


def guide_asset_path(game_type: str, cartridge_id: str, relpath: str) -> str:
    return f"{guide_dir(game_type, cartridge_id)}/{relpath}"


def guide_temp_dir(game_type: str, cartridge_id: str, token: str) -> str:
    """攻略上传暂存目录：与最终 guide 目录同层，替换时才能用改名做到原子。"""
    return f"{game_dir(game_type, cartridge_id)}/.guide-{token}"


def gallery_dir(game_type: str, cartridge_id: str) -> str:
    return f"{game_dir(game_type, cartridge_id)}/{GALLERY_DIR_NAME}"


def gallery_file_path(
    game_type: str, cartridge_id: str, token: str, extension: str
) -> str:
    return (
        f"{gallery_dir(game_type, cartridge_id)}"
        f"/{token}{normalize_extension(extension)}"
    )


def save_dir(username: str, game_type: str, cartridge_id: str) -> str:
    return f"{SAVE_DIR}/{username}/{game_type}/{cartridge_id}"


def save_file_path(username: str, game_type: str, cartridge_id: str, token: str) -> str:
    return f"{save_dir(username, game_type, cartridge_id)}/{token}{SAVE_EXTENSION}"


def screenshot_dir(username: str, game_type: str, cartridge_id: str) -> str:
    return f"{IMAGE_DIR}/{username}/{game_type}/{cartridge_id}"


def screenshot_file_path(
    username: str, game_type: str, cartridge_id: str, token: str, extension: str
) -> str:
    return (
        f"{screenshot_dir(username, game_type, cartridge_id)}"
        f"/{token}{normalize_extension(extension)}"
    )
