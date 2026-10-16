/**
 * 「美化封面」的 canvas 合成：把一张普通封面合成成光盘 / 卡带的外观，产出 PNG Blob。
 *
 * 纯 canvas，无 Vue 依赖——调用方（components/games/CoverBeautifyDialog.vue）负责
 * 载入原封面、预览与上传。几何常量在 constants/coverStyles.js。
 *
 * 两种合成：
 *   - flash：**程序化绘制**，没有底图。照抄原先卡片上那套「实体光盘」的 CSS 渲染
 *            （圆形裁切 + 盘面贴封面 + 盘心 Flash 标志 + 三层反光），逐条换算成 canvas。
 *   - 卡带：**先把封面缩放到洞口的宽高比，再与底图合并**。底图是成品素材，
 *            中间的贴纸窗已经挖空，封面直接贴进洞口位置即可。
 *
 * 输出的 PNG **必须带 Alpha**：光盘圆外、卡带洞口圆角之外都要透明
 * （卡带那边尤其重要——底图在圆角外还留着机身像素与凹槽阴影，要透出来接缝才自然）。
 */

import { CART_STYLES, FLASH_DISC } from "@/constants/coverStyles";

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
 * @param {string} styleId "flash" | "gb" | "gba"（见 constants/coverStyles.js）
 * @param {HTMLImageElement} sourceImg 已载入完成的原封面
 * @returns {Promise<Blob>} PNG
 */
export async function composeCover(styleId, sourceImg) {
    if (styleId === "flash") {
        return composeFlashDisc(sourceImg);
    }
    const cart = CART_STYLES[styleId];
    if (!cart) {
        throw new Error("不支持的美化类型。");
    }
    return composeCartridge(cart, sourceImg);
}

/* ---------------------------------------------------------------- 卡带 ---- */

/**
 * 卡带：底图铺满 → 把封面**拉伸填满**洞口（`object-fit: fill` 的做法，不改比例地
 * 拉成洞口的长宽比，不裁切也不留边）→ 与底图合成。
 *
 * 贴之前一定要按洞口的圆角裁一刀：底图的洞口是按圆角挖的，圆角之外仍是机身像素
 * （GBA 是不透明的机身灰、GBC 是半透明的凹槽阴影），不裁的话矩形封面会把这圈盖掉。
 */
async function composeCartridge(cart, sourceImg) {
    const { image, hole, radius } = cart;
    const base = await loadImage(cart.url);
    const ctx = makeContext(image.width, image.height);

    ctx.drawImage(base, 0, 0, image.width, image.height);

    ctx.save();
    roundRectPath(ctx, hole.x, hole.y, hole.width, hole.height, radius);
    ctx.clip();
    // 没有源矩形：整张封面直接拉伸到洞口大小
    ctx.drawImage(sourceImg, hole.x, hole.y, hole.width, hole.height);
    ctx.restore();

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
    const base = cssAngleGradient(ctx, 0, 0, d, d, 135);
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
    //    hub 的基准是**盘直径**（CSS 里 width: 15% 相对的是盘那个正方形）
    const hub = d * hubRatio;
    ctx.drawImage(logo, (d - hub) / 2, (d - hub) / 2, hub, hub);

    // 4. 反光三层。CSS 的 background 里**第一条在最上**，canvas 没有多背景，
    //    所以在这里必须倒着画：先 linear，再外圈暗调，最后盘心环
    drawGloss(ctx, d, r);
    drawRim(ctx, r);
    drawHubRing(ctx, r);

    ctx.restore();
    return toPngBlob(ctx.canvas);
}

/** 透明色（三层反光里到处在用） */
const CLEAR = "rgba(255, 255, 255, 0)";

/** 斜向高光：`linear-gradient(118deg, …)`，压在最底下 */
function drawGloss(ctx, d, r) {
    const gloss = cssAngleGradient(ctx, 0, 0, d, d, 118);
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
 * 外圈弧度暗调 + 透明塑料边：`radial-gradient(circle closest-side, …)`。
 *
 * 百分比基准是**盘半径**（正方形盒上 closest-side 的半径就是 r），不是盘直径——
 * 这是整套换算里最容易搞错的一处。CSS 的双位置 stop（`A 91% 92.5%`）在 canvas 里
 * 必须拆成两条同色 stop，因为 addColorStop 一次只吃一个 offset。
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
 * 盘心外围那圈积层环：`radial-gradient(circle closest-side, …)`，压在最上层。
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
 * CSS 的 `linear-gradient(θdeg, …)` 换算成 canvas 的 `createLinearGradient`。
 *
 * CSS 的角度是 0deg 朝上、顺时针增大；canvas 的 y 轴朝下，所以方向向量是
 * (sinθ, −cosθ)。渐变线过盒心，长度取盒子在渐变方向上的投影
 * `|W·sinθ| + |H·cosθ|`。
 *
 * 别图省事拿 (x,y)→(x+w,y+h) 当端点：那只在 45° 的整数倍上碰巧对。
 * 自检：正方形上 135deg 应得左上角 → 右下角。
 */
function cssAngleGradient(ctx, x, y, w, h, deg) {
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
 * 圆角矩形路径。不用 `ctx.roundRect`：那个 Chrome 99+ / Safari 16+ 才有，
 * 这几行 arcTo 到处都能跑。
 */
function roundRectPath(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
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
