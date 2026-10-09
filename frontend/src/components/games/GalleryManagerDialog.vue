<template>
    <!-- 图集管理：相册式弹框本体在 ImageAlbumDialog，这里只钉住「按游戏共享的图集」这套接口 -->
    <image-album-dialog
        :model-value="modelValue"
        title="图集管理"
        upload-text="上传图片"
        alt-text="图集图片"
        :game-id="gameId"
        :source="galleryAlbum"
        @update:model-value="emit('update:modelValue', $event)"
        @changed="emit('changed')"
    />
</template>

<script setup>
import {
    deleteGalleryAPI,
    galleryImagePath,
    listGalleryAPI,
    moveGalleryAPI,
    updateGalleryAPI,
    uploadGalleryAPI,
} from "@/api/games";
import ImageAlbumDialog from "@components/games/ImageAlbumDialog.vue";

defineProps({
    modelValue: { type: Boolean, default: false },
    gameId: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue", "changed"]);

const galleryAlbum = {
    list: listGalleryAPI,
    upload: uploadGalleryAPI,
    update: updateGalleryAPI,
    move: moveGalleryAPI,
    remove: deleteGalleryAPI,
    imagePath: galleryImagePath,
};
</script>
