/**
 * 「美化封面」的 canvas 合成：把一张普通封面合成成光盘 / 卡带的外观，产出 PNG Blob。
 *
 * 纯 canvas，无 Vue 依赖——调用方（components/games/CoverBeautifyDialog.vue）负责
 * 载入原封面、预览与上传。几何常量在 constants/coverStyles.js。
 *
 * 两种合成：
 *   - flash：**程序化绘制**，没有底图——圆形裁切 + 盘面贴封面 + 盘心 Flash 标志 + 三层反光。
 *   - 卡带：**先把封面缩放到洞口的宽高比，再与底图合并**。底图是成品素材——一张
 *            没贴过贴纸的原始卡带，封面直接盖到洞口位置即可。
 *
 * 输出的 PNG **必须带 Alpha**：光盘圆外、卡带轮廓之外（缺口与四角）都要透明，
 * 不然摆到卡片上就是一块方形底。
 */

import {
    CART_STYLES,
    FLASH_DISC,
    cornerChamfers,
    cornerRadii,
} from "@/constants/coverStyles";

// 素材图（卡带底图、Flash 标志）按 URL 缓存，同一张只解码一次。
// 值存的是 Promise：并发调用不会各下载一遍。
const imageCache = new Map();

/**
 * 载入一张图并等它 decode 完。
 *
 * 必须 await：`naturalWidth/Height` 在 load 之前是 0，而 `drawImage` 收到没加载完的
 * Image 时**静默什么都不画**（不报错，只是空白），这种 bug 很难查。
 */
export function loadImage(src) {
    const cached = imageCache.get(src);
    if (cached) {
        return cached;
    }
    const pending = new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error("图片加载失败。"));
        img.src = src;
    });
    imageCache.set(src, pending);
    // 失败的不留在缓存里，否则这张图以后永远拿不到
    pending.catch(() => imageCache.delete(src));
    return pending;
}

/**
 * 合成入口：按样式 id 出图。
 *
 * @param {string} styleId "flash" | "gb" | "gbc" | "gba" | "nds" | "fc" | "nes"（见 constants/coverStyles.js）
 * @param {HTMLImageElement} sourceImg 已载入完成的原封面
 * @param {string} [cartridgeId] 卡带 ID；有 `serial` 配置的样式会把它写进画面
 * @returns {Promise<Blob>} PNG
 */
export async function composeCover(styleId, sourceImg, cartridgeId = "") {
    if (styleId === "flash") {
        return composeFlashDisc(sourceImg);
    }
    const cart = CART_STYLES[styleId];
    if (!cart) {
        throw new Error("不支持的美化类型。");
    }
    return composeCartridge(cart, sourceImg, cartridgeId);
}

/* ---------------------------------------------------------------- 卡带 ---- */

/**
 * 卡带：先在贴图区铺底色、把封面**拉伸填满**贴图区（`object-fit: fill` 的做法，
 * 不改比例地拉成贴图区的长宽比，不裁切也不留边），再与底图合并。
 *
 * 两种图层顺序由 `baseOnTop` 决定：
 *   - 普通卡带（默认）：底图先铺，封面盖在洞口上；底图洞口已填机身色，洞口形状之外的
 *     机身像素靠 `clip()` 留住（GBA 是机身灰、GBC 是贴纸凹槽的阴影）。
 *   - NDS（`baseOnTop: true`）：封面先画在镂空窗里，**底图最后整张盖上来**——顶部 logo
 *     黑区、左右黑分隔线、下方黑条都露在封面上面，封面只从镂空窗透出来。
 *
 * 圆角可以**按角给**（`cornerRadii()` 归一化成 `{ tl, tr, br, bl }`）；
 * 斜角由 `cornerChamfers()` 给（同一个角有斜角就不再走圆角）。
 *
 * `holeFill` 铺在封面下面：封面自带透明像素时，空缺处露出这层底色（NDS 是贴纸黑），
 * 不会露出底图的透明窗。`serial` 是画在底图上的卡带 ID 文字（目前只有 NDS 配了），
 * 在封面与底图之后画，位置用输出画布坐标。
 */
async function composeCartridge(cart, sourceImg, cartridgeId = "") {
    const { image, hole } = cart;
    const base = await loadImage(cart.url);
    const ctx = makeContext(image.width, image.height);

    const drawCover = () => {
        ctx.save();
        roundRectPath(
            ctx,
            hole.x,
            hole.y,
            hole.width,
            hole.height,
            cornerRadii(cart.radius),
            cornerChamfers(cart.chamfer),
        );
        ctx.clip();
        // 封面自带透明像素时露出的贴纸底色
        if (cart.holeFill) {
            ctx.fillStyle = cart.holeFill;
            ctx.fillRect(hole.x, hole.y, hole.width, hole.height);
        }
        // 没有源矩形：整张封面直接拉伸到贴图区大小
        ctx.drawImage(sourceImg, hole.x, hole.y, hole.width, hole.height);
        ctx.restore();
    };

    if (cart.baseOnTop) {
        // NDS：封面在下，卡带框盖在上面，只从镂空窗露出
        drawCover();
        ctx.drawImage(base, 0, 0, image.width, image.height);
    } else {
        ctx.drawImage(base, 0, 0, image.width, image.height);
        drawCover();
    }

    // 卡带 ID：靠右固定留白，按字形墨迹的上下边界垂直居中
    // （textBaseline "middle" 对等宽字体偏高约 3px，所以改用 actualBoundingBox 量出墨迹）
    if (cart.serial && cartridgeId) {
        const { rightEdge, paddingRight, centerY, font, color } = cart.serial;
        const text = String(cartridgeId);
        ctx.save();
        ctx.font = font;
        ctx.fillStyle = color;
        ctx.textAlign = "right";
        const metrics = ctx.measureText(text);
        const ascent = metrics.actualBoundingBoxAscent;
        const descent = metrics.actualBoundingBoxDescent;
        if (Number.isFinite(ascent) && Number.isFinite(descent)) {
            ctx.textBaseline = "alphabetic";
            ctx.fillText(
                text,
                rightEdge - paddingRight,
                centerY + (ascent - descent) / 2,
            );
        } else {
            // 老浏览器没有 actualBoundingBox，退回 middle
            ctx.textBaseline = "middle";
            ctx.fillText(text, rightEdge - paddingRight, centerY);
        }
        ctx.restore();
    }

    return toPngBlob(ctx.canvas);
}

/* ------------------------------------------------------------ Flash 光盘 ---- */

/**
 * Flash 光盘：整盘先做一次圆形裁切，之后所有图层都在圆内画，圆外保持透明。
 * 坐标全部换到「盘内局部坐标」——translate 之后 (0,0)-(d,d) 就是盘的外接正方形。
 */
async function composeFlashDisc(sourceImg) {
    const { size, padRatio, hubRatio, logoUrl } = FLASH_DISC;
    const logo = await loadImage(logoUrl);

    const ctx = makeContext(size, size);
    const d = size * padRatio; // 盘直径
    const r = d / 2; // 盘半径
    const offset = (size - d) / 2;

    ctx.save();
    ctx.translate(offset, offset);
    ctx.beginPath();
    ctx.arc(r, r, r, 0, Math.PI * 2);
    ctx.clip();

    // 1. 盘面底色。有封面时基本被盖住，只有封面自己带透明像素才看得见，
    //    但照画——没封面时它就是那张「空白盘」的金属感
    const base = angleGradient(ctx, 0, 0, d, d, 135);
    base.addColorStop(0, "#f8fafc");
    base.addColorStop(0.42, "#cbd5e1");
    base.addColorStop(0.58, "#eef2f7");
    base.addColorStop(1, "#b6c0cc");
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, d, d);

    // 2. 盘面贴封面（object-fit: cover）。目标是正方形，所以源矩形恒为居中的
    //    min(宽, 高) 正方形——不用写通用的 cover 裁剪公式
    const side = Math.min(sourceImg.naturalWidth, sourceImg.naturalHeight);
    ctx.drawImage(
        sourceImg,
        (sourceImg.naturalWidth - side) / 2,
        (sourceImg.naturalHeight - side) / 2,
        side,
        side,
        0,
        0,
        d,
        d
    );

    // 3. 盘心那枚 Flash 标志，正好盖住盘中心那一圈。
    //    hub 的基准是**盘直径**（与反光那几层占半径不同）
    const hub = d * hubRatio;
    ctx.drawImage(logo, (d - hub) / 2, (d - hub) / 2, hub, hub);

    // 4. 反光三层，**由底到顶**依次画：先斜向高光，再外圈暗调与塑料边，最后盘心积层环。
    //    顺序反了上面那层会把下面的盖掉
    drawGloss(ctx, d, r);
    drawRim(ctx, r);
    drawHubRing(ctx, r);

    ctx.restore();
    return toPngBlob(ctx.canvas);
}

/** 透明色（三层反光里到处在用） */
const CLEAR = "rgba(255, 255, 255, 0)";

/** 斜向高光，压在最底下 */
function drawGloss(ctx, d, r) {
    const gloss = angleGradient(ctx, 0, 0, d, d, 118);
    gloss.addColorStop(0, "rgba(255, 255, 255, 0.42)");
    gloss.addColorStop(0.24, "rgba(255, 255, 255, 0.06)");
    gloss.addColorStop(0.3, CLEAR);
    gloss.addColorStop(0.64, CLEAR);
    gloss.addColorStop(0.8, "rgba(255, 255, 255, 0.18)");
    gloss.addColorStop(1, CLEAR);
    ctx.fillStyle = gloss;
    ctx.fillRect(0, 0, d, d);
}

/**
 * 外圈弧度暗调 + 透明塑料边。
 *
 * 径向渐变的百分比基准是**盘半径**，不是盘直径——这是整套几何里最容易搞错的一处
 * （盘心标志那个 hubRatio 是占直径的，见 constants/coverStyles.js）。同色双位置
 * stop（`91%` 与 `92.5%` 之间没有过渡）要写成两条同色 stop，`addColorStop` 一次只吃一个 offset。
 */
function drawRim(ctx, r) {
    const rim = ctx.createRadialGradient(r, r, 0, r, r, r);
    rim.addColorStop(0, CLEAR);
    rim.addColorStop(0.74, CLEAR);
    // 盘面外圈渐渐压暗：一点弧度感，盘就不是一张平贴的圆纸片
    rim.addColorStop(0.91, "rgba(15, 23, 42, 0.18)");
    rim.addColorStop(0.925, "rgba(15, 23, 42, 0.18)");
    // 透明塑料边：内侧浅、贴边一道强反光
    rim.addColorStop(0.94, "rgba(255, 255, 255, 0.2)");
    rim.addColorStop(0.955, "rgba(255, 255, 255, 0.2)");
    rim.addColorStop(0.975, "rgba(255, 255, 255, 0.62)");
    rim.addColorStop(0.99, "rgba(255, 255, 255, 0.62)");
    rim.addColorStop(1, "rgba(255, 255, 255, 0.35)");
    ctx.fillStyle = rim;
    ctx.fillRect(0, 0, r * 2, r * 2);
}

/**
 * 盘心外围那圈积层环，压在最上层。
 *
 * 起始位置 0.16 与盘心标志的边缘 0.15（同样占半径）之间**刻意留一道缝**，
 * 封面从缝里透出来——这就是「孔外一圈积层环」的观感，别把 0.16 改成 0.15。
 */
function drawHubRing(ctx, r) {
    const ring = ctx.createRadialGradient(r, r, 0, r, r, r);
    ring.addColorStop(0, CLEAR);
    ring.addColorStop(0.16, CLEAR);
    ring.addColorStop(0.175, "rgba(255, 255, 255, 0.55)");
    ring.addColorStop(0.21, CLEAR);
    ctx.fillStyle = ring;
    ctx.fillRect(0, 0, r * 2, r * 2);
}

/* ------------------------------------------------------------------ 通用 ---- */

/**
 * 按角度建一条线性渐变：角度 0 朝上、顺时针增大（canvas 的 y 轴朝下，所以方向向量是
 * `(sinθ, −cosθ)`）。渐变线过盒心，长度取盒子在渐变方向上的投影 `|W·sinθ| + |H·cosθ|`。
 *
 * 别图省事拿 (x,y)→(x+w,y+h) 当端点：那只在 45° 的整数倍上碰巧对。
 * 自检：正方形上 135deg 应得左上角 → 右下角。
 */
function angleGradient(ctx, x, y, w, h, deg) {
    const rad = (deg * Math.PI) / 180;
    const dx = Math.sin(rad);
    const dy = -Math.cos(rad);
    const length = Math.abs(w * Math.sin(rad)) + Math.abs(h * Math.cos(rad));
    const cx = x + w / 2;
    const cy = y + h / 2;
    return ctx.createLinearGradient(
        cx - (dx * length) / 2,
        cy - (dy * length) / 2,
        cx + (dx * length) / 2,
        cy + (dy * length) / 2
    );
}

/**
 * 卡带贴纸窗路径：四角可以是**圆角**（`r`，`{ tl, tr, br, bl }`）或**斜角**
 * （`c`，同样四角，数字是沿两条边切掉的长度）。同一个角同时给了斜角和圆角时以斜角为准。
 * 0 = 直角。不用 `ctx.roundRect`：那个 Chrome 99+ / Safari 16+ 才有，而且只吃一个统一半径。
 * `arcTo` 半径 0 是退化情形，这里干脆跳过它——上一句 lineTo 已经走到角上了。
 */
function roundRectPath(ctx, x, y, w, h, r, c = { tl: 0, tr: 0, br: 0, bl: 0 }) {
    // 每条边从角点往里缩的距离：斜角优先，其次圆角，否则 0（直角）
    const off = {
        tl: c.tl || r.tl,
        tr: c.tr || r.tr,
        br: c.br || r.br,
        bl: c.bl || r.bl,
    };
    ctx.beginPath();
    ctx.moveTo(x + off.tl, y);
    ctx.lineTo(x + w - off.tr, y);
    if (c.tr) {
        ctx.lineTo(x + w, y + c.tr);
    } else if (r.tr) {
        ctx.arcTo(x + w, y, x + w, y + r.tr, r.tr);
    }
    ctx.lineTo(x + w, y + h - off.br);
    if (c.br) {
        ctx.lineTo(x + w - c.br, y + h);
    } else if (r.br) {
        ctx.arcTo(x + w, y + h, x + w - r.br, y + h, r.br);
    }
    ctx.lineTo(x + off.bl, y + h);
    if (c.bl) {
        ctx.lineTo(x, y + h - c.bl);
    } else if (r.bl) {
        ctx.arcTo(x, y + h, x, y + h - r.bl, r.bl);
    }
    ctx.lineTo(x, y + off.tl);
    if (c.tl) {
        ctx.lineTo(x + c.tl, y);
    } else if (r.tl) {
        ctx.arcTo(x, y, x + r.tl, y, r.tl);
    }
    ctx.closePath();
}

function makeContext(width, height) {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    // 注意别传 { alpha: false }（模拟器截图那边是这么用的）：这里靠透明区做
    // 光盘圆外与卡带圆角，一旦关掉 alpha，画布会变成不透明黑底，两处全废
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    return ctx;
}

/** 出 PNG Blob。必须是 PNG——jpeg 会把透明区压成黑底。 */
function toPngBlob(canvas) {
    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
            if (blob) {
                resolve(blob);
            } else {
                reject(new Error("生成图片失败。"));
            }
        }, "image/png");
    });
}
