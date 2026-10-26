<template>
    <app-button
        text
        :size="variant === 'pill' ? 'sm' : 'md'"
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
/* 卡带 ID 药丸：可复制的数据 chip，不是操作按钮。
   高度固定 20px，discover 表格的 44px 行高依赖它。 */
.app-button.app-button--text.copy-button--pill.el-button {
    height: 20px;
    min-height: 0;
    padding: 0 8px;
    border: 0;
    border-radius: var(--app-radius-pill);
    background: var(--app-surface-subtle);
    color: #282828;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    font-weight: 500;
    line-height: 20px;
}

.app-button.app-button--text.copy-button--pill.el-button:hover {
    background: #e4e4e4;
    color: #282828;
    text-decoration: none;
}

.app-button.app-button--text.copy-button--pill.el-button:focus-visible {
    border-color: transparent;
    box-shadow: inset 0 0 0 1px var(--app-color-primary-active);
    text-decoration: none;
}

.app-button.app-button--text.copy-button--pill.is-disabled.el-button,
.app-button.app-button--text.copy-button--pill.is-disabled.el-button:hover {
    background: var(--app-color-disabled-bg);
    color: var(--app-color-disabled-text);
}
</style>
