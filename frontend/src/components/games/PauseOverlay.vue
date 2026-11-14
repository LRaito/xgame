<template>
    <div class="pause-overlay" role="status" aria-live="polite">
        <span class="pause-overlay__title">{{ title }}</span>
        <span v-if="hint" class="pause-overlay__hint">{{ hint }}</span>
    </div>
</template>

<script setup>
defineProps({
    // 主文案；当前绑定被关闭时 hint 为空，只显示主文案
    title: { type: String, required: true },
    hint: { type: String, default: "" },
});
</script>

<style scoped>
/* 覆盖游戏画面：参考开始页 INSERT COIN 的像素字体、霓虹光、扫描线与径向光晕，
   额外加一层浅黑底，保证文字落在任何画面上都清楚。 */
.pause-overlay {
    position: absolute;
    inset: 0;
    z-index: 7;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: clamp(10px, 1.2vw, 16px);
    padding: 24px;
    overflow: hidden;
    pointer-events: none;
    background: rgba(2, 6, 16, 0.55);
}

.pause-overlay::before {
    content: "";
    position: absolute;
    left: 50%;
    top: 50%;
    width: min(520px, 80vw);
    height: min(520px, 80vw);
    transform: translate(-50%, -50%);
    border-radius: 50%;
    background: radial-gradient(circle, rgba(255, 107, 154, 0.16), transparent 65%);
}

.pause-overlay::after {
    content: "";
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
        0deg,
        rgba(2, 6, 16, 0.3) 0 1px,
        transparent 1px 4px
    );
    opacity: 0.22;
}

.pause-overlay__title,
.pause-overlay__hint {
    position: relative;
    z-index: 1;
    font-family: "Press Start 2P", "Courier New", monospace;
    text-align: center;
    text-transform: uppercase;
}

.pause-overlay__title {
    font-size: clamp(16px, 2.2vw, 30px);
    line-height: 1.35;
    letter-spacing: 0.18em;
    color: #7cf3ff;
    text-shadow:
        0 0 6px #00e5ff,
        0 0 18px rgba(0, 229, 255, 0.7),
        0 0 36px rgba(0, 229, 255, 0.35);
}

.pause-overlay__hint {
    font-size: clamp(10px, 1.1vw, 14px);
    line-height: 1.6;
    letter-spacing: 0.22em;
    color: #ff6b9a;
    text-shadow:
        0 0 10px rgba(255, 107, 154, 0.5),
        0 0 24px rgba(255, 107, 154, 0.25);
}
</style>
