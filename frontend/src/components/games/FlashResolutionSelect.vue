<template>
    <playback-select
        label="窗口"
        :model-value="modelValue"
        :options="options"
        @update:model-value="$emit('update:modelValue', $event)"
    />
</template>

<script setup>
import { computed } from "vue";
import PlaybackSelect from "@components/games/PlaybackSelect.vue";

const props = defineProps({
    modelValue: { type: String, default: "native" },
    // 当前 Flash 文件的原生分辨率，加载出来后用于给「原生」选项标注尺寸
    nativeSize: { type: Object, default: null },
});

defineEmits(["update:modelValue"]);

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

const options = computed(() => [
    { value: "native", label: `原生${nativeLabel.value}` },
    ...PRESETS.map((res) => ({ value: res.key, label: res.label })),
]);
</script>
