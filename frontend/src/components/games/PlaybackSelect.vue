<template>
    <div ref="rootRef" class="playback-select">
        <span v-if="label" class="playback-select__text">{{ label }}</span>
        <app-button
            class="playback-select__button"
            variant="secondary"
            tone="dark"
            size="lg"
            :aria-expanded="open ? 'true' : 'false'"
            @click="open = !open"
        >
            {{ currentLabel }}
        </app-button>

        <!-- 面板就地渲染在标题栏里（不 teleport）：鼠标移进面板仍算在标题栏内，
             标题栏不会收起把它一起带走 -->
        <div v-if="open" class="playback-select__panel">
            <app-button
                v-for="option in options"
                :key="option.value"
                class="playback-select__cell"
                variant="secondary"
                tone="dark"
                size="sm"
                block
                :pressed="option.value === modelValue"
                @click="pick(option.value)"
            >
                {{ option.label }}
            </app-button>
        </div>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

// 播放页标题栏里的通用下拉：触发按钮与面板格子统一用 AppButton（深色、大号触发、
// 小号格子），「画质 / 窗口」两处共用这一个组件，样式保持一致。
const props = defineProps({
    // 左侧标签（画质 / 窗口）；空字符串则不显示
    label: { type: String, default: "" },
    modelValue: { type: String, default: "" },
    // [{ value, label }]；当前值不在表里时显示第一项
    options: { type: Array, required: true },
});

const emit = defineEmits(["update:modelValue"]);

const rootRef = ref(null);
const open = ref(false);

const currentLabel = computed(() => {
    const hit = props.options.find((option) => option.value === props.modelValue);
    return hit ? hit.label : props.options[0]?.label || "";
});

function pick(value) {
    emit("update:modelValue", value);
    open.value = false;
}

function onDocumentPointerDown(event) {
    if (!rootRef.value?.contains(event.target)) {
        open.value = false;
    }
}

function onDocumentKeydown(event) {
    if (event.key === "Escape") {
        open.value = false;
    }
}

// 只在面板打开期间挂全局监听（点外面/按 ESC 收起）
watch(open, (value) => {
    if (value) {
        document.addEventListener("pointerdown", onDocumentPointerDown, true);
        document.addEventListener("keydown", onDocumentKeydown);
    } else {
        document.removeEventListener("pointerdown", onDocumentPointerDown, true);
        document.removeEventListener("keydown", onDocumentKeydown);
    }
});

onBeforeUnmount(() => {
    document.removeEventListener("pointerdown", onDocumentPointerDown, true);
    document.removeEventListener("keydown", onDocumentKeydown);
});
</script>

<style scoped>
.playback-select {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
}

.playback-select__text {
    font-size: 13px;
    color: #94a3b8;
    white-space: nowrap;
}

/* 面板挂在按钮下方、右对齐：标题栏靠右，右对齐才不会被视口切掉 */
.playback-select__panel {
    position: absolute;
    top: calc(100% + 10px);
    right: 0;
    z-index: 30;
    display: grid;
    grid-template-columns: 1fr;
    gap: 4px;
    padding: 8px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 10px;
    background: rgba(15, 23, 42, 0.96);
    box-shadow: 0 14px 34px rgba(2, 6, 23, 0.55);
    backdrop-filter: blur(8px);
}

/* Element Plus 给相邻按钮加 12px 左边距，会把格子挤出面板；面板内一律贴齐 */
.playback-select__panel :deep(.el-button) {
    margin-left: 0;
}
</style>
