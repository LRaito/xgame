<template>
    <div ref="areaRef" class="flash-player">
        <div v-if="loading" class="flash-player__status">
            <flash-load-progress :label="phaseLabel" :percent="progress" :hint="hint" />
        </div>
        <div v-else-if="error" class="flash-player__status flash-player__status--error">{{ error }}</div>
        <div ref="containerRef" class="flash-player__stage" :class="{ 'flash-player__stage--hidden': loading || error }" />
    </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { createRufflePlayer, destroyRufflePlayer, isRuffleLoaded } from "@/utils/ruffle";
import FlashLoadProgress from "@components/games/FlashLoadProgress.vue";

const props = defineProps({
    swfUrl: { type: String, required: true },
    // 播放窗口分辨率 key：native 用 Flash 文件原生分辨率；否则形如 "1280x720"
    resolution: { type: String, default: "native" },
    // 播放画质（low / medium / high，等价 Flash 的 Stage.quality），加载期生效，
    // 变化时重建播放器让 Ruffle 按新画质重新加载。
    quality: { type: String, default: "high" },
    // 是否处于全屏；全屏时忽略所选分辨率，直接铺满屏幕
    fullscreen: { type: Boolean, default: false },
});

const emit = defineEmits(["native-size"]);

const containerRef = ref(null);
const areaRef = ref(null);
const loading = ref(true);
const error = ref("");
const progress = ref(0);
const phaseLabel = ref("正在准备…");
const hint = ref("");

// 阶段标签：先进游戏页先下 SWF（通常是耗时大头，按真实字节显示进度），下完再启动模拟器。
const DOWNLOAD_LABEL = "首次游玩需要下载游戏文件";
const INIT_LABEL = "启动 Ruffle 模拟器";

let playerEl = null;
let nativeWidth = null;
let nativeHeight = null;

let phase = "download";
let downloadTotalKnown = false;
let progressTimer = null;
let finishTimer = null;
let lastHintAt = 0;

function fmtBytes(bytes) {
    if (bytes == null) {
        return "";
    }
    if (bytes < 1024 * 1024) {
        return `${Math.max(0, Math.round(bytes / 1024))} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setPhase(next) {
    phase = next;
    progress.value = 0;
    phaseLabel.value = `${next === "download" ? DOWNLOAD_LABEL : INIT_LABEL}…`;
}

// 主线程主动下载 SWF（走 Service Worker 流式缓存），实时读字节驱动进度条。
async function downloadSwf() {
    const resp = await fetch(props.swfUrl, { credentials: "same-origin", ruffleProgress: false });
    if (!resp.ok) {
        const message = resp.status === 401 ? "登录已失效，请重新登录" : "游戏文件下载失败";
        throw new Error(message);
    }

    const total = Number(resp.headers.get("Content-Length")) || 0;
    downloadTotalKnown = total > 0;
    lastHintAt = 0;

    if (!resp.body) {
        // 极少见无流式 body：整包读入后一把到位。
        const buffer = await resp.arrayBuffer();
        progress.value = 100;
        return new Blob([buffer], { type: resp.headers.get("Content-Type") || "application/x-shockwave-flash" });
    }

    const reader = resp.body.getReader();
    const chunks = [];
    let loaded = 0;
    for (;;) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        if (!value) {
            continue;
        }
        chunks.push(value);
        loaded += value.length;

        // 至少每 ~100ms 更新一次进度，避免高频重渲染。
        const now = Date.now();
        if (now - lastHintAt >= 100 || loaded === 0) {
            lastHintAt = now;
            if (total > 0) {
                progress.value = Math.min(100, (loaded / total) * 100);
            }
            hint.value = total > 0 ? `已下载 ${fmtBytes(loaded)} / ${fmtBytes(total)}` : `已下载 ${fmtBytes(loaded)}`;
        }
    }

    progress.value = 100;
    if (downloadTotalKnown) {
        hint.value = `已下载 ${fmtBytes(loaded)} / ${fmtBytes(total)}`;
    } else {
        hint.value = `已下载 ${fmtBytes(loaded)}`;
    }
    return new Blob(chunks, { type: resp.headers.get("Content-Type") || "application/x-shockwave-flash" });
}

function tickProgress() {
    if (phase === "download" && !downloadTotalKnown) {
        // 拿不到总字节数时缓慢推进示意，避免像卡死
        progress.value = Math.min(92, progress.value + 0.5);
    } else if (phase === "init") {
        // 引擎初始化/编译无外部进度信号，缓慢爬升示意
        progress.value = Math.min(96, progress.value + Math.max(0.2, (96 - progress.value) * 0.02));
    }
}

function startTicker() {
    stopTicker();
    progressTimer = window.setInterval(tickProgress, 120);
}

function stopTicker() {
    if (progressTimer) {
        window.clearInterval(progressTimer);
        progressTimer = null;
    }
}

// 加载成功：进度到 100，短暂停留后撤掉 loading 展示游戏。
function finishLoading() {
    if (!playerEl || error.value) {
        loading.value = false;
        return;
    }
    progress.value = 100;
    phaseLabel.value = "启动完成";
    hint.value = "";
    finishTimer = window.setTimeout(() => {
        if (playerEl && !error.value) {
            loading.value = false;
            progress.value = 0;
        }
    }, 220);
}

function setPlayerSize(width, height) {
    // 真实改变元素盒尺寸，让 ruffle 按该分辨率重绘（不要用 transform 缩放，那会把画布当位图放大而变糊）。
    playerEl.style.width = `${Math.max(1, Math.round(width))}px`;
    playerEl.style.height = `${Math.max(1, Math.round(height))}px`;
    playerEl.style.flex = "0 0 auto";
}

function applySize() {
    if (!playerEl) {
        return;
    }

    // 全屏时忽略所选分辨率，铺满整个屏幕（等比 letterbox，不拉伸变形）。
    // 宽度以实际可视区为准，避免被滚动条挤出一点导致横向滚动。
    if (props.fullscreen) {
        const areaWidth = areaRef.value?.clientWidth;
        const width = areaWidth && areaWidth > 0 ? Math.min(window.innerWidth, areaWidth) : window.innerWidth;
        setPlayerSize(width, window.innerHeight);
        return;
    }

    let width;
    let height;
    if (props.resolution === "native") {
        // 原生分辨率尚未读到（metadata 缺失等）时不改动，保持 ruffle 自身布局。
        if (!nativeWidth || !nativeHeight) {
            return;
        }
        width = nativeWidth;
        height = nativeHeight;
    } else {
        const parts = props.resolution.split("x");
        width = Number(parts[0]);
        height = Number(parts[1]);
        if (!width || !height) {
            return;
        }
    }
    setPlayerSize(width, height);
}

// 直接从 ruffle 暴露的元数据取原生分辨率；返回是否取到。
function readMetadataNative() {
    if (!playerEl) {
        return false;
    }
    const instance = playerEl.ruffle?.();
    const width = instance?.metadata?.width || playerEl.metadata?.width;
    const height = instance?.metadata?.height || playerEl.metadata?.height;
    if (!width || !height) {
        return false;
    }
    nativeWidth = Math.round(width);
    nativeHeight = Math.round(height);
    emit("native-size", { width: nativeWidth, height: nativeHeight });
    return true;
}

// 元数据缺失时的兜底：去掉宽度约束，让 ruffle 按自身默认布局，量出自然盒尺寸当原生分辨率。
async function measureNativeFallback() {
    if (!playerEl) {
        return;
    }
    playerEl.style.width = "";
    playerEl.style.height = "";
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const width = playerEl.offsetWidth;
    const height = playerEl.offsetHeight;
    if (!width || !height) {
        return;
    }
    nativeWidth = Math.round(width);
    nativeHeight = Math.round(height);
    emit("native-size", { width: nativeWidth, height: nativeHeight });
    applySize();
}

async function mountPlayer() {
    if (!containerRef.value || !props.swfUrl) {
        return;
    }

    stopTicker();
    if (finishTimer) {
        window.clearTimeout(finishTimer);
        finishTimer = null;
    }

    loading.value = true;
    error.value = "";
    downloadTotalKnown = false;
    hint.value = "";
    setPhase("download");
    startTicker();

    destroyRufflePlayer(containerRef.value);
    playerEl = null;

    try {
        // 1) 先下载 SWF（真实字节进度），同时让 Service Worker 把内容按该 URL 落缓存。
        const blob = await downloadSwf();
        if (!blob || blob.size === 0) {
            throw new Error("游戏文件为空");
        }
        // 2) 让 Ruffle 直接按真实 URL 加载（SW 刚已缓存，基本不再走网络）。
        //    不能用 Blob URL：Ruffle 的 SharedObject 存档以 movie URL（host + 路径）派生
        //    localStorage key，Blob 的随机 id 会让 key 每次不同，本地存档从此读不回。
        hint.value = isRuffleLoaded() ? "" : "首次需下载并编译 Ruffle 模拟器引擎…";
        setPhase("init");
        playerEl = await createRufflePlayer(containerRef.value, props.swfUrl, null, props.quality);
    } catch (err) {
        error.value = err?.message || "Flash 游戏加载失败";
        hint.value = "";
    }
    stopTicker();

    if (!playerEl) {
        loading.value = false;
        return;
    }

    hint.value = "";
    if (readMetadataNative() || props.resolution !== "native") {
        applySize();
        finishLoading();
    } else {
        // 兜底测量需要舞台先可见：直接撤 loading，随后在后台量尺寸。
        loading.value = false;
        requestAnimationFrame(() => requestAnimationFrame(() => measureNativeFallback()));
    }
}

watch(
    () => props.swfUrl,
    () => {
        mountPlayer();
    },
);

// 切换窗口分辨率时重设播放器尺寸。
watch(
    () => props.resolution,
    () => {
        applySize();
    },
);

// Ruffle 的 quality 是加载期配置（等价 Stage.quality），公开 API 无法运行时设置；
// 变更画质需重建播放器按新配置重新加载。
watch(
    () => props.quality,
    () => {
        mountPlayer();
    },
);

// 进入/退出全屏后（视口尺寸变化需下一帧才稳定）按全屏铺满或所选分辨率重设。
watch(
    () => props.fullscreen,
    () => {
        requestAnimationFrame(() => applySize());
    },
);

function handleResize() {
    if (props.fullscreen) {
        applySize();
    }
}

onMounted(() => {
    window.addEventListener("resize", handleResize);
    mountPlayer();
});

onBeforeUnmount(() => {
    window.removeEventListener("resize", handleResize);
    stopTicker();
    if (finishTimer) {
        window.clearTimeout(finishTimer);
        finishTimer = null;
    }
    if (containerRef.value) {
        destroyRufflePlayer(containerRef.value);
    }
    playerEl = null;
});
</script>

<style scoped>
.flash-player {
    width: 100%;
    min-height: 480px;
    overflow: auto;
}

.flash-player__stage {
    width: fit-content;
    min-width: 100%;
    min-height: 480px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
}

.flash-player__stage--hidden {
    display: none;
}

.flash-player__status {
    min-height: 480px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    color: #cbd5e1;
}

.flash-player__status--error {
    color: #fca5a5;
}
</style>
