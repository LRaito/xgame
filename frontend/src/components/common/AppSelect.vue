<template>
    <el-select
        v-bind="$attrs"
        :model-value="modelValue"
        :disabled="disabled"
        @update:model-value="onUpdate"
        @change="onChange"
    >
        <el-option
            v-for="item in options"
            :key="item.value"
            :label="item.label"
            :value="item.value"
        />
    </el-select>
</template>

<script setup>
/**
 * 通用下拉框：只渲染调用方给的 `{ label, value }` 选项，不绑定任何业务映射。
 *
 * 与 AppTypeSelect 的区别：不强制 `filterable`，适合「榜单类型 / 库存类型」这类
 * 只有两三个固定选项的筛选。清空行为交给 `clearable`，清空值由页面自行映射。
 */
defineOptions({ inheritAttrs: false });

defineProps({
    modelValue: { type: [String, Number, Boolean], default: "" },
    // [{ label, value }]
    options: { type: Array, default: () => [] },
    disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "change"]);

function onUpdate(value) {
    emit("update:modelValue", value);
}

function onChange(value) {
    emit("change", value);
}
</script>
