/* global __APP_VERSION__ */
/**
 * 构建期版本号，由 vite.config.js 的 define 注入，与产物里的 /version.txt 是同一个值
 * （见 vite.config.js 的 resolveAppVersion）。dev server 或未注入时为 "dev"，
 * 此时 utils/versionCheck.js 不启动轮询。
 */
export const APP_VERSION = typeof __APP_VERSION__ === "undefined" ? "dev" : __APP_VERSION__;

/**
 * 侧栏展示用版本号：dev server 注入的是字符串 "dev"，显示成 v0.0.0；
 * 正式版形如 v1.0.0-<提交时间戳>（scripts/version.sh 产出），只保留到第一个 "-" 之前。
 * 不要用 DISPLAY_VERSION 替换 APP_VERSION——versionCheck.js 需要原始值与 /version.txt 比较。
 */
function formatDisplayVersion(version) {
    if (version === "dev") {
        return "v0.0.0";
    }
    const dash = version.indexOf("-");
    return dash === -1 ? version : version.slice(0, dash);
}

export const DISPLAY_VERSION = formatDisplayVersion(APP_VERSION);
