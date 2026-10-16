<template>
    <!-- 只有一页时整块不渲染（连 margin 都不留）。用 pageCount 而不是
         `total > pageSize` 判断：total 为 0 时后者也成立，会渲染出一个空分页条 -->
    <div v-if="pageCount > 1" class="app-pagination">
        <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next, total"
            background
            @current-change="onPagerChange"
        />
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue";

/**
 * 列表分页条（游戏管理 / 游戏检索共用）。
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

function onKeydown(event) {
    if (!props.keyboard) {
        return;
    }
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
    }
    // 带修饰键的一律放行：Ctrl/Shift+方向是选词，Alt+左右是浏览器前进/后退
    if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) {
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
    goTo(props.page + (event.key === "ArrowRight" ? 1 : -1));
}

// 挂在 window 的**冒泡**阶段：这只是页面级便利，不跟模态那种要独占键盘的组件抢。
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<style scoped>
/* 表格下面居中一行 */
.app-pagination {
    display: flex;
    justify-content: center;
    margin-top: 20px;
}
</style>
