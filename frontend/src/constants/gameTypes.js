/**
 * 游戏类型展示适配器。
 *
 * **这里不再保存任何机种映射**：label、extensions、默认后缀全部来自
 * `GET /api/games/status`（后端由 `backend/games/platforms.py` 派生），
 * 缓存与查询在 `@/store/gameTypes`。本文件只保留同名函数，减少调用方改动。
 *
 * 唯一留在前端的类型信息是图标与角标这类纯 UI 元数据，见 store 的 `iconOf()`。
 */
import { extensionOfFilename, useGameTypesStore } from "@/store/gameTypes";

/** 按类型取展示元数据（id / label / kind / core / extensions / icon）。 */
export function gameTypeMeta(slug) {
    return useGameTypesStore().metaOf(slug);
}

/** 类型的中文名（用于下拉/表格），未知类型回退为类型值本身。 */
export function gameTypeLabel(slug) {
    return useGameTypesStore().labelOf(slug);
}

/** 该后缀的全部候选类型，顺序即后端 `GAME_TYPES` 顺序。 */
export function gameTypeCandidatesByExtension(extension) {
    return useGameTypesStore().candidatesOfExtension(extension);
}

/** 按本体文件名取候选类型（空数组 = 未收录格式）。 */
export function gameTypeCandidatesByFilename(filename) {
    return useGameTypesStore().candidatesOfFilename(filename);
}

/** 按本体文件名取默认类型（候选第 1 个）；未收录返回 null。 */
export function gameTypeByExtension(filename) {
    return gameTypeCandidatesByFilename(filename)[0] || null;
}

/** 地址路径里的扩展名（小写、含点），解析不出来返回空串。 */
export function extensionOfUrl(url) {
    try {
        const name = decodeURIComponent(new URL(String(url || "").trim()).pathname.split("/").pop() || "");
        return extensionOfFilename(name);
    } catch {
        return "";
    }
}

/** 按下载地址取候选类型；地址看不出后缀时返回空数组。 */
export function gameTypeCandidatesByUrl(url) {
    return gameTypeCandidatesByExtension(extensionOfUrl(url));
}
