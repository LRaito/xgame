<template>
    <span class="image-upload">
        <app-button :loading="busy" @click="onPick">{{ label }}</app-button>
        <!-- 原生文件选择器藏起来（样式没法统一），只由按钮代点 -->
        <input
            ref="fileInputRef"
            class="image-upload__input"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            @change="onFileChange"
        />
    </span>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";
import AppButton from "@components/common/AppButton.vue";

/**
 * 「直接上传一张图」的快捷按钮：弹框外的入口（详情弹框的截图、编辑弹框的图集都用它），
 * 选完文件立刻上传，不必先进相册弹框。上传接口由外部注入，组件不认识任何业务 API。
 */
const props = defineProps({
    gameId: { type: Number, default: null },
    // 上传接口：(FormData) => Promise
    upload: { type: Function, required: true },
    label: { type: String, default: "上传" },
});

const emit = defineEmits(["uploaded"]);

const busy = ref(false);
const fileInputRef = ref(null);

function onPick() {
    if (!busy.value) {
        fileInputRef.value?.click();
    }
}

async function onFileChange(event) {
    const input = event.target;
    const file = input?.files?.[0];
    input.value = ""; // 清掉，选同一个文件两次也要能触发 change
    if (!file || !props.gameId) {
        return;
    }
    busy.value = true;
    try {
        const form = new FormData();
        form.append("game_id", String(props.gameId));
        form.append("description", "");
        form.append("file", file, file.name || "image.png");
        await props.upload(form);
        ElMessage.success("已上传图片。");
        emit("uploaded");
    } catch {
        // 错误提示已由请求层 toast
    } finally {
        busy.value = false;
    }
}
</script>

<style scoped>
.image-upload {
    display: inline-flex;
}

.image-upload__input {
    display: none;
}
</style>
