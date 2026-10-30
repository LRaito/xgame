/**
 * 模拟器（EmulatorJS）设置块在浏览器 localStorage 里的读写。
 *
 * 引擎把「键位 + 选项 + 金手指」整块写在一个按游戏隔离的键里：
 *   ejs-{gameId}-{系统名}-{游戏名}-settings
 * 系统名那段等于各平台 gameTypes 里的 core（引擎的 getCore(true) 对系统名原样返回）。
 *
 * 引擎只在启动流程里（started 置位之前）读一次这个键，之后再写不会被采纳，
 * 所以「用云端的设置覆盖本机」必须赶在引擎起来之前写完——这正是本模块的用途。
 *
 * 值必须是 {controlSettings: Object, settings: Object, cheats: Array}：
 * 引擎会逐项校验，任一不合规就整块丢弃，故写入前先按同样规则挡一层。
 */

/** 引擎读写设置用的键名。 */
export function engineSettingsKey(gameId, system, gameName) {
    return `ejs-${gameId}-${system}-${gameName}-settings`;
}

/** 是否是引擎认得的设置块（三项都在且类型正确）。 */
export function isValidEngineSettings(value) {
    return Boolean(
        value &&
            typeof value === "object" &&
            !Array.isArray(value) &&
            value.controlSettings &&
            typeof value.controlSettings === "object" &&
            !Array.isArray(value.controlSettings) &&
            value.settings &&
            typeof value.settings === "object" &&
            !Array.isArray(value.settings) &&
            Array.isArray(value.cheats),
    );
}

/** 读当前设置块的原始 JSON 串；键不存在或内容不合规返回 null。 */
export function readEngineSettingsRaw(key) {
    if (!key) {
        return null;
    }
    try {
        const raw = localStorage.getItem(key);
        if (!raw) {
            return null;
        }
        return isValidEngineSettings(JSON.parse(raw)) ? raw : null;
    } catch {
        return null;
    }
}

/** 写入设置块；内容不合规时拒绝并返回 false（不写坏引擎启动时要读的键）。 */
export function writeEngineSettings(key, value) {
    if (!key || !isValidEngineSettings(value)) {
        return false;
    }
    try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
    } catch {
        return false;
    }
}

// NDS 的屏幕布局由播放页的布局模式（- / =）和 iframe 的 ?nds= 参数控制，
// 引擎设置菜单里也已经隐藏这两项；这里仍要剔除，防止历史云端/本机设置把它们带回来。
const NDS_DISPLAY_OPTIONS = ["melonds_screen_layout", "melonds_screen_gap"];

/**
 * 剔除 NDS 的布局选项，返回**新对象**（不改入参）。
 *
 * 引擎在启动流程里会读设置块，而云端/本机存过的旧值优先级高于宿主页的
 * `EJS_defaultOptions`——不剔除的话，用户以前在引擎设置菜单里改过的布局会盖掉
 * 当前 `?nds=` 选定的模式，机壳、遮罩就对不上屏幕几何。非 NDS 或结构不完整的值原样返回。
 */
export function stripNdsDisplayOptions(value) {
    if (!isValidEngineSettings(value)) {
        return value;
    }
    const settings = value.settings;
    if (!NDS_DISPLAY_OPTIONS.some((key) => key in settings)) {
        return value;
    }
    const nextSettings = { ...settings };
    for (const key of NDS_DISPLAY_OPTIONS) {
        delete nextSettings[key];
    }
    return { ...value, settings: nextSettings };
}
