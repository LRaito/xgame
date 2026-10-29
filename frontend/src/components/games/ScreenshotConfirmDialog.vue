<template>
    <!-- 截完先在这里确认：上面 180px 正方形限制框预览（与游戏详情图片栏同一套缩放），
         下面一行描述（刚好放下 15 字），点「确认」或直接回车才真正上传入库 -->
    <app-dialog
        :model-value="modelValue"
        title="保存截图"
        width="320px"
        align-center
        confirm-text="确认"
        :confirm-loading="saving"
        @update:model-value="emit('update:modelValue', $event)"
        @confirm="onConfirm"
    >
        <div class="shot-confirm">
            <!-- 宽度固定 180，高度按截图真实比例（竖屏如 NDS 会变高；横屏仍限在 180 方框内） -->
            <div class="shot-confirm__frame" :style="frameStyle">
                <img v-if="previewUrl" class="shot-confirm__img" :src="previewUrl" alt="截图预览" />
            </div>
            <!-- 单行输入：回车即确认（描述最多 15 字，一行放得下） -->
            <input
                ref="descInputRef"
                v-model="descDraft"
                class="shot-confirm__input"
                maxlength="15"
                placeholder="描述（可选）"
                @keydown.enter.prevent="onConfirm"
            />
        </div>
    </app-dialog>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import AppDialog from "@components/common/AppDialog.vue";

const props = defineProps({
    modelValue: { type: Boolean, default: false },
    // 截下来的那张图（父组件的 objectURL）
    previewUrl: { type: String, default: "" },
    // 截图的真实像素宽高：预览框按比例变高（NDS 双屏是竖版），拿不到就退回 1:1
    previewWidth: { type: Number, default: 0 },
    previewHeight: { type: Number, default: 0 },
    // 上传中：确认按钮转圈，并挡掉重复提交
    saving: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "confirm"]);

const descDraft = ref("");
const descInputRef = ref(null);

// 框宽固定 180，高度 = 180 / 比例。比例大于 1（横图）时仍按 1 算，保持 180 方框。
const frameStyle = computed(() => {
    const ratio =
        props.previewWidth > 0 && props.previewHeight > 0
            ? Math.min(1, props.previewWidth / props.previewHeight)
            : 1;
    return { aspectRatio: String(ratio) };
});

function onConfirm() {
    if (props.saving) {
        return;
    }
    emit("confirm", descDraft.value.trim().slice(0, 15));
}

// 每次弹出都是一张新截图：描述从空开始，焦点直接落在描述框上（敲完回车就确认）
watch(
    () => props.modelValue,
    async (visible) => {
        if (!visible) {
            return;
        }
        descDraft.value = "";
        await nextTick();
        descInputRef.value?.focus();
    }
);
</script>

<style scoped>
.shot-confirm {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
}

/* 与游戏详情图片栏同一套限制：宽 180（不加底色、不做圆角），高度按截图的
   aspect-ratio 算（竖版 NDS 会变成 180 × 约 308），图片等比缩放到框内 */
.shot-confirm__frame {
    flex: 0 0 auto;
    width: 180px;
    height: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
}

.shot-confirm__img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    object-position: center;
    display: block;
}

.shot-confirm__input {
    display: block;
    width: 100%;
    height: 32px;
    box-sizing: border-box;
    padding: 0 10px;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #0f172a;
    font-size: 13px;
    font-family: inherit;
}

.shot-confirm__input:focus {
    outline: none;
    border-color: var(--el-color-primary);
}
</style>
