<template>
    <!-- 美化封面：左边原封面、右边合成结果，确认就把合成图存成该游戏的新封面。
         弹出即自动合成（没有「制作」这一步）。**样式由游戏类型给一组**（见
         constants/coverStyles.js 的 beautifyStylesFor），第一个是默认样式；
         标题右边始终有一排方框单选（只有一个样式的类型也出、那一项不可选），
         切换只重新合成、不重新下载原封面。

         入口是游戏管理页编辑弹框「游戏封面」那行的「美化封面」按钮，只在
         类型支持美化且该游戏已有封面时可用。 -->
    <app-dialog
        :model-value="modelValue"
        title="美化封面"
        width="720px"
        confirm-text="确认"
        :confirm-disabled="!blob"
        :confirm-loading="confirmLoading"
        @update:model-value="emit('update:modelValue', $event)"
        @confirm="onConfirm"
    >
        <template #header>
            <!-- 每个样式都在这里露个名字（flash→DISK、gba→GBA 这类只有一个样式的类型
                 也出，只是那一项点不动）：一排方框单选就是这盘封面会变成什么壳 -->
            <app-segmented
                v-if="styles.length"
                v-model="styleId"
                class="cover-beautify__styles"
                :options="styleOptions"
                size="sm"
                aria-label="封面样式"
                @change="compose"
            />
        </template>

        <div class="cover-beautify">
            <!-- 建议尺寸按样式取：各样式洞口的比例差得很远（GBA 是 1.97:1 的横版，
                 NES 是 0.61:1 的竖版） -->
            <p class="cover-beautify__hint">{{ styleHint }}</p>

            <div class="cover-beautify__panes">
                <section class="cover-beautify__pane">
                    <h3 class="cover-beautify__pane-title">原封面</h3>
                    <div class="cover-beautify__stage">
                        <img v-if="sourceUrl" :src="sourceUrl" alt="原封面" />
                    </div>
                    <p class="cover-beautify__meta">{{ sourceMeta }}</p>
                </section>

                <section class="cover-beautify__pane">
                    <h3 class="cover-beautify__pane-title">美化后</h3>
                    <!-- 棋盘格底：光盘圆外与卡带轮廓外的透明区一眼可见 -->
                    <div
                        v-loading="status === 'working'"
                        class="cover-beautify__stage cover-beautify__stage--checker"
                    >
                        <img v-if="resultUrl" :src="resultUrl" alt="美化后的封面" />
                        <span v-else-if="status === 'error'" class="cover-beautify__error">
                            合成失败
                        </span>
                    </div>
                    <p class="cover-beautify__meta">{{ resultMeta }}</p>
                </section>
            </div>

            <p class="cover-beautify__warn">
                确认后将覆盖该游戏当前的封面，原封面文件会被删除。
            </p>
        </div>
    </app-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import AppDialog from "@components/common/AppDialog.vue";
import { gameCoverPath } from "@/api/games";
import { beautifyStylesFor } from "@/constants/coverStyles";
import { composeCover, loadImage } from "@/utils/coverCompose";

const props = defineProps({
    modelValue: { type: Boolean, default: false },
    // 要美化的游戏（管理页载荷：需要 id / game_type / cover_path / updated_at）
    game: { type: Object, default: null },
    // 上传中：确认按钮转圈，并挡掉重复提交
    confirmLoading: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "confirm"]);

const status = ref("idle"); // idle | working | ready | error
const sourceUrl = ref("");
const sourceMeta = ref("");
const resultUrl = ref("");
const resultMeta = ref("");
const blob = ref(null);

/** 这个游戏类型可用的样式（空数组 = 不支持，正常走不到这儿） */
const styles = computed(() => beautifyStylesFor(props.game?.game_type));
/** 只有一个样式时也显示出来，但不可点（它表示「就是这种壳」） */
const styleOptions = computed(() =>
    styles.value.map((item) => ({
        label: item.label,
        value: item.id,
        disabled: styles.value.length < 2,
    })),
);
/** 当前选中的样式 id（打开时重置成列表第一个，也就是默认样式） */
const styleId = ref("");
const style = computed(
    () => styles.value.find((item) => item.id === styleId.value) || styles.value[0] || null
);
const styleHint = computed(() => style.value?.hint || "该游戏类型暂不支持封面美化。");

// 已经载入好的原封面：切样式时直接拿它重合成，不再走一次网络
let sourceImage = null;
// 每轮合成发一个号：弹框关掉、重开或又切了样式时号会变，
// 在途的那次回来发现号对不上就丢弃，免得它把结果写进下一次的预览里
let runToken = 0;

function releaseResult() {
    if (resultUrl.value) {
        URL.revokeObjectURL(resultUrl.value);
    }
    resultUrl.value = "";
    resultMeta.value = "";
    blob.value = null;
}

function reset() {
    runToken += 1;
    releaseResult();
    status.value = "idle";
    sourceUrl.value = "";
    sourceMeta.value = "";
    sourceImage = null;
}

/** 合成当前样式。只用已经载入好的原封面（切样式走这条）。 */
async function compose() {
    const current = style.value;
    if (!current || !sourceImage) {
        return;
    }
    const token = ++runToken;
    releaseResult();
    status.value = "working";
    try {
        const composed = await composeCover(
            current.id,
            sourceImage,
            props.game?.cartridge_id,
        );
        if (token !== runToken) {
            return;
        }
        blob.value = composed;
        resultUrl.value = URL.createObjectURL(composed);
        resultMeta.value = `美化后 ${current.output.width} × ${current.output.height}`;
        status.value = "ready";
    } catch (err) {
        if (token !== runToken) {
            return;
        }
        status.value = "error";
        ElMessage.error(err?.message || "美化失败，请重试。");
    }
}

/** 弹出时跑一次：载入原封面 → 合成默认样式。
 *  原封面走 gameCoverPath（同源直连后端），不走 Service Worker——少一层缓存。 */
async function run() {
    reset();
    const list = styles.value;
    const gameId = props.game?.id;
    if (!list.length || !gameId || !props.game?.cover_path) {
        return;
    }
    // 默认样式：游戏当前的封面类型命中列表里哪个就选哪个（上次美化用的就是它），
    // 没设过（新建的游戏都是空的）就是列表第一个
    const preferred = list.find((item) => item.id === props.game?.cover_type);
    styleId.value = (preferred || list[0]).id;
    const token = ++runToken;
    status.value = "working";
    try {
        const src = gameCoverPath(gameId, props.game.updated_at);
        const image = await loadImage(src);
        if (token !== runToken) {
            return;
        }
        sourceImage = image;
        sourceUrl.value = src;
        sourceMeta.value = `原封面 ${image.naturalWidth} × ${image.naturalHeight}`;
    } catch (err) {
        if (token !== runToken) {
            return;
        }
        status.value = "error";
        ElMessage.error(err?.message || "原封面加载失败。");
        return;
    }
    // 这里是直接赋 styleId，不走单选的 change 事件，所以只会合成一次
    await compose();
}

function onConfirm() {
    if (!blob.value || props.confirmLoading) {
        return;
    }
    // 样式 id 一起交出去：管理页要把它写进游戏的封面类型（与封面文件同一次提交）
    emit("confirm", { blob: blob.value, styleId: styleId.value });
}

// AppDialog 是 destroy-on-close，但它只销毁插槽内容，本组件的 ref 不会重置，
// 所以每次打开都得自己重跑一遍
watch(
    () => props.modelValue,
    (visible) => {
        if (visible) {
            run();
        } else {
            reset();
        }
    }
);

onBeforeUnmount(reset);
</script>

<style scoped>
/* 标题右边那排样式分段按钮：跟着标题的基线走，别把标题挤下去 */
.cover-beautify__styles {
    margin-left: 16px;
    vertical-align: middle;
}

/* 建议尺寸：一行说明，压在两个预览区上面 */
.cover-beautify__hint {
    margin: 0 0 14px;
    font-size: 13px;
    line-height: 1.6;
    color: #475569;
}

.cover-beautify__panes {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 16px;
}

.cover-beautify__pane {
    min-width: 0;
}

.cover-beautify__pane-title {
    margin: 0 0 8px;
    font-size: 13px;
    font-weight: 600;
    color: #334155;
}

/* 两个预览框等高（图片按 contain 缩放到框内，不裁不拉），右栏铺棋盘格 */
.cover-beautify__stage {
    height: 260px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: #fff;
}

.cover-beautify__stage--checker {
    background-color: #fff;
    background-image:
        linear-gradient(45deg, #e2e8f0 25%, transparent 25%, transparent 75%, #e2e8f0 75%),
        linear-gradient(45deg, #e2e8f0 25%, transparent 25%, transparent 75%, #e2e8f0 75%);
    background-size: 16px 16px;
    background-position: 0 0, 8px 8px;
}

.cover-beautify__stage img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
}

.cover-beautify__error {
    font-size: 13px;
    color: #94a3b8;
}

.cover-beautify__meta {
    margin: 8px 0 0;
    font-size: 12px;
    color: var(--text-muted);
    text-align: center;
}

.cover-beautify__warn {
    margin: 16px 0 0;
    font-size: 12px;
    line-height: 1.6;
    color: #b45309;
}
</style>
