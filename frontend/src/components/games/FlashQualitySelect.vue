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
    height: var(--app-control-h-lg);
    padding: 0 var(--app-control-px-sm);
    border: 1px solid var(--app-dark-border);
    border-radius: var(--app-radius-control);
    background: var(--app-dark-surface);
    color: var(--app-dark-text);
    font-family: inherit;
    font-size: var(--app-font-size-md);
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
    max-width: 96px;
}

.flash-quality-select__select:hover {
    background: var(--app-dark-surface-hover);
    border-color: var(--app-dark-border-hover);
}

.flash-quality-select__select:focus-visible {
    outline: var(--app-focus-axis) solid var(--app-focus-ring-dark);
    outline-offset: var(--app-focus-offset);
}
</style>
