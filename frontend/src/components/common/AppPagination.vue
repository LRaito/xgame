<template>
    <!-- 只有一页时整块不渲染（连 margin 都不留）。用 pageCount 而不是
         `total > pageSize` 判断：total 为 0 时后者也成立，会渲染出一个空分页条 -->
    <div v-if="pageCount > 1" class="app-pagination">
        <!-- total 不交给 EP 的 layout：它的总数是一整段文本节点，
             没法只把数字加粗。这里自己渲染「共 N 条」，数字加粗、标签弱化 -->
        <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            background
            @current-change="onPagerChange"
        />
        <span class="app-pagination__total">共 <b>{{ total }}</b> 条</span>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue";
import { matchesShortcut } from "@/utils/shortcuts";

/**
 * 列表分页条（游戏管理 / 游戏发现共用）。
 *
 * 只管页码，不管数据：父级把 page / total / pageSize 传进来，翻页时收到
 * `update:page`（先）与 `change`（后），在 `change` 的处理函数里发请求。
 *
 * **左右方向键翻页**也在这个组件里（两个列表页因此自动都有），守卫见 onKeydown。
 */
const props = defineProps({
    total: { type: Number, default: 0 },
    page: { type: Number, default: 1 },
    pageSize: { type: Number, default: 10 },
    // 键盘翻页开关。同一时刻页面上只应有一个分页条（监听挂在 window 上），
    // 将来真要在同一页放两个，给其中一个传 false。
    keyboard: { type: Boolean, default: true },
    // 按键管理页里的动作 id：游戏管理与游戏发现各有一套，互不影响。
    previousShortcut: { type: String, default: "" },
    nextShortcut: { type: String, default: "" },
});

const emit = defineEmits(["update:page", "change"]);

const pageCount = computed(() =>
    Math.max(1, Math.ceil(props.total / Math.max(1, props.pageSize)))
);

/**
 * 跳到第 target 页（收敛到 [1, pageCount]）。
 *
 * **先发 update:page 再发 change，顺序不能反**：父级的 change 处理函数（reload / load）
 * 读的是它自己那个 page ref，先发 change 会拿着旧页码去请求。
 */
function goTo(target) {
    const next = Math.min(Math.max(1, Math.trunc(target)), pageCount.value);
    if (!Number.isFinite(next) || next === props.page) {
        return;
    }
    emit("update:page", next);
    emit("change", next);
}

function onPagerChange(value) {
    goTo(Number(value));
}

/**
 * 焦点在能打字的元素里时，左右键是「移光标 / 选词」，不能抢。
 * el-select 的触发器本身就是个真 input（tag 判断已覆盖），外面那层壳也一并挡掉。
 */
function isTypingTarget(target) {
    const tag = String(target?.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return true;
    }
    if (target?.isContentEditable) {
        return true;
    }
    return Boolean(target?.closest?.(".el-select, .el-input, .el-textarea, .el-popper"));
}

/**
 * 有模态开着时（弹框 / 确认框 / 抽屉），左右键不该翻底下的表格。
 *
 * Element Plus 的 useLockscreen（dialog、message-box、drawer 都走它）会给 body 加
 * `el-popup-parent--hidden`，这是它自己对外可见的行为，比自己数一遍页面上的弹框 ref 稳。
 * 两个已知耦合：1) 弹框若显式传 `:lock-scroll="false"` 就不加这个类；2) 它摘类有个
 * 200ms 的 setTimeout，刚关掉弹框的 200ms 内按左右键会被吃掉。
 */
function isModalOpen() {
    return document.body.classList.contains("el-popup-parent--hidden");
}

/** 这次按键对应的翻页方向：1 下一页、-1 上一页、0 不匹配。 */
function shortcutDirection(event) {
    if (matchesShortcut(event, props.nextShortcut)) {
        return 1;
    }
    if (matchesShortcut(event, props.previousShortcut)) {
        return -1;
    }
    return 0;
}

function onKeydown(event) {
    if (!props.keyboard) {
        return;
    }
    // 绑定串已经包含完整的修饰键要求：用户把翻页改成别的键后，原来的方向键要放行。
    const direction = shortcutDirection(event);
    if (!direction) {
        return;
    }
    // 按住不放的连发不翻（服务端分页一次一页，连发会刷出一串请求）；输入法组字中的方向键也不碰
    if (event.repeat || event.isComposing) {
        return;
    }
    // 只有一页：什么都不做，也**不拦默认行为**（把横向滚动留给浏览器）
    if (pageCount.value <= 1) {
        return;
    }
    if (isModalOpen() || isTypingTarget(event.target)) {
        return;
    }

    // 认下这一下就拦掉，横向滚动与焦点移动都别发生（到头也一样拦，行为一致）
    event.preventDefault();
    goTo(props.page + direction);
}

// 挂在 window 的**冒泡**阶段：这只是页面级便利，不跟模态那种要独占键盘的组件抢。
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<style scoped>
/* 表格下面居中一行 */
.app-pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 20px;
}

/*
 * 分页条外观：白色填充、无描边，选中实心品牌蓝。
 *
 * 白块靠页面底色（:root 的 #f1f5f9）显形：分页条在表格卡片之外，
 * 不要再给 .app-pagination 加白色底，否则两者会糊成一片。
 *
 * 只覆盖 EP 的内部结构样式，颜色、尺寸、圆角、焦点环全部取 index.css 的
 * token。EP 的 pagination 变量在这里逐项对齐，避免出现第二套色值。
 */
.app-pagination :deep(.el-pagination) {
    --el-pagination-font-size: var(--app-font-size-sm);
    --el-pagination-border-radius: var(--app-radius-control-sm);
    /* is-background 下页码与箭头的填充色 */
    --el-pagination-button-bg-color: var(--surface);
    /* 页码与箭头用正文色（01 里的深色数字），总数标签单独弱化 */
    --el-pagination-button-color: var(--app-text);
    --el-pagination-hover-color: var(--app-color-selected-fg);
    --el-pagination-button-disabled-bg-color: transparent;
    --el-pagination-button-disabled-color: var(--app-color-disabled-text);
    --el-pagination-item-gap: 6px;
}

/* EP is-background 每个格子左右各 4px（相邻即 8px），这里收到 3px 凑 6px 间距 */
.app-pagination :deep(.el-pagination.is-background .el-pager li),
.app-pagination :deep(.el-pagination.is-background .btn-prev),
.app-pagination :deep(.el-pagination.is-background .btn-next) {
    margin: 0 3px;
}
/* 上一页不再额外缩进（EP 默认给它 16px），右侧靠 total 的 3px 补成同一间距 */
.app-pagination :deep(.el-pagination.is-background .btn-prev) {
    margin-left: 0;
}
/* 总数自己在模板里渲染：数字加粗、正文色，两侧文字用弱化色。
   布局里去掉 total 后 next 成了最后一项，EP 用 !important 清掉了它的右外边距，
   所以这里给 6px 左外边距就是唯一的间距。 */
.app-pagination__total {
    margin-left: 6px;
    color: var(--app-text-muted);
    font-size: var(--app-font-size-sm);
    white-space: nowrap;
}
.app-pagination__total b {
    color: var(--app-text);
    font-weight: 600;
}

/* 悬停：浅蓝底 + 深蓝字。省略号（li.more）同样是按钮，一起给 */
.app-pagination :deep(.el-pagination.is-background .el-pager li:hover:not(.is-active):not(.is-disabled)),
.app-pagination :deep(.el-pagination.is-background .btn-prev:hover:not(:disabled):not(.is-disabled)),
.app-pagination :deep(.el-pagination.is-background .btn-next:hover:not(:disabled):not(.is-disabled)) {
    background-color: var(--app-color-selected-bg);
    color: var(--app-color-selected-fg);
}

/* 选中：实心品牌蓝 + 白字。字号不变，只把 EP 的 700 收回到 600 */
.app-pagination :deep(.el-pagination.is-background .el-pager li.is-active) {
    background-color: var(--app-color-primary);
    color: var(--el-color-white);
    font-weight: 600;
}

/* 到头时箭头不留灰块，只留浅灰图标 */
.app-pagination :deep(.el-pagination.is-background .btn-prev:disabled),
.app-pagination :deep(.el-pagination.is-background .btn-prev.is-disabled),
.app-pagination :deep(.el-pagination.is-background .btn-next:disabled),
.app-pagination :deep(.el-pagination.is-background .btn-next.is-disabled) {
    background-color: transparent;
    color: var(--app-color-disabled-text);
}

/* 箭头图标与页码视觉同号（EP 默认 12px） */
.app-pagination :deep(.el-pagination .btn-prev .el-icon),
.app-pagination :deep(.el-pagination .btn-next .el-icon) {
    font-size: var(--app-font-size-md);
}

/* 键盘焦点沿用全站焦点 token（EP 默认是 1px 内侧描边） */
.app-pagination :deep(.el-pagination .el-pager li:focus-visible),
.app-pagination :deep(.el-pagination .btn-prev:focus-visible),
.app-pagination :deep(.el-pagination .btn-next:focus-visible) {
    outline: var(--app-focus-axis) solid var(--app-focus-ring-light);
    outline-offset: var(--app-focus-offset);
}
</style>
