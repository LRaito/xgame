/**
 * 模拟器播放页的「复古滤镜」清单，按游戏类型给出可选值。
 *
 * 一个滤镜由两部分组成（哪部分为空就跳过那部分）：
 *   options —— 内核选项（键值对）。引擎在**内核加载之前**把它写进内核设置文件，
 *              内核启动时据此初始化；运行中切换则逐个下发（见宿主页的 setFilter）。
 *   shader  —— EmulatorJS 内置 GLSL 着色器的**键名**（见引擎里的 window.EJS_SHADERS，
 *              有的键带 .glslp 后缀，必须一字不差）。空串表示这个滤镜不用着色器。
 *
 * 所有键值都对着随包 EmulatorJS 4.2.3 与各内核源码的 libretro_core_options.h 核过。
 * 界面文案只能是中文，着色器原名（lottes 等）作为专名保留。
 * 每台机器的列表第一项必须是「无」：它是默认值，也是表以外的取值回落的目标。
 */

const NONE = { id: "none", label: "无", shader: "", options: null };

// 引擎内置的 CRT 着色器（键名见 window.EJS_SHADERS）
const CRT_LOTTES = { id: "crt-lottes", label: "CRT（lottes）", shader: "crt-lottes", options: null };
const CRT_EASYMODE = {
    id: "crt-easymode",
    label: "CRT（简易模式）",
    shader: "crt-easymode.glslp",
    options: null,
};

export const EMU_FILTERS = {
    // GBA（mgba）：色彩校正 + 拖影 + CRT
    gba: [
        NONE,
        {
            id: "lcd",
            label: "真机液晶",
            shader: "",
            options: {
                mgba_color_correction: "GBA",
                mgba_interframe_blending: "mix_smart",
            },
        },
        {
            id: "lcd-ghost",
            label: "真机液晶（强拖影）",
            shader: "",
            options: {
                mgba_color_correction: "GBA",
                mgba_interframe_blending: "lcd_ghosting",
            },
        },
        CRT_LOTTES,
        CRT_EASYMODE,
    ],
};

/**
 * 各内核选项的**关闭值**（切滤镜时把上一个滤镜留下的键复位成它）。
 * 不统一：mGBA 用 `OFF`，其余内核用 `disabled`——真机行为各不相同，所以逐个写死，
 * 不能拿一个常量去关所有的键（关不干净的滤镜会一直留在画面上）。
 */
const OFF_VALUES = {
    mgba_color_correction: "OFF",
    mgba_interframe_blending: "OFF",
};

/**
 * 滤镜会用到的**引擎设置键**：所有滤镜的内核选项名 + 固定的 shader 键。
 * 播放页在拉起引擎之前要把这些键从引擎设置块里清掉——引擎存过的旧值优先级高于
 * 本次启动传下去的内核默认值，不清就会把用户此刻选的滤镜顶掉。
 */
export const EMU_FILTER_SETTING_KEYS = (() => {
    const keys = new Set(["shader"]);
    for (const list of Object.values(EMU_FILTERS)) {
        for (const filter of list) {
            for (const key of Object.keys(filter.options || {})) {
                keys.add(key);
            }
        }
    }
    return [...keys];
})();

/** 取该游戏类型的滤镜清单；没配到返回 null（这类游戏不显示滤镜入口）。 */
export function emuFiltersFor(gameType) {
    return EMU_FILTERS[gameType] || null;
}

/**
 * 该游戏类型所有滤镜涉及的内核选项及其关闭值（`{键: 关闭值}`）。
 * 运行中切滤镜时宿主页先按它复位，否则上一个滤镜的取值会跟着新滤镜继续生效。
 */
export function emuFilterResets(gameType) {
    const resets = {};
    for (const filter of emuFiltersFor(gameType) || []) {
        for (const name of Object.keys(filter.options || {})) {
            resets[name] = OFF_VALUES[name] || "disabled";
        }
    }
    return resets;
}

/** 按 id 取滤镜；表里没有（换了清单、手改过 localStorage）就回落到「无」。 */
export function emuFilterFor(gameType, id) {
    const list = emuFiltersFor(gameType);
    if (!list) {
        return NONE;
    }
    return list.find((filter) => filter.id === id) || NONE;
}
