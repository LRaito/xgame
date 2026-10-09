/**
 * 模拟器游戏（EmulatorJS）的本地存档：每个游戏固定只有一份，写入即覆盖。
 *
 * 引擎自身只维护“单份浏览器即时存档”（IndexedDB `EmulatorJS-states` 的 `{base}.state`），
 * x 把它捕捉出来另存为本地档，用于下载留底与同步云端。
 *
 * - 内容键   x_emusave:{gameId}:state1   IndexedDB 里的 base64
 * - 索引     x_emusave_index_v1          内容键 → {gameId,id,name,size,updatedAt}
 *
 * 存档 .state 可达数百 KB～数 MB，内容存 IndexedDB（避免 localStorage 配额），
 * 元数据索引放 localStorage（体积小、同步列出方便）。IndexedDB 不可用（个别隐私模式）
 * 时降级写回 localStorage，功能等价。
 *
 * 存档固定叫 `save.state`（本地展示/下载、云端快照文件同名），内容键同时用作云端快照的
 * local_key，云还原时按它写回同一位置。
 * 索引不随登出清理：模拟器本地档与 Flash 本地档一致，跨登出保留。
 */
const EMU_INDEX_KEY = "x_emusave_index_v1";
const EMU_VALUE_PREFIX = "x_emusave";
/** 唯一槽位 id（键的一部分） */
const EMU_SLOT_ID = "state1";
/** 存档固定文件名：本地展示、下载与云端快照文件都用它 */
export const EMU_SAVE_FILENAME = "save.state";
/** 旧版「多槽位档库」→ 单档模型的一次性收敛标记 */
const LEGACY_PURGE_KEY = "x_emusave_single_v1";

const DB_NAME = "x_emu_saves";
const STORE_NAME = "saves";

const SINGLE_KEY_SUFFIX = `:${EMU_SLOT_ID}`;

/** 本地档内容键：形如 x_emusave:5:state1（ASCII，可安全作云端 local_key）。 */
export function emuValueKey(gameId) {
    return `${EMU_VALUE_PREFIX}:${gameId}:${EMU_SLOT_ID}`;
}

// ---------- IndexedDB 存取（内容），失败降级 localStorage ----------

function openDb() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME);
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function dbGet(key) {
    const db = await openDb();
    try {
        return await new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, "readonly");
            const request = tx.objectStore(STORE_NAME).get(key);
            request.onsuccess = () => resolve(request.result || null);
            request.onerror = () => reject(request.error);
        });
    } finally {
        db.close();
    }
}

async function dbPut(key, value) {
    const db = await openDb();
    try {
        await new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, "readwrite");
            const request = tx.objectStore(STORE_NAME).put(value, key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    } finally {
        db.close();
    }
}

async function dbDelete(key) {
    const db = await openDb();
    try {
        await new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, "readwrite");
            const request = tx.objectStore(STORE_NAME).delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    } finally {
        db.close();
    }
}

async function dbKeys() {
    const db = await openDb();
    try {
        return await new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, "readonly");
            const request = tx.objectStore(STORE_NAME).getAllKeys();
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    } finally {
        db.close();
    }
}

async function storageWrite(key, base64) {
    try {
        await dbPut(key, base64);
    } catch {
        // IndexedDB 不可用（隐私模式等）：降级到 localStorage
        try {
            localStorage.setItem(key, base64);
        } catch {
            // 双写都失败则忽略（调用方后续会因读不到内容而提示）
        }
    }
}

async function storageRead(key) {
    try {
        const value = await dbGet(key);
        if (value != null) {
            return value;
        }
    } catch {
        // 落到 localStorage 尝试
    }
    try {
        return localStorage.getItem(key);
    } catch {
        return null;
    }
}

async function storageRemove(key) {
    try {
        await dbDelete(key);
    } catch {
        // 忽略
    }
    try {
        localStorage.removeItem(key);
    } catch {
        // 忽略
    }
}

// ---------- 旧「多槽位档库」收敛为单档（一次性） ----------

/** 旧模型的键形如 x_emusave:{gameId}:slot-0；新模型只认 …:state1。 */
function isLegacyValueKey(key) {
    const text = String(key || "");
    return text.startsWith(`${EMU_VALUE_PREFIX}:`) && !text.endsWith(SINGLE_KEY_SUFFIX);
}

let purgePromise = null;

/**
 * 把历史遗留的「多槽位本地档」清干净，之后每个游戏只剩 state1 一份。
 * 只在首次调用时真正执行（结果记在 localStorage 标记里），重复调用共享同一 Promise。
 * 清掉的内容仍可从云端快照恢复。
 */
export function ensureSingleSlotModel() {
    if (!purgePromise) {
        purgePromise = purgeLegacySaves();
    }
    return purgePromise;
}

async function purgeLegacySaves() {
    try {
        if (localStorage.getItem(LEGACY_PURGE_KEY) === "1") {
            return;
        }
    } catch {
        // localStorage 不可用：不清也无妨（索引与内容都读不到）
        return;
    }
    await purgeLegacyContent();
    purgeLegacyIndex();
    try {
        localStorage.setItem(LEGACY_PURGE_KEY, "1");
    } catch {
        // 写不进标记则下次再跑一遍，无副作用
    }
}

async function purgeLegacyContent() {
    try {
        const stale = (await dbKeys()).filter(isLegacyValueKey);
        for (const key of stale) {
            await dbDelete(key);
        }
    } catch {
        // IndexedDB 不可用：内容本就写在 localStorage 里，下面照常清
    }
    try {
        const stale = [];
        for (let i = 0; i < localStorage.length; i += 1) {
            const key = localStorage.key(i);
            if (isLegacyValueKey(key)) {
                stale.push(key);
            }
        }
        stale.forEach((key) => localStorage.removeItem(key));
    } catch {
        // 忽略
    }
}

function purgeLegacyIndex() {
    const index = readIndex();
    let dirty = false;
    for (const key of Object.keys(index)) {
        if (isLegacyValueKey(key)) {
            delete index[key];
            dirty = true;
        }
    }
    if (dirty) {
        writeIndex(index);
    }
}

// ---------- 索引（localStorage，小体积、同步） ----------

function readIndex() {
    try {
        const raw = localStorage.getItem(EMU_INDEX_KEY);
        const value = raw ? JSON.parse(raw) : {};
        return value && typeof value === "object" ? value : {};
    } catch {
        return {};
    }
}

function writeIndex(index) {
    try {
        localStorage.setItem(EMU_INDEX_KEY, JSON.stringify(index));
    } catch {
        // 隐私模式等写失败场景忽略
    }
}

function byteSizeOfBase64(base64) {
    const text = String(base64 || "");
    const padding = text.endsWith("==") ? 2 : text.endsWith("=") ? 1 : 0;
    return Math.floor((text.length * 3) / 4) - padding;
}

// ---------- 对外 API ----------

/**
 * 某游戏当前的本地档（仅元数据）；没有返回 null。
 * @returns {{key: string, id: string, name: string, size: number, updatedAt: number}|null}
 */
export function getLocalEmuSave(gameId) {
    const key = emuValueKey(gameId);
    const meta = readIndex()[key];
    if (!meta) {
        return null;
    }
    return {
        key,
        id: EMU_SLOT_ID,
        name: EMU_SAVE_FILENAME,
        size: Number(meta.size) || 0,
        updatedAt: Number(meta.updatedAt) || 0,
    };
}

/**
 * 覆盖写入本地档：捕捉当前进度、导入 .state 文件、云端还原到本地都走它。
 * 存档固定叫 save.state，只有内容与更新时间会变。
 * @returns {Promise<string>} 内容键（也是云端快照的 local_key）
 */
export async function writeLocalEmuSave(gameId, { base64 }) {
    if (!base64) {
        throw new Error("存档内容为空。");
    }
    const key = emuValueKey(gameId);
    await storageWrite(key, base64);
    const index = readIndex();
    index[key] = {
        gameId: Number(gameId),
        id: EMU_SLOT_ID,
        name: EMU_SAVE_FILENAME,
        size: byteSizeOfBase64(base64),
        updatedAt: Date.now(),
    };
    writeIndex(index);
    return key;
}

/** 取当前本地档内容（base64）；不存在/不可读返回 null。 */
export async function getEmuSaveBase64(gameId) {
    return storageRead(emuValueKey(gameId));
}

/** 删除当前本地档并清掉索引项。 */
export async function deleteLocalEmuSave(gameId) {
    const key = emuValueKey(gameId);
    await storageRemove(key);
    const index = readIndex();
    if (index[key]) {
        delete index[key];
        writeIndex(index);
    }
}

/** base64 存档字节 → Blob，供“上传云端/下载到本机”用。 */
export function emuBase64ToBlob(base64, mime = "application/octet-stream") {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type: mime });
}
