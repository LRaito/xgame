/**
 * 本地存档（Ruffle SharedObject）的当前游戏收集与“最后更新时间”打点。
 *
 * Ruffle 把存档以 base64(.sol) 形式直接写进 localStorage，不经我们代码、也不带写入
 * 时间。本工具用一条自维护的索引记录每个存档属于哪个游戏、内容签名与最后更新时间：
 *
 * - 属于当前游戏 = 存档 key 命中当前 SWF 的路径 token（/game-assets/swf/{gameId}），
 *   或已在索引里登记为当前游戏（兜底 Ruffle key 格式变化）。
 * - 时间只在“首次见到该档 / 其内容发生变化”时更新。存档是游戏运行中产生、播放器卸载
 *   才落盘的（见 Ruffle issue #798），因此正常流程“游戏内存档 → 重启同步 → 打开面板”
 *   采集到的首次出现时间 ≈ 落盘时间。
 *
 * 该索引不加入 utils/auth.js 的登出清理清单：Ruffle 存档与 games.flash.* 本就跨登出
 * 保留，索引须与其一致，否则重登后时间戳全部丢失。
 */
import { isB64SOL } from "@/utils/ruffle";

const SAVE_INDEX_KEY = "x_game_save_index_v1";

/** 存档展示名：取 key 末段并去掉 .sol 后缀。 */
function solDisplayName(key) {
    const raw = String(key).split("/").pop() || String(key);
    return raw.toLowerCase().endsWith(".sol") ? raw.slice(0, -4) : raw;
}

function readIndex() {
    try {
        const raw = localStorage.getItem(SAVE_INDEX_KEY);
        const value = raw ? JSON.parse(raw) : {};
        return value && typeof value === "object" ? value : {};
    } catch {
        return {};
    }
}

function writeIndex(index) {
    try {
        localStorage.setItem(SAVE_INDEX_KEY, JSON.stringify(index));
    } catch {
        // 隐私模式等写失败场景忽略
    }
}

/** 内容签名：长度 + base64 末 64 字符，能捕捉“新增内容 / 同长度改内容”。 */
function signatureOf(value) {
    return `${value.length}:${value.slice(-64)}`;
}

function isCurrentGameSave(key, gameId, index) {
    const recorded = index[key];
    if (recorded && Number(recorded.gameId) === gameId) {
        return true;
    }
    // Ruffle 按 SWF 播放路径归属 key；数字边界避免 1 误匹配 13 这类前缀冲突
    const pattern = new RegExp(`/game-assets/swf/${gameId}(?![0-9])`);
    return pattern.test(key);
}

/**
 * 列出“当前游戏”的本地存档，并维护索引里的最后更新时间。
 * @returns {Array<{key: string, name: string, size: number, updatedAt: number|null, base64?: string}>}
 */
export function collectLocalSaves(gameId, opts = {}) {
    const withContent = Boolean(opts.withContent);
    const index = readIndex();
    let dirty = false;
    const entries = [];
    const liveKeys = new Set();

    try {
        for (let i = 0; i < localStorage.length; i += 1) {
            const key = localStorage.key(i);
            const value = localStorage.getItem(key);
            if (!isB64SOL(value)) {
                continue;
            }
            if (!isCurrentGameSave(key, gameId, index)) {
                continue;
            }
            liveKeys.add(key);
            const size = atob(value).length;
            const sig = signatureOf(value);
            const recorded = index[key];
            const now = Date.now();
            if (!recorded || Number(recorded.gameId) !== gameId) {
                index[key] = { gameId, name: solDisplayName(key), size, sig, updatedAt: now };
                dirty = true;
            } else if (recorded.sig !== sig) {
                recorded.size = size;
                recorded.sig = sig;
                recorded.name = solDisplayName(key);
                recorded.updatedAt = now;
                dirty = true;
            }
            const entry = {
                key,
                name: index[key].name,
                size,
                updatedAt: index[key].updatedAt,
            };
            if (withContent) {
                entry.base64 = value;
            }
            entries.push(entry);
        }
    } catch {
        // 隐私模式等 localStorage 不可用场景，视为没有本地存档
        return [];
    }

    // 清除该游戏已不存在的索引项（存档被 Ruffle/用户删掉等）
    for (const key of Object.keys(index)) {
        if (Number(index[key].gameId) === gameId && !liveKeys.has(key)) {
            delete index[key];
            dirty = true;
        }
    }
    if (dirty) {
        writeIndex(index);
    }

    entries.sort((a, b) => a.name.localeCompare(b.name));
    return entries;
}

/** 写入一条本地存档并登记时间（替换档 / 还原云端档都用它）。 */
export function writeLocalSave(gameId, key, base64) {
    localStorage.setItem(key, base64);
    const index = readIndex();
    index[key] = {
        gameId: Number(gameId),
        name: solDisplayName(key),
        size: atob(base64).length,
        sig: signatureOf(base64),
        updatedAt: Date.now(),
    };
    writeIndex(index);
}

/** 删除一条本地存档并清掉对应索引项。 */
export function deleteLocalSave(key) {
    localStorage.removeItem(key);
    const index = readIndex();
    if (index[key]) {
        delete index[key];
        writeIndex(index);
    }
}

/**
 * 由当前游戏某条既有存档的 key 派生一个新槽位的 key。
 * Ruffle 的 key 形如“{SWF 路径基座}/{存档名}”，同一游戏的 key 共享基座：
 * 上传新档时取任一条现存 key 去掉末段名字作为基座，接上新名（按基座是否带 .sol 补后缀）。
 */
export function buildKeyFromReference(referenceKey, name) {
    const ref = String(referenceKey);
    const index = ref.lastIndexOf("/");
    const base = index >= 0 ? ref.slice(0, index + 1) : "";
    const withDotSol = ref.toLowerCase().endsWith(".sol");
    return `${base}${name}${withDotSol ? ".sol" : ""}`;
}

/**
 * 当前游戏还没有任何本地存档、无 key 基座可参照时兜底：
 * 按 Ruffle 的归属规律构造 key —— 主机名（不带 scheme 与端口）+ 本游戏 SWF 播放路径 + 存档名，
 * 例如 127.0.0.1/game-assets/swf/2/gamelzy。
 * Ruffle 用 movie URL 的 hostname（不含端口）作为 key 前缀，不能用 location.host（含端口），
 * 否则开发端口下写入的 key 与 Ruffle 读取的 key 错位。
 */
export function buildKeyFromSwfOrigin(gameId, name) {
    const hostname = typeof window !== "undefined" ? window.location.hostname : "";
    return `${hostname}/game-assets/swf/${gameId}/${name}`;
}

/** base64 → .sol Blob，供“同步至云端”上传表单使用。 */
export function solBase64ToBlob(base64) {
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
    return new Blob([bytes], { type: "application/octet-stream" });
}

/** ArrayBuffer / Blob → base64，供“同步至本地”下载云端文件后写回 localStorage。 */
export async function blobToBase64(blob) {
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
}
