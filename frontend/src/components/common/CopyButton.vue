<template>
    <app-button type="primary" link :loading="copying" @click="copy">复制</app-button>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";

const props = defineProps({
    text: { type: String, default: "" },
    getter: { type: Function, default: null },
});

const copying = ref(false);

/**
 * 写剪贴板。
 *
 * `navigator.clipboard` 只在安全上下文里有（HTTPS 或 localhost）：Windows「解压即用」包
 * 在局域网里是 http://<IP>:8910，手机和别的电脑打开时这个对象根本不存在。所以留一条老办法
 * 兜底——用隐藏的 textarea + execCommand，它在 http 下仍可用。
 */
async function writeClipboard(value) {
    if (navigator.clipboard?.writeText) {
        try {
            await navigator.clipboard.writeText(value);
            return true;
        } catch {
            // 落到下面的兜底（用户拒绝授权、或文档不在焦点上时会走这里）
        }
    }
    const holder = document.createElement("textarea");
    holder.value = value;
    holder.setAttribute("readonly", "");
    holder.style.position = "fixed";
    holder.style.opacity = "0";
    document.body.appendChild(holder);
    try {
        holder.select();
        return document.execCommand("copy");
    } catch {
        return false;
    } finally {
        document.body.removeChild(holder);
    }
}

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
