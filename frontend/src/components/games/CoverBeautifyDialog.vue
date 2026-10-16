<template>
    <!-- 美化封面：左边原封面、右边合成结果，确认就把合成图存成该游戏的新封面。
         弹出即自动合成（没有「制作」这一步），样式由游戏类型决定，用户不用选 —— 见
         constants/coverStyles.js 的 beautifyStyleFor()。

         入口是游戏管理页编辑弹框「游戏封面」那行的「美化封面」按钮，只在
         支持美化的类型（flash / gb / gba）且该游戏已有封面时可用。 -->
    <app-dialog
        :model-value="modelValue"
        title="美化封面"
        width="720px"
        @update:model-value="emit('update:modelValue', $event)"
    >
        <div class="cover-beautify">
            <!-- 建议尺寸按样式取：三种样式的输入比例差别很大（GBA 洞口是 1.97:1 的横版） -->
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
                    <!-- 棋盘格底：光盘圆外与卡带圆角外的透明区一眼可见 -->
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

        <template #footer>
            <app-button @click="emit('update:modelValue', false)">取消</app-button>
            <app-button
                type="primary"
                :disabled="!blob"
                :loading="confirmLoading"
                @click="onConfirm"
            >
                确认
            </app-button>
        </template>
    </app-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import AppDialog from "@components/common/AppDialog.vue";
import { gameCoverPath } from "@/api/games";
import { beautifyStyleFor } from "@/constants/coverStyles";
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

const styleHint = computed(
    () => beautifyStyleFor(props.game?.game_type)?.hint || "该游戏类型暂不支持封面美化。"
);

// 每轮合成发一个号：弹框关掉或重开时号会变，在途的那次回来发现号对不上就丢弃，
// 免得它把结果写进下一次打开的弹框里
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
}

/** 弹出即合成。原封面走 gameCoverPath（同源直连后端），不走 Service Worker——少一层缓存。 */
async function run() {
    reset();
    const style = beautifyStyleFor(props.game?.game_type);
    const gameId = props.game?.id;
    if (!style || !gameId || !props.game?.cover_path) {
        return;
    }
    const token = ++runToken;
    status.value = "working";
    try {
        const src = gameCoverPath(gameId, props.game.updated_at);
        const image = await loadImage(src);
        if (token !== runToken) {
            return;
        }
        sourceUrl.value = src;
        sourceMeta.value = `原封面 ${image.naturalWidth} × ${image.naturalHeight}`;

        const composed = await composeCover(style.id, image);
        if (token !== runToken) {
            return;
        }
        blob.value = composed;
        resultUrl.value = URL.createObjectURL(composed);
        resultMeta.value = `美化后 ${style.output.width} × ${style.output.height}`;
        status.value = "ready";
    } catch (err) {
        if (token !== runToken) {
            return;
        }
        status.value = "error";
        ElMessage.error(err?.message || "美化失败，请重试。");
    }
}

function onConfirm() {
    if (!blob.value || props.confirmLoading) {
        return;
    }
    emit("confirm", blob.value);
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
