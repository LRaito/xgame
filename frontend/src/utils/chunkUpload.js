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
 * 把一组文件分片上传到暂存区，返回 `{uploads, upload_ids, files}`。
 *
 * 每个物理文件各开一个现有分片会话，再把「文件 × 分片」拍平成任务池共用 5 路并发。
 * 失败语义：任一分片重试耗尽 → 取消其余分片、删除全部服务端会话、抛出中文错误；
 * 调用方拿到的上传是整体失败，不会留下半成品游戏条目。
 */
export async function uploadFilesInChunks(
    files,
    { gameType = "", onProgress = null, signal = null } = {}
) {
    const list = Array.from(files || []);
    if (!list.length) {
        throw new Error("请选择要上传的文件。");
    }
    const totalSize = list.reduce((sum, file) => sum + Number(file.size || 0), 0);
    const controller = joinSignal(signal);
    const sessions = [];

    async function discardAll() {
        await Promise.all(
            sessions.map(async (session) => {
                try {
                    await abortGameUploadAPI(session.uploadId);
                } catch {
                    // 清理失败不影响把原始错误交给调用方；服务端还有 24 小时 TTL 兜底
                }
            }),
        );
    }

    try {
        for (const file of list) {
            if (controller.signal.aborted) {
                throw abortError();
            }
            const upload = await createGameUploadAPI({
                filename: file.name,
                size: file.size,
                game_type: gameType,
            });
            sessions.push({
                file,
                uploadId: upload.upload_id,
                chunkSize: Number(upload.chunk_size) || CHUNK_SIZE_BYTES,
                totalChunks: Number(upload.total_chunks) || 1,
            });
        }
    } catch (err) {
        controller.abort();
        await discardAll();
        throw err;
    }

    const tasks = [];
    sessions.forEach((session, fileIndex) => {
        for (let index = 0; index < session.totalChunks; index += 1) {
            tasks.push({ fileIndex, index });
        }
    });

    // 每个分片已上传的字节数：进度按全部文件求和，重试时把该片归零
    const loadedByTask = new Map();
    let fatalError = null;
    let lastReported = -1;
    function report(key, loaded, length) {
        loadedByTask.set(key, Math.max(0, Math.min(Number(loaded) || 0, length)));
        let totalLoaded = 0;
        for (const value of loadedByTask.values()) {
            totalLoaded += value;
        }
        if (totalLoaded === lastReported) {
            return;
        }
        lastReported = totalLoaded;
        onProgress?.({ loaded: totalLoaded, total: totalSize });
    }

    async function uploadOne(task) {
        const session = sessions[task.fileIndex];
        const start = task.index * session.chunkSize;
        const end = Math.min(start + session.chunkSize, session.file.size);
        const length = end - start;
        const key = `${task.fileIndex}:${task.index}`;
        for (let attempt = 0; ; attempt += 1) {
            if (controller.signal.aborted) {
                throw abortError();
            }
            try {
                await uploadGameChunkAPI(
                    session.uploadId,
                    task.index,
                    session.file.slice(start, end),
                    {
                        signal: controller.signal,
                        onUploadProgress: (event) => report(key, event.loaded, length),
                    },
                );
                report(key, length, length);
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
                report(key, 0, length);
                await delay(CHUNK_RETRY_DELAY_MS, controller.signal);
            }
        }
    }

    const workerCount = Math.max(1, Math.min(CHUNK_CONCURRENCY, tasks.length));
    let nextTask = 0;
    async function worker() {
        while (!controller.signal.aborted) {
            const task = tasks[nextTask];
            nextTask += 1;
            if (!task) {
                return;
            }
            await uploadOne(task);
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
        const uploads = [];
        for (const session of sessions) {
            const done = await completeGameUploadAPI(session.uploadId, {
                signal: controller.signal,
            });
            uploads.push({
                upload_id: session.uploadId,
                filename: done.filename,
                size: done.size,
            });
        }
        return {
            uploads,
            upload_ids: uploads.map((item) => item.upload_id),
            files: list.map((file) => ({ name: file.name, size: file.size })),
        };
    } catch (err) {
        controller.abort();
        await discardAll();
        throw fatalError || err;
    }
}

/**
 * 单文件版本的薄包装：保留原调用方使用的 `{upload_id, filename, size}` 形状。
 */
export async function uploadFileInChunks(file, options = {}) {
    if (!file) {
        throw new Error("请选择要上传的文件。");
    }
    const result = await uploadFilesInChunks([file], options);
    return result.uploads[0];
}
