<template>
    <div
        class="app-truncatable"
        :class="{ 'app-truncatable--truncated': truncated }"
        @click.capture="onToggle"
    >
        <!-- 收起态：单行省略接。scrollWidth 只有溢出时才会超过 clientWidth，
             这是「名字被截断没有」的判据（+1 容差防亚像素抖动） -->
        <div ref="lineEl" class="app-truncatable__line">
            <slot />
        </div>

        <!-- 展开态浮层：白底 + 投影盖住下方的行，显示全名，再点收起；
             #panel-extra 里的内容只在展开层出现（如顺带展示的描述） -->
        <div v-if="expanded" class="app-truncatable__panel">
            <slot />
            <slot name="panel-extra" />
        </div>
    </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, onUpdated, ref } from "vue";

// 截断与否决定 cursor 与点击是否响应；宽度随窗口/内容变化都要重测
const lineEl = ref(null);
const truncated = ref(false);
const expanded = ref(false);

function measure() {
    const el = lineEl.value;
    if (!el) {
        return;
    }
    truncated.value = el.scrollWidth > el.clientWidth + 1;
    if (!truncated.value) {
        expanded.value = false;
    }
}

let observer = null;

onMounted(() => {
    measure();
    observer = new ResizeObserver(measure);
    observer.observe(lineEl.value);
});

onBeforeUnmount(() => observer?.disconnect());
onUpdated(measure);

/**
 * 单击截断的名字：展开/收起浮层。整个根上在捕获阶段拦——
 * 名称里可能是真链接（榜单表 router-link 渲染成原生 <a>），
 * 截断时单击优先展开，preventDefault + stopPropagation 把链接的默认跳转与后续监听拦掉；
 * 没截断的名字原样放行，链接照常跳转。
 */
function onToggle(event) {
    if (!truncated.value) {
        return;
    }
    event.preventDefault();
    event.stopPropagation();
    expanded.value = !expanded.value;
}
</script>

<style scoped>
.app-truncatable {
    position: relative;
    min-width: 0;
}

.app-truncatable--truncated {
    cursor: pointer;
}

.app-truncatable__line {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

/* 展开层：钉在本行下方往下铺，白底 + 投影盖住下面的行；
   宽随内容排版溢不受限于本格（min-width 保底取本行宽，长 URL 一类的内容靠 max-width 兜住折行） */
.app-truncatable__panel {
    position: absolute;
    top: 100%;
    left: 0;
    z-index: 4;
    min-width: 100%;
    width: max-content;
    max-width: min(70vw, 520px);
    padding: 10px 14px;
    white-space: normal;
    word-break: break-all;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 10px 18px rgba(15, 23, 42, 0.12);
    cursor: pointer;
}
</style>
