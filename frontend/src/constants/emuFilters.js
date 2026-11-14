/**
 * 模拟器播放页的「复古滤镜」清单，按游戏类型给出可选值。
 *
 * 一个滤镜由两部分组成（哪部分为空就跳过那部分）：
 *   options —— 内核选项（键值对）。引擎启动前从设置块写进内核选项文件；
 *              运行中切换则逐个 setVariable（见宿主页的 setFilter）。
 *   shader  —— EmulatorJS 内置 GLSL 着色器的**键名**（见引擎里的 window.EJS_SHADERS，
 *              有的键带 .glslp 后缀，必须一字不差）。空串表示这个滤镜不用着色器。
 *
 * 着色器是所有内核通用的（引擎层面；34 个 core 都导出了 shader_enable），
 * 所以每个机种都配 CRT 档；内核选项则要看默认内核有没有那个选项——
 * 下面每条都对着各内核源码与随包 wasm 核过（取值、关闭值、默认值）。
 * 用户在引擎菜单里把默认内核切走之后，原生选项可能失效，只有着色器仍然生效。
 *
 * 界面文案只能是中文，着色器原名（lottes 等）作为专名保留。
 * 每台机器的列表第一项必须是「无滤镜」：它是默认值，也是表以外的取值回落的目标。
 *
 * 本地记忆只记条目 id（见播放页的 games.emu.filters），不随账号走。
 */

const NONE = { id: "none", label: "无滤镜", shader: "", options: null };

/** 「无滤镜」的条目本身：播放页在清单里找不到当前选择时用它兜底。 */
export const EMU_FILTER_NONE = NONE;

// 所有平台共用的 CRT 着色器三档（引擎内置，键名见 window.EJS_SHADERS）。
// 刻意不用 crt-geom：它会弯曲/缩放几何，会破坏 NDS 拆屏与机壳洞的对齐。
const CRT_EASY = {
    id: "crt-easymode",
    label: "CRT 简易",
    shader: "crt-easymode.glslp",
    options: null,
};
const CRT_ZFAST = { id: "crt-zfast", label: "CRT zfast", shader: "crt-zfast", options: null };
const CRT_LOTTES = { id: "crt-lottes", label: "CRT lottes", shader: "crt-lottes", options: null };

// full = 低分辨率 2D 机种；light = 高分辨率 / 3D 机种，去掉较重的 lottes。
const CRT_FULL = [CRT_EASY, CRT_ZFAST, CRT_LOTTES];
const CRT_LIGHT = [CRT_EASY, CRT_ZFAST];

const withNone = (entries) => [NONE, ...entries];

export const EMU_FILTERS = {
    // FC/NES（fceumm）：Blargg 的 NTSC 滤镜模拟各种视频信号
    nes: withNone([
        { id: "composite", label: "复合", shader: "", options: { fceumm_ntsc_filter: "composite" } },
        { id: "svideo", label: "S-Video", shader: "", options: { fceumm_ntsc_filter: "svideo" } },
        { id: "mono", label: "单色", shader: "", options: { fceumm_ntsc_filter: "monochrome" } },
        ...CRT_FULL,
    ]),
    // SFC/SNES（snes9x）：Blargg NTSC 比 fceumm 多一档 RF 天线
    snes: withNone([
        { id: "composite", label: "复合", shader: "", options: { snes9x_blargg: "composite" } },
        { id: "rf", label: "RF", shader: "", options: { snes9x_blargg: "rf" } },
        { id: "mono", label: "单色", shader: "", options: { snes9x_blargg: "monochrome" } },
        ...CRT_FULL,
    ]),
    // GB/GBC（gambatte）：真机 LCD 的两档拖影 + GBC 色彩校正
    gb: withNone([
        { id: "lcd", label: "液晶", shader: "", options: { gambatte_mix_frames: "mix" } },
        {
            id: "lcd-ghost",
            label: "液晶强拖影",
            shader: "",
            options: { gambatte_mix_frames: "lcd_ghosting" },
        },
        {
            id: "gbc-color",
            label: "GBC 色彩",
            shader: "",
            options: { gambatte_gbc_color_correction: "GBC only" },
        },
        ...CRT_FULL,
    ]),
    // GBA（mgba）：色彩校正 + 两档帧混合
    gba: withNone([
        {
            id: "lcd",
            label: "液晶",
            shader: "",
            options: { mgba_color_correction: "GBA", mgba_interframe_blending: "mix_smart" },
        },
        {
            id: "lcd-ghost",
            label: "液晶强拖影",
            shader: "",
            options: { mgba_color_correction: "GBA", mgba_interframe_blending: "lcd_ghosting" },
        },
        ...CRT_FULL,
    ]),
    // MD（genesis_plus_gx）：复合信号 + Nomad 那块 LCD 的鬼影
    segaMD: withNone([
        {
            id: "composite",
            label: "复合",
            shader: "",
            options: { genesis_plus_gx_blargg_ntsc_filter: "composite" },
        },
        {
            id: "lcd-ghost",
            label: "Nomad 鬼影",
            shader: "",
            options: { genesis_plus_gx_lcd_filter: "enabled" },
        },
        ...CRT_FULL,
    ]),
    // GG（同一个 genesis_plus_gx 内核）：Game Gear 本来就是 LCD，鬼影排在前
    segaGG: withNone([
        {
            id: "lcd-ghost",
            label: "GG 鬼影",
            shader: "",
            options: { genesis_plus_gx_lcd_filter: "enabled" },
        },
        {
            id: "composite",
            label: "复合",
            shader: "",
            options: { genesis_plus_gx_blargg_ntsc_filter: "composite" },
        },
        ...CRT_FULL,
    ]),
    // Sega CD（genesis_plus_gx）：与 MD 同核
    segaCD: withNone([
        {
            id: "composite",
            label: "复合",
            shader: "",
            options: { genesis_plus_gx_blargg_ntsc_filter: "composite" },
        },
        ...CRT_FULL,
    ]),
    // SMS（smsplus）
    segaMS: withNone([
        { id: "composite", label: "复合", shader: "", options: { smsplus_ntsc_filter: "composite" } },
        { id: "svideo", label: "S-Video", shader: "", options: { smsplus_ntsc_filter: "svideo" } },
        { id: "mono", label: "单色", shader: "", options: { smsplus_ntsc_filter: "monochrome" } },
        ...CRT_FULL,
    ]),
    // Atari 2600（stella2014）：帧间混合模拟 CRT 荧光粉拖影
    atari2600: withNone([
        { id: "mix-frames", label: "混合轻", shader: "", options: { stella2014_mix_frames: "mix" } },
        {
            id: "mix-frames-strong",
            label: "混合强",
            shader: "",
            options: { stella2014_mix_frames: "ghost_75" },
        },
        ...CRT_FULL,
    ]),
    // Lynx（handy）：真机 LCD 拖影，2 / 4 帧两档
    lynx: withNone([
        {
            id: "lcd-ghost",
            label: "液晶轻拖影",
            shader: "",
            options: { handy_lcd_ghosting: "2frames" },
        },
        {
            id: "lcd-ghost-strong",
            label: "液晶强拖影",
            shader: "",
            options: { handy_lcd_ghosting: "4frames" },
        },
        ...CRT_FULL,
    ]),
    // Atari 5200（a5200）：帧间混合，与 Atari 2600 同一套取值
    atari5200: withNone([
        { id: "mix-frames", label: "混合轻", shader: "", options: { a5200_mix_frames: "mix" } },
        {
            id: "mix-frames-strong",
            label: "混合强",
            shader: "",
            options: { a5200_mix_frames: "ghost_75" },
        },
        ...CRT_FULL,
    ]),
    // PET（vice_xpet）：VICE 的 CRTC 滤镜，模拟 PET 显示器的荧光余辉
    pet: withNone([
        {
            id: "crt-filter",
            label: "CRT 显示",
            shader: "",
            options: { vice_crtc_filter: "enabled" },
        },
        ...CRT_FULL,
    ]),
    // 其余低分辨率 2D 机种：只给 CRT
    nds: withNone(CRT_FULL),
    pce: withNone(CRT_FULL),
    pcfx: withNone(CRT_LIGHT),
    ngp: withNone(CRT_FULL),
    ws: withNone(CRT_FULL),
    atari7800: withNone(CRT_FULL),
    coleco: withNone(CRT_FULL),
    c64: withNone(CRT_FULL),
    c128: withNone(CRT_FULL),
    plus4: withNone(CRT_FULL),
    vic20: withNone(CRT_FULL),
    amiga: withNone(CRT_FULL),
    arcade: withNone(CRT_FULL),
    sega32x: withNone(CRT_LIGHT),
    // 高分辨率 / 3D 机种：只给轻量档，保护移动端与文字清晰度
    n64: withNone(CRT_LIGHT),
    psx: withNone(CRT_LIGHT),
    segaSaturn: withNone(CRT_LIGHT),
    "3do": withNone(CRT_LIGHT),
    jaguar: withNone(CRT_LIGHT),
    dos: withNone(CRT_LIGHT),
    psp: withNone(CRT_LIGHT),
    vb: withNone(CRT_LIGHT),
};

/** 未在表里出现的机种（含 sega / mame 兜底 key）：只给 full CRT，保证入口永远存在。 */
const DEFAULT_FILTERS = withNone(CRT_FULL);

/**
 * 各内核选项的**关闭值**（切滤镜时把上一个滤镜留下的键复位成它）。
 * 不统一：mGBA 用 `OFF`，其余内核用 `disabled`——真机行为各不相同，所以逐个写死，
 * 不能拿一个常量去关所有的键（关不干净的滤镜会一直留在画面上）。
 */
export const EMU_FILTER_OFF_VALUES = {
    mgba_color_correction: "OFF",
    mgba_interframe_blending: "OFF",
    gambatte_mix_frames: "disabled",
    gambatte_gbc_color_correction: "disabled",
    fceumm_ntsc_filter: "disabled",
    snes9x_blargg: "disabled",
    genesis_plus_gx_blargg_ntsc_filter: "disabled",
    genesis_plus_gx_lcd_filter: "disabled",
    smsplus_ntsc_filter: "disabled",
    handy_lcd_ghosting: "disabled",
    stella2014_mix_frames: "disabled",
    a5200_mix_frames: "disabled",
    vice_crtc_filter: "disabled",
};

/**
 * 滤镜会用到的**引擎设置键**：所有滤镜的内核选项名 + 固定的 shader 键。
 * 播放页在写入滤镜前把这张表里的键全部复位；云端读写时也按它剔除滤镜键——
 * 滤镜只留在本机，不进账号。
 */
export const EMU_FILTER_SETTING_KEYS = (() => {
    const keys = new Set(["shader"]);
    for (const list of Object.values(EMU_FILTERS)) {
        for (const filter of list) {
            for (const name of Object.keys(filter.options || {})) {
                keys.add(name);
            }
        }
    }
    for (const name of Object.keys(EMU_FILTER_OFF_VALUES)) {
        keys.add(name);
    }
    return Array.from(keys);
})();

/**
 * 各机种的**默认内核**（EmulatorJS `getCores()` 的第一项）。
 * 原生选项只对这些内核有效：用户从引擎设置菜单把内核切走之后，键名对不上，
 * 宿主页据此判断并提示「仅着色器生效」。表里没有的机种不传内核名。
 */
export const EMU_FILTER_CORES = {
    nes: "fceumm",
    snes: "snes9x",
    gb: "gambatte",
    gba: "mgba",
    nds: "melonds",
    segaMD: "genesis_plus_gx",
    segaGG: "genesis_plus_gx",
    segaCD: "genesis_plus_gx",
    segaMS: "smsplus",
    atari2600: "stella2014",
    lynx: "handy",
    atari5200: "a5200",
    pet: "vice_xpet",
};

/** 按 id 取滤镜；清单里没有该 id（手改过 localStorage 等）就回落到「无滤镜」。 */
export function emuFilterFor(gameType, id) {
    const list = emuFiltersFor(gameType);
    return list.find((filter) => filter.id === id) || NONE;
}

/** 该机种的滤镜清单；没配到的机种回落到 full CRT。 */
export function emuFiltersFor(gameType) {
    return EMU_FILTERS[gameType] || DEFAULT_FILTERS;
}

/**
 * 该机种所有滤镜涉及的内核键 → 关闭值。
 * 运行中切滤镜时先按它复位本机种涉及的滤镜键，再下发新条目。
 */
export function emuFilterResets(gameType) {
    const resets = {};
    for (const filter of emuFiltersFor(gameType)) {
        for (const name of Object.keys(filter.options || {})) {
            resets[name] = EMU_FILTER_OFF_VALUES[name] || "disabled";
        }
    }
    return resets;
}

/**
 * 启动前写进引擎设置块的补丁：
 *   1) 所有受控键先写成关闭值；
 *   2) 覆盖选中条目的内核选项；
 *   3) 最后写 shader（空串写 "disabled"）。
 * 返回新对象，不改入参。
 */
export function emuFilterSettingsPatch(gameType, id) {
    const filter = emuFilterFor(gameType, id);
    const patch = { ...emuFilterResets(gameType) };
    Object.assign(patch, filter.options || {});
    patch.shader = filter.shader || "disabled";
    return patch;
}
