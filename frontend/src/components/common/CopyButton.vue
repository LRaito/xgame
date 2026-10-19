<template>
    <app-button type="primary" link :loading="copying" @click="copy">复制</app-button>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { writeClipboard } from "@/utils/clipboard";

const props = defineProps({
    text: { type: String, default: "" },
    getter: { type: Function, default: null },
});

const copying = ref(false);

async function copy() {
    copying.value = true;
    try {
        const value = props.getter ? await props.getter() : props.text;
        if (!value) {
            ElMessage.warning("没有可复制的内容。");
            return;
        }
        if (await writeClipboard(value)) {
            ElMessage.success("已复制。");
        } else {
            ElMessage.warning("浏览器不允许自动复制，请手动选中后复制。");
        }
    } finally {
        copying.value = false;
    }
}
</script>
