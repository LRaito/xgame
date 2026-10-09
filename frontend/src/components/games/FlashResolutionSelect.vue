<template>
    <label class="flash-resolution-select">
        <span class="flash-resolution-select__text">窗口</span>
        <select class="flash-resolution-select__select" :value="modelValue" @change="onChange">
            <option value="native">
                原生{{ nativeLabel }}
            </option>
            <option v-for="res in PRESETS" :key="res.key" :value="res.key">
                {{ res.label }}
            </option>
        </select>
    </label>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
    modelValue: { type: String, default: "native" },
    // 当前 Flash 文件的原生分辨率，加载出来后用于给「原生」选项标注尺寸
    nativeSize: { type: Object, default: null },
});

const emit = defineEmits(["update:modelValue"]);

const nativeLabel = computed(() => {
    const size = props.nativeSize;
    if (!size || !size.width || !size.height) {
        return "";
    }
    return ` (${size.width} × ${size.height})`;
});

// 常见 4:3 与 16:9 分辨率
const PRESETS = [
    { key: "640x480", label: "640 × 480" },
    { key: "800x600", label: "800 × 600" },
    { key: "1024x768", label: "1024 × 768" },
    { key: "1152x720", label: "1152 × 720" },
    { key: "1280x720", label: "1280 × 720" },
    { key: "1366x768", label: "1366 × 768" },
    { key: "1600x900", label: "1600 × 900" },
    { key: "1920x1080", label: "1920 × 1080" },
];

function onChange(event) {
    emit("update:modelValue", event.target.value);
}
</script>

<style scoped>
.flash-resolution-select {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
}

.flash-resolution-select__text {
    font-size: 13px;
    color: #94a3b8;
    white-space: nowrap;
}

.flash-resolution-select__select {
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
    max-width: 160px;
}

.flash-resolution-select__select:hover {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}

.flash-resolution-select__select:focus-visible {
    outline: none;
    border-color: #38bdf8;
}
</style>
