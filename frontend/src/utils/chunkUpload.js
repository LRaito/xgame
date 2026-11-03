import {
    abortGameUploadAPI,
    completeGameUploadAPI,
    createGameUploadAPI,
    uploadGameChunkAPI,
} from "@/api/games";

/** 后端 /status.upload 未加载时的回退值；正常情况下以后端下发为准。 */
export const SINGLE_FILE_MAX_BYTES = 30 * 1024 * 1024;
export const CHUNK_SIZE_BYTES = 16 * 1024 * 1024;
/** 并发、重试与等待间隔是前端策略，后端只约束分片大小。 */
export const CHUNK_CONCURRENCY = 5;
export const CHUNK_MAX_RETRIES = 5;
export const CHUNK_RETRY_DELAY_MS = 5000;

export function shouldUseChunkedUpload(file, singleFileMax = SINGLE_FILE_MAX_BYTES) {
    return Boolean(file && Number(file.size) > Number(singleFileMax || SINGLE_FILE_MAX_BYTES));
}

function abortError() {
    const error = new Error("上传已取消。");
    error.aborted = true;
    error.reported = true;
    return error;
}

function delay(ms, signal) {
    return new Promise((resolve, reject) => {
        if (signal.aborted) {
            reject(abortError());
            return;
        }
        const timer = setTimeout(() => {
            signal.removeEventListener("abort", onAbort);
            resolve();
        }, ms);
        function onAbort() {
            clearTimeout(timer);
            reject(abortError());
        }
        signal.addEventListener("abort", onAbort, { once: true });
    });
}

function joinSignal(external) {
    // 自己持有一个 controller：外部取消时转发；内部失败时也能停掉其余分片
    const controller = new AbortController();
    if (external) {
        if (external.aborted) {
            controller.abort();
        } else {
            external.addEventListener("abort", () => controller.abort(), { once: true });
        }
    }
    return controller;
}

/**
 * 把一个大文件分片上传到暂存区，返回 `{upload_id, filename, size}`。
 *
 * 失败语义：任一分片重试耗尽 → 取消其余分片、删除服务端会话、抛出中文错误；
 * 调用方拿到的上传是整体失败，不会留下半成品游戏条目。
 */
export async function uploadFileInChunks(
    file,
    { gameType = "", onProgress = null, signal = null } = {}
) {
    if (!file) {
        throw new Error("请选择要上传的文件。");
    }
    const controller = joinSignal(signal);
    const upload = await createGameUploadAPI({
        filename: file.name,
        size: file.size,
        game_type: gameType,
    });
    const uploadId = upload.upload_id;
    const chunkSize = Number(upload.chunk_size) || CHUNK_SIZE_BYTES;
    const totalChunks = Number(upload.total_chunks) || 1;

    // 每片已上传的字节数：进度按所有分片求和，重试时把该片归零
    const loadedByIndex = new Map();
    let fatalError = null;
    let lastReported = -1;
    function report(index, loaded, length) {
        loadedByIndex.set(index, Math.max(0, Math.min(Number(loaded) || 0, length)));
        let totalLoaded = 0;
        for (const value of loadedByIndex.values()) {
            totalLoaded += value;
        }
        if (totalLoaded === lastReported) {
            return;
        }
        lastReported = totalLoaded;
        onProgress?.({ loaded: totalLoaded, total: file.size });
    }

    async function uploadOne(index) {
        const start = index * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        const length = end - start;
        for (let attempt = 0; ; attempt += 1) {
            if (controller.signal.aborted) {
                throw abortError();
            }
            try {
                await uploadGameChunkAPI(uploadId, index, file.slice(start, end), {
                    signal: controller.signal,
                    onUploadProgress: (event) => report(index, event.loaded, length),
                });
                report(index, length, length);
                return;
            } catch (err) {
                if (controller.signal.aborted) {
                    throw err;
                }
                if (attempt >= CHUNK_MAX_RETRIES) {
                    const error = new Error("分片上传失败，请稍后重试。");
                    error.reported = false;
                    fatalError = error;
                    controller.abort();
                    throw error;
                }
                report(index, 0, length);
                await delay(CHUNK_RETRY_DELAY_MS, controller.signal);
            }
        }
    }

    const workerCount = Math.max(1, Math.min(CHUNK_CONCURRENCY, totalChunks));
    let nextIndex = 0;
    async function worker() {
        while (!controller.signal.aborted) {
            const index = nextIndex;
            nextIndex += 1;
            if (index >= totalChunks) {
                return;
            }
            await uploadOne(index);
        }
    }

    try {
        const results = await Promise.allSettled(
            Array.from({ length: workerCount }, () => worker())
        );
        const failed = results.find((result) => result.status === "rejected");
        if (failed) {
            throw fatalError || failed.reason;
        }
        const done = await completeGameUploadAPI(uploadId, { signal: controller.signal });
        return { upload_id: uploadId, filename: done.filename, size: done.size };
    } catch (err) {
        controller.abort();
        try {
            await abortGameUploadAPI(uploadId);
        } catch {
            // 清理失败不影响把原始错误交给调用方；服务端还有 24 小时 TTL 兜底
        }
        throw fatalError || err;
    }
}
