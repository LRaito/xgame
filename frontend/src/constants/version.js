/* global __APP_VERSION__ */
/**
 * 构建期版本号，由 vite.config.js 的 define 注入，与产物里的 /version.txt 是同一个值
 * （见 vite.config.js 的 resolveAppVersion）。dev server 或未注入时为 "dev"，
 * 此时 utils/versionCheck.js 不启动轮询。
 */
export const APP_VERSION = typeof __APP_VERSION__ === "undefined" ? "dev" : __APP_VERSION__;
