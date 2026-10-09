let ruffleReadyPromise = null;

/** 本页会话内 Ruffle 引擎是否已加载完成（首次冷加载前为 false）。 */
export function isRuffleLoaded() {
    return Boolean(window.RufflePlayer?.newest);
}

function loadRuffleScript() {
    if (window.RufflePlayer?.newest) {
        return Promise.resolve();
    }

    if (ruffleReadyPromise) {
        return ruffleReadyPromise;
    }

    ruffleReadyPromise = new Promise((resolve, reject) => {
        const existing = document.querySelector('script[data-ruffle="true"]');
        if (existing) {
            existing.addEventListener("load", () => resolve());
            existing.addEventListener("error", () => reject(new Error("Ruffle 脚本加载失败")));
            return;
        }

        const script = document.createElement("script");
        script.src = "/ruffle/ruffle.js";
        script.dataset.ruffle = "true";
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("Ruffle 脚本加载失败"));
        document.head.appendChild(script);
    });

    return ruffleReadyPromise;
}

// ---------------------------------------------------------------------------
// 下载进度截获：ruffle 自己发起的 WASM（引擎）与 SWF（游戏）下载，
// 由我们包一层 fetch 按真实字节折算进度，读完文件后重建 Response 交还 ruffle。
// 不改 ruffle 的加载逻辑，只“看”它的下载并如实上报。
// ---------------------------------------------------------------------------

let fetchProgressWrapped = false;
let progressHandler = null;
let requestSeq = 0;
const activeRequests = new Map(); // id -> { kind, loaded, total }
const finishedTotal = { engine: 0, game: 0 };
const lastEmit = {};

function classifyProgressUrl(rawUrl) {
    try {
        const url = new URL(rawUrl, window.location.href);
        if (url.origin !== window.location.origin) {
            return null;
        }
        const path = url.pathname;
        if (path.startsWith("/ruffle/") && path.endsWith(".wasm")) {
            return "engine";
        }
        if (path.startsWith("/game-assets/swf/")) {
            return "game";
        }
        // Service Worker 不可用时的退化直连路径
        if (/^\/api\/games\/\d+\/play$/.test(path)) {
            return "game";
        }
        return null;
    } catch {
        return null;
    }
}

function aggregateKind(kind) {
    let activeLoaded = 0;
    let activeTotal = 0;
    for (const record of activeRequests.values()) {
        if (record.kind !== kind) {
            continue;
        }
        activeLoaded += record.loaded;
        if (record.total) {
            activeTotal += record.total;
        }
    }
    const total = finishedTotal[kind] + activeTotal;
    const loaded = finishedTotal[kind] + activeLoaded;
    return { loaded, total, frac: total > 0 ? Math.min(1, loaded / total) : null };
}

// 每类下载做节流：至少隔 120ms 或跨过 0.5% 才发一次事件，避免高频重渲染。
function maybeEmitProgress(kind, force = false) {
    if (!progressHandler) {
        return;
    }
    const agg = aggregateKind(kind);
    const now = Date.now();
    const prev = lastEmit[kind];
    const step = prev?.frac != null && agg.frac != null ? Math.abs(agg.frac - prev.frac) : 1;
    if (force || now - (prev?.t || 0) >= 120 || (agg.frac != null && step >= 0.005)) {
        lastEmit[kind] = { t: now, frac: agg.frac };
        progressHandler({ kind, ...agg });
    }
}

function installFetchProgress() {
    if (fetchProgressWrapped || typeof window === "undefined" || !window.fetch) {
        return;
    }
    fetchProgressWrapped = true;
    const originalFetch = window.fetch.bind(window);

    window.fetch = async (input, init) => {
        let rawUrl = "";
        try {
            rawUrl = typeof input === "string" ? input : input instanceof Request ? input.url : "";
        } catch {
            return originalFetch(input, init);
        }

        // FlashPlayer 主动下载 SWF 时自行按字节计数，这里直接放行，避免重复整读一份内存。
        if (init && init.ruffleProgress === false) {
            return originalFetch(input, init);
        }

        // 当前没有进度订阅者时不做截获：让请求（含 SW 缓存命中）直接通过，避免多一次整读缓冲。
        if (!progressHandler) {
            return originalFetch(input, init);
        }

        const kind = classifyProgressUrl(rawUrl);
        if (!kind) {
            return originalFetch(input, init);
        }

        const response = await originalFetch(input, init);
        if (!response || !response.ok || !response.body) {
            return response;
        }

        const id = ++requestSeq;
        const total = Number(response.headers.get("Content-Length")) || null;
        activeRequests.set(id, { kind, loaded: 0, total });
        maybeEmitProgress(kind);

        const reader = response.body.getReader();
        const chunks = [];
        let loaded = 0;
        for (;;) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            if (value) {
                chunks.push(value);
                loaded += value.length;
                const record = activeRequests.get(id);
                if (record) {
                    record.loaded = loaded;
                }
                maybeEmitProgress(kind);
            }
        }

        const record = activeRequests.get(id);
        if (record) {
            finishedTotal[kind] += record.total || loaded;
            activeRequests.delete(id);
        }
        maybeEmitProgress(kind, true);

        const buffer = new Uint8Array(loaded);
        let offset = 0;
        for (const chunk of chunks) {
            buffer.set(chunk, offset);
            offset += chunk.length;
        }

        // 读完整个文件后才交给 ruffle；重建 Response，保留状态与类型头。
        const headers = new Headers(response.headers);
        headers.set("Content-Length", String(loaded));
        return new Response(buffer, {
            status: response.status,
            statusText: response.statusText,
            headers,
        });
    };
}

/** 幂等安装进度截获，并清空上一局残留计数。 */
export function prepareRuffleProgress() {
    installFetchProgress();
    activeRequests.clear();
    finishedTotal.engine = 0;
    finishedTotal.game = 0;
    lastEmit.engine = undefined;
    lastEmit.game = undefined;
}

/** 注册本局下载进度回调；返回注销函数。 */
export function subscribeRuffleProgress(handler) {
    progressHandler = handler;
    return () => {
        if (progressHandler === handler) {
            progressHandler = null;
        }
    };
}

export async function createRufflePlayer(container, swfUrl, onPhase, quality = "high") {
    onPhase?.("engine");
    await loadRuffleScript();
    onPhase?.("runtime");

    const ruffle = window.RufflePlayer.newest();
    const player = ruffle.createPlayer();
    // 尺寸由调用方（FlashPlayer）在读取原生分辨率后按所选分辨率写入具体像素值，
    // 这里只保证加载阶段有可见宽度。不要用 transform 缩放，
    // 那会把 ruffle 画布当位图放大而变糊。
    player.style.width = "100%";
    player.style.flex = "0 0 auto";
    container.replaceChildren(player);
    const instance = player.ruffle();
    // 不关 Ruffle 自带右键菜单：那会把游戏自身注册的右键项一并禁用、影响游戏右键。
    // 标题栏（画质/存档/全屏等）只是额外快捷入口，与官方右键共存。
    instance.config = {
        autoplay: "on",
        unmuteOverlay: "hidden",
        letterbox: "on",
        // 质量等价 Flash 的 Stage.quality（low / medium / high），加载期生效；
        // 改动时由 FlashPlayer.vue 重建播放器生效。
        quality,
    };
    onPhase?.("core");
    // 提前挂载进度截获，覆盖引擎 wasm 与随后 SWF 的下载。
    installFetchProgress();
    onPhase?.("movie");
    await instance.load(swfUrl);
    return player;
}

export function destroyRufflePlayer(container) {
    container.replaceChildren();
}

/**
 * Ruffle 存档（SharedObject）以浏览器 localStorage 为持久层：每个存档一条，
 * key 由 Ruffle 内核生成（含主机与播放路径），值为该 .sol 文件的 base64。
 * 与 Ruffle 自带「存档管理」读同一份数据。当前游戏运行中的最新进度要在
 * 播放器卸载/重载后才会写回这里，见 Ruffle issue #798。
 */

// 判定一段 base64 是否像一个 .sol 文件（复用 Ruffle 内部 isSolData 的头部结构校验）。
export function isB64SOL(value) {
    if (typeof value !== "string" || !value) {
        return false;
    }
    try {
        const bytes = atob(value);
        return (
            bytes.charCodeAt(0) === 0x00 &&
            bytes.charCodeAt(1) === 0xbf &&
            bytes.slice(6, 10) === "TCSO" &&
            [0x00, 0x04, 0x00, 0x00, 0x00, 0x00].every((v, i) => bytes.charCodeAt(10 + i) === v)
        );
    } catch {
        return false;
    }
}

/** 列出浏览器本地已由 Ruffle 落盘的存档（与 Ruffle「存档管理」看到的一致）。 */
export function listLocalSaves() {
    const saves = [];
    try {
        for (let i = 0; i < localStorage.length; i += 1) {
            const key = localStorage.key(i);
            const value = localStorage.getItem(key);
            if (isB64SOL(value)) {
                const rawName = String(key.split("/").pop() || key);
                saves.push({
                    key,
                    // 存档名可能带 .sol，也可能不带，下载时统一补齐后缀。
                    name: rawName.toLowerCase().endsWith(".sol") ? rawName.slice(0, -4) : rawName,
                });
            }
        }
    } catch {
        // 隐私模式等 localStorage 不可用场景，视为没有本地存档
    }
    // 名字相近的排一起，方便辨认。
    saves.sort((a, b) => a.name.localeCompare(b.name));
    return saves;
}

/** 把某个本地存档（base64 .sol）下载成可导入 Ruffle 的 .sol 文件。 */
export function downloadLocalSave(key, name) {
    let value;
    try {
        value = localStorage.getItem(key);
    } catch {
        return false;
    }
    if (!value) {
        return false;
    }
    const bytes = Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
    const blob = new Blob([bytes], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${name}.sol`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return true;
}
