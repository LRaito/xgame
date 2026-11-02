"""把卡带成品图里印着封面的贴纸窗整块清掉，补上机身色，输出一张「还没贴过贴纸的原始卡带」。

难点：
  * 贴纸窗不能靠某个具体颜色分出来 —— 贴纸的白边亮、图案有深有浅、卡带机身是灰的，
    三种东西互相交错，所以判据只能是「够亮 **或** 有彩色」，不能是「等于某个色」；
  * 贴纸边上还有 1~2px 的抗锯齿与阴影过渡带，填得正正好会在补色块边上留一圈细边，
    所以检测出来的窗口要往外让开 --pad 像素再填；
  * 贴纸四角是圆的，填的时候也得按圆角填，否则圆角外那圈机身会被方块啃掉一块；
  * 补什么颜色：默认取窗外那圈**机身色**（见 body_color）。窗外不是机身时（比如透明壳的
    GBC 卡带，窗外看到的深绿其实是下层电路板透出来的）必须用 --color 手工指定。

做法（旋钮就是下面那几个常量，改脚本前先读同目录 SKILL.md）：
  1. 用饱和度找出贴纸上的彩色图案，取它的 bbox 当种子框；
  2. 从种子框中段那几行向左右扫「还算不算贴纸」，走到机身灰为止 —— 得到窗口左右边；
  3. 在左边栏内部那几列上向上下扫，同样走到机身灰为止 —— 得到窗口上下边
     （白色分界栏是通高的，拿它的列比拿图案的行稳）。
     往外走的判据要看远一点（见 walk_out）：白边上的黑字、贴纸边的阴影都是窄条，
     一碰到就停会把窗口边留在半路；
  4. 四条边各取中位数，再各往外扩 --pad，按 --radius 圆角矩形把这块**填成机身色**；
  5. 打印四条边各自的一致性：某条边「范围」大，就是那一步被图案带偏了。

用法见同目录 SKILL.md；本文件依赖 Pillow（`pip install Pillow`，不在项目 requirements 里）。
"""
import argparse
import os
import statistics
import sys

from PIL import Image, ImageDraw

# 判据的调参都在这里：换一张卡带图先动这几个数
SAT = 60        # HSV 饱和度阈值（0-255）：贴纸的彩色图案够得着，机身灰与白边够不着
SEED_MIN = 5    # 种子框判据：这一行/列至少要有这么多彩色像素才算「有图案」
BRIGHT = 200    # 亮度阈值（0-255）：贴纸白边（亮）与卡带机身（暗）的分界
EDGE_TOL = 3    # 四条边各自的范围超过它就在报告里标一下（说明检测被图案带偏了）
SAMPLE = 0.25   # 左右边取样让开种子框上下各四分之一，避开图案自己的圆角
PAD = 2         # 检测出的窗口向外扩这么多像素再填（贴纸自己的过渡边要一起清掉）
RADIUS = 8      # 洞口圆角半径（像素）
PROBE_STEPS = (8, 14, 20)  # 取机身色时往窗外让开的距离；太近会踩到贴纸凹槽那圈阴影
PROBE_SIDE = 3  # 每条边在几个位置上取样（四分之一、一半、四分之三处）
OPAQUE = 200    # 取样只认 alpha 高于它的像素（窗外可能是卡带自己的透明缺口）
CHECK_CELL = 16  # --check 那张图里棋盘格的格子边长
LOOKAHEAD = 12  # 往外走时允许跳过的暗色窄条上限（白边上的黑字、贴纸边的阴影）
MAX_GAP = 80    # 从种子框往外最多走这么远，防止判据失灵时一路啃进机身


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="把卡带图里贴纸窗那一整块扣成透明，输出一张没有封面的「无色底图」",
    )
    parser.add_argument("src", help="源图片路径（png/jpg/webp 等 Pillow 能读的格式）")
    parser.add_argument(
        "-o", "--out-dir",
        default=None,
        help="输出目录，默认与源图同目录",
    )
    parser.add_argument(
        "--rect",
        default=None,
        help="手工指定要扣的矩形 x,y,w,h（源图坐标，含左上不含右下），不给就自动检测",
    )
    parser.add_argument(
        "--radius", default=str(RADIUS),
        help="洞口圆角半径，默认 %d；也可以写成 tl,tr,br,bl 按角给"
             "（洞口顶到画布上边时上面两角要给 0）" % RADIUS,
    )
    parser.add_argument(
        "--pad", type=int, default=PAD,
        help="自动检测出的窗口向外扩多少像素，默认 %d（--rect 时不用它）" % PAD,
    )
    parser.add_argument(
        "--color",
        default=None,
        help='补色，写成 R,G,B，不给就自动取窗外那圈机身色（窗外不是机身时必须给）',
    )
    parser.add_argument(
        "--check", action="store_true",
        help="额外出一张棋盘底合成图，并在上面描出窗口矩形，用来肉眼验洞口",
    )
    return parser.parse_args(argv)


def parse_color(text):
    """解析 --color 的 R,G,B。"""
    try:
        parts = [int(v) for v in text.replace(" ", "").split(",")]
    except ValueError:
        sys.exit("--color 要写成 R,G,B 三个 0-255 的整数，收到的是 %r" % text)
    if len(parts) != 3 or not all(0 <= v <= 255 for v in parts):
        sys.exit("--color 要写成 R,G,B 三个 0-255 的整数，收到的是 %r" % text)
    return tuple(parts)


def parse_radius(text):
    """--radius：一个整数 = 四角相同；`tl,tr,br,bl` 四个整数 = 按角给。

    按角给是给「洞口顶到画布上边」那种素材用的（源图顶部被裁掉了，上面两角必须是直角，
    圆角会把画面顶端啃掉两块）。
    """
    parts = [v for v in text.replace(" ", "").split(",") if v != ""]
    try:
        nums = [int(v) for v in parts]
    except ValueError:
        sys.exit("--radius 要写成 1 个或 4 个整数，收到的是 %r" % text)
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 4:
        return dict(zip(("tl", "tr", "br", "bl"), nums))
    sys.exit("--radius 要写成 1 个或 4 个整数，收到的是 %r" % text)


def fmt_radius(radius):
    """把半径写回 coverStyles.js 的样子（没写的角按直角算，所以只列非零的）。"""
    if isinstance(radius, int):
        return str(radius)
    parts = ["%s: %d" % (k, radius[k]) for k in ("tl", "tr", "br", "bl") if radius.get(k)]
    return "{ %s }" % ", ".join(parts) if parts else "0"


def rounded_mask(size, rect, radius):
    """洞口那块圆角矩形的 mask（255 = 在洞口里）。

    `ImageDraw.rounded_rectangle` 的 xy 与 rectangle 一样**含右下端点**（别学 numpy 的
    写法去 +1，那会多填一列一行，成品洞口就比报告里说的大 1px）。按角给半径时它只吃
    一个统一值，所以四角各挖一次再用扇形补回来。
    """
    x0, y0, x1, y1 = rect
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if isinstance(radius, int):
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=255)
        return mask

    draw.rectangle((x0, y0, x1, y1), fill=255)
    # PIL 的角度：0 在三点钟方向、顺时针增大（y 轴朝下），所以四个象限就是
    # 右下 0-90、左下 90-180、左上 180-270、右上 270-360
    for corner, (cx, cy, angles) in {
        "tl": (x0, y0, (180, 270)),
        "tr": (x1, y0, (270, 360)),
        "br": (x1, y1, (0, 90)),
        "bl": (x0, y1, (90, 180)),
    }.items():
        r = radius.get(corner, 0)
        if r <= 0:
            continue
        # 先把这个角整个 r×r 的方块挖掉，再把圆心落在 (角内 r, r) 处的四分之一圆补回来
        sx = 1 if corner in ("tl", "bl") else -1
        sy = 1 if corner in ("tl", "tr") else -1
        draw.rectangle(
            (min(cx, cx + sx * (r - 1)), min(cy, cy + sy * (r - 1)),
             max(cx, cx + sx * (r - 1)), max(cy, cy + sy * (r - 1))),
            fill=0,
        )
        mx, my = cx + sx * r, cy + sy * r
        draw.pieslice((mx - r, my - r, mx + r, my + r), angles[0], angles[1], fill=255)
    return mask


def load(src):
    try:
        im = Image.open(src)
    except OSError as exc:
        sys.exit("读不出源图 %s：%s" % (src, exc))
    return im.convert("RGBA")


def walk_out(is_label, start, step, limit):
    """从一个「还算贴纸」的位置出发，沿 step 方向往外走，返回最后一个贴纸位置。

    判据不是「下一个像素是不是贴纸」：白边上的黑色文字、贴纸边上的阴影都只有几像素宽，
    一碰到就停会把窗口边留在半路（这张图的右栏竖排警告语就横跨了整个窗口高度）。
    所以要看远一点：**往后 LOOKAHEAD 个像素里一个贴纸像素都没有**，才算真的走出去了。
    宁可多啃几像素机身（看不出来），也不能把贴纸留在底图上（一眼就看出来）。
    """
    pos = start
    while abs(pos - start) < MAX_GAP:
        nxt = pos + step
        if not 0 <= nxt <= limit:
            return pos
        if not is_label(nxt):
            ahead = range(nxt + step, nxt + step * (LOOKAHEAD + 1), step)
            if not any(is_label(p) for p in ahead if 0 <= p <= limit):
                return pos
        pos = nxt
    return pos


def detect_rect(im, pad):
    """自动找贴纸窗。返回含两端的 (x0, y0, x1, y1)。"""
    w, h = im.size
    sat = im.convert("HSV").getchannel("S").load()
    lum = im.convert("L").load()
    alpha = im.getchannel("A").load()

    def is_label(x, y):
        # 「够亮或有彩色」= 还是贴纸；机身灰两头都不占。
        # 透明像素（卡带自己的缺口）也一律不算贴纸
        return alpha[x, y] > 128 and (lum[x, y] > BRIGHT or sat[x, y] > SAT)

    cols = [x for x in range(w) if sum(1 for y in range(h) if sat[x, y] > SAT) >= SEED_MIN]
    rows = [y for y in range(h) if sum(1 for x in range(w) if sat[x, y] > SAT) >= SEED_MIN]
    if not cols or not rows:
        sys.exit(
            "找不到彩色贴纸图案（这张图的贴纸可能是灰度的），"
            "请用 --rect x,y,w,h 手工指定窗口"
        )
    sx0, sx1, sy0, sy1 = cols[0], cols[-1], rows[0], rows[-1]
    print("贴纸图案 bbox：x %d..%d  y %d..%d" % (sx0, sx1, sy0, sy1))

    # 左右边：种子框中段那几行，各自从图案边界往外走，走到机身灰为止
    margin = int(round((sy1 - sy0) * SAMPLE))
    lefts, rights = [], []
    for y in range(sy0 + margin, sy1 - margin + 1):
        lefts.append(walk_out(lambda x, y=y: is_label(x, y), sx0, -1, w - 1))
        rights.append(walk_out(lambda x, y=y: is_label(x, y), sx1, 1, w - 1))

    # 上下边：左边栏内部那几列，各自从图案边界往外走（白边通高，用它的列最稳）
    bar_w = sx0 - min(lefts)
    tops, bottoms = [], []
    for k in (1, 2, 3):
        x = min(lefts) + max(1, bar_w * k // 4)
        tops.append(walk_out(lambda y, x=x: is_label(x, y), sy0, -1, h - 1))
        bottoms.append(walk_out(lambda y, x=x: is_label(x, y), sy1, 1, h - 1))

    for name, values in (("左", lefts), ("右", rights), ("上", tops), ("下", bottoms)):
        lo, hi = min(values), max(values)
        flag = "  ← 不平，检测可能被图案带偏了" if hi - lo > EDGE_TOL else ""
        print(
            "贴纸窗%s边：%d（范围 %d..%d，%d 条扫描线）%s"
            % (name, int(statistics.median(values)), lo, hi, len(values), flag)
        )

    x0 = max(0, int(statistics.median(lefts)) - pad)
    x1 = min(w - 1, int(statistics.median(rights)) + pad)
    y0 = max(0, int(statistics.median(tops)) - pad)
    y1 = min(h - 1, int(statistics.median(bottoms)) + pad)
    return x0, y0, x1, y1


def body_color(im, rect):
    """取窗口外那圈机身像素的中位数，当补色用。

    取样点要**让开一段距离**（PROBE_STEPS）：紧贴窗口的那几像素是贴纸自己的抗锯齿边与
    凹槽阴影，取到它补出来就是一圈暗边。窗外可能是卡带自己的透明缺口，所以只认不透明像素。
    """
    x0, y0, x1, y1 = rect
    w, h = im.size
    px = im.load()
    samples = []
    for d in PROBE_STEPS:
        for k in (1, 2, 3):
            # 左右两条边各取 3 个高度，上下两条边各取 3 个横向位置
            ys = y0 + (y1 - y0) * k // (PROBE_SIDE + 1)
            xs = x0 + (x1 - x0) * k // (PROBE_SIDE + 1)
            for x, y in ((x0 - d, ys), (x1 + d, ys), (xs, y0 - d), (xs, y1 + d)):
                if 0 <= x < w and 0 <= y < h and px[x, y][3] > OPAQUE:
                    samples.append(px[x, y][:3])
    if not samples:
        sys.exit("窗外取不到不透明像素，请用 --color R,G,B 手工指定补色")
    return tuple(int(statistics.median([s[i] for s in samples])) for i in range(3))


def fill_window(im, rect, radius, color):
    """把 rect 那块按圆角填成 color（不透明），返回新图（原图不动）。

    只动圆角矩形以内：圆角之外那圈机身像素、卡带轮廓、缺口透明一律原样保留。
    """
    mask = rounded_mask(im.size, rect, radius)
    out = im.copy()
    out.paste(Image.new("RGBA", im.size, tuple(color) + (255,)), (0, 0), mask)
    return out


def checkerboard(size, cell=CHECK_CELL):
    board = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(board)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(226, 232, 240))
    return board


def main(argv=None):
    args = parse_args(argv)
    im = load(args.src)
    w, h = im.size

    if args.rect:
        try:
            rx, ry, rw, rh = (int(v) for v in args.rect.replace(" ", "").split(","))
        except ValueError:
            sys.exit("--rect 要写成 x,y,w,h 四个整数，收到的是 %r" % args.rect)
        rect = (rx, ry, rx + rw - 1, ry + rh - 1)
        print("手工指定窗口：x %d..%d  y %d..%d" % rect)
    else:
        rect = detect_rect(im, args.pad)

    radius = parse_radius(args.radius)
    x0, y0, x1, y1 = rect
    hole_w, hole_h = x1 - x0 + 1, y1 - y0 + 1
    color = parse_color(args.color) if args.color else body_color(im, rect)
    print(
        "补色的矩形：(x %d, y %d, %d × %d)  圆角 %s"
        % (x0, y0, hole_w, hole_h, fmt_radius(radius))
    )
    print("补色：rgb%s%s" % (color, "" if args.color else "（自动取的窗外机身色）"))
    # 这一行就是美化封面 constants/coverStyles.js 里要填的那几个数
    print(
        "底图几何：image { width: %d, height: %d }, hole { x: %d, y: %d, width: %d, height: %d }, "
        "radius: %s" % (w, h, x0, y0, hole_w, hole_h, fmt_radius(radius))
    )
    if hole_w < 8 or hole_h < 8:
        print("警告：洞口只有 %d × %d，小得不像贴纸窗，八成检测错了" % (hole_w, hole_h))

    out = fill_window(im, rect, radius, color)
    stem = os.path.splitext(os.path.basename(args.src))[0]
    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.src))
    dst = os.path.join(out_dir, stem + "_blank.png")
    out.save(dst)
    print("已写出 %s" % dst)

    if args.check:
        check = os.path.join(out_dir, stem + "_blank_check.png")
        board = checkerboard(out.size)
        board.paste(out, (0, 0), out)
        # 补色之后洞口不再是透明区，棋盘底上看不出它在哪，所以把窗口矩形描出来：
        # 描边要正好压在贴纸窗边上，偏了就是检测不准（补色块里剩的贴纸像素也能一眼看到）
        ImageDraw.Draw(board).rectangle((x0, y0, x1, y1), outline=(255, 0, 255))
        board.save(check)
        print("已写出 %s（棋盘底 + 洋红描边，肉眼验洞口用）" % check)


if __name__ == "__main__":
    main()
