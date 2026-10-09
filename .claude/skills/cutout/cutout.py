"""把不规整的长方形封面从深色背景里抠出来，输出透明底 PNG（保留原有倾斜角度）。

难点：
  * 封面图案里深色的部分颜色和照片背景几乎一样，靠颜色分不开；
  * 照片边缘的过渡像素是"暗背景 + 封面"的混合色，直接当不透明会留一圈黑边。

做法：
  1. 逐行/逐列从外往内扫，找第一个"碰到封面本体"的位置：参考色是这条扫描线最外侧
     几个像素的中位数再沿这条边平滑（跟得住背景自身的明暗渐变），判据是窗口内
     "与参考色的通道差"的中位数 —— 不用先知道背景是什么颜色，暗色封面压在同样暗的
     背景上也分得开；封面顶到画面边缘的扫描线按 0 留白算，不切封面；
  2. 四条边各自的采样点用 RANSAC 拟合（乱点可能比真边上的点还多），定出四条直线边，
     四条边以外的像素一律透明 —— 封面图案里与背景同色的暗部因此漏不出去；
  3. 边缘带内按"亮度反推覆盖率"当作 alpha，并把颜色换成内侧封面本色，消掉那圈黑边。

用法见同目录 SKILL.md；本文件依赖 Pillow（`pip install Pillow`，不在项目 requirements 里）。
"""
import argparse
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# 判据与几何的调参都在这里：换一张背景明暗不同的照片时先动这几个数
REF_PX = 4    # 边缘"背景参考色"取最外侧这么多像素的中位数
SMOOTH_W = 21   # 背景参考色沿这条边做中位数平滑的半宽（扫描线数），用来吃背景本身的明暗渐变
TOL = 7       # 窗口内"与参考色的通道差"中位数超过它，就认为碰到封面本体了
WIN = 9       # 判据用的窗口宽度（像素）：单像素噪声判不动，暗封面压在暗背景上也认得出来
BG_TOL = 12   # 扫描线自己的参考色偏离平滑参考色这么多 = 封面顶到画面边缘了，按 0 留白算
BG_HARD = 30  # 平滑参考色本身都偏离全画面背景色这么多 = 一整片都是封面，同样按 0 留白算
LIMIT = 200   # 从图像边缘往内最多找这么多像素，背景留白比它宽就会找不到边


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="去除封面图四周的杂色/黑边，输出透明底 PNG（并裁掉四周多余留白）",
    )
    parser.add_argument("src", help="源图片路径（jpg/png/webp 等 Pillow 能读的格式）")
    parser.add_argument(
        "-o", "--out-dir",
        default=None,
        help="输出目录，默认与源图同目录",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="额外在品红/白底上各出一张缩略检查图，外加一张画出四条切边的图，用来肉眼验边",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        im = Image.open(args.src).convert("RGB")
    except OSError as exc:
        sys.exit("读不出源图 %s：%s" % (args.src, exc))

    W, H = im.size
    data = im.tobytes()
    sm = im.filter(ImageFilter.BoxBlur(1)).tobytes()   # 平滑一下，免得被 JPEG 噪点带跑

    # ---------- 1) 从外侧定位四条边 ----------

    # 全画面背景色：边框一圈像素的逐通道中位数。背景比封面大得多，中位数不会被
    # "封面顶到画面边缘"的那几段带跑；再来一轮只留贴合它的像素，估计更稳。
    ring = []
    for x in range(W):
        for y in (0, 1, H - 2, H - 1):
            j = 3 * (y * W + x)
            ring.append((data[j], data[j + 1], data[j + 2]))
    for y in range(H):
        for x in (0, 1, W - 2, W - 1):
            j = 3 * (y * W + x)
            ring.append((data[j], data[j + 1], data[j + 2]))

    def ring_median(pxs):
        return [sorted(p[c] for p in pxs)[len(pxs) // 2] for c in range(3)]

    bg_ref = ring_median(ring)
    close = [p for p in ring if max(abs(p[c] - bg_ref[c]) for c in range(3)) <= 30]
    if len(close) >= len(ring) // 2:
        bg_ref = ring_median(close)
    print('全画面背景色 rgb=%s（边框 %d 像素里 %d 个贴合）' % (tuple(bg_ref), len(ring), len(close)))

    def scanlines(side):
        """这条边上的扫描线：[(沿边坐标, 关键函数)]，关键函数把"从边缘数第 t 个像素"映射成 data 下标。"""
        if side == "top":
            return [(x, lambda t, x=x: t * W + x) for x in range(4, W - 4, 3)]
        if side == "bottom":
            return [(x, lambda t, x=x: (H - 1 - t) * W + x) for x in range(4, W - 4, 3)]
        if side == "left":
            return [(y, lambda t, y=y: y * W + t) for y in range(50, H - 50, 3)]
        return [(y, lambda t, y=y: y * W + W - 1 - t) for y in range(50, H - 50, 3)]

    def edge_points(side):
        """从外往内逐条扫描线找"第一个持续偏离背景色的位置"，返回该边的采样点。

        参考色不写死成"深色偏冷"之类：先取这条扫描线最外侧 REF_PX 个像素的中位数，
        再沿这条边做中位数平滑 —— 背景本身的明暗渐变跟得住，暗色封面压在暗背景上
        也照样分得开。外侧已经不是背景色（封面顶到画面边缘）的扫描线按 0 留白算，
        它们同样进拟合：那一段本来就该切在画面边缘上。
        """
        lines = scanlines(side)
        raw = [[sorted(sm[3 * key(t) + c] for t in range(REF_PX))[REF_PX // 2] for c in range(3)]
               for _, key in lines]
        pts = []
        def coord_of(k):
            if side == "bottom":
                return H - 1 - k
            if side == "right":
                return W - 1 - k
            return k

        for i, (coord, key) in enumerate(lines):
            lo, hi = max(0, i - SMOOTH_W), min(len(raw), i + SMOOTH_W + 1)
            win = raw[lo:hi]
            ref = [sorted(p[c] for p in win)[len(win) // 2] for c in range(3)]
            if (max(abs(raw[i][c] - ref[c]) for c in range(3)) > BG_TOL
                    or max(abs(ref[c] - bg_ref[c]) for c in range(3)) > BG_HARD):
                # 外侧已经不是背景色 = 封面顶到画面边缘：这一侧的边就在画面上，按 0 留白算。
                # （宁可多留几像素背景，也不要把封面切掉一块。）
                pts.append((coord, coord_of(0)))
                continue
            for t in range(REF_PX, LIMIT):
                devs = []
                for u in range(t, min(t + WIN, LIMIT)):
                    j = 3 * key(u)
                    devs.append(max(abs(sm[j + c] - ref[c]) for c in range(3)))
                devs.sort()
                if devs[len(devs) // 2] > TOL:
                    # 窗口里过半像素已偏离参考色：真边在窗口前段，往回退半个窗口
                    pts.append((coord, coord_of(max(REF_PX, t + WIN // 2 - 1))))
                    break
        return pts

    INLIER_TOL = 3.0   # 采样点离拟合线这么多像素以内就算内点

    def inliers(pts, m, b):
        return [p for p in pts
                if abs(m * p[0] - p[1] + b) / math.hypot(m, 1.0) <= INLIER_TOL]

    def fit_line(pts, min_inliers=12):
        """RANSAC 找主直线，再用内点最小二乘精修（拟合 因变量 = m*自变量 + b）。

        封面图案里暗部的边界、反光等会给出不少乱点，有时比真边上的点还多，
        取斜率中位数的稳健拟合会被带偏 —— 所以找"内点最多的那条线"。
        """
        pts = list(pts)
        n = len(pts)
        if n < 2:
            return None
        step = max(1, n // 40)
        sub = pts[::step]
        best = ([], None, None)
        for i in range(len(sub)):
            for j in range(i + 1, len(sub)):
                u1, v1 = sub[i]
                u2, v2 = sub[j]
                if abs(u2 - u1) < 1e-9:
                    continue
                m = (v2 - v1) / (u2 - u1)
                b = v1 - m * u1
                keep = inliers(pts, m, b)
                if len(keep) > len(best[0]):
                    best = (keep, m, b)
        keep, m, b = best
        if m is None or len(keep) < min_inliers:
            return None
        for _ in range(4):                      # 内点最小二乘精修，再收一轮内点
            k = len(keep)
            sx = sum(p[0] for p in keep)
            sy = sum(p[1] for p in keep)
            sxx = sum(p[0] * p[0] for p in keep)
            sxy = sum(p[0] * p[1] for p in keep)
            m = (k * sxy - sx * sy) / (k * sxx - sx * sx)
            b = (sy - m * sx) / k
            grow = inliers(pts, m, b)
            if len(grow) == len(keep):
                break
            keep = grow
        return m, b, len(keep)

    raw_pts = {name: edge_points(name) for name in ("left", "right", "top", "bottom")}
    fits = {name: fit_line(pts) for name, pts in raw_pts.items()}
    for name in ("left", "right", "top", "bottom"):
        fit = fits[name]
        print('%s边: 采样 %d 点，%s' % (
            name, len(raw_pts[name]),
            '一条边都没找到' if fit is None else '内点 %d 点' % fit[2]))
    missing = [name for name, fit in fits.items() if fit is None]
    if missing:
        sys.exit(
            "定位不到%s边：图像四周 %d 像素内找不到持续偏离边缘参考色的像素，"
            "确认这是深色背景上的封面照，或调大脚本里的 LIMIT" % ("/".join(missing), LIMIT)
        )
    (mL, bL, _) = fits["left"]
    (mR, bR, _) = fits["right"]
    (mT, bT, _) = fits["top"]
    (mB, bB, _) = fits["bottom"]
    print('四条边: left x=%.5f*y%+.2f | right x=%.5f*y%+.2f | top y=%.5f*x%+.2f | bottom y=%.5f*x%+.2f'
          % (mL, bL, mR, bR, mT, bT, mB, bB))

    def inter_x(mv, bv, mh, bh):
        y = (mh * bv + bh) / (1.0 - mh * mv)
        return (mv * y + bv, y)

    quad = [inter_x(mL, bL, mT, bT), inter_x(mR, bR, mT, bT),
            inter_x(mR, bR, mB, bB), inter_x(mL, bL, mB, bB)]
    print('四角: TL=(%.1f,%.1f) TR=(%.1f,%.1f) BR=(%.1f,%.1f) BL=(%.1f,%.1f)' % tuple(sum(quad, ())))

    # ---------- 2) 四条直线边以内留下，以外一律透明 ----------
    cx = sum(p[0] for p in quad) / 4.0
    cy = sum(p[1] for p in quad) / 4.0
    edges = []
    for i in range(4):
        ax, ay = quad[i]
        ex, ey = quad[(i + 1) % 4][0] - ax, quad[(i + 1) % 4][1] - ay
        elen = math.hypot(ex, ey)
        sgn = 1.0 if ex * (cy - ay) - ey * (cx - ax) > 0 else -1.0
        edges.append((ax, ay, ex, ey, elen, sgn))

    mask_bytes = bytearray(W * H)
    for y in range(H):
        base = y * W
        for x in range(W):
            px_, py_ = x + 0.5, y + 0.5
            for ax, ay, ex, ey, elen, sgn in edges:
                if sgn * (ex * (py_ - ay) - ey * (px_ - ax)) / elen < 0.0:
                    break
            else:
                mask_bytes[base + x] = 255

    binary = Image.frombytes('L', (W, H), bytes(mask_bytes))

    # ---------- 4) 边缘带：按亮度反推覆盖率，消掉黑边 ----------
    inverted = binary.point(lambda v: 255 - v)
    band = ImageChops.multiply(binary, inverted.filter(ImageFilter.MaxFilter(17)))  # 透明区外扩 8px
    core_mask = binary.filter(ImageFilter.MinFilter(7))                             # 向内缩 3px 取本色

    BLUR_R = 12
    den = core_mask.filter(ImageFilter.BoxBlur(BLUR_R)).load()
    trio = Image.merge('RGB', (core_mask, core_mask, core_mask))
    num = ImageChops.multiply(im, trio).filter(ImageFilter.BoxBlur(BLUR_R)).load()

    # 背景色 / 背景亮度：四边形外面（就是被裁掉的那片）里够暗的像素
    sr = sg = sb = n = 0
    for i in range(W * H):
        if mask_bytes[i] == 0:
            j = 3 * i
            if data[j + 2] < 60:
                sr += data[j]
                sg += data[j + 1]
                sb += data[j + 2]
                n += 1
    if n == 0:
        sys.exit("量不出背景色：裁掉的区域里没有足够暗的像素，确认这是深色背景上的封面照")
    bg_rgb = (sr / n, sg / n, sb / n)
    lum_bg = 0.299 * bg_rgb[0] + 0.587 * bg_rgb[1] + 0.114 * bg_rgb[2]
    print('背景色 rgb=(%.1f,%.1f,%.1f) lum=%.1f (n=%d)' % (bg_rgb + (lum_bg, n)))

    lum = im.convert('L').load()
    bandp = band.load()
    out = im.convert('RGBA')
    opx = out.load()
    final_a = bytearray(mask_bytes)
    changed = 0
    for y in range(H):
        base = y * W
        for x in range(W):
            if bandp[x, y] == 0:
                continue
            dv = den[x, y]
            if dv < 8:                       # 附近取不到封面本色，保持原样
                continue
            col = tuple(max(0, min(255, num[x, y][c] * 255 // dv)) for c in range(3))
            lc = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
            if lc - lum_bg >= 25 and lum[x, y] > lum_bg:
                # 只有"比背景亮"的像素才可能是 背景 + 封面本色 的混合色。比背景还暗的
                # 像素是封面自己的暗部（暗封面压在同样暗的背景上），照原样留着别擦掉，
                # 否则暗边会被啃成一圈参差的缺口。
                c = (lum[x, y] - lum_bg) / (lc - lum_bg)
                c = 1.0 if c > 1 else c
            else:
                c = 1.0
            if c >= 0.995:
                continue
            opx[x, y] = col
            final_a[base + x] = int(round(c * 255))
            changed += 1
    print('按覆盖率修正的边缘像素: %d' % changed)

    alpha = Image.frombytes('L', (W, H), bytes(final_a)).filter(ImageFilter.GaussianBlur(0.5))
    out.putalpha(alpha)

    stem = os.path.splitext(os.path.basename(args.src))[0]
    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.src))
    os.makedirs(out_dir, exist_ok=True)

    full_path = os.path.join(out_dir, stem + '_transparent.png')
    out.save(full_path)
    print('透明底原尺寸图: %s (%dx%d)' % (full_path, W, H))

    bbox = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
    if bbox is None:
        sys.exit("抠完什么都不剩（全透明），判据没匹配上这张图")
    crop = out.crop(bbox)
    crop_path = os.path.join(out_dir, stem + '_transparent_cropped.png')
    crop.save(crop_path)
    print('裁掉四周留白: %s %s (bbox %s)' % (crop_path, crop.size, bbox))

    if args.check:
        for suffix, col in (('_check_magenta.png', (255, 0, 255)), ('_check_white.png', (255, 255, 255))):
            chk = Image.new('RGB', out.size, col)
            chk.paste(out, (0, 0), out)
            p = os.path.join(out_dir, stem + suffix)
            chk.resize((W // 2, H // 2), Image.LANCZOS).save(p)
            print('检查图: %s' % p)
        # 把四条切边画在缩略图上：抠之前先确认切边真的压在封面轮廓上
        marked = im.copy()
        ImageDraw.Draw(marked).line(quad + [quad[0]], fill=(255, 0, 255), width=3)
        p = os.path.join(out_dir, stem + '_check_edges.png')
        marked.resize((W // 2, H // 2), Image.LANCZOS).save(p)
        print('切边检查图: %s' % p)

    print('done')
    return 0


if __name__ == '__main__':
    sys.exit(main())
