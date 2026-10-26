<template>
    <el-dialog
        :model-value="modelValue"
        :title="title"
        :width="width"
        :align-center="alignCenter"
        :close-on-click-modal="false"
        :close-on-press-escape="true"
        destroy-on-close
        @close="close"
    >
        <!-- 标题右边还想放东西（比如美化封面的样式单选）就走这个插槽：
             el-dialog 的 header 插槽只替换标题那一段，右上角的关闭按钮不受影响 -->
        <template v-if="$slots.header" #header>
            <span class="el-dialog__title">{{ title }}</span>
            <slot name="header" />
        </template>

        <slot />
        <template v-if="footerMode !== 'none'" #footer>
            <div class="app-dialog__footer">
                <slot name="footer">
                    <app-button
                        v-if="footerMode === 'default'"
                        variant="secondary"
                        @click="close"
                    >
                        {{ cancelText }}
                    </app-button>
                    <app-button
                        v-if="footerMode === 'close-only'"
                        variant="secondary"
                        @click="close"
                    >
                        {{ closeText }}
                    </app-button>
                    <app-button
                        v-if="footerMode === 'default' || footerMode === 'confirm-only'"
                        :variant="confirmVariant"
                        :loading="confirmLoading"
                        :disabled="confirmDisabled"
                        @click="emit('confirm')"
                    >
                        {{ confirmText }}
                    </app-button>
                </slot>
            </div>
        </template>
    </el-dialog>
</template>

<script setup>
defineProps({
    modelValue: { type: Boolean, default: false },
    title: { type: String, default: "" },
    width: { type: String, default: "480px" },
    // default：取消 + 确认；confirm-only：只有确认；close-only：只有关闭；
    // custom：只渲染 #footer 插槽；none：不渲染 footer
    footerMode: { type: String, default: "default" },
    cancelText: { type: String, default: "取消" },
    closeText: { type: String, default: "关闭" },
    confirmText: { type: String, default: "确定" },
    confirmVariant: { type: String, default: "secondary" },
    confirmDisabled: { type: Boolean, default: false },
    confirmLoading: { type: Boolean, default: false },
    alignCenter: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "confirm"]);

function close() {
    emit("update:modelValue", false);
}
</script>

<style>
/* 弹框底部固定：次要/关闭在左、主操作在右，间距统一。
   el-dialog 的 footer 可能被 teleport 到 body，所以用非 scoped 的唯一类名。 */
.app-dialog__footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--app-space-3, 12px);
}

.app-dialog__footer .el-button + .el-button {
    margin-left: 0;
}
</style>
