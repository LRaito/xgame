<template>
    <div v-if="modelValue" class="save-manager" @click.self="close">
        <section
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

            <section class="save-manager__local">
                <header class="save-manager__local-head">
                    <h2 class="save-manager__section-title">本地存档</h2>
                    <div class="save-manager__local-actions">
                        <slot name="local-actions" />
                    </div>
                </header>
                <div class="save-manager__local-body">
                    <slot name="local" />
                </div>
            </section>

            <section class="save-manager__cloud">
                <slot name="cloud" />
            </section>
        </section>
    </div>
</template>

<script setup>
defineProps({
    modelValue: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue"]);

function close() {
    emit("update:modelValue", false);
}
</script>

<style>
/* 统一存档管理弹框：上本地固定单卡高度，下云端剩余高度。
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
    width: min(1180px, calc(100vw - 48px));
    height: min(800px, calc(100vh - 48px));
    display: grid;
    grid-template-rows: 164px minmax(0, 1fr);
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
    /* 与右侧按钮同高，云端标题栏也用 32px，两个分区标题对齐 */
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

.save-manager__local-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
}

.save-manager__local-body {
    flex: 1;
    min-height: 0;
    padding-top: 8px;
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

.save-manager__cloud {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    padding-top: 12px;
}
</style>
