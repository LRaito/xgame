<template>
    <playback-select
        label="滤镜"
        :model-value="modelValue"
        :options="options"
        @update:model-value="$emit('update:modelValue', $event)"
    />
</template>

<script setup>
import { computed } from "vue";
import PlaybackSelect from "@components/games/PlaybackSelect.vue";

const props = defineProps({
    // 当前滤镜 id；表里没有的值（换了清单）由父页面回落后再传进来
    modelValue: { type: String, default: "none" },
    // 该游戏类型的滤镜清单（见 constants/emuFilters.js），第一项恒为「无」
    filters: { type: Array, required: true },
});

defineEmits(["update:modelValue"]);

const options = computed(() =>
    props.filters.map((filter) => ({ value: filter.id, label: filter.label })),
);
</script>
