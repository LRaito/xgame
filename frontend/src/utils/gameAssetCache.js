/**
 * 游戏封面 / SWF 的同源 URL 生成 + Service Worker 缓存。
 * SW 可用时走 /game-assets/…（SW 拦截并按 key + updated_at 持久缓存，离线/跨会话复用）；
 * SW 不可用或首次安装尚未接管时，退化为直接请求后端流式接口，保证封面与游戏仍可显示/游玩。
 * ensureGameAssetSw 永不抛错，只返回 SW 是否已接管，调用方不应被它阻塞。
 */

const SW_URL = "/game-asset-sw.js";
let swReady = null;
let swUsable = false;

/**
 * 破缓存用的版本后缀：updated_at 在改封面/换本体/换类型/改名时都会刷新，
 * 是「这份内容变了没有」的可靠信号。
 */
function versionQuery(game) {
    return game.updated_at ? `?v=${encodeURIComponent(game.updated_at)}` : "";
}

export function gameCoverUrl(game) {
    if (!game || !game.cover_path) {
        return "";
    }
    if (swUsable) {
        const params = new URLSearchParams({
            key: game.cover_path,
            v: game.updated_at || "",
        });
        return `/game-assets/cover/${game.id}?${params}`;
    }
    // 兜底直连后端：这条同样要带版本号。游戏 id 会被复用（删掉最大 id 的游戏再新建
    // 可能拿回同一个 id），裸地址会让浏览器缓存把新封面渲染成旧封面。
    return `/api/games/${game.id}/cover${versionQuery(game)}`;
}

export function gameSwfUrl(game) {
    if (!game || !game.game_path) {
        return "";
    }
    if (swUsable) {
        const params = new URLSearchParams({
            key: game.game_path,
            v: game.updated_at || "",
            // 携带字节数，供 Service Worker 给下载进度提供总大小
            s: game.size || "",
        });
        return `/game-assets/swf/${game.id}?${params}`;
    }
    // 兜底直连后端：换本体时文件名（game.{后缀}）通常不变，光靠 id 认不出内容已经换了，
    // 必须带 updated_at，否则会加载到缓存里的旧 ROM
    return `/api/games/${game.id}/play${versionQuery(game)}`;
}

export async function ensureGameAssetSw() {
    if (!swReady) {
        swReady = initGameAssetSw();
    }
    return swReady;
}

async function initGameAssetSw() {
    if (!("serviceWorker" in navigator)) {
        return false;
    }
    try {
        const registration = await navigator.serviceWorker.register(SW_URL, {
            scope: "/",
        });
        if (registration.waiting) {
            registration.waiting.postMessage({ type: "SKIP_WAITING" });
        }
        await navigator.serviceWorker.ready;
        if (navigator.serviceWorker.controller) {
            swUsable = true;
            return true;
        }
        // 首次安装：等待 SW claim 接管当前页面；超时不强求，退回直连。
        swUsable = await new Promise((resolve) => {
            let settled = false;
            const timer = setTimeout(() => finish(false), 3000);
            function finish(value) {
                if (settled) {
                    return;
                }
                settled = true;
                clearTimeout(timer);
                navigator.serviceWorker.removeEventListener("controllerchange", onChange);
                resolve(value);
            }
            function onChange() {
                finish(true);
            }
            navigator.serviceWorker.addEventListener("controllerchange", onChange, {
                once: true,
            });
        });
        return swUsable;
    } catch {
        swUsable = false;
        return false;
    }
}
