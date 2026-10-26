<template>
    <div
        class="app-segmented"
        :class="[`app-segmented--${tone}`, `app-segmented--${size}`]"
        role="group"
        :aria-label="ariaLabel || undefined"
    >
        <button
            v-for="option in options"
            :key="option.value"
            type="button"
            class="app-segmented__item"
            :class="{ 'is-active': option.value === modelValue }"
            :disabled="disabled || option.disabled"
            :aria-pressed="String(option.value === modelValue)"
            @click="select(option)"
        >
            {{ option.label }}
        </button>
    </div>
</template>

<script setup>
const props = defineProps({
    modelValue: { type: [String, Number], default: "" },
    // [{ label, value, disabled? }]
    options: { type: Array, default: () => [] },
    tone: { type: String, default: "light" },
    size: { type: String, default: "md" },
    ariaLabel: { type: String, default: "" },
    disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "change"]);

function select(option) {
    if (props.disabled || option.disabled || option.value === props.modelValue) {
        return;
    }
    emit("update:modelValue", option.value);
    emit("change", option.value);
}
</script>

<style>
/* 分段控件与 AppButton 共享高度、圆角、焦点环与禁用 token。
   用普通 button + aria-pressed，避免 el-radio-group 的左右键行为抢分页键。 */
.app-segmented {
    display: inline-flex;
}

.app-segmented--sm {
    --_seg-h: var(--app-control-h-sm);
    --_seg-px: 12px;
    --_seg-fs: var(--app-font-size-sm);
}

.app-segmented--md {
    --_seg-h: var(--app-control-h-md);
    --_seg-px: 18px;
    --_seg-fs: var(--app-font-size-md);
}

.app-segmented--lg {
    --_seg-h: var(--app-control-h-lg);
    --_seg-px: 40px;
    --_seg-fs: var(--app-font-size-lg);
}

.app-segmented--light {
    --_seg-bg: var(--surface);
    --_seg-fg: var(--app-text-muted);
    --_seg-border: var(--app-border);
    --_seg-hover-bg: var(--app-surface-subtle);
    --_seg-hover-fg: var(--app-color-primary);
    --_seg-hover-border: var(--app-color-primary-hover);
    --_seg-active-bg: var(--app-color-selected-bg);
    --_seg-active-border: var(--app-color-selected-border);
    --_seg-active-fg: var(--app-color-selected-fg);
    --_seg-disabled-bg: var(--app-color-disabled-bg);
    --_seg-disabled-border: var(--app-color-disabled-border);
    --_seg-disabled-fg: var(--app-color-disabled-text);
    --_seg-focus: var(--app-focus-ring-light);
}

.app-segmented--dark {
    --_seg-bg: rgba(30, 41, 59, 0.6);
    --_seg-fg: #cbd5e1;
    --_seg-border: rgba(148, 163, 184, 0.24);
    --_seg-hover-bg: rgba(51, 65, 85, 0.9);
    --_seg-hover-fg: #fff;
    --_seg-hover-border: var(--app-dark-accent-border);
    --_seg-active-bg: var(--app-dark-primary);
    --_seg-active-border: var(--app-dark-accent-border);
    --_seg-active-fg: #e6f5fd;
    --_seg-disabled-bg: var(--app-disabled-bg-dark);
    --_seg-disabled-border: var(--app-disabled-border-dark);
    --_seg-disabled-fg: var(--app-disabled-text-dark);
    --_seg-focus: var(--app-focus-ring-dark);
}

.app-segmented__item {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: var(--_seg-h);
    margin-left: -1px;
    padding: 0 var(--_seg-px);
    border: 1px solid var(--_seg-border);
    background: var(--_seg-bg);
    color: var(--_seg-fg);
    font-family: inherit;
    font-size: var(--_seg-fs);
    font-weight: 500;
    line-height: 1;
    letter-spacing: 1px;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
    transition:
        background-color 0.15s ease,
        border-color 0.15s ease,
        color 0.15s ease;
}

.app-segmented__item:first-child {
    margin-left: 0;
    border-radius: var(--app-radius-button) 0 0 var(--app-radius-button);
}

.app-segmented__item:last-child {
    border-radius: 0 var(--app-radius-button) var(--app-radius-button) 0;
}

.app-segmented__item:only-child {
    border-radius: var(--app-radius-button);
}

.app-segmented__item:hover:not(:disabled):not(.is-active) {
    background: var(--_seg-hover-bg);
    color: var(--_seg-hover-fg);
    border-color: var(--_seg-hover-border);
}

.app-segmented__item.is-active {
    position: relative;
    z-index: 1;
    background: var(--_seg-active-bg);
    border-color: var(--_seg-active-border);
    color: var(--_seg-active-fg);
}

.app-segmented__item:disabled {
    background: var(--_seg-disabled-bg);
    border-color: var(--_seg-disabled-border);
    color: var(--_seg-disabled-fg);
    cursor: not-allowed;
}

/* 只有一个选项时，它是「已选中的事实」，不是灰掉的控件 */
.app-segmented__item.is-active:disabled {
    background: var(--_seg-active-bg);
    border-color: var(--_seg-active-border);
    color: var(--_seg-active-fg);
    cursor: default;
}

.app-segmented__item:focus-visible {
    position: relative;
    z-index: 2;
    outline: var(--app-focus-axis) solid var(--_seg-focus);
    outline-offset: var(--app-focus-offset);
}

@media (prefers-reduced-motion: reduce) {
    .app-segmented__item {
        transition: none;
    }
}
</style>
