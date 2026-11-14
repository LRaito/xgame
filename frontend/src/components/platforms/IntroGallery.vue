<template>
    <!-- 图片区：一行若干张，点击看大图。
         大图预览照 GameScreenshotGallery 的做法 teleport 到 body，
         避免被详情页的滚动容器裁掉。 -->
    <div v-if="items.length" class="intro-gallery">
        <figure v-for="(item, index) in items" :key="item.key" class="intro-gallery__cell">
            <div class="intro-gallery__frame">
                <img
                    class="intro-gallery__img"
                    :src="item.url"
                    :alt="item.alt"
                    loading="lazy"
                    tabindex="0"
                    role="button"
                    @click="openPreview(index)"
                    @keydown.enter="openPreview(index)"
                />
            </div>
        </figure>
    </div>

    <teleport to="body">
        <div
            v-if="previewIndex !== null"
            class="viewer"
            :style="{ zIndex: previewZIndex }"
            @click="closePreview"
        >
            <img
                class="viewer__img"
                :src="items[previewIndex].url"
                :alt="items[previewIndex].alt"
            />
            <app-button
                v-if="items.length > 1"
                class="viewer__nav viewer__nav--prev"
                variant="secondary"
                tone="image"
                size="sm"
                icon-only
                round
                aria-label="上一张"
                :disabled="previewIndex === 0"
                @click.stop="stepPreview(-1)"
            >
                ‹
            </app-button>
            <app-button
                v-if="items.length > 1"
                class="viewer__nav viewer__nav--next"
                variant="secondary"
                tone="image"
                size="sm"
                icon-only
                round
                aria-label="下一张"
                :disabled="previewIndex === items.length - 1"
                @click.stop="stepPreview(1)"
            >
                ›
            </app-button>
        </div>
    </teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useZIndex } from "element-plus";
import { PLATFORM_IMAGES } from "@/constants/platformIntros/images";
import { matchesShortcut } from "@/utils/shortcuts";

const props = defineProps({
    /** 图片 key 列表，如 nes-console-1；缺失的 key 会被跳过。 */
    images: {
        type: Array,
        default: () => [],
    },
    /** 图片替代文字的前缀，通常传机种名。 */
    label: {
        type: String,
        default: "",
    },
});

const items = computed(() =>
    (props.images || [])
        .map((key) => ({
            key,
            url: PLATFORM_IMAGES[key],
            alt: props.label ? `${props.label} 图片` : "机型图片",
        }))
        .filter((item) => Boolean(item.url)),
);

const previewIndex = ref(null);
const previewZIndex = ref(0);
const { nextZIndex } = useZIndex();

function openPreview(index) {
    previewIndex.value = index;
    previewZIndex.value = nextZIndex();
}

function closePreview() {
    previewIndex.value = null;
}

function stepPreview(delta) {
    if (previewIndex.value === null) {
        return;
    }
    const next = previewIndex.value + delta;
    if (next >= 0 && next < items.value.length) {
        previewIndex.value = next;
    }
}

function onKeydown(event) {
    if (previewIndex.value === null) {
        return;
    }
    if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closePreview();
    } else if (matchesShortcut(event, "preview.prev")) {
        event.preventDefault();
        event.stopPropagation();
        stepPreview(-1);
    } else if (matchesShortcut(event, "preview.next")) {
        event.preventDefault();
        event.stopPropagation();
        stepPreview(1);
    }
}

watch(previewIndex, (value) => {
    if (value === null) {
        window.removeEventListener("keydown", onKeydown, true);
    } else {
        window.addEventListener("keydown", onKeydown, true);
    }
});

onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown, true);
});
</script>

<style scoped>
.intro-gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
}

.intro-gallery__cell {
    margin: 0;
}

.intro-gallery__frame {
    position: relative;
    aspect-ratio: 4 / 3;
    min-height: 0;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    overflow: hidden;
    cursor: zoom-in;
}

.intro-gallery__img {
    position: absolute;
    inset: 8px;
    width: calc(100% - 16px);
    height: calc(100% - 16px);
    object-fit: contain;
    background: #fff;
}

.viewer {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(15, 23, 42, 0.88);
}

.viewer__img {
    max-width: 92vw;
    max-height: 88vh;
    object-fit: contain;
    background: #fff;
    border-radius: var(--radius-md);
}

.viewer .viewer__nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
}

.viewer__nav--prev {
    left: 24px;
}

.viewer__nav--next {
    right: 24px;
}
</style>
