<template>
    <div
        ref="shellRef"
        class="game-shell"
        :class="{
            'game-shell--fullscreen': isFullscreen,
            'game-shell--header-visible': headerVisible,
            'game-shell--cursor-hidden': cursorHidden,
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
                <app-button variant="secondary" tone="dark" size="lg" @click="toggleFullscreen">
                    {{ isFullscreen ? "退出全屏" : "全屏" }}
                </app-button>
                <app-button variant="secondary" tone="dark" size="lg" @click="goBack">
                    返回游戏中心
                </app-button>
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

const emit = defineEmits(["fullscreen-change", "cursor-idle-change"]);

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

// ---------- 全屏闲置隐藏光标 ----------
// 全屏游玩时鼠标静止 3 秒就隐藏光标，并顺手收起标题栏浮层；任何鼠标活动立即恢复。
// 判据只看鼠标：键盘操作不该让光标一直亮着。播放页要把 iframe 里的指针活动
// 也转进来（iframe 内的事件不冒泡到外层，见 notifyActivity）。
const CURSOR_IDLE_MS = 3000;
const cursorHidden = ref(false);
let cursorIdleTimer = null;

function clearCursorIdleTimer() {
    if (cursorIdleTimer) {
        window.clearTimeout(cursorIdleTimer);
        cursorIdleTimer = null;
    }
}

function setCursorHidden(hidden) {
    // 状态没变不重复 emit（模拟器播放页靠这个事件同步 iframe 内的光标）
    if (cursorHidden.value === hidden) {
        return;
    }
    cursorHidden.value = hidden;
    if (hidden) {
        // 静止时标题栏也一起收起；hover 标记清掉，回来后再按正常规则重新判断
        headerVisible.value = false;
        headerHovering.value = false;
    }
    emit("cursor-idle-change", hidden);
}

function armCursorIdleTimer() {
    clearCursorIdleTimer();
    // 只在全屏（原生全屏或 F11）下启用
    if (!isFullscreen.value && !browserFullscreen.value) {
        return;
    }
    cursorIdleTimer = window.setTimeout(() => {
        cursorIdleTimer = null;
        if (!isFullscreen.value && !browserFullscreen.value) {
            return;
        }
        setCursorHidden(true);
    }, CURSOR_IDLE_MS);
}

/** 鼠标有活动：立即恢复光标并重新计时。播放页把 iframe 里的指针活动也转到这里。 */
function notifyActivity() {
    setCursorHidden(false);
    armCursorIdleTimer();
}

// 进入全屏开始计时；退出全屏（含 F11）立即恢复光标
watch([isFullscreen, browserFullscreen], ([native, browser]) => {
    if (native || browser) {
        armCursorIdleTimer();
        return;
    }
    clearCursorIdleTimer();
    setCursorHidden(false);
}, { immediate: true });

defineExpose({ notifyActivity });

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
    // 闲置计时挂在 document 捕获阶段：鼠标事件在 Ruffle 的 shadow root 里、或被某个
    // 组件 stopPropagation 了，也照样算活动（外壳自己的 mousemove 只管标题栏唤出）
    document.addEventListener("mousemove", notifyActivity, true);
    document.addEventListener("mousedown", notifyActivity, true);
    document.addEventListener("wheel", notifyActivity, { capture: true, passive: true });
});

onBeforeUnmount(() => {
    document.documentElement.classList.remove("game-shell-locked");
    document.removeEventListener("fullscreenchange", syncFullscreenState);
    document.removeEventListener("mousemove", notifyActivity, true);
    document.removeEventListener("mousedown", notifyActivity, true);
    document.removeEventListener("wheel", notifyActivity, true);
    clearCursorIdleTimer();
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

/* 全屏闲置：整棵子树都不显示光标。插槽内容属于播放页组件、没有本组件的
   scope 属性，必须用 :deep 才能覆盖到（含模拟器/H5 的 iframe 元素与 Flash 的
   ruffle-player）。 */
.game-shell--cursor-hidden,
.game-shell--cursor-hidden :deep(*) {
    cursor: none !important;
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
