"""游戏素材与存档在两个文件根目录下的相对路径约定。

路径分隔符一律用 `/`，SQLite 里存的就是这些相对路径。目录名一律用「游戏类型键 + 卡带ID」
——卡带ID 创建后不可改，所以改游戏名不会挪动任何文件，磁盘上永远是人能直接看懂、
能直接拷走的普通目录。

**两个根**（不配 `RUNTIME_ROOT` 时它们是同一个目录，也就是同一棵树）：

数据根（`STORAGE_ROOT`）——会被整体拷走交给外部备份的那一份，只放「原始素材」：

    game/{game_type}/{卡带ID}/game.{后缀}           本体（H5 就是 game.zip）
    game/{game_type}/{卡带ID}/cover.{后缀}          封面
    game/{game_type}/{卡带ID}/guide.zip             攻略包（原始 zip，与 guide.pdf 二选一）
    game/{game_type}/{卡带ID}/guide.pdf             攻略 PDF（与 guide.zip 二选一）
    game/{game_type}/{卡带ID}/image/{uuid}.{后缀}   图集（全站共享，随游戏类型迁移）
    save/{用户名}/{game_type}/{卡带ID}/{uuid}.state 云端存档文件
    image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀} 游戏截图（按账号隔离；播放页截的是 .png）

运行时根（`RUNTIME_ROOT`）——SQLite 库与**解包产物**，全是派生物，删了会自动重建：

    db/app.db                                       SQLite 库
    game/{game_type}/{卡带ID}/h5/{包内相对路径}      H5 解包资源
    game/{game_type}/{卡带ID}/guide/{包内相对路径}   攻略解包资源（入口固定 index.html）
    game/{game_type}/{卡带ID}/.{h5,guide}-{随机}     解包暂存目录（与最终目录同层，靠改名做到原子）

两个根下的相对路径**逐字一致**，只是拼的根不同——所以下面这些路径函数对两个根都适用，
调用方自己决定交给哪个 `LocalStorage`。
"""

from backend.errors import ValidationError

GAME_DIR = "game"
SAVE_DIR = "save"
IMAGE_DIR = "image"

H5_DIR_NAME = "h5"
GUIDE_DIR_NAME = "guide"
# 两个包的入口都固定叫 index.html（见 backend/games/archive.py 的 ENTRY_NAME）
ENTRY_NAME = "index.html"
# 图集目录：虽与顶层截图目录同名（都是 image），但它挂在游戏目录下、按游戏共享，
# 与 image/{用户名}/… 那套按账号隔离的截图是两回事，取值刻意复用以保持目录可读。
GALLERY_DIR_NAME = "image"
BODY_STEM = "game"
COVER_STEM = "cover"
# 攻略包与解包目录同名不同后缀（guide.zip | guide.pdf / guide/），一眼能对上
GUIDE_STEM = "guide"
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
    """H5 解包产物的目录（运行时根下）。"""
    return f"{game_dir(game_type, cartridge_id)}/{H5_DIR_NAME}"


def h5_zip_path(game_type: str, cartridge_id: str) -> str:
    """H5 游戏的本体：原始 zip（数据根下，就是 games.game_path）。"""
    return f"{game_dir(game_type, cartridge_id)}/{BODY_STEM}.zip"


def h5_asset_path(game_type: str, cartridge_id: str, relpath: str) -> str:
    return f"{h5_dir(game_type, cartridge_id)}/{relpath}"


def h5_entry_path(game_type: str, cartridge_id: str) -> str:
    """H5 入口文件；它存在就说明这个游戏已经解包过了。"""
    return f"{h5_dir(game_type, cartridge_id)}/{ENTRY_NAME}"


def h5_temp_dir(game_type: str, cartridge_id: str, token: str) -> str:
    """解包暂存目录：与最终 h5 目录同层，替换时才能用改名做到原子。"""
    return f"{game_dir(game_type, cartridge_id)}/.h5-{token}"


def guide_dir(game_type: str, cartridge_id: str) -> str:
    """攻略解包产物的目录（运行时根下）。"""
    return f"{game_dir(game_type, cartridge_id)}/{GUIDE_DIR_NAME}"


def guide_zip_path(game_type: str, cartridge_id: str) -> str:
    """攻略包：原始 zip（数据根下）；它与 guide.pdf 任一存在就算有攻略。"""
    return f"{game_dir(game_type, cartridge_id)}/{GUIDE_STEM}.zip"


def guide_pdf_path(game_type: str, cartridge_id: str) -> str:
    """攻略 PDF（数据根下）；与 guide.zip 二选一，PDF 不解包。"""
    return f"{game_dir(game_type, cartridge_id)}/{GUIDE_STEM}.pdf"


def guide_entry_path(game_type: str, cartridge_id: str) -> str:
    """攻略入口文件；它存在就说明这个游戏已经解包过了。"""
    return f"{guide_dir(game_type, cartridge_id)}/{ENTRY_NAME}"


def guide_asset_path(game_type: str, cartridge_id: str, relpath: str) -> str:
    return f"{guide_dir(game_type, cartridge_id)}/{relpath}"


def guide_temp_dir(game_type: str, cartridge_id: str, token: str) -> str:
    """攻略解包暂存目录：与最终 guide 目录同层，替换时才能用改名做到原子。"""
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
