<template>
    <!-- 截图管理：相册式弹框本体在 ImageAlbumDialog，这里只钉住「本人的截图」这套接口 -->
    <image-album-dialog
        :model-value="modelValue"
        title="截图管理"
        upload-text="上传图片"
        alt-text="游戏截图"
        :game-id="gameId"
        :source="screenshotAlbum"
        :frame-aspect="frameAspect"
        @update:model-value="emit('update:modelValue', $event)"
        @changed="emit('changed')"
    />
</template>

<script setup>
import {
    deleteScreenshotAPI,
    listScreenshotsAPI,
    moveScreenshotAPI,
    screenshotImagePath,
    updateScreenshotAPI,
    uploadScreenshotAPI,
} from "@/api/games";
import ImageAlbumDialog from "@components/games/ImageAlbumDialog.vue";

defineProps({
    modelValue: { type: Boolean, default: false },
    gameId: { type: Number, default: null },
    // 截图的宽高比：NDS 双屏是竖版，格子跟着变高（图集管理走默认 1）
    frameAspect: { type: Number, default: 1 },
});

const emit = defineEmits(["update:modelValue", "changed"]);

const screenshotAlbum = {
    list: listScreenshotsAPI,
    upload: uploadScreenshotAPI,
    update: updateScreenshotAPI,
    move: moveScreenshotAPI,
    remove: deleteScreenshotAPI,
    imagePath: screenshotImagePath,
};
</script>
