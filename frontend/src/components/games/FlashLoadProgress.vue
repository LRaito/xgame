<template>
    <div class="flash-loading">
        <div class="flash-loading__head">
            <span class="flash-loading__label">{{ label }}</span>
            <span class="flash-loading__pct">{{ percentText }}</span>
        </div>
        <div class="flash-loading__track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
            <div class="flash-loading__bar" :style="{ width: `${clampedPercent}%` }" />
        </div>
        <p v-if="hint" class="flash-loading__hint">{{ hint }}</p>
    </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
    label: { type: String, default: "" },
    percent: { type: Number, default: 0 },
    hint: { type: String, default: "" },
});

const clampedPercent = computed(() => Math.max(0, Math.min(100, props.percent)));
const percentText = computed(() => `${Math.floor(clampedPercent.value)}%`);
</script>

<style scoped>
.flash-loading {
    width: 380px;
    max-width: 80vw;
}

.flash-loading__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
    font-size: 13px;
    color: #cbd5e1;
}

.flash-loading__pct {
    font-variant-numeric: tabular-nums;
    color: #7dd3fc;
}

.flash-loading__track {
    height: 6px;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.25);
    overflow: hidden;
}

.flash-loading__bar {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #0ea5e9, #38bdf8);
    transition: width 0.15s ease;
}

.flash-loading__hint {
    margin: 10px 0 0;
    font-size: 12px;
    line-height: 1.7;
    color: #94a3b8;
}
</style>
