<template>
    <label class="flash-quality-select">
        <span class="flash-quality-select__text">画质</span>
        <select class="flash-quality-select__select" :value="modelValue" @change="onChange">
            <option v-for="opt in OPTIONS" :key="opt.value" :value="opt.value">
                {{ opt.label }}
            </option>
        </select>
    </label>
</template>

<script setup>
// Ruffle 的 quality 等价于 Flash 的 Stage.quality，取值 low / medium / high。
// 默认为 high（高画质），切换后 Ruffle 需重新加载播放器才生效。
const props = defineProps({
    modelValue: { type: String, default: "high" },
});

const emit = defineEmits(["update:modelValue"]);

const OPTIONS = [
    { value: "high", label: "高" },
    { value: "medium", label: "中" },
    { value: "low", label: "低" },
];

function onChange(event) {
    emit("update:modelValue", event.target.value);
}
</script>

<style scoped>
.flash-quality-select {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
}

.flash-quality-select__text {
    font-size: 13px;
    color: #94a3b8;
    white-space: nowrap;
}

.flash-quality-select__select {
    /* 与标题栏的按钮（.game-shell__btn / .emulator-player__action）同一套盒模型：
       8px 上下内边距 + 14px 字号 + 1.6 行高 = 40px 高，并排时上下沿对齐 */
    padding: 8px 10px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 8px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 14px;
    line-height: 1.6;
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
    max-width: 96px;
}

.flash-quality-select__select:hover {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}

.flash-quality-select__select:focus-visible {
    outline: none;
    border-color: #38bdf8;
}
</style>
