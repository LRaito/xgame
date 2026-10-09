/* 游戏封面 / SWF 同源缓存。缓存源来自后端流式下载。
   未命中时边下载边把字节流式返回给页面，便于前端展示真实下载进度；读完再整包写入缓存。 */
const CACHE_NAME = "x-game-assets-v3";
const PREFIX = "/game-assets/";

self.addEventListener("install", (event) => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener("message", (event) => {
    if (event.data && event.data.type === "SKIP_WAITING") {
        self.skipWaiting();
    }
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        (async () => {
            const keys = await caches.keys();
            await Promise.all(
                keys
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name)),
            );
            await self.clients.claim();
        })(),
    );
});

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin || !url.pathname.startsWith(PREFIX)) {
        return;
    }
    event.respondWith(respondWithCache(event.request));
});

async function respondWithCache(request) {
    const cache = await caches.open(CACHE_NAME);
    const hit = await cache.match(request);
    if (hit) {
        return hit;
    }

    const url = new URL(request.url);
    const segments = url.pathname.split("/").filter(Boolean);
    const kind = segments[1];
    const gameId = segments[2];

    let source = "";
    if (kind === "cover") {
        // 走游戏专属封面接口，不再依赖按 key 的通用下载
        source = `/api/games/${encodeURIComponent(gameId)}/cover`;
    } else if (kind === "swf") {
        source = `/api/games/${encodeURIComponent(gameId)}/play`;
    } else {
        return new Response("不支持的游戏资源类型", { status: 400 });
    }

    const fileResponse = await fetch(source, { credentials: "include" });
    if (!fileResponse.ok) {
        const message = fileResponse.status === 401 ? "登录已失效" : "下载游戏资源失败";
        return new Response(message, { status: fileResponse.status });
    }
    if (!fileResponse.body) {
        // 极少见后端不带流式 body：退回“整包读入再返回并缓存”的旧逻辑。
        return respondWithBuffered(cache, request, fileResponse, kind);
    }

    const mime =
        fileResponse.headers.get("Content-Type") ||
        (kind === "swf" ? "application/x-shockwave-flash" : "application/octet-stream");

    // 总大小：优先用 URL 里携带的 s 参数（游戏列表里的字节数），否则看后端响应头。
    const requestedSize = Number(url.searchParams.get("s")) || null;
    const headerSize = Number(fileResponse.headers.get("Content-Length")) || null;
    const total = requestedSize || headerSize;

    const reader = fileResponse.body.getReader();
    const chunks = [];
    let cached = false;

    const stream = new ReadableStream({
        // 在 pull 里读后端，天然背压：页面消费多少，这里才读多少，进度随网络真实推进。
        async pull(controller) {
            try {
                const { done, value } = await reader.read();
                if (done) {
                    controller.close();
                    writeCache();
                    return;
                }
                chunks.push(value);
                controller.enqueue(value);
            } catch (err) {
                controller.error(err);
                reader.cancel().catch(() => {});
            }
        },
        cancel() {
            reader.cancel().catch(() => {});
        },
    });

    const headers = { "Content-Type": mime };
    if (total) {
        headers["Content-Length"] = String(total);
    }
    const response = new Response(stream, { status: 200, headers });

    function writeCache() {
        if (cached) {
            return;
        }
        cached = true;
        const blob = new Blob(chunks, { type: mime });
        const cachedResponse = new Response(blob, {
            status: 200,
            headers: {
                "Content-Type": mime,
                "Content-Length": String(blob.size),
                "Cache-Control": "private, max-age=31536000, immutable",
            },
        });
        caches.open(CACHE_NAME).then((cacheStore) => cacheStore.put(request, cachedResponse));
    }

    return response;
}

// 后端无流式 body 的兜底：整包读入，写缓存并返回。
async function respondWithBuffered(cache, request, fileResponse, kind) {
    const mime =
        fileResponse.headers.get("Content-Type") ||
        (kind === "swf" ? "application/x-shockwave-flash" : "application/octet-stream");
    const blob = await fileResponse.blob();
    const cachedResponse = new Response(blob, {
        status: 200,
        headers: {
            "Content-Type": mime,
            "Content-Length": String(blob.size),
            "Cache-Control": "private, max-age=31536000, immutable",
        },
    });
    await cache.put(request, cachedResponse.clone());
    return cachedResponse;
}
