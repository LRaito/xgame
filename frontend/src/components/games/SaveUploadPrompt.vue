<template>
    <div
        v-if="modelValue"
        class="save-upload-prompt"
        @click.self="close"
    >
        <div
            class="save-upload-prompt__card"
            @keydown.esc.stop.prevent="close"
        >
            <header class="save-upload-prompt__head">
                <h3 class="save-upload-prompt__title">{{ title }}</h3>
                <app-button
                    text
                    tone="dark"
                    size="sm"
                    icon-only
                    round
                    aria-label="关闭"
                    @click="close"
                >
                    ✕
                </app-button>
            </header>
            <p class="save-upload-prompt__hint">{{ hint }}</p>
            <textarea
                ref="inputRef"
                v-model="remark"
                class="save-upload-prompt__input"
                rows="4"
                maxlength="100"
                placeholder="描述（可选）"
                @keydown.enter.ctrl.prevent="confirm"
                @keydown.enter.meta.prevent="confirm"
            ></textarea>
            <div class="save-upload-prompt__count">{{ remark.length }}/100</div>
            <div class="save-upload-prompt__actions">
                <app-button tone="dark" @click="close">取消</app-button>
                <app-button tone="dark" :loading="busy" @click="confirm">
                    {{ confirmText }}
                </app-button>
            </div>
        </div>
    </div>
</template>

<script setup>
import { nextTick, ref, watch } from "vue";

const props = defineProps({
    modelValue: { type: Boolean, default: false },
    busy: { type: Boolean, default: false },
    title: { type: String, default: "同步至云端" },
    hint: { type: String, default: "把当前本地存档备份到云端" },
    confirmText: { type: String, default: "同步" },
});

const emit = defineEmits(["update:modelValue", "confirm"]);

const remark = ref("");
const inputRef = ref(null);

watch(
    () => props.modelValue,
    async (visible) => {
        if (!visible) {
            remark.value = "";
            return;
        }
        remark.value = "";
        await nextTick();
        inputRef.value?.focus();
    },
);

function close() {
    if (props.busy) {
        return;
    }
    emit("update:modelValue", false);
}

function confirm() {
    if (props.busy) {
        return;
    }
    const value = remark.value.trim().slice(0, 100);
    emit("update:modelValue", false);
    emit("confirm", { remark: value });
}
</script>

<style>
.save-upload-prompt {
    position: fixed;
    inset: 0;
    z-index: 80;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(2, 6, 23, 0.62);
}

.save-upload-prompt__card {
    width: 480px;
    max-width: 100%;
    padding: 20px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, 0.24);
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    box-shadow: 0 24px 64px rgba(2, 6, 23, 0.5);
    color: #f8fafc;
}

.save-upload-prompt__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.save-upload-prompt__title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
}

.save-upload-prompt__hint {
    margin: 8px 0 12px;
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.6;
}

.save-upload-prompt__input {
    box-sizing: border-box;
    width: 100%;
    min-height: 96px;
    resize: vertical;
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid rgba(148, 163, 184, 0.28);
    background: rgba(15, 23, 42, 0.55);
    color: #f8fafc;
    font-family: inherit;
    font-size: 13px;
    line-height: 1.6;
    outline: none;
}

.save-upload-prompt__input:focus {
    border-color: var(--app-color-primary);
}

.save-upload-prompt__count {
    margin-top: 6px;
    color: #64748b;
    font-size: 12px;
    text-align: right;
}

.save-upload-prompt__actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 14px;
}
</style>
