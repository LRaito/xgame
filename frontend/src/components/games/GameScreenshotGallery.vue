<template>
    <!-- 图片栏：一行 4 个 180px 正方形限制框（与「最近游玩」卡片等高），
         封面固定占第一页第一格（没有封面就留一个空占位框），接着是图集（按游戏共享），
         最后是本人的截图；放不下时左右翻页，第 2 页起不再显示封面。
         图片一律等比缩放到长边到上限为止。
         左键单击任意一张图（含封面）看大图，见下面的看大图层 -->
    <div v-if="visible" class="gallery" @wheel="onWheel">
        <button
            v-if="pageCount > 1"
            type="button"
            class="gallery__nav gallery__nav--prev"
            aria-label="上一页"
            :disabled="page === 0"
            @click="page -= 1"
        >
            ‹
        </button>

        <!-- 所有格子排在一条轨道上，翻页靠整条轨道水平滑动（一页正好一屏） -->
        <div class="gallery__viewport">
            <div class="gallery__track" :style="{ transform: `translateX(-${page * PAGE_OFFSET}px)` }">
                <div v-for="(slot, index) in slots" :key="index" class="gallery__cell">
                    <div class="gallery__frame" :class="{ 'gallery__frame--empty': !slot.url }">
                        <img
                            v-if="slot.url"
                            class="gallery__img"
                            :src="slot.url"
                            :alt="slot.alt"
                            loading="lazy"
                            @click="openPreview(slot)"
                        />
                    </div>
                    <!-- 描述行始终占位（封面那格为空串），换页与有无描述都不跳版 -->
                    <p class="gallery__caption">{{ slot.caption }}</p>
                </div>
            </div>
        </div>

        <button
            v-if="pageCount > 1"
            type="button"
            class="gallery__nav gallery__nav--next"
            aria-label="下一页"
            :disabled="page === pageCount - 1"
            @click="page += 1"
        >
            ›
        </button>
    </div>

    <!-- 看大图：铺满视口的深色遮罩 + 等比放大到视口内的原图。
         单击任意位置（包括图片本身）退回，ESC 也退回；左右两侧按钮与键盘左右键翻页
         （翻的是整条图片栏的图：封面 + 全部截图，见 onPreviewKeydown 与 stepPreview）。
         teleport 到 body：留在弹框里会被弹框的层叠与滚动容器裁掉 -->
    <teleport to="body">
        <div
            v-if="previewImage"
            class="viewer"
            :style="{ zIndex: previewZIndex }"
            role="presentation"
            @click="closePreview"
        >
            <img class="viewer__img" :src="previewImage.url" :alt="previewImage.alt" />

            <!-- 只有一张图时不摆按钮；按钮上的点击不能冒泡到遮罩（否则一点就退回） -->
            <template v-if="imageCount > 1">
                <button
                    type="button"
                    class="viewer__nav viewer__nav--prev"
                    aria-label="上一张"
                    :disabled="!canPrev"
                    @click.stop="stepPreview(-1)"
                >
                    ‹
                </button>
                <button
                    type="button"
                    class="viewer__nav viewer__nav--next"
                    aria-label="下一张"
                    :disabled="!canNext"
                    @click.stop="stepPreview(1)"
                >
                    ›
                </button>
            </template>
        </div>
    </teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useZIndex } from "element-plus";
import { galleryImagePath, screenshotImagePath } from "@/api/games";

const props = defineProps({
    // 封面（共享）的图片地址；为空时第一格渲染空占位
    coverUrl: { type: String, default: "" },
    coverAlt: { type: String, default: "" },
    // 图集（按游戏共享），排在封面之后、本人截图之前，已按后端给的展示顺序排好
    gallery: { type: Array, default: () => [] },
    // 本人该游戏的截图，已按后端给的展示顺序排好
    screenshots: { type: Array, default: () => [] },
});

// 每页 4 格；格子边长与格间距见样式里的 --cell / --cell-gap（两边必须一致）
const PAGE_SIZE = 4;
const CELL_SIZE = 180;
const CELL_GAP = 14;
// 翻一页轨道要滑多远：4 格宽 + 4 个间距（含下一页第一格前的那道缝）
const PAGE_OFFSET = PAGE_SIZE * (CELL_SIZE + CELL_GAP);

const page = ref(0);

// 第一格恒为封面（没有封面也是一个空占位），其后是图集、最后是本人截图。
// imageIndex 是这张图在「能看大图的那串图」里的下标（空占位是 -1）：
// 看大图按它左右翻，所以没有封面的那个空占位不参与翻页
const slots = computed(() => {
    const list = [
        { url: props.coverUrl, alt: props.coverAlt, caption: "" },
        ...props.gallery.map((item) => ({
            url: galleryImagePath(item),
            alt: item.description || "图集图片",
            caption: item.description || "",
        })),
        ...props.screenshots.map((item) => ({
            url: screenshotImagePath(item),
            alt: item.description || "游戏截图",
            caption: item.description || "",
        })),
    ];
    let count = 0;
    return list.map((slot) => {
        if (!slot.url) {
            return { ...slot, imageIndex: -1 };
        }
        const imageIndex = count;
        count += 1;
        return { ...slot, imageIndex };
    });
});

// 看大图能翻的那串图（与图片栏同序：封面（有图才算）+ 全部截图）
const imageSlots = computed(() => slots.value.filter((slot) => slot.imageIndex >= 0));

const pageCount = computed(() => Math.ceil(slots.value.length / PAGE_SIZE));

// 封面、图集与截图都没有时整条图片栏（含分隔线）不出现，免得一屏空框
const visible = computed(
    () =>
        Boolean(props.coverUrl) || props.gallery.length > 0 || props.screenshots.length > 0
);

// 删掉截图后页数可能变少，把页码收敛回最后一页，不停在空页上
watch(pageCount, (count) => {
    if (page.value > count - 1) {
        page.value = Math.max(0, count - 1);
    }
});

/** 滚轮翻页：上滚前翻、下滚后翻。只有真能翻的时候才拦默认行为，
 *  免得在图片栏上滚动时页面滚不动（只有一页时完全放行）。 */
function onWheel(event) {
    if (pageCount.value <= 1 || !event.deltaY) {
        return;
    }
    const forward = event.deltaY > 0;
    const target = forward ? page.value + 1 : page.value - 1;
    if (target < 0 || target > pageCount.value - 1) {
        return;
    }
    event.preventDefault();
    page.value = target;
}

/* ---------- 看大图 ---------- */

// 正在放大的那张在 imageSlots 里的下标，-1 = 没在看
const previewIndex = ref(-1);
// 遮罩的层级：跟 Element Plus 的弹框要一个比当前弹框更大的 z-index（详情弹框本身的
// z-index 是它打开时分配的，写死一个常数早晚会被压住）
const previewZIndex = ref(0);
const { nextZIndex } = useZIndex();

const previewImage = computed(() => imageSlots.value[previewIndex.value] || null);
const imageCount = computed(() => imageSlots.value.length);
const canPrev = computed(() => previewIndex.value > 0);
const canNext = computed(
    () => previewIndex.value >= 0 && previewIndex.value < imageCount.value - 1
);

/** 左键单击图片栏里的一张图：放大显示。空格子（没有封面）不可点。 */
function openPreview(slot) {
    if (!slot || slot.imageIndex < 0) {
        return;
    }
    previewIndex.value = slot.imageIndex;
    previewZIndex.value = nextZIndex();
}

/** 单击遮罩任意位置退回。 */
function closePreview() {
    previewIndex.value = -1;
}

/** 翻到前/后一张；到头就停住不动（按钮同时置灰）。 */
function stepPreview(delta) {
    const target = previewIndex.value + delta;
    if (target < 0 || target > imageCount.value - 1) {
        return;
    }
    previewIndex.value = target;
}

/** 看大图期间接管按键：左右翻页，ESC 退回。捕获阶段就拦下并阻止默认行为——
 *  既别让详情弹框跟着一起关（只关最上面这层），也别让遮罩底下的页面跟着滚。 */
function onPreviewKeydown(event) {
    const actions = {
        Escape: closePreview,
        ArrowLeft: () => stepPreview(-1),
        ArrowRight: () => stepPreview(1),
    };
    const action = actions[event.key];
    if (!action) {
        return;
    }
    event.preventDefault();
    event.stopPropagation();
    action();
}

watch(previewImage, (value) => {
    if (value) {
        window.addEventListener("keydown", onPreviewKeydown, true);
    } else {
        window.removeEventListener("keydown", onPreviewKeydown, true);
    }
});

// 弹框 destroy-on-close 会把本组件整个卸掉，监听必须跟着撤（否则按 ESC 会报错）
onBeforeUnmount(() => window.removeEventListener("keydown", onPreviewKeydown, true));
</script>

<style scoped>
/* 762px = 4×180 + 3×14，与「最近游玩」rail 的列宽/间距同一套 */
.gallery {
    position: relative;
    width: 762px;
    max-width: 100%;
    margin: 0 auto 14px;
}

/* 一屏正好一页（4 格 + 3 道缝）：多出来的格子被裁掉，翻页时整条轨道滑过去 */
.gallery__viewport {
    width: 762px;
    max-width: 100%;
    overflow: hidden;
}

.gallery__track {
    display: flex;
    column-gap: 14px;
    transition: transform 0.3s ease;
    will-change: transform;
}

.gallery__cell {
    flex: 0 0 180px;
}

/* 不加底色、不做圆角：截图是什么样就什么样，方框只负责限尺寸 */
.gallery__frame {
    width: 180px;
    height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
}

/* 没有封面时的空占位：虚线框，只表示「这里留给封面」 */
.gallery__frame--empty {
    border: 1px dashed #cbd5e1;
}

.gallery__img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    object-position: center;
    display: block;
    cursor: zoom-in;
}

/* 定高的一行：描述再长也只占一行，超出省略 */
.gallery__caption {
    margin: 4px 0 0;
    height: 18px;
    line-height: 18px;
    font-size: 12px;
    color: #64748b;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* 翻页按钮压在画面左右边缘上：图片栏宽度正好是 4 格，两侧没有多余空间可占 */
.gallery__nav {
    position: absolute;
    top: 90px;
    transform: translateY(-50%);
    z-index: 1;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 0 2px;
    border: 0;
    border-radius: 50%;
    background: rgba(15, 23, 42, 0.45);
    color: #fff;
    font-size: 20px;
    line-height: 1;
    cursor: pointer;
    transition: background 0.15s ease, opacity 0.15s ease;
}

.gallery__nav:hover:not(:disabled) {
    background: rgba(15, 23, 42, 0.72);
}

.gallery__nav:disabled {
    opacity: 0.25;
    cursor: default;
}

.gallery__nav--prev {
    left: 6px;
}

.gallery__nav--next {
    right: 6px;
}

/* ---------- 看大图 ---------- */

/* 遮罩铺满视口，图片在正中：单击遮罩（或图片，它会冒泡上来）就退回 */
.viewer {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4vh 4vw;
    background: rgba(15, 23, 42, 0.86);
    cursor: zoom-out;
}

/* 撑满遮罩去掉内边距后的那圈空间，图按 contain 放大到触到某条边为止——
   用 width/height 100% 而不是 max-*，否则比 180px 格子大不了多少的小图不会被放大；
   四周多出来的部分留黑（不裁切、不出现滚动条） */
.viewer__img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
}

/* 翻页按钮压在遮罩左右边缘（图片之上）：遮罩是深的，所以用半透明白，
   比图片栏那对深色按钮更看得见。到头的那个置灰 */
.viewer__nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 0 4px;
    border: 0;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.16);
    color: #fff;
    font-size: 30px;
    line-height: 1;
    cursor: pointer;
    transition: background 0.15s ease, opacity 0.15s ease;
}

.viewer__nav:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.3);
}

.viewer__nav:disabled {
    opacity: 0.25;
    cursor: default;
}

.viewer__nav--prev {
    left: 3vw;
}

.viewer__nav--next {
    right: 3vw;
}
</style>
