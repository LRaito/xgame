<template>
    <app-button
        :variant="variant === 'pill' ? 'secondary' : 'link'"
        :size="variant === 'pill' ? 'xs' : 'md'"
        :class="{ 'copy-button--pill': variant === 'pill' }"
        :loading="copying"
        :disabled="disabled"
        :aria-label="`复制 ${text || label}`"
        @click="copy"
    >
        {{ variant === "pill" ? text : label }}
    </app-button>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { writeClipboard } from "@/utils/clipboard";

const props = defineProps({
    text: { type: String, default: "" },
    getter: { type: Function, default: null },
    // link：文字「复制」；pill：直接显示内容（卡带 ID 药丸）
    variant: { type: String, default: "link" },
    label: { type: String, default: "复制" },
    successMessage: { type: String, default: "已复制。" },
    disabled: { type: Boolean, default: false },
});

const copying = ref(false);

async function copy() {
    if (props.disabled) {
        return;
    }
    copying.value = true;
    try {
        const value = props.getter ? await props.getter() : props.text;
        if (!value) {
            ElMessage.warning("没有可复制的内容。");
            return;
        }
        if (await writeClipboard(value)) {
            ElMessage.success(props.successMessage);
        } else {
            ElMessage.warning("浏览器不允许自动复制，请手动选中后复制。");
        }
    } finally {
        copying.value = false;
    }
}
</script>

<style>
/* 卡带 ID 药丸：与 AppButton 的 secondary xs 共用底色与圆角，只压一行高度。 */
.app-button.copy-button--pill.el-button {
    height: 20px;
    padding: 0 8px;
    border-radius: var(--app-radius-pill);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: var(--app-font-size-xs);
    font-weight: 500;
    line-height: 14px;
}
</style>
