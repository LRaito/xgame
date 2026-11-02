"""从源图生成快捷方式用的图标 `xgame.ico`。

**源图是 `xgame.png`（就在本目录，随仓库提交的静态资源）。换图标 = 替换那张 PNG，
然后重跑这个脚本**：

    python3 packaging/windows/make_icon.py       # 需要 Pillow，只在打包机上用，不进包

为什么要有这一步：Windows 的快捷方式只认 `.ico` / `.exe` / `.dll` 里的图标，不认 PNG；
而 `.ico` 里要塞 16 / 32 / 48 / 256 好几种尺寸（任务栏、桌面、大图标视图各取一张）。
所以 `.ico` 是提交进仓库的产物、不需要每次构建都算——改了源图再跑一次这个脚本就行。
（打包脚本会在源图比 .ico 新的时候提醒你跑。）
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "xgame.png"
OUT = HERE / "xgame.ico"

# 任务栏 16、桌面 32/48、大图标视图 256……都塞进去，让 Windows 自己挑
SIZES = (16, 24, 32, 48, 64, 128, 256)
# 源图至少这么大，256 那一档才不会糊
RECOMMENDED = 256


def load_square(path: Path) -> Image.Image:
    """读源图并保证是正方形（图标必须是方的，非方形就居中裁）。"""
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    if width != height:
        side = min(width, height)
        left, top = (width - side) // 2, (height - side) // 2
        image = image.crop((left, top, left + side, top + side))
        print(f"源图不是正方形（{width}×{height}），已居中裁成 {side}×{side}。")
    return image


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(
            f"找不到源图：{SOURCE}\n放一张正方形 PNG 到那里（换图标就是替换它），再跑一次。"
        )

    image = load_square(SOURCE)
    if image.width < RECOMMENDED:
        print(
            f"提示：源图只有 {image.width}×{image.width}，日常够用，"
            f"但大图标（{RECOMMENDED}）会有点糊；有更大的图更好。"
        )

    # 自己先缩好再交给 Pillow，避免它用最近邻插值生成小尺寸（那样 16×16 会很难看）
    largest = image.resize((max(SIZES), max(SIZES)), Image.LANCZOS)
    largest.save(OUT, format="ICO", sizes=[(size, size) for size in SIZES])
    print(f"已生成 {OUT}（{OUT.stat().st_size} 字节，含 {len(SIZES)} 种尺寸）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
