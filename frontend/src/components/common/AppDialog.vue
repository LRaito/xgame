<template>
    <el-dialog
        :model-value="modelValue"
        :title="title"
        :width="width"
        :close-on-click-modal="false"
        :close-on-press-escape="true"
        destroy-on-close
        @close="emit('update:modelValue', false)"
    >
        <slot />
        <template #footer>
            <slot name="footer">
                <app-button @click="emit('update:modelValue', false)">取消</app-button>
                <app-button type="primary" :loading="confirmLoading" @click="emit('confirm')">
                    {{ confirmText }}
                </app-button>
            </slot>
        </template>
    </el-dialog>
</template>

<script setup>
defineProps({
    modelValue: { type: Boolean, default: false },
    title: { type: String, default: "" },
    width: { type: String, default: "480px" },
    confirmText: { type: String, default: "确定" },
    confirmLoading: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "confirm"]);
</script>
