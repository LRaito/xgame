/**
 * 「服务端已部署新版本」探测。
 *
 * 入口 HTML 现在由 nginx 强制 no-cache，新开标签页必然拿到新产物；但**已经打开、没刷新的
 * 页面**仍跑着旧代码（而且新镜像里旧哈希文件已不存在，切路由会 404），只有运行时比对版本号
 * 才能发现。这里定时拉取同源 /version.txt，与本页构建期注入的版本号比对，不一致就把
 * updateReady 置为该版本号，由 AppUpdateBanner 提示用户刷新。
 *
 * 用原生 fetch 而不是 utils/request.js：那是 /api 的 axios 实例，会带 CSRF 头、401 时跳
 * 登录页、失败时弹 ElMessage。版本探测必须静默失败。注册在 utils/gameAssetCache.js 的
 * Service Worker 只拦 /game-assets/ 前缀，本请求直接穿透，两者互不干扰。
 * 本模块永不抛错。
 */
import { ref } from "vue";
import { APP_VERSION } from "@/constants/version";

const VERSION_URL = "/version.txt";
// 5 分钟一轮：响应不到 1KB，页面隐藏时完全停发，个人应用量级可忽略
const POLL_INTERVAL_MS = 5 * 60 * 1000;
// 版本号只可能是短 ASCII。这条白名单与 nginx 的 try_files $uri =404 是两道独立防线，
// 防的是同一个坑：探针文件缺失时被 /index.html 兜底返回 200 + 整篇 HTML，
// 前端会把 HTML 当版本号，于是「提示有新版本 → 点击刷新 → 还是同一版 → 再提示」死循环。
const VERSION_PATTERN = /^[0-9a-zA-Z._-]{1,64}$/;

/** 探测到的新版本号；非空即表示需要提示用户刷新。 */
export const updateReady = ref("");

let timer = null;
let inFlight = false;
let started = false;
// 用户点过「稍后」的版本：同一版本不再打扰，出现更新的版本照常提示
let dismissedVersion = "";

/**
 * 启动探测。dev（本机 vite dev 没有 version.txt）或版本号不合法时直接不启动，
 * 避免每 5 分钟一次无谓的 404；HMR 本就即时生效。
 */
export function startVersionCheck() {
    if (started) {
        return true;
    }
    if (import.meta.env.DEV || !VERSION_PATTERN.test(APP_VERSION)) {
        return false;
    }
    started = true;
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("online", onOnline);
    schedule(POLL_INTERVAL_MS);
    return true;
}

/** 本次先不刷新。 */
export function dismissVersion() {
    dismissedVersion = updateReady.value;
    updateReady.value = "";
}

/**
 * 刷新页面。只做 location.reload() 就够：入口 HTML 已 no-cache，会带 ETag 回源校验，
 * 变了拿新的、没变走 304；新 HTML 引用的是新哈希的 /assets/*，长缓存不会命中旧文件。
 * 不要清 localStorage（里面是布局偏好与模拟器/Flash 存档），也不要拼时间戳查询串。
 */
export function reloadPage() {
    window.location.reload();
}

function schedule(delay) {
    if (timer) {
        clearTimeout(timer);
    }
    timer = setTimeout(check, delay);
}

async function check() {
    timer = null;
    if (inFlight) {
        schedule(POLL_INTERVAL_MS);
        return;
    }
    inFlight = true;
    try {
        const response = await fetch(VERSION_URL, {
            cache: "no-store",
            credentials: "same-origin",
        });
        if (response.ok) {
            const version = (await response.text()).trim();
            if (
                VERSION_PATTERN.test(version) &&
                version !== APP_VERSION &&
                version !== dismissedVersion
            ) {
                updateReady.value = version;
            }
        }
    } catch {
        // 网络抖动 / 离线：忽略，等下一轮
    } finally {
        inFlight = false;
        schedule(POLL_INTERVAL_MS);
    }
}

function onVisibilityChange() {
    if (document.visibilityState === "hidden") {
        // 页面不可见：停掉定时器，不再发请求
        if (timer) {
            clearTimeout(timer);
            timer = null;
        }
        return;
    }
    // 回到前台立刻查一次（最常见场景：切回来才发现已经部署过了）
    if (!timer && !inFlight) {
        schedule(0);
    }
}

function onOnline() {
    if (!timer && !inFlight) {
        schedule(0);
    }
}
