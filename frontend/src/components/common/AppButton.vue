<template>
    <el-button
        class="app-button"
        :class="[
            `app-button--${resolvedVariant}`,
            `app-button--${size}`,
            `app-button--${tone}`,
            {
                'app-button--plain': plain,
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
    // 语义角色：primary / secondary / ghost / danger / link
    variant: { type: String, default: "" },
    // xs 药丸 / sm 行内 / md 工具栏与弹框 / lg 播放器
    size: { type: String, default: "md" },
    // light 浅色页面 / dark 深色区域 / image 图片上 / overlay 遮罩上
    tone: { type: String, default: "light" },
    // primary / danger 的浅底描边
    plain: { type: Boolean, default: false },
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

const resolvedVariant = computed(() => props.variant || "secondary");

const isPressed = computed(() => props.pressed === true);
const pressedState = computed(() => {
    if (props.pressed === null || props.pressed === undefined) {
        return undefined;
    }
    return String(props.pressed);
});
</script>

<style>
/* 尺寸、圆角、字体与状态全部走 styles/index.css 的 token。tone 只定义局部变量，
   variant 只消费变量——深色区域因此不需要再复制一套按钮 CSS。 */
.app-button.el-button {
    gap: 6px;
    height: var(--_btn-h, var(--app-control-h-md));
    padding: 0 var(--_btn-px, var(--app-control-px-md));
    border-radius: var(--_btn-radius, var(--app-radius-control));
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

.app-button--xs {
    --_btn-h: var(--app-control-h-xs);
    --_btn-px: var(--app-control-px-xs);
    --_btn-fs: var(--app-font-size-xs);
    --_btn-radius: var(--app-radius-pill);
}

.app-button--sm {
    --_btn-h: var(--app-control-h-sm);
    --_btn-px: var(--app-control-px-sm);
    --_btn-fs: var(--app-font-size-sm);
    --_btn-radius: var(--app-radius-control-sm);
}

.app-button--lg {
    --_btn-h: var(--app-control-h-lg);
    --_btn-px: var(--app-control-px-lg);
    --_btn-fs: var(--app-font-size-lg);
}

/* ---------- tone：只定义变量 ---------- */
.app-button.app-button--light {
    --_btn-bg: var(--surface);
    --_btn-fg: var(--app-text);
    --_btn-border: var(--app-border);
    --_btn-hover-bg: var(--app-surface-subtle);
    --_btn-hover-fg: var(--app-color-primary);
    --_btn-hover-border: var(--app-color-primary-light-5);
    --_btn-active-bg: var(--app-color-primary-soft);
    --_btn-active-border: var(--app-color-primary);
    --_btn-primary-bg: var(--app-color-primary);
    --_btn-primary-fg: #fff;
    --_btn-primary-border: var(--app-color-primary);
    --_btn-primary-hover-bg: var(--app-color-primary-hover);
    --_btn-primary-active-bg: var(--app-color-primary-active);
    --_btn-danger-bg: var(--app-color-danger);
    --_btn-danger-fg: #fff;
    --_btn-danger-border: var(--app-color-danger);
    --_btn-danger-hover-bg: var(--app-color-danger-hover);
    --_btn-danger-soft-fg: var(--app-color-danger);
    --_btn-danger-soft-border: var(--app-color-danger-light-5);
    --_btn-ghost-hover-bg: rgba(15, 23, 42, 0.06);
    --_btn-pressed-bg: var(--app-color-primary);
    --_btn-pressed-border: var(--app-color-primary);
    --_btn-pressed-fg: #fff;
    --app-focus-ring: var(--app-focus-ring-light);
}

.app-button.app-button--dark {
    --_btn-bg: var(--app-dark-surface);
    --_btn-fg: var(--app-dark-text);
    --_btn-border: var(--app-dark-border);
    --_btn-hover-bg: var(--app-dark-surface-hover);
    --_btn-hover-fg: #fff;
    --_btn-hover-border: var(--app-dark-border-hover);
    --_btn-active-bg: var(--app-dark-surface-hover);
    --_btn-active-border: var(--app-dark-border-hover);
    --_btn-primary-bg: var(--app-dark-primary);
    --_btn-primary-fg: #fff;
    --_btn-primary-border: var(--app-dark-primary-border);
    --_btn-primary-hover-bg: var(--app-dark-primary-hover);
    --_btn-primary-active-bg: var(--app-dark-primary-hover);
    --_btn-danger-bg: transparent;
    --_btn-danger-fg: var(--app-dark-danger-text);
    --_btn-danger-border: var(--app-dark-danger-border);
    --_btn-danger-hover-bg: var(--app-dark-danger-hover-bg);
    --_btn-danger-soft-fg: var(--app-dark-danger-text);
    --_btn-danger-soft-border: var(--app-dark-danger-border);
    --_btn-ghost-hover-bg: rgba(255, 255, 255, 0.08);
    --_btn-pressed-bg: var(--app-dark-primary);
    --_btn-pressed-border: var(--app-dark-primary-border);
    --_btn-pressed-fg: #f8fafc;
    --app-focus-ring: var(--app-focus-ring-dark);
    /* 深色按钮上的 loading 遮罩不能用白 */
    --el-mask-color-extra-light: rgba(15, 23, 42, 0.35);
}

.app-button.app-button--image {
    --_btn-bg: var(--app-image-surface);
    --_btn-fg: #fff;
    --_btn-border: transparent;
    --_btn-hover-bg: var(--app-image-surface-hover);
    --_btn-hover-fg: #fff;
    --_btn-hover-border: transparent;
    --_btn-active-bg: var(--app-image-surface-hover);
    --_btn-active-border: transparent;
    --_btn-ghost-hover-bg: var(--app-image-surface-hover);
    --_btn-pressed-bg: var(--app-color-primary);
    --_btn-pressed-border: var(--app-color-primary);
    --_btn-pressed-fg: #fff;
    --app-focus-ring: #fff;
}

.app-button.app-button--overlay {
    --_btn-bg: var(--app-overlay-surface);
    --_btn-fg: #fff;
    --_btn-border: transparent;
    --_btn-hover-bg: var(--app-overlay-surface-hover);
    --_btn-hover-fg: #fff;
    --_btn-hover-border: transparent;
    --_btn-active-bg: var(--app-overlay-surface-hover);
    --_btn-active-border: transparent;
    --_btn-ghost-hover-bg: var(--app-overlay-surface-hover);
    --_btn-pressed-bg: rgba(255, 255, 255, 0.32);
    --_btn-pressed-border: transparent;
    --_btn-pressed-fg: #fff;
    --app-focus-ring: #fff;
}

/* ---------- variant：只消费 tone 变量 ---------- */
.app-button.app-button--secondary {
    --el-button-bg-color: var(--_btn-bg);
    --el-button-text-color: var(--_btn-fg);
    --el-button-border-color: var(--_btn-border);
    --el-button-hover-bg-color: var(--_btn-hover-bg);
    --el-button-hover-text-color: var(--_btn-hover-fg);
    --el-button-hover-border-color: var(--_btn-hover-border);
    --el-button-active-bg-color: var(--_btn-active-bg);
    --el-button-active-text-color: var(--_btn-hover-fg);
    --el-button-active-border-color: var(--_btn-active-border);
    --el-button-disabled-bg-color: var(--_btn-bg);
    --el-button-disabled-border-color: var(--_btn-border);
    --el-button-disabled-text-color: var(--_btn-fg);
}

.app-button.app-button--primary {
    --el-button-bg-color: var(--_btn-primary-bg);
    --el-button-text-color: var(--_btn-primary-fg);
    --el-button-border-color: var(--_btn-primary-border);
    --el-button-hover-bg-color: var(--_btn-primary-hover-bg);
    --el-button-hover-text-color: var(--_btn-primary-fg);
    --el-button-hover-border-color: var(--_btn-primary-hover-bg);
    --el-button-active-bg-color: var(--_btn-primary-active-bg);
    --el-button-active-border-color: var(--_btn-primary-active-bg);
    --el-button-disabled-bg-color: var(--_btn-primary-bg);
    --el-button-disabled-border-color: var(--_btn-primary-border);
    --el-button-disabled-text-color: var(--_btn-primary-fg);
}

.app-button.app-button--danger {
    --el-button-bg-color: var(--_btn-danger-bg);
    --el-button-text-color: var(--_btn-danger-fg);
    --el-button-border-color: var(--_btn-danger-border);
    --el-button-hover-bg-color: var(--_btn-danger-hover-bg);
    --el-button-hover-text-color: var(--_btn-danger-fg);
    --el-button-hover-border-color: var(--_btn-danger-hover-bg);
    --el-button-active-bg-color: var(--_btn-danger-hover-bg);
    --el-button-active-border-color: var(--_btn-danger-hover-bg);
    --el-button-disabled-bg-color: var(--_btn-danger-bg);
    --el-button-disabled-border-color: var(--_btn-danger-border);
    --el-button-disabled-text-color: var(--_btn-danger-fg);
}

.app-button.app-button--ghost {
    --el-button-bg-color: transparent;
    --el-button-text-color: var(--_btn-fg);
    --el-button-border-color: transparent;
    --el-button-hover-bg-color: var(--_btn-ghost-hover-bg);
    --el-button-hover-text-color: var(--_btn-hover-fg);
    --el-button-hover-border-color: transparent;
    --el-button-active-bg-color: var(--_btn-ghost-hover-bg);
    --el-button-active-border-color: transparent;
    --el-button-disabled-bg-color: transparent;
    --el-button-disabled-border-color: transparent;
    --el-button-disabled-text-color: var(--_btn-fg);
}

.app-button.app-button--link {
    height: auto;
    padding: 2px 4px;
    --el-button-bg-color: transparent;
    --el-button-text-color: var(--app-color-primary);
    --el-button-border-color: transparent;
    --el-button-hover-bg-color: transparent;
    --el-button-hover-text-color: var(--app-color-primary-hover);
    --el-button-hover-border-color: transparent;
    --el-button-active-bg-color: transparent;
    --el-button-active-border-color: transparent;
    --el-button-disabled-bg-color: transparent;
    --el-button-disabled-border-color: transparent;
    --el-button-disabled-text-color: var(--app-text-muted);
}

.app-button.app-button--dark.app-button--link {
    --el-button-text-color: #93c5fd;
    --el-button-hover-text-color: #bfdbfe;
    --el-button-disabled-text-color: #64748b;
}

/* primary / danger 的浅底描边 */
.app-button.app-button--plain.app-button--primary {
    --el-button-bg-color: var(--app-color-primary-soft);
    --el-button-text-color: var(--app-color-primary);
    --el-button-border-color: var(--app-color-primary-light-5);
    --el-button-hover-bg-color: var(--app-color-primary);
    --el-button-hover-text-color: #fff;
    --el-button-hover-border-color: var(--app-color-primary);
}

.app-button.app-button--plain.app-button--danger {
    --el-button-bg-color: transparent;
    --el-button-text-color: var(--_btn-danger-soft-fg);
    --el-button-border-color: var(--_btn-danger-soft-border);
    --el-button-hover-bg-color: var(--app-color-danger);
    --el-button-hover-text-color: #fff;
    --el-button-hover-border-color: var(--app-color-danger);
}

.app-button.app-button--dark.app-button--plain.app-button--danger {
    --el-button-hover-bg-color: var(--app-dark-danger-hover-bg);
    --el-button-hover-text-color: var(--app-dark-danger-text);
    --el-button-hover-border-color: var(--app-dark-danger-border);
}

.app-button.app-button--dark.app-button--plain.app-button--primary {
    --el-button-bg-color: rgba(37, 99, 235, 0.16);
    --el-button-text-color: #fff;
    --el-button-border-color: var(--app-dark-primary-border);
}

/* 开关按下的状态 */
.app-button.app-button--pressed {
    --el-button-bg-color: var(--_btn-pressed-bg);
    --el-button-border-color: var(--_btn-pressed-border);
    --el-button-text-color: var(--_btn-pressed-fg);
    --el-button-hover-bg-color: var(--_btn-pressed-bg);
    --el-button-hover-border-color: var(--_btn-pressed-border);
    --el-button-hover-text-color: var(--_btn-pressed-fg);
    --el-button-active-bg-color: var(--_btn-pressed-bg);
    --el-button-active-border-color: var(--_btn-pressed-border);
}

/* 禁用态统一：颜色仍由 variant 给，只降透明度，避免深色按钮被 EP 刷白 */
.app-button.is-disabled,
.app-button.is-disabled:hover,
.app-button.is-disabled:active {
    opacity: var(--app-disabled-opacity);
    cursor: not-allowed;
}

/* 焦点环统一 */
.app-button.el-button:focus-visible {
    outline: var(--app-focus-axis) solid var(--app-focus-ring);
    outline-offset: var(--app-focus-offset);
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
