/**
 * 模拟器播放页的「复古滤镜」清单，按游戏类型给出可选值。
 *
 * 一个滤镜由两部分组成（哪部分为空就跳过那部分）：
 *   options —— 内核选项（键值对）。引擎在**内核加载之前**把它写进内核设置文件，
 *              内核启动时据此初始化；运行中切换则逐个下发（见宿主页的 setFilter）。
 *   shader  —— EmulatorJS 内置 GLSL 着色器的**键名**（见引擎里的 window.EJS_SHADERS，
 *              有的键带 .glslp 后缀，必须一字不差）。空串表示这个滤镜不用着色器。
 *
 * 着色器是**所有内核通用**的（引擎层面：切换 = 写 /shader/shader.glslp + 调内核的
 * shader_enable，本项目 6 个内核的两种构建都导出了它），所以每个平台都配 CRT 系；
 * 内核选项则要看对应内核有没有那个选项——下面每条都对着各内核源码的
 * libretro_core_options.h 与随包 wasm 核过（取值、关闭值、默认值）。
 *
 * 界面文案只能是中文，着色器原名（lottes 等）作为专名保留。
 * 每台机器的列表第一项必须是「无」：它是默认值，也是表以外的取值回落的目标。
 */

const NONE = { id: "none", label: "无", shader: "", options: null };

/** 「无」的条目本身：播放页在清单里找不到当前选择时用它兜底。 */
export const EMU_FILTER_NONE = NONE;

// 所有平台共用的 CRT 着色器两项（引擎内置，键名见 window.EJS_SHADERS）
const CRT_LOTTES = { id: "crt-lottes", label: "CRT（lottes）", shader: "crt-lottes", options: null };
const CRT_EASYMODE = {
    id: "crt-easymode",
    label: "CRT（简易模式）",
    shader: "crt-easymode.glslp",
    options: null,
};

export const EMU_FILTERS = {
    // FC/NES（fceumm）：Blargg 的 NTSC 滤镜模拟各种视频信号
    nes: [
        NONE,
        { id: "composite", label: "复合信号", shader: "", options: { fceumm_ntsc_filter: "composite" } },
        { id: "svideo", label: "S-Video 信号", shader: "", options: { fceumm_ntsc_filter: "svideo" } },
        { id: "mono", label: "单色电视", shader: "", options: { fceumm_ntsc_filter: "monochrome" } },
        CRT_LOTTES,
        CRT_EASYMODE,
    ],
    // SFC/SNES（snes9x）：Blargg NTSC 比 fceumm 多一档 RF 天线
    snes: [
        NONE,
        { id: "composite", label: "复合信号", shader: "", options: { snes9x_blargg: "composite" } },
        { id: "rf", label: "RF 天线", shader: "", options: { snes9x_blargg: "rf" } },
        { id: "mono", label: "单色电视", shader: "", options: { snes9x_blargg: "monochrome" } },
        CRT_LOTTES,
        CRT_EASYMODE,
    ],
    // GB/GBC（gambatte）：真机 LCD 的两档拖影（没有 mGBA 那档 mix_smart）
    gb: [
        NONE,
        { id: "lcd", label: "真机液晶", shader: "", options: { gambatte_mix_frames: "mix" } },
        {
            id: "lcd-ghost",
            label: "真机液晶（强拖影）",
            shader: "",
            options: { gambatte_mix_frames: "lcd_ghosting" },
        },
        CRT_LOTTES,
        CRT_EASYMODE,
    ],
    // GBA（mgba）
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
    // MD（genesis_plus_gx）：复合信号 + Nomad 那块 LCD 的鬼影
    segaMD: [
        NONE,
        {
            id: "composite",
            label: "复合信号",
            shader: "",
            options: { genesis_plus_gx_blargg_ntsc_filter: "composite" },
        },
        {
            id: "lcd-ghost",
            label: "LCD 鬼影（Nomad）",
            shader: "",
            options: { genesis_plus_gx_lcd_filter: "enabled" },
        },
        CRT_LOTTES,
        CRT_EASYMODE,
    ],
    // GG（同一个 genesis_plus_gx 内核）：Game Gear 本来就是 LCD，鬼影排在前
    segaGG: [
        NONE,
        {
            id: "lcd-ghost",
            label: "LCD 鬼影（Game Gear 屏）",
            shader: "",
            options: { genesis_plus_gx_lcd_filter: "enabled" },
        },
        {
            id: "composite",
            label: "复合信号",
            shader: "",
            options: { genesis_plus_gx_blargg_ntsc_filter: "composite" },
        },
        CRT_LOTTES,
        CRT_EASYMODE,
    ],
    // SMS（smsplus）
    segaMS: [
        NONE,
        { id: "composite", label: "复合信号", shader: "", options: { smsplus_ntsc_filter: "composite" } },
        { id: "svideo", label: "S-Video 信号", shader: "", options: { smsplus_ntsc_filter: "svideo" } },
        { id: "mono", label: "单色电视", shader: "", options: { smsplus_ntsc_filter: "monochrome" } },
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
    gambatte_mix_frames: "disabled",
    fceumm_ntsc_filter: "disabled",
    snes9x_blargg: "disabled",
    genesis_plus_gx_blargg_ntsc_filter: "disabled",
    genesis_plus_gx_lcd_filter: "disabled",
    smsplus_ntsc_filter: "disabled",
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

/**
 * 引擎内置着色器的**键名 → 显示名**（键名见引擎里的 window.EJS_SHADERS，一字不差）。
 * 上面表里用到的两个 CRT 也在其中，所以面板里的名字与引擎自带菜单里的一致。
 * 引擎升级后若多出新的着色器也没关系：`emuShaderLabel` 会回落到键名本身。
 */
export const EMU_SHADER_LABELS = {
    "crt-lottes": "CRT（lottes）",
    "crt-easymode.glslp": "CRT（简易模式）",
    "crt-aperture.glslp": "CRT（荫栅式）",
    "crt-beam": "CRT（电子束）",
    "crt-caligari": "CRT（caligari）",
    "crt-geom.glslp": "CRT（几何）",
    "crt-mattias.glslp": "CRT（马蒂亚斯）",
    "crt-yeetron": "CRT（yeetron）",
    "crt-zfast": "CRT（zfast）",
    "2xScaleHQ.glslp": "2xScaleHQ",
    "4xScaleHQ.glslp": "4xScaleHQ",
    sabr: "SABR",
    bicubic: "Bicubic",
    "mix-frames": "Mix frames",
};

/** 着色器键名 → 显示名；不认识的直接给键名（引擎加过新着色器时就这样显示）。 */
export function emuShaderLabel(name) {
    return EMU_SHADER_LABELS[name] || name;
}

/** 内核选项的规范化签名：与顺序无关，用于比较两个条目的选项是否同一套。 */
export function filterOptionsKey(options) {
    return Object.entries(options || {})
        .map(([name, value]) => `${name}=${value}`)
        .sort()
        .join(",");
}

/**
 * 引擎自带菜单里换了着色器之后，找/造对应的滤镜条目。
 *
 * 引擎菜单（底部工具栏 → 图形设置 → 着色器）是个「试衣间」：它改完着色器后，本函数找一条
 * **同一套内核选项、着色器换成新值**的条目；表里没有就照当前条目的选项造一条新的，
 * 由调用方记住（这样引擎菜单里的改动不会在下次进游戏时被本页的重置逻辑丢掉）。
 * 返回 `{ entry, created }`：`created=true` 表示条目是刚造出来的、需要持久化。
 */
export function filterForShader(list, current, shader) {
    const key = filterOptionsKey(current.options);
    const hit = list.find(
        (item) => filterOptionsKey(item.options) === key && (item.shader || "") === shader,
    );
    if (hit) {
        return { entry: hit, created: false };
    }
    const base = list.find((item) => filterOptionsKey(item.options) === key);
    const label = shader
        ? base && base.id !== "none"
            ? `${base.label} + ${emuShaderLabel(shader)}`
            : emuShaderLabel(shader)
        : base
          ? base.label
          : "自定义";
    return {
        entry: { id: `auto:${shader}|${key}`, label, options: current.options || null, shader },
        created: true,
    };
}
