<template>
    <div class="start-gate">
        <app-button
            class="start-gate__btn"
            variant="primary"
            size="lg"
            @click="$emit('start')"
        >
            开始游戏
        </app-button>
    </div>
</template>

<script setup>
defineEmits(["start"]);
</script>

<style scoped>
.start-gate {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    box-sizing: border-box;
}

/* 开始游戏是全站唯一的渐变 CTA：结构走 AppButton，视觉保留渐变与上浮 */
.start-gate .start-gate__btn.el-button {
    --el-button-bg-color: transparent;
    --el-button-hover-bg-color: transparent;
    --el-button-active-bg-color: transparent;
    height: auto;
    min-height: 52px;
    padding: 14px 38px;
    border: 0;
    border-radius: var(--app-radius-cta);
    background: var(--app-cta-gradient);
    color: #fff;
    font-family: inherit;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.02em;
    box-shadow: var(--app-cta-shadow);
    transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}

.start-gate .start-gate__btn.el-button:hover {
    background: var(--app-cta-gradient);
    box-shadow: var(--app-cta-shadow-hover);
    filter: brightness(1.05);
    transform: translateY(-1px);
}

.start-gate .start-gate__btn.el-button:active {
    transform: translateY(0);
}
</style>
