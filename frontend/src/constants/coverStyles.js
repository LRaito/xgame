/**
 * 「美化封面」的样式配置：把一张普通封面合成成光盘 / 卡带的外观。
 *
 * 入口是游戏管理页编辑弹框「游戏封面」那行的「美化封面」按钮
 * （见 components/games/CoverBeautifyDialog.vue）。**一个游戏类型可以有好几种样式**，
 * 查表函数 `beautifyStylesFor(gameType)` 返回这个类型可用的那一组（顺序 = 弹框里
 * 「GB卡带 / GBC卡带」那个方框单选的顺序，第一个是默认选中的）；返回空数组 = 这个类型
 * 不支持美化，按钮整条不显示；只有一个样式时不出单选。
 *
 * 绘制算法在 utils/coverCompose.js（纯 canvas，无 Vue 依赖）。
 *
 * ---------------------------------------------------------------
 * 卡带底图与洞口几何
 * ---------------------------------------------------------------
 * 底图是成品素材——一张**没贴过贴纸的原始卡带**，中间那块贴纸窗已经填成机身色，
 * 三个数字一组：整图尺寸、洞口矩形、洞口圆角。**换素材必须同步改这三组数字**，
 * 否则封面会错位；下面的值已逐像素核对过：
 *
 *   gb-cart.png     426 × 500  洞口 (53, 151) 322 × 287   圆角 8   （洞口 322:287 ≈ 1.12:1）
 *   gbc-cart.png    438 × 503  洞口 (58, 163) 322 × 287   圆角 8   （洞口同上）
 *   gba-cart.png    640 × 370  洞口 (88,  86) 464 × 235   圆角 12  （洞口 464:235 ≈ 1.97:1）
 *   nes-jp-cart.png 700 × 460  洞口 (56,  54) 592 × 290   圆角 10  （洞口 592:290 ≈ 2.04:1）
 *   nes-us-cart.png 700 × 779  洞口 (283,  0) 323 × 527   圆角 10  （洞口 323:527 ≈ 0.61:1）
 *                                                          ↑ 洞口上边就是画布顶边，见下
 *
 * **要贴同一张画的多个样式，洞口尺寸必须做成一样**：同一张封面贴进哪个样式，成品里
 * 封面占的区域都得是同一个大小，不然观感对不上（底图按 `sx = 目标洞口宽 / 原洞口宽`、
 * `sy = 目标洞口高 / 原洞口高` 整图重采样，再按整数坐标重填一遍洞口）。
 * **本来就该贴不同画的样式各按自己的素材来，别去对齐**：FC 日版挖的是横版整块标签、
 * 美版挖的是竖版贴纸，形状差得远。
 *
 * `radius` 是**封面裁切**用的圆角（写一个数字 = 四角相同；也可以写成 `{ tl, tr, br, bl }`
 * 按角指定，没写的角按直角算，见 `cornerRadii()` 与 utils/coverCompose.js 的 `roundRectPath()`）。
 * 合成时按它 `clip()` 一刀，**圆角之外那圈底图像素要留着**（GBA 是机身灰、GB/GBC 是贴纸
 * 凹槽的阴影），不能被方形封面盖掉。
 *
 * **注意「底图填色」与「封面裁切」是两件事，`nes-us` 那张上最容易搞混**：它的洞口上边就是
 * 画布顶边（源图顶部被裁掉了，标签上边缘不在画面里），所以**底图填色时上面两角是直角**
 * （那两块本来就是洞口的一部分，必须一起填上，否则底图上会留两个透明缺口）；而**封面
 * 裁切仍然是四角 r=10**，裁掉的上两角露出的是底图填好的机身色。重跑底图填色时记得这点
 * （`clear_scene.py --radius 0,0,10,10`）。
 *
 * 底图本身带透明的地方只有卡带轮廓之外（缺口、四角），与洞口无关。
 */

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
    logoUrl: "/flash-logo.png",
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

/** 卡带底图配置，按样式 id 索引（id 与 STYLE_META、STYLE_BY_GAME_TYPE 里的键一一对应）。 */
export const CART_STYLES = {
    gb: {
        label: "GB卡带",
        url: "/gb-cart.png",
        image: { width: 426, height: 500 },
        hole: { x: 53, y: 151, width: 322, height: 287 },
        radius: 8,
    },
    gbc: {
        label: "GBC卡带",
        url: "/gbc-cart.png",
        image: { width: 438, height: 503 },
        hole: { x: 58, y: 163, width: 322, height: 287 },
        radius: 8,
    },
    gba: {
        label: "GBA卡带",
        url: "/gba-cart.png",
        image: { width: 640, height: 370 },
        hole: { x: 88, y: 86, width: 464, height: 235 },
        radius: 12,
    },
    "nes-jp": {
        label: "FC日版",
        url: "/nes-jp-cart.png",
        image: { width: 700, height: 460 },
        hole: { x: 56, y: 54, width: 592, height: 290 },
        radius: 10,
    },
    "nes-us": {
        label: "FC美版",
        url: "/nes-us-cart.png",
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
    nes: ["nes-jp", "nes-us"],
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
        label: "Flash光盘",
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
    "nes-jp": {
        id: "nes-jp",
        label: CART_STYLES["nes-jp"].label,
        // 游戏自己是日版时默认选它（见 CoverBeautifyDialog 的默认样式）
        cartridgeType: "jp",
        output: { ...CART_STYLES["nes-jp"].image },
        hint: "建议 592 : 290（约 2.04:1）的横版图，至少 592×290。比例不符会拉伸填满整块标签窗。",
    },
    "nes-us": {
        id: "nes-us",
        label: CART_STYLES["nes-us"].label,
        cartridgeType: "us",
        output: { ...CART_STYLES["nes-us"].image },
        hint: "建议 323 : 527（约 0.61:1）的竖版图，至少 323×527。比例不符会拉伸填满贴纸窗。",
    },
};

/**
 * 按游戏类型取可用的美化样式；返回空数组 = 该类型不支持美化（调用方据此决定按不按得出按钮）。
 */
export function beautifyStylesFor(gameType) {
    return (STYLE_BY_GAME_TYPE[gameType] || []).map((id) => STYLE_META[id]);
}
