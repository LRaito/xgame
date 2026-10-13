<template>
    <div ref="rootRef" class="emu-filter-select">
        <span class="emu-filter-select__text">滤镜</span>
        <button
            type="button"
            class="emu-filter-select__button"
            :aria-expanded="open ? 'true' : 'false'"
            @click="open = !open"
        >
            {{ currentLabel }}
        </button>

        <!-- 面板就地渲染在标题栏里（不 teleport）：鼠标移进面板仍算在标题栏内，
             标题栏不会收起把它一起带走 -->
        <div v-if="open" class="emu-filter-select__panel">
            <button
                v-for="filter in filters"
                :key="filter.id"
                type="button"
                class="emu-filter-select__cell"
                :class="{ 'is-active': filter.id === modelValue }"
                @click="pick(filter.id)"
            >
                {{ filter.label }}
            </button>
        </div>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
    // 当前滤镜 id；表里没有的值（换了清单）由父页面回落后再传进来
    modelValue: { type: String, default: "none" },
    // 该游戏类型的滤镜清单（见 constants/emuFilters.js），第一项恒为「无」
    filters: { type: Array, required: true },
});

const emit = defineEmits(["update:modelValue"]);

const rootRef = ref(null);
const open = ref(false);

const currentLabel = computed(() => {
    const hit = props.filters.find((filter) => filter.id === props.modelValue);
    return hit ? hit.label : props.filters[0]?.label || "无";
});

function pick(id) {
    emit("update:modelValue", id);
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
.emu-filter-select {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
}

.emu-filter-select__text {
    font-size: 13px;
    color: #94a3b8;
    white-space: nowrap;
}

/* 与标题栏的按钮（.game-shell__btn / .emulator-player__action）同一套盒模型：
   8px 上下内边距 + 14px 字号 + 1.6 行高 = 40px 高，并排时上下沿对齐 */
.emu-filter-select__button {
    padding: 8px 10px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 8px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 14px;
    line-height: 1.6;
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
    white-space: nowrap;
}

.emu-filter-select__button:hover {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}

.emu-filter-select__button:focus-visible {
    outline: none;
    border-color: #38bdf8;
}

/* 面板挂在按钮下方、右对齐：标题栏靠右，右对齐才不会被视口切掉 */
.emu-filter-select__panel {
    position: absolute;
    top: calc(100% + 10px);
    right: 0;
    z-index: 30;
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 10px;
    background: rgba(15, 23, 42, 0.96);
    box-shadow: 0 14px 34px rgba(2, 6, 23, 0.55);
    backdrop-filter: blur(8px);
}

.emu-filter-select__cell {
    padding: 8px 10px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 13px;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s ease, border-color 0.15s ease;
}

.emu-filter-select__cell:hover {
    background: rgba(51, 65, 85, 0.95);
    border-color: rgba(148, 163, 184, 0.4);
}

/* 当前生效的那一项点亮 */
.emu-filter-select__cell.is-active {
    background: rgba(37, 99, 235, 0.85);
    border-color: rgba(96, 165, 250, 0.6);
    color: #f8fafc;
}
</style>
