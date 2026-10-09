<template>
    <div
        ref="shellRef"
        class="game-shell"
        :class="{
            'game-shell--fullscreen': isFullscreen,
            'game-shell--header-visible': headerVisible,
        }"
        @mousemove="onShellMouseMove"
        @mouseleave="onShellMouseLeave"
    >
        <header
            class="game-shell__header"
            @mouseenter="onHeaderEnter"
            @mouseleave="onHeaderLeave"
        >
            <div class="game-shell__leading">
                <h1 class="game-shell__title">{{ title }}</h1>
                <div v-if="$slots.extra" class="game-shell__extra">
                    <slot name="extra" />
                </div>
            </div>
            <div class="game-shell__actions">
                <slot name="actions" />
                <button type="button" class="game-shell__btn" @click="toggleFullscreen">
                    {{ isFullscreen ? "退出全屏" : "全屏" }}
                </button>
                <button type="button" class="game-shell__btn" @click="goBack">返回游戏中心</button>
            </div>
        </header>
        <div class="game-shell__body">
            <slot />
        </div>

        <!-- 顶部感应带：标题栏收起时铺在最上方，鼠标靠近即唤出。游戏跑在同源 iframe 里，
            那里面的 mousemove 不会冒泡到外层，光靠外壳的 mousemove 在全屏下唤不出标题栏。 -->
        <div v-if="!headerVisible" class="game-shell__reveal" @mouseenter="showHeader"></div>
    </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useFullscreenState } from "@/utils/fullscreen";

defineProps({
    title: { type: String, required: true },
});

const emit = defineEmits(["fullscreen-change"]);

const router = useRouter();
const shellRef = ref(null);
const isFullscreen = ref(false);
// 标题栏常驻收起：以浮层形式盖在游戏区之上（不占位、不挤压游戏区），
// 鼠标靠近页面顶部边界时滑出，移开即收起。
const headerVisible = ref(false);
const headerHovering = ref(false);

const HEADER_REVEAL_ZONE = 48;

// 把全屏状态广播给外层，便于播放器等按需做全屏适配。
watch(isFullscreen, (value) => {
    emit("fullscreen-change", value);
});

// 浏览器 F11 全屏：标题栏本来就收起，只需跟着改一下取景方式（见样式里的 --fullscreen）。
const { browserFullscreen } = useFullscreenState();

watch(browserFullscreen, () => {
    headerVisible.value = false;
    headerHovering.value = false;
}, { immediate: true });

function syncFullscreenState() {
    isFullscreen.value = document.fullscreenElement === shellRef.value;
    headerVisible.value = false;
    headerHovering.value = false;
}

function showHeader() {
    headerVisible.value = true;
}

function hideHeaderIfNeeded() {
    if (!headerHovering.value) {
        headerVisible.value = false;
    }
}

function onShellMouseMove(event) {
    if (!shellRef.value) {
        return;
    }

    const top = shellRef.value.getBoundingClientRect().top;
    if (event.clientY - top <= HEADER_REVEAL_ZONE) {
        showHeader();
    }
}

function onShellMouseLeave() {
    hideHeaderIfNeeded();
}

function onHeaderEnter() {
    headerHovering.value = true;
    showHeader();
}

function onHeaderLeave() {
    headerHovering.value = false;
    hideHeaderIfNeeded();
}

async function toggleFullscreen() {
    if (!shellRef.value) {
        return;
    }

    if (document.fullscreenElement === shellRef.value) {
        await document.exitFullscreen();
        return;
    }

    await shellRef.value.requestFullscreen();
}

function goBack() {
    if (document.fullscreenElement === shellRef.value) {
        document.exitFullscreen();
    }
    router.push("/games");
}

// 播放页自身铺满视口、滚动都发生在 `.game-shell__body` 里，页面不该滚动。
// 锁住 html 的滚动并去掉滚动条槽位（样式见 styles/index.css 的 html.game-shell-locked）：
// 不加的话右侧会一直空出一条 :root 背景色的竖条（scrollbar-gutter: stable 留的槽位）。
onMounted(() => {
    document.addEventListener("fullscreenchange", syncFullscreenState);
    document.documentElement.classList.add("game-shell-locked");
});

onBeforeUnmount(() => {
    document.documentElement.classList.remove("game-shell-locked");
    document.removeEventListener("fullscreenchange", syncFullscreenState);
    if (document.fullscreenElement === shellRef.value) {
        document.exitFullscreen();
    }
});
</script>

<style scoped>
.game-shell {
    position: relative;
    margin: -28px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    background: linear-gradient(165deg, #0f172a 0%, #1e293b 45%, #0f172a 100%);
    color: #f8fafc;
}

/* 标题栏是盖在游戏区之上的浮层：平时整体藏在页面顶部之外（不占位、不挤压游戏区），
   鼠标靠近页面顶部边界才滑出。全屏时只是把定位基准从外壳换成视口。 */
.game-shell__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    padding: 16px 24px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.28);
    background: rgba(15, 23, 42, 0.92);
    backdrop-filter: blur(8px);
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 20;
    transform: translateY(-100%);
    transition: transform 0.22s ease;
}

.game-shell--header-visible .game-shell__header {
    transform: translateY(0);
}

/* 顶部唤出感应带：透明、不占位，只在标题栏收起时存在（展开后让位给标题栏自身的悬停） */
.game-shell__reveal {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 10;
    height: 12px;
}

.game-shell__leading {
    display: flex;
    align-items: center;
    gap: 16px;
    min-width: 0;
    flex: 1;
}

.game-shell__title {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 0.02em;
    white-space: nowrap;
}

.game-shell__extra {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 14px;
    color: #cbd5e1;
    min-width: 0;
}

.game-shell__actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
}

.game-shell__btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 8px 14px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 10px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
    white-space: nowrap;
}

.game-shell__btn:hover {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}

.game-shell__body {
    flex: 1;
    display: flex;
    padding: 12px 12px 16px;
    min-height: 0;
    /* 所选分辨率可能超出视口，允许在游戏外壳内滚动；safe 保证超界时从起点可滚到 */
    overflow: auto;
    align-items: safe center;
    justify-content: safe center;
}

.game-shell--fullscreen {
    margin: 0;
    width: 100%;
    height: 100%;
    min-height: 100%;
}

/* 全屏时标题栏改为相对视口定位（外壳此时就是视口范围），游戏区去掉留白 */
.game-shell--fullscreen .game-shell__header {
    position: fixed;
}

.game-shell--fullscreen .game-shell__body {
    padding: 0;
}
</style>
