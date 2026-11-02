<template>
    <el-button
        class="app-button"
        :class="[
            `app-button--${resolvedVariant}`,
            `app-button--${resolvedSize}`,
            `app-button--${tone}`,
            {
                'app-button--text': text,
                'app-button--block': block,
                'app-button--icon-only': iconOnly,
                'app-button--round': round,
                'app-button--pressed': isPressed,
            },
        ]"
        :loading="loading"
        :disabled="disabled"
        :native-type="nativeType"
        :aria-label="ariaLabel || undefined"
        :aria-pressed="pressedState"
        @click="$emit('click', $event)"
    >
        <slot />
    </el-button>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
    // 只有两种类型：secondary（其他按钮）/ danger（删除按钮）
    variant: { type: String, default: "secondary" },
    // sm 行内 / md 工具栏与弹框 / lg 播放器
    size: { type: String, default: "md" },
    // light 浅色页面 / dark 深色区域 / image 图片上 / overlay 遮罩上
    tone: { type: String, default: "light" },
    // 无框形态：行内文字与浮在内容上的图标按钮
    text: { type: Boolean, default: false },
    // 开关型按钮：null = 不是开关
    pressed: { type: Boolean, default: null },
    block: { type: Boolean, default: false },
    iconOnly: { type: Boolean, default: false },
    round: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    nativeType: { type: String, default: "button" },
    ariaLabel: { type: String, default: "" },
});

defineEmits(["click"]);

const resolvedVariant = computed(() =>
    props.variant === "danger" ? "danger" : "secondary",
);

const resolvedSize = computed(() => {
    if (props.size === "xs") {
        return "sm";
    }
    return ["sm", "md", "lg"].includes(props.size) ? props.size : "md";
});

const isPressed = computed(() => props.pressed === true);
const pressedState = computed(() => {
    if (props.pressed === null || props.pressed === undefined) {
        return undefined;
    }
    return String(props.pressed);
});
</script>

<style>
/* 两种类型、三个尺寸、四种场景。
   tone 只定义配色变量，variant 只消费变量；text 是去掉背景和边框的形态，
   pressed 是开关的选中状态，两者都不是第三种按钮类型。 */
.app-button.el-button {
    gap: 6px;
    height: var(--_btn-h, var(--app-control-h-md));
    padding: 0 var(--_btn-px, var(--app-control-px-md));
    border-radius: var(--app-radius-button);
    font-family: inherit;
    font-size: var(--_btn-fs, var(--app-font-size-md));
    font-weight: 500;
    transition:
        background-color 0.15s ease,
        border-color 0.15s ease,
        color 0.15s ease,
        opacity 0.15s ease,
        box-shadow 0.15s ease;
}

.app-button--sm {
    --_btn-h: var(--app-control-h-sm);
    --_btn-px: var(--app-control-px-sm);
    --_btn-fs: var(--app-font-size-sm);
}

.app-button--md {
    --_btn-h: var(--app-control-h-md);
    --_btn-px: var(--app-control-px-md);
    --_btn-fs: var(--app-font-size-md);
}

.app-button--lg {
    --_btn-h: var(--app-control-h-lg);
    --_btn-px: var(--app-control-px-lg);
    --_btn-fs: var(--app-font-size-lg);
}

/* ---------- tone：只定义变量 ---------- */
.app-button.app-button--light {
    --_btn-bg: #fff;
    --_btn-hover-bg: #eee;
    --_btn-active-bg: #eee;
    --_btn-secondary-fg: #0098ee;
    --_btn-secondary-border: #0098ee;
    --_btn-secondary-border-hover: #33acf1;
    --_btn-secondary-border-focus: #0088d5;
    --_btn-danger-fg: #ff3320;
    --_btn-danger-border: #ff3320;
    --_btn-danger-border-hover: #ff3320;
    --_btn-danger-border-focus: #ff3320;
    --_btn-text-fg: #0098ee;
    --_btn-text-hover-fg: #0088d5;
    --_btn-text-hover-bg: #eee;
    --_btn-text-disabled-fg: #aaa;
    --_btn-pressed-bg: var(--app-color-selected-bg);
    --_btn-pressed-fg: var(--app-color-selected-fg);
    --_btn-pressed-border: var(--app-color-selected-border);
    --_btn-disabled-bg: #eee;
    --_btn-disabled-border: #eee;
    --_btn-disabled-fg: #aaa;
}

.app-button.app-button--dark {
    --_btn-bg: rgba(30, 41, 59, 0.72);
    --_btn-hover-bg: rgba(51, 65, 85, 0.9);
    --_btn-active-bg: rgba(51, 65, 85, 0.9);
    --_btn-secondary-fg: #7fd4f8;
    --_btn-secondary-border: #33acf1;
    --_btn-secondary-border-hover: #66c2f5;
    --_btn-secondary-border-focus: #7fd4f8;
    --_btn-danger-fg: #ff6b5c;
    --_btn-danger-border: #ff6b5c;
    --_btn-danger-border-hover: #ff8a7e;
    --_btn-danger-border-focus: #ff8a7e;
    --_btn-text-fg: #e2e8f0;
    --_btn-text-hover-fg: #fff;
    --_btn-text-hover-bg: rgba(255, 255, 255, 0.1);
    --_btn-text-disabled-fg: #7a8699;
    --_btn-pressed-bg: var(--app-dark-primary);
    --_btn-pressed-fg: #fff;
    --_btn-pressed-border: var(--app-dark-primary-border);
    --_btn-disabled-bg: var(--app-disabled-bg-dark);
    --_btn-disabled-border: var(--app-disabled-border-dark);
    --_btn-disabled-fg: var(--app-disabled-text-dark);
    /* 深色按钮上的 loading 遮罩不能用白 */
    --el-mask-color-extra-light: rgba(15, 23, 42, 0.35);
}

.app-button.app-button--image {
    --_btn-bg: var(--app-image-surface);
    --_btn-hover-bg: var(--app-image-surface-hover);
    --_btn-active-bg: var(--app-image-surface-hover);
    --_btn-secondary-fg: #e6f5fd;
    --_btn-secondary-border: #7fd4f8;
    --_btn-secondary-border-hover: #9addfa;
    --_btn-secondary-border-focus: #fff;
    --_btn-danger-fg: #ff8a7e;
    --_btn-danger-border: #ff8a7e;
    --_btn-danger-border-hover: #ffb0a8;
    --_btn-danger-border-focus: #ffb0a8;
    --_btn-text-fg: #e6f5fd;
    --_btn-text-hover-fg: #fff;
    --_btn-text-hover-bg: rgba(255, 255, 255, 0.15);
    --_btn-text-disabled-fg: rgba(226, 232, 240, 0.45);
    --_btn-pressed-bg: rgba(0, 152, 238, 0.5);
    --_btn-pressed-fg: #fff;
    --_btn-pressed-border: #fff;
    --_btn-disabled-bg: rgba(15, 23, 42, 0.35);
    --_btn-disabled-border: rgba(148, 163, 184, 0.2);
    --_btn-disabled-fg: rgba(226, 232, 240, 0.45);
}

.app-button.app-button--overlay {
    --_btn-bg: var(--app-overlay-surface);
    --_btn-hover-bg: var(--app-overlay-surface-hover);
    --_btn-active-bg: var(--app-overlay-surface-hover);
    --_btn-secondary-fg: #fff;
    --_btn-secondary-border: #7fd4f8;
    --_btn-secondary-border-hover: #e6f5fd;
    --_btn-secondary-border-focus: #fff;
    --_btn-danger-fg: #ff8a7e;
    --_btn-danger-border: #ff8a7e;
    --_btn-danger-border-hover: #ffb0a8;
    --_btn-danger-border-focus: #ffb0a8;
    --_btn-text-fg: #fff;
    --_btn-text-hover-fg: #e6f5fd;
    --_btn-text-hover-bg: rgba(255, 255, 255, 0.18);
    --_btn-text-disabled-fg: rgba(255, 255, 255, 0.4);
    --_btn-pressed-bg: rgba(0, 152, 238, 0.5);
    --_btn-pressed-fg: #fff;
    --_btn-pressed-border: #fff;
    --_btn-disabled-bg: rgba(255, 255, 255, 0.06);
    --_btn-disabled-border: rgba(255, 255, 255, 0.12);
    --_btn-disabled-fg: rgba(255, 255, 255, 0.4);
}

/* ---------- variant：只消费 tone 变量 ---------- */
.app-button.app-button--secondary {
    --el-button-bg-color: var(--_btn-bg);
    --el-button-text-color: var(--_btn-secondary-fg);
    --el-button-border-color: var(--_btn-secondary-border);
    --el-button-hover-bg-color: var(--_btn-hover-bg);
    --el-button-hover-text-color: var(--_btn-secondary-fg);
    --el-button-hover-border-color: var(--_btn-secondary-border-hover);
    --el-button-active-bg-color: var(--_btn-active-bg);
    --el-button-active-text-color: var(--_btn-secondary-fg);
    --el-button-active-border-color: var(--_btn-secondary-border-hover);
    --el-button-disabled-bg-color: var(--_btn-disabled-bg);
    --el-button-disabled-border-color: var(--_btn-disabled-border);
    --el-button-disabled-text-color: var(--_btn-disabled-fg);
    --_btn-border-focus: var(--_btn-secondary-border-focus);
}

.app-button.app-button--danger {
    --el-button-bg-color: var(--_btn-bg);
    --el-button-text-color: var(--_btn-danger-fg);
    --el-button-border-color: var(--_btn-danger-border);
    --el-button-hover-bg-color: var(--_btn-hover-bg);
    --el-button-hover-text-color: var(--_btn-danger-border-hover);
    --el-button-hover-border-color: var(--_btn-danger-border-hover);
    --el-button-active-bg-color: var(--_btn-active-bg);
    --el-button-active-text-color: var(--_btn-danger-border-hover);
    --el-button-active-border-color: var(--_btn-danger-border-hover);
    --el-button-disabled-bg-color: var(--_btn-disabled-bg);
    --el-button-disabled-border-color: var(--_btn-disabled-border);
    --el-button-disabled-text-color: var(--_btn-disabled-fg);
    --_btn-border-focus: var(--_btn-danger-border-focus);
}

/* ---------- 无框形态 ---------- */
.app-button.app-button--text.el-button {
    --el-button-bg-color: transparent;
    --el-button-text-color: var(--_btn-text-fg);
    --el-button-border-color: transparent;
    --el-button-hover-bg-color: transparent;
    --el-button-hover-text-color: var(--_btn-text-hover-fg);
    --el-button-hover-border-color: transparent;
    --el-button-active-bg-color: transparent;
    --el-button-active-text-color: var(--_btn-text-hover-fg);
    --el-button-active-border-color: transparent;
    --el-button-disabled-bg-color: transparent;
    --el-button-disabled-border-color: transparent;
    --el-button-disabled-text-color: var(--_btn-text-disabled-fg);
    height: auto;
    min-height: 0;
    padding: 0 2px;
    border: 0;
    line-height: inherit;
    vertical-align: baseline;
}

/* 行内文字跟随所在段落的字号；图标按钮仍用 size 档 */
.app-button.app-button--text:not(.app-button--icon-only).el-button {
    font-size: inherit;
}

.app-button.app-button--text.el-button:hover {
    text-decoration: underline;
}

.app-button.app-button--text.app-button--danger.el-button {
    --el-button-text-color: var(--_btn-danger-fg);
    --el-button-hover-text-color: var(--_btn-danger-border-hover);
    --el-button-active-text-color: var(--_btn-danger-border-hover);
}

.app-button.app-button--text.app-button--icon-only.el-button {
    width: var(--_btn-h);
    height: var(--_btn-h);
    padding: 0;
    border-radius: var(--app-radius-pill);
    line-height: 1;
    vertical-align: middle;
}

.app-button.app-button--text.app-button--icon-only.el-button:hover {
    background: var(--_btn-text-hover-bg);
    text-decoration: none;
}

/* ---------- 开关的持续选中态 ---------- */
.app-button.app-button--pressed {
    --el-button-bg-color: var(--_btn-pressed-bg);
    --el-button-text-color: var(--_btn-pressed-fg);
    --el-button-border-color: var(--_btn-pressed-border);
    --el-button-hover-bg-color: var(--_btn-pressed-bg);
    --el-button-hover-text-color: var(--_btn-pressed-fg);
    --el-button-hover-border-color: var(--_btn-pressed-border);
    --el-button-active-bg-color: var(--_btn-pressed-bg);
    --el-button-active-text-color: var(--_btn-pressed-fg);
    --el-button-active-border-color: var(--_btn-pressed-border);
}

/* 禁用态统一：背景/边框/文字三处同时变灰，不用透明度 */
.app-button.is-disabled,
.app-button.is-disabled:hover,
.app-button.is-disabled:focus,
.app-button.is-disabled:active {
    opacity: 1;
    cursor: not-allowed;
    background-color: var(--_btn-disabled-bg);
    border-color: var(--_btn-disabled-border);
    color: var(--_btn-disabled-fg);
}

.app-button.app-button--text.is-disabled,
.app-button.app-button--text.is-disabled:hover,
.app-button.app-button--text.is-disabled:focus,
.app-button.app-button--text.is-disabled:active {
    background-color: transparent;
    border-color: transparent;
    color: var(--_btn-text-disabled-fg);
}

/* 焦点只变边框色，不加外环 */
.app-button.el-button:focus-visible {
    outline: none;
    border-color: var(--_btn-border-focus);
}

.app-button.app-button--text.el-button:focus-visible {
    border-color: transparent;
    color: var(--_btn-text-hover-fg);
    text-decoration: underline;
}

.app-button.app-button--text.app-button--icon-only.el-button:focus-visible {
    background: var(--_btn-text-hover-bg);
    box-shadow: inset 0 0 0 1px var(--_btn-border-focus);
    text-decoration: none;
}

.app-button--icon-only.el-button {
    width: var(--_btn-h);
    padding: 0;
}

.app-button--round.el-button {
    border-radius: var(--app-radius-pill);
}

.app-button--block.el-button {
    display: flex;
    width: 100%;
}

.app-button .el-icon.is-loading {
    font-size: 1.05em;
}

@media (prefers-reduced-motion: reduce) {
    .app-button.el-button {
        transition: none;
    }
}
</style>
