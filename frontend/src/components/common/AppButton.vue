<template>
    <el-button
        :type="type"
        :plain="plain"
        :link="link"
        :loading="loading"
        :disabled="disabled"
        @click="$emit('click', $event)"
    >
        <slot />
    </el-button>
</template>

<script setup>
defineProps({
    type: { type: String, default: "default" },
    plain: { type: Boolean, default: false },
    link: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
});

defineEmits(["click"]);
</script>
