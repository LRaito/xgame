<template>
    <el-select
        v-bind="$attrs"
        :model-value="modelValue"
        :disabled="disabled"
        filterable
        :filter-method="onFilter"
        @update:model-value="onUpdate"
        @change="onChange"
        @visible-change="onVisibleChange"
    >
        <el-option
            v-for="item in filteredOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
        />
    </el-select>
</template>

<script setup>
/**
 * 游戏类型 / 机种下拉框：可下拉，也可直接输入过滤。
 *
 * Element Plus 的 `filterable` 默认按 label 区分大小写匹配；这里统一改成
 * 「label 或 value 的不区分大小写子串匹配」，中英文、大小写都能搜到。
 *
 * 选项由调用方给（含「全部」这类空值项），组件不持有任何业务映射。
 */
import { ref, watch } from "vue";

defineOptions({ inheritAttrs: false });

const props = defineProps({
    modelValue: { type: [String, Number], default: "" },
    // [{ label, value }]
    options: { type: Array, default: () => [] },
    disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "change"]);

// 当前展示的选项；空搜索时与 props.options 一致
const filteredOptions = ref([...props.options]);

function resetOptions() {
    filteredOptions.value = [...props.options];
}

watch(() => props.options, resetOptions);

function onFilter(query) {
    const keyword = String(query || "").trim().toLowerCase();
    if (!keyword) {
        resetOptions();
        return;
    }
    filteredOptions.value = props.options.filter(
        (item) =>
            String(item.label ?? "").toLowerCase().includes(keyword) ||
            String(item.value ?? "").toLowerCase().includes(keyword)
    );
}

function onUpdate(value) {
    emit("update:modelValue", value);
}

function onChange(value) {
    // 选完收起输入、恢复完整列表，下次打开看到全部选项
    resetOptions();
    emit("change", value);
}

function onVisibleChange(visible) {
    if (!visible) {
        resetOptions();
    }
}
</script>
