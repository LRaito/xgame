<template>
    <div v-if="modelValue" class="save-manager" @click.self="close">
        <section
            ref="cardRef"
            class="save-manager__card"
            role="dialog"
            aria-modal="true"
            aria-label="存档管理"
        >
            <app-button
                class="save-manager__close"
                text
                tone="dark"
                size="sm"
                icon-only
                round
                aria-label="关闭"
                @click="close"
            >
                ✕
            </app-button>

            <!-- 贯穿本地/云端、把左右两侧分开的竖线（与本地底部的横线组成十字） -->
            <span class="save-manager__divider" aria-hidden="true"></span>

            <section class="save-manager__local">
                <header class="save-manager__local-head">
                    <h2 class="save-manager__section-title">本地存档</h2>
                </header>
                <div class="save-manager__local-main">
                    <div ref="actionsRef" class="save-manager__local-actions">
                        <slot name="local-actions" />
                    </div>
                    <span class="save-manager__local-divider" aria-hidden="true"></span>
                    <div class="save-manager__local-body">
                        <slot name="local" />
                    </div>
                </div>
            </section>

            <section class="save-manager__cloud">
                <slot name="cloud" />
            </section>
        </section>
    </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
    modelValue: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue"]);

const cardRef = ref(null);
const actionsRef = ref(null);
let actionsObserver = null;

/** 把左侧按钮列的实时宽度写进 CSS 变量，云端侧栏据此与分隔符对齐。 */
function syncActionsWidth() {
    if (!cardRef.value || !actionsRef.value) {
        return;
    }
    cardRef.value.style.setProperty(
        "--save-local-actions-width",
        `${actionsRef.value.offsetWidth}px`,
    );
}

function observeActions() {
    actionsObserver?.disconnect();
    actionsObserver = null;
    syncActionsWidth();
    if (typeof ResizeObserver !== "function" || !actionsRef.value) {
        return;
    }
    actionsObserver = new ResizeObserver(syncActionsWidth);
    actionsObserver.observe(actionsRef.value);
}

watch(
    () => props.modelValue,
    async (visible) => {
        if (!visible) {
            actionsObserver?.disconnect();
            actionsObserver = null;
            return;
        }
        // 弹框是 v-if 渲染，等 DOM 出来再量
        await nextTick();
        observeActions();
    },
    { immediate: true },
);

onBeforeUnmount(() => {
    actionsObserver?.disconnect();
});

function close() {
    emit("update:modelValue", false);
}
</script>

<style>
/* 统一存档管理弹框：上本地（按钮竖排在左、卡片在右），下云端剩余高度。
   尺寸按原树形模式的 1180×800；视口不足时云端收缩。 */
.save-manager {
    position: fixed;
    inset: 0;
    z-index: 60;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(2, 6, 23, 0.62);
    backdrop-filter: blur(2px);
}

.save-manager__card {
    position: relative;
    box-sizing: border-box;
    /* 左侧按钮列宽度，打开弹框后由脚本按实际内容写入 */
    --save-local-actions-width: 114px;
    width: min(1180px, calc(100vw - 48px));
    height: min(800px, calc(100vh - 48px));
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    padding: 20px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, 0.24);
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    box-shadow: 0 24px 64px rgba(2, 6, 23, 0.5);
    overflow: hidden;
    color: #f8fafc;
}

.save-manager__close {
    position: absolute;
    top: 10px;
    right: 12px;
    z-index: 2;
}

.save-manager__local {
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding-bottom: 12px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.55);
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.06);
}

.save-manager__local-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    /* 与按钮同高，云端标题栏也用 32px，两个分区标题对齐 */
    height: 32px;
    padding-right: 44px;
}

.save-manager__section-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: #f8fafc;
    line-height: 1.4;
}

.save-manager__local-main {
    display: flex;
    flex: 1;
    min-height: 0;
    gap: 12px;
    padding-top: 8px;
}

/* 左右两块之间的竖向分隔线：贯穿整个弹框，与本地底部的横线组成十字 */
.save-manager__divider {
    position: absolute;
    top: 20px;
    bottom: 20px;
    left: calc(20px + var(--save-local-actions-width) + 12px);
    width: 1px;
    background: rgba(148, 163, 184, 0.32);
    pointer-events: none;
}

/* 本地 main 里的占位，让卡片区与竖线之间保持和云端一致的间距 */
.save-manager__local-divider {
    flex: 0 0 1px;
    align-self: stretch;
    background: transparent;
}

.save-manager__local-actions {
    display: grid;
    flex: 0 0 auto;
    align-self: flex-start;
    grid-auto-flow: row;
    grid-auto-columns: max-content;
    gap: 8px;
    /* 至少和云端列表同宽（节点 92 + 左右留白 20 + 边框 2） */
    min-width: 114px;
}

/* 竖排按钮等宽：列宽由最长的按钮决定，其余按钮撑满这一列。
   Element Plus 给相邻按钮默认加了 margin-left，竖排时必须清掉，否则后两个按钮会右移。 */
.save-manager__local-actions > .app-button {
    width: 100%;
    margin: 0;
}

.save-manager__local-body {
    display: flex;
    flex: 1;
    min-width: 0;
    min-height: 0;
    align-items: center;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-gutter: stable;
    scrollbar-width: thin;
    scrollbar-color: rgba(148, 163, 184, 0.35) transparent;
}

.save-manager__local-body::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

.save-manager__local-body::-webkit-scrollbar-track,
.save-manager__local-body::-webkit-scrollbar-corner {
    background: transparent;
}

.save-manager__local-body::-webkit-scrollbar-thumb {
    border-radius: 3px;
    background: rgba(148, 163, 184, 0.35);
}

.save-manager__local-body::-webkit-scrollbar-thumb:hover {
    background: rgba(148, 163, 184, 0.55);
}

/* 云端分区不再留上间距：画布要顶到本地分区底部的横线；
   标题与侧栏的让位改由它们各自的定位/外边距完成。 */
.save-manager__cloud {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    padding-top: 0;
}
</style>
