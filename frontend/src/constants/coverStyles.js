/**
 * 「美化封面」的样式配置：把一张普通封面合成成光盘 / 卡带的外观。
 *
 * 入口是游戏管理页编辑弹框「游戏封面」那行的「美化封面」按钮
 * （见 components/games/CoverBeautifyDialog.vue）。**一个游戏类型可以有好几种样式**，
 * 查表函数 `beautifyStylesFor(gameType)` 返回这个类型可用的那一组（顺序 = 弹框里
 * 那排方框单选的顺序，第一个是默认选中的）；返回空数组 = 这个类型
 * 不支持美化，按钮整条不显示。**每个类型都出那排单选**——只有一种样式的 `flash` / `gba`
 * 也把 `DISK` / `GBA` 摆出来（那一项不可选），所以 `label` 是用户唯一能看到的样式名。
 *
 * **样式 id 就是「封面类型」**（`games.cover_type` 存的值）：美化封面时选中的那个
 * 样式会连同封面文件写进游戏行，游戏中心在游戏类型分组内按它分子网格、详情弹框展示它、
 * 编辑弹框里可以手动改。取值的权威来源在后端 `backend/games/models.py` 的
 * `COVER_TYPES_BY_GAME_TYPE`，这里的 `STYLE_BY_GAME_TYPE` 是展示层镜像（见 `coverTypesFor()`）。
 *
 * 绘制算法在 utils/coverCompose.js（纯 canvas，无 Vue 依赖）。
 *
 * ---------------------------------------------------------------
 * 卡带底图与洞口几何
 * ---------------------------------------------------------------
 * 底图是成品素材——一张**没贴过贴纸的原始卡带**，中间那块贴纸窗通常已经填成机身色，
 * 几组数字：整图尺寸、贴图区矩形、圆角（个别样式还有斜角）。**换素材必须同步改这些
 * 数字**，否则封面会错位；下面的值已逐像素核对过：
 *
 *   gb-cart.png    426 × 500  洞口 (53, 151) 322 × 287   圆角 8   （洞口 322:287 ≈ 1.12:1）
 *   gbc-cart.png   438 × 503  洞口 (58, 163) 322 × 287   圆角 8   （洞口同上）
 *   gba-cart.png   640 × 370  洞口 (88,  86) 464 × 235   圆角 12  （洞口 464:235 ≈ 1.97:1）
 *   nds-cart.png   487 × 520  标签贴图区 (51, 35) 395 × 374  直角矩形（封面先画、底图盖在上面）
 *                                                         （只从中间镂空窗露出，顶部黑条盖住封面顶部）
 *   fc-cart.png    700 × 460  洞口 (56,  54) 592 × 290   圆角 10  （洞口 592:290 ≈ 2.04:1）
 *   nes-cart.png   700 × 779  洞口 (283,  0) 323 × 527   圆角 10  （洞口 323:527 ≈ 0.61:1）
 *                                                         ↑ 洞口上边就是画布顶边，见下
 *
 * 底图文件名一律 `<样式 id>-cart.png`（见下面的 CART_STYLES），加样式就照这个来。
 *
 * **要贴同一张画的多个样式，洞口尺寸必须做成一样**：同一张封面贴进哪个样式，成品里
 * 封面占的区域都得是同一个大小，不然观感对不上（底图按 `sx = 目标洞口宽 / 原洞口宽`、
 * `sy = 目标洞口高 / 原洞口高` 整图重采样，再按整数坐标重填一遍洞口）。
 * **本来就该贴不同画的样式各按自己的素材来，别去对齐**：FC 日版挖的是横版整块标签、
 * NES 那张挖的是竖版贴纸，形状差得远。
 *
 * `radius` 是**封面裁切**用的圆角（写一个数字 = 四角相同；也可以写成 `{ tl, tr, br, bl }`
 * 按角指定，没写的角按直角算，见 `cornerRadii()` 与 utils/coverCompose.js 的 `roundRectPath()`）。
 * 合成时按它 `clip()` 一刀，**圆角之外那圈底图像素要留着**（GBA 是机身灰、GB/GBC 是贴纸
 * 凹槽的阴影），不能被方形封面盖掉。
 *
 * `chamfer` 是**斜角**（直线切角），写一个数字 = 四角都切，也可以写成
 * `{ tl, tr, br, bl }`，见 `cornerChamfers()`。同一个角给了 `chamfer` 就不再走
 * 圆角，`roundRectPath()` 里画直线；目前没有样式在用（NDS 改成整块贴纸区后不再切
 * 左下角），能力保留给以后可能出现的素材。
 *
 * NDS 的贴图逻辑和别的卡带**反过来**：封面左上角对准**顶部 logo 黑条的左上角**，铺满
 * 整块标签区；**底图最后整张盖上来**，顶部 logo 黑区、左右黑分隔线、下方黑条都还是
 * 卡带本身——就像拿一张中间镂空的卡带框盖在贴图上，贴图只从镂空窗露出。封面顶部
 * （包括封面自己带着的 logo）会被卡带黑条完全盖住，不会出现两个 logo。`baseOnTop: true`
 * 控制这个顺序。NDS 另有两条专属配置：`holeFill` 是封面自带透明像素时露出的贴纸底色；
 * `serial` 是把卡带 ID 写在下方黑条里的位置、字体与颜色。
 *
 * **注意「底图填色」与「封面裁切」是两件事，`nes-cart.png` 那张上最容易搞混**：它的洞口上边就是
 * 画布顶边（源图顶部被裁掉了，标签上边缘不在画面里），所以**底图填色时上面两角是直角**
 * （那两块本来就是洞口的一部分，必须一起填上，否则底图上会留两个透明缺口）；而**封面
 * 裁切仍然是四角 r=10**，裁掉的上两角露出的是底图填好的机身色。重跑底图填色时记得这点
 * （`clear_scene.py --radius 0,0,10,10`）。
 *
 * 底图本身带透明的地方通常是卡带轮廓之外（缺口、四角）；NDS 底图的贴纸窗也是透明的，
 * 合成时由 `holeFill` 在封面下面补一层贴纸底色。
 *
 * ---------------------------------------------------------------
 * 素材位置
 * ---------------------------------------------------------------
 * 底图与盘心标志都放在 `src/assets/` 下，**用 import 取 URL**，别写回 `"/xxx.png"`：
 * Vite 会给产物文件名带上内容哈希，重跑底图后 URL 跟着变，浏览器缓存必然失效。
 * 留在 `public/` 下则是固定文件名，而 nginx 的 `location /`（以及 Windows 包的
 * `static_site.py`）对这些文件**不带任何 Cache-Control**，浏览器按启发式规则缓存住旧图，
 * 换图后得手动硬刷新才看得见。同理见 views/games/emulator-player.vue 的机壳图。
 */

import flashLogoUrl from "@/assets/flash-logo.png";
import gbCartUrl from "@/assets/carts/gb-cart.png";
import gbcCartUrl from "@/assets/carts/gbc-cart.png";
import gbaCartUrl from "@/assets/carts/gba-cart.png";
import ndsCartUrl from "@/assets/carts/nds-cart.png";
import fcCartUrl from "@/assets/carts/fc-cart.png";
import nesCartUrl from "@/assets/carts/nes-cart.png";

/**
 * Flash 光盘的几何（程序化绘制，没有底图）。
 *
 * 光盘直径只占整幅边长的 84%，四周留一圈透明。
 */
export const FLASH_DISC = {
    // 输出画布边长
    size: 1024,
    // 光盘直径占画布边长的比例（84cqw 的等价物）；四周留空是刻意的观感
    padRatio: 0.84,
    // 盘心 Flash 标志的边长占**光盘直径**的比例。
    // 注意基准与渐变不同：反光那几层的百分比是占**盘半径**的，见 coverCompose.js。
    hubRatio: 0.15,
    logoUrl: flashLogoUrl,
};

/**
 * 洞口圆角统一成四角 `{ tl, tr, br, bl }`：给数字 = 四角相同；给对象 = 按角指定，
 * **没写的角按 0（直角）算**。绘制那边只认这个形状，见 utils/coverCompose.js。
 */
export function cornerRadii(radius) {
    if (typeof radius === "number") {
        return { tl: radius, tr: radius, br: radius, bl: radius };
    }
    return { tl: 0, tr: 0, br: 0, bl: 0, ...radius };
}

/**
 * 四角的**斜角**切边长度，形状与 `cornerRadii()` 相同：数字 = 四角相同，
 * `{ tl, tr, br, bl }` 按角给，没写的角为 0。与圆角冲突时以斜角为准。
 */
export function cornerChamfers(chamfer) {
    if (!chamfer) {
        return { tl: 0, tr: 0, br: 0, bl: 0 };
    }
    if (typeof chamfer === "number") {
        return { tl: chamfer, tr: chamfer, br: chamfer, bl: chamfer };
    }
    return { tl: 0, tr: 0, br: 0, bl: 0, ...chamfer };
}

/** 卡带底图配置，按样式 id 索引（id 与 STYLE_META、STYLE_BY_GAME_TYPE 里的键一一对应）。 */
export const CART_STYLES = {
    gb: {
        label: "GB",
        url: gbCartUrl,
        image: { width: 426, height: 500 },
        hole: { x: 53, y: 151, width: 322, height: 287 },
        radius: 8,
    },
    gbc: {
        label: "GBC",
        url: gbcCartUrl,
        image: { width: 438, height: 503 },
        hole: { x: 58, y: 163, width: 322, height: 287 },
        radius: 8,
    },
    gba: {
        label: "GBA",
        url: gbaCartUrl,
        image: { width: 640, height: 370 },
        hole: { x: 88, y: 86, width: 464, height: 235 },
        radius: 12,
    },
    nds: {
        label: "NDS",
        url: ndsCartUrl,
        image: { width: 487, height: 520 },
        // 封面左上角对准标签区左上角（顶部 logo 黑条的左上角），铺满整块标签区；
        // 底图（带透明窗）最后整张盖上来，封面只从中间镂空窗露出。
        hole: { x: 51, y: 35, width: 395, height: 374 },
        baseOnTop: true,
        // 封面自带透明像素时露出的贴纸底色（logo 黑条同色）
        holeFill: "rgb(35, 28, 29)",
        // 卡带 ID：写在下方黑条（y 409–461）里，靠右固定留白；垂直居中按字形墨迹计算
        serial: {
            rightEdge: 445,
            paddingRight: 20,
            centerY: 435,
            font: '22px ui-monospace, SFMono-Regular, Menlo, Consolas, "Courier New", monospace',
            color: "#ffffff",
        },
    },
    fc: {
        label: "FC",
        url: fcCartUrl,
        image: { width: 700, height: 460 },
        hole: { x: 56, y: 54, width: 592, height: 290 },
        radius: 10,
    },
    nes: {
        label: "NES",
        url: nesCartUrl,
        image: { width: 700, height: 779 },
        // 洞口上边就是画布顶边（素材的标签上边缘被裁掉了），封面裁切照样四角 r=10，
        // 裁掉的上两角露出的是底图填好的机身色（底图填色时上两角是直角，见文件头）
        hole: { x: 283, y: 0, width: 323, height: 527 },
        radius: 10,
    },
};

/** 游戏类型 → 可用的美化样式 id 列表，**顺序就是弹框里单选的顺序**。不在这张表里的类型不显示按钮。 */
const STYLE_BY_GAME_TYPE = {
    flash: ["flash"],
    gb: ["gb", "gbc"],
    gba: ["gba"],
    nds: ["nds"],
    nes: ["fc", "nes"],
};

/**
 * 各样式在弹框里显示给用户的建议尺寸。
 *
 * `hint` 说的是**输入**建议（用户该拿多大的图来美化），`output` 是合成结果尺寸。
 * 卡带那几条要讲清楚比例不符会被拉伸——合成是 `object-fit: fill` 的做法，
 * 不裁切、不留边，比例不对就是变形。
 */
const STYLE_META = {
    flash: {
        id: "flash",
        label: "DISK",
        output: { width: FLASH_DISC.size, height: FLASH_DISC.size },
        hint: "建议 1:1 方形图，长边 ≥ 512px。封面按中心正方形裁切后画进光盘。",
    },
    gb: {
        id: "gb",
        label: CART_STYLES.gb.label,
        output: { ...CART_STYLES.gb.image },
        hint: "建议 322 : 287（约 1.12:1），至少 322×287。比例不符会拉伸填满卡带贴纸窗。",
    },
    gbc: {
        id: "gbc",
        label: CART_STYLES.gbc.label,
        output: { ...CART_STYLES.gbc.image },
        hint: "建议 322 : 287（约 1.12:1），至少 322×287。比例不符会拉伸填满卡带贴纸窗。",
    },
    gba: {
        id: "gba",
        label: CART_STYLES.gba.label,
        output: { ...CART_STYLES.gba.image },
        hint: "建议 464 : 235（约 1.97:1），至少 464×235。比例不符会拉伸填满卡带贴纸窗。",
    },
    nds: {
        id: "nds",
        label: CART_STYLES.nds.label,
        output: { ...CART_STYLES.nds.image },
        hint: "建议 395 : 374（约 1.06:1），至少 395×374。封面从顶部 logo 黑条左上角开始铺满标签区，卡带最后盖上来，只从中间镂空窗露出；封面顶部会被黑条盖住。",
    },
    fc: {
        id: "fc",
        label: CART_STYLES.fc.label,
        output: { ...CART_STYLES.fc.image },
        hint: "建议 592 : 290（约 2.04:1）的横版图，至少 592×290。比例不符会拉伸填满整块标签窗。",
    },
    nes: {
        id: "nes",
        label: CART_STYLES.nes.label,
        output: { ...CART_STYLES.nes.image },
        hint: "建议 323 : 527（约 0.61:1）的竖版图，至少 323×527。比例不符会拉伸填满贴纸窗。",
    },
};

/**
 * 该游戏类型可用的**封面类型** id 列表（顺序即展示顺序、第一个是默认）。
 *
 * 这个顺序同时是三处的顺序来源：美化弹框那排单选、编辑弹框「封面类型」的单选、
 * 游戏中心「全部游戏」在游戏类型分组内按封面类型分子网格。返回空数组 = 该类型
 * 不支持美化封面，也就永远没有封面类型（`games.cover_type` 为空）。
 *
 * 后端权威是 `backend/games/models.py` 的 `COVER_TYPES_BY_GAME_TYPE`，**两边的 id
 * 集合与顺序必须逐字一致**（后端是接口只认的取值来源，这里是展示层镜像）。
 */
export function coverTypesFor(gameType) {
    return STYLE_BY_GAME_TYPE[gameType] || [];
}

/** 封面类型 id → 展示名（DISK / GB / GBC / GBA / FC / NES）；空值或未知 id 返回空串。 */
export function coverTypeLabel(value) {
    return STYLE_META[value]?.label || "";
}

/**
 * 按游戏类型取可用的美化样式；返回空数组 = 该类型不支持美化（调用方据此决定按不按得出按钮）。
 */
export function beautifyStylesFor(gameType) {
    return coverTypesFor(gameType).map((id) => STYLE_META[id]);
}
