/**
 * 游戏类型（game_type）展示层配置。
 *
 * 后端 backend/games/service.py 的 GAME_TYPES / 扩展名白名单是「可上传、可落库」
 * 的权威来源；这里只负责 UI 展示与播放器接线：显示名（纯展示，不进键名/路径）、
 * 中心分组文案、上传 accept 提示、以及 EmulatorJS 的 core（system key）。
 * 两者新增/修改类型时需同步。
 */

const GAME_TYPE_LIST = [
    {
        slug: "flash",
        label: "Flash",
        kind: "flash",
        core: null,
        extensions: [".swf"],
        icon: "⚡",
        description: "经典 Flash 作品，通过 Ruffle 模拟器运行。",
    },
    {
        slug: "h5",
        label: "HTML5",
        kind: "h5",
        core: null,
        extensions: [".zip"],
        icon: "🌐",
        description:
            "HTML5 网页游戏，上传 ZIP 后在浏览器内直接运行；沙箱运行，不支持云存档。",
        uploadHint: "仅支持 .zip，且压缩包根目录需包含 index.html",
    },
    {
        slug: "nes",
        label: "FC NES",
        kind: "emulator",
        core: "nes",
        extensions: [".nes"],
        icon: "🎮",
        description: "通过 EmulatorJS 在浏览器内运行；支持账号云存档。",
    },
    {
        slug: "snes",
        label: "SFC SNES",
        kind: "emulator",
        core: "snes",
        extensions: [".sfc", ".smc"],
        icon: "🎮",
        description: "通过 EmulatorJS 在浏览器内运行；支持账号云存档。",
    },
    {
        slug: "gb",
        label: "Game_Boy Color",
        kind: "emulator",
        core: "gb",
        extensions: [".gb", ".gbc"],
        icon: "🎮",
        description: "通过 EmulatorJS 在浏览器内运行；支持账号云存档。",
    },
    {
        slug: "gba",
        label: "Game_Boy_Advance",
        kind: "emulator",
        core: "gba",
        extensions: [".gba"],
        icon: "🎮",
        description: "通过 EmulatorJS 在浏览器内运行；支持账号云存档。",
    },
    {
        slug: "segaMD",
        label: "Mega_Drive Genesis",
        kind: "emulator",
        core: "segaMD",
        extensions: [".md", ".gen"],
        icon: "🎮",
        description: "通过 EmulatorJS 在浏览器内运行；支持账号云存档。",
    },
    {
        slug: "segaGG",
        label: "Game_Gear",
        kind: "emulator",
        core: "segaGG",
        extensions: [".gg"],
        icon: "🎮",
        description: "通过 EmulatorJS 在浏览器内运行；支持账号云存档。",
    },
    {
        slug: "segaMS",
        label: "Sega_Master_System",
        kind: "emulator",
        core: "segaMS",
        extensions: [".sms"],
        icon: "🎮",
        description: "通过 EmulatorJS 在浏览器内运行；支持账号云存档。",
    },
];

/** 全部可上传的本体扩展名（供上传控件的 accept 提示）。 */
const ALL_GAME_EXTENSIONS = GAME_TYPE_LIST.flatMap((type) => type.extensions);

/** 按本体文件名的扩展名猜类型，仅用于表单即时提示；落库类型以后端判定为准。 */
function gameTypeByExtension(filename) {
    const name = String(filename || "").toLowerCase();
    const dot = name.lastIndexOf(".");
    if (dot < 0) {
        return null;
    }
    const extension = name.slice(dot);
    const meta = GAME_TYPE_LIST.find((type) => type.extensions.includes(extension));
    return meta ? meta.slug : null;
}

/** 按类型取展示配置；未知类型返回 null。 */
export function gameTypeMeta(slug) {
    return GAME_TYPE_LIST.find((type) => type.slug === slug) || null;
}

/** 类型的中文名（用于下拉/表格），未知类型回退为类型值本身。 */
export function gameTypeLabel(slug) {
    return gameTypeMeta(slug)?.label || slug;
}

export { ALL_GAME_EXTENSIONS, GAME_TYPE_LIST, gameTypeByExtension };
