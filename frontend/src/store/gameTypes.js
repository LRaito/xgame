import { defineStore } from "pinia";
import { gamesStatusAPI } from "@/api/games";
import { CHUNK_SIZE_BYTES, SINGLE_FILE_MAX_BYTES } from "@/utils/chunkUpload";

/**
 * 游戏类型注册表：`/api/games/status` 的后端派生数据在前端的唯一缓存。
 *
 * 机种与后缀的映射只在 `backend/games/platforms.py` 维护，后端经 `/status` 下发；
 * 这里不再手写任何 label / extensions，避免第二份映射表漂移。
 *
 * 加载失败时保留 `loaded=false`，`metaOf()` 仍返回可用的最小对象：
 * 模拟器的 core 就是 game_type（EJS system key），所以播放页不会因为状态接口失败而打不开。
 */

const FLASH = "flash";
const H5 = "h5";

function kindOf(id) {
    if (id === FLASH) {
        return FLASH;
    }
    if (id === H5) {
        return H5;
    }
    return "emulator";
}

/** 卡片/列表用的图标：纯 UI 元数据，不参与机种映射。 */
function iconOf(id) {
    if (id === FLASH) {
        return "⚡";
    }
    if (id === H5) {
        return "🌐";
    }
    return "🎮";
}

/** 后端 BIOS 元数据 → 前端可用形状；没有 BIOS 需求时统一为 null。 */
function normalizeBios(raw) {
    if (!raw || typeof raw.file !== "string" || !raw.file) {
        return null;
    }
    return {
        file: raw.file,
        required_files: Array.isArray(raw.required_files)
            ? raw.required_files.filter((name) => typeof name === "string")
            : [],
        optional: raw.optional === true,
    };
}

/** 后端 `types` 的一条 → 前端可直接消费的元数据（补 core / icon）。 */
function decorateType(item) {
    const kind = item.kind || kindOf(item.id);
    const extensions = Array.isArray(item.extensions) ? item.extensions : [];
    const bundleExtensions = Array.isArray(item.bundle_extensions)
        ? item.bundle_extensions
        : [];
    return {
        ...item,
        kind,
        core: kind === "emulator" ? item.id : null,
        label: item.label || item.id,
        extensions,
        bundleExtensions,
        bundleEntries: Array.isArray(item.bundle_entries)
            ? item.bundle_entries
            : [],
        uploadExtensions: Array.isArray(item.upload_extensions)
            ? item.upload_extensions
            : [...new Set([...extensions, ...bundleExtensions])],
        multiFile: item.multi_file === true || bundleExtensions.length > 0,
        threads: item.threads === true,
        bios: normalizeBios(item.bios),
        icon: iconOf(item.id),
    };
}

/** 状态接口还没回来时的最小元数据；字段与后端 `types` 保持一致。 */
function fallbackMeta(id) {
    const kind = kindOf(id);
    return {
        id,
        label: id,
        kind,
        core: kind === "emulator" ? id : null,
        extensions: [],
        bundleExtensions: [],
        bundleEntries: [],
        uploadExtensions: [],
        multiFile: false,
        threads: false,
        default_extension: "",
        bios: null,
        icon: iconOf(id),
    };
}

function normalizeExtension(extension) {
    const value = String(extension || "").trim().toLowerCase();
    if (!value) {
        return "";
    }
    return value.startsWith(".") ? value : `.${value}`;
}

/** 文件名或 URL 的后缀（小写、含点）；取不到返回空串。 */
export function extensionOfFilename(name) {
    const value = String(name || "").trim().toLowerCase();
    const dot = value.lastIndexOf(".");
    return dot < 0 ? "" : value.slice(dot);
}

export const useGameTypesStore = defineStore("gameTypes", {
    state: () => ({
        types: [],
        gameTypes: [],
        bodyExtensions: [],
        extensionCandidates: {},
        defaultGameTypeByExtension: {},
        // 后端下发的上传阈值；没拿到时用 chunkUpload.js 的回退常量
        uploadLimits: null,
        loaded: false,
        loading: null,
        error: "",
    }),
    getters: {
        metaMap(state) {
            return Object.fromEntries(state.types.map((item) => [item.id, item]));
        },
        singleFileMaxBytes(state) {
            const value = Number(state.uploadLimits?.single_file_max_bytes);
            return value > 0 ? value : SINGLE_FILE_MAX_BYTES;
        },
        chunkSizeBytes(state) {
            const value = Number(state.uploadLimits?.chunk_size_bytes);
            return value > 0 ? value : CHUNK_SIZE_BYTES;
        },
        /** 文件选择框 accept 的全集：所有类型单文件 + 包内后缀（去重保序）。 */
        allUploadExtensions(state) {
            const result = [...state.bodyExtensions];
            for (const item of state.types) {
                for (const ext of item.uploadExtensions || []) {
                    if (!result.includes(ext)) {
                        result.push(ext);
                    }
                }
            }
            return result;
        },
    },
    actions: {
        /** 只请求一次；并发调用共用同一个 in-flight Promise，失败后下次可重试。 */
        async ensureLoaded() {
            if (this.loaded) {
                return;
            }
            if (this.loading) {
                return this.loading;
            }
            this.loading = (async () => {
                try {
                    const status = await gamesStatusAPI();
                    this.types = Array.isArray(status.types)
                        ? status.types.map(decorateType)
                        : [];
                    this.gameTypes = Array.isArray(status.game_types)
                        ? status.game_types
                        : this.types.map((item) => item.id);
                    this.bodyExtensions = Array.isArray(status.body_extensions)
                        ? status.body_extensions
                        : [];
                    this.extensionCandidates = status.extension_candidates || {};
                    this.defaultGameTypeByExtension =
                        status.default_game_type_by_extension || {};
                    this.uploadLimits =
                        status.upload && typeof status.upload === "object"
                            ? status.upload
                            : null;
                    this.loaded = this.types.length > 0;
                    this.error = this.loaded ? "" : "游戏类型信息为空";
                } catch (err) {
                    this.error = err?.message || "游戏类型信息加载失败";
                } finally {
                    this.loading = null;
                }
            })();
            return this.loading;
        },
        /** 类型元数据；未加载或未知类型返回最小回退对象。 */
        metaOf(id) {
            if (!id) {
                return null;
            }
            return this.metaMap[id] || fallbackMeta(id);
        },
        labelOf(id) {
            return this.metaOf(id)?.label || "";
        },
        candidatesOfExtension(extension) {
            const key = normalizeExtension(extension);
            return key ? this.extensionCandidates[key] || [] : [];
        },
        defaultOfExtension(extension) {
            const key = normalizeExtension(extension);
            if (!key) {
                return "";
            }
            return (
                this.defaultGameTypeByExtension[key] ||
                this.candidatesOfExtension(key)[0] ||
                ""
            );
        },
        candidatesOfFilename(name) {
            return this.candidatesOfExtension(extensionOfFilename(name));
        },
        defaultOfFilename(name) {
            return this.defaultOfExtension(extensionOfFilename(name));
        },
        uploadExtensionsOf(id) {
            return this.metaOf(id)?.uploadExtensions || [];
        },
        /** 一组文件可以落成哪些多文件类型：所有后缀都要在该类型的包内白名单里。 */
        bundleCandidatesOfFiles(files) {
            const extensions = (files || [])
                .map((file) =>
                    extensionOfFilename(typeof file === "string" ? file : file?.name),
                )
                .filter(Boolean);
            if (!extensions.length) {
                return [];
            }
            return this.types.filter(
                (item) =>
                    item.multiFile &&
                    extensions.every((ext) => item.bundleExtensions.includes(ext)),
            );
        },
        /** 该后缀只能作为多文件本体成员（cue / bin / m3u），不能单独成盘。 */
        isBundleOnlyExtension(extension) {
            const key = normalizeExtension(extension);
            if (!key) {
                return false;
            }
            const single = this.types.some((item) =>
                item.extensions.includes(key),
            );
            if (single) {
                return false;
            }
            return this.types.some((item) =>
                item.bundleExtensions.includes(key),
            );
        },
        reset() {
            this.types = [];
            this.gameTypes = [];
            this.bodyExtensions = [];
            this.extensionCandidates = {};
            this.defaultGameTypeByExtension = {};
            this.uploadLimits = null;
            this.loaded = false;
            this.loading = null;
            this.error = "";
        },
    },
});
