<template>
    <playback-select
        label="画质"
        :model-value="modelValue"
        :options="OPTIONS"
        @update:model-value="$emit('update:modelValue', $event)"
    />
</template>

<script setup>
import PlaybackSelect from "@components/games/PlaybackSelect.vue";

// Ruffle 的 quality 等价于 Flash 的 Stage.quality，取值 low / medium / high。
// 默认为 high（高画质），切换后 Ruffle 需重新加载播放器才生效。
defineProps({
    modelValue: { type: String, default: "high" },
});

defineEmits(["update:modelValue"]);

const OPTIONS = [
    { value: "high", label: "高" },
    { value: "medium", label: "中" },
    { value: "low", label: "低" },
];
</script>
