/**
 * 「美化封面」的样式配置：把一张普通封面合成成光盘 / 卡带的外观。
 *
 * 入口是游戏管理页编辑弹框「游戏封面」那行的「美化封面」按钮
 * （见 components/games/CoverBeautifyDialog.vue），**样式由游戏自己的类型决定**，
 * 用户不用选。所以这里除了几何常量，还提供 `beautifyStyleFor(gameType)` 查表：
 * 查不到 = 这个类型不支持美化，按钮整条不显示。
 *
 * 绘制算法在 utils/coverCompose.js（纯 canvas，无 Vue 依赖）。
 *
 * ---------------------------------------------------------------
 * 卡带底图与洞口几何
 * ---------------------------------------------------------------
 * 底图是外部的成品素材（机身 + 中间挖空的贴纸窗），三个数字一组：
 * 整图尺寸、洞口矩形、洞口圆角。**换素材必须同步改这三组数字**，否则封面会错位。
 * 底图文件自带一份 size.txt 规格说明，下面的值就是照它抄的，并且已逐像素核对过：
 *
 *   gbc-cart.png  438 × 503   洞口 (58, 163) 322 × 287   圆角 8    （洞口 322:287 ≈ 1.12:1）
 *   gba-cart.png  640 × 370   洞口 (88,  86) 464 × 235   圆角 12   （洞口 464:235 ≈ 1.97:1）
 *
 * 洞口在底图里是**真透明**的；洞口圆角之外仍是机身像素（GBA 是不透明的机身灰，
 * GBC 是半透明的凹槽阴影），所以合成时必须把封面裁成同样的圆角矩形再贴，
 * 那圈机身/阴影才不会被方形封面盖掉。
 */

/**
 * Flash 光盘的几何（程序化绘制，没有底图）。
 *
 * 比值沿用被删掉的那套卡片渲染：光盘直径只占整幅边长的 84%，四周留一圈透明。
 */
export const FLASH_DISC = {
    // 输出画布边长
    size: 1024,
    // 光盘直径占画布边长的比例（84cqw 的等价物）；四周留空是刻意的观感
    padRatio: 0.84,
    // 盘心 Flash 标志的边长占**光盘直径**的比例。
    // 注意基准与渐变不同：反光那几层渐变的百分比是占**盘半径**的，见 coverCompose.js。
    hubRatio: 0.15,
    logoUrl: "/flash-logo.png",
};

/** 卡带底图配置，按美化样式的 id 索引。 */
export const CART_STYLES = {
    gb: {
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
};

/** 游戏类型 → 美化样式 id。不在这张表里的类型不显示「美化封面」按钮。 */
const STYLE_BY_GAME_TYPE = {
    flash: "flash",
    gb: "gb",
    gba: "gba",
};

/**
 * 三种样式在弹框里显示给用户的建议尺寸。
 *
 * `hint` 说的是**输入**建议（用户该拿多大的图来美化），`output` 是合成结果尺寸。
 * 卡带那两条要讲清楚比例不符会被拉伸——合成是 `object-fit: fill` 的做法，
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
    gba: {
        id: "gba",
        label: CART_STYLES.gba.label,
        output: { ...CART_STYLES.gba.image },
        hint: "建议 464 : 235（约 1.97:1），至少 464×235。比例不符会拉伸填满卡带贴纸窗。",
    },
};

/**
 * 按游戏类型取美化配置；该类型不支持美化时返回 null（调用方据此决定按不按得出按钮）。
 */
export function beautifyStyleFor(gameType) {
    const id = STYLE_BY_GAME_TYPE[gameType];
    return id ? STYLE_META[id] : null;
}
