<template>
    <div v-if="updateReady" class="update-banner" role="status" aria-live="polite">
        <span class="update-banner__text">发现新版本，刷新页面后生效。</span>
        <app-button type="primary" @click="reloadPage">立即刷新</app-button>
        <button type="button" class="update-banner__later" @click="dismissVersion">
            稍后
        </button>
    </div>
</template>

<script setup>
import { updateReady, dismissVersion, reloadPage } from "@/utils/versionCheck";
</script>

<style scoped>
/* 固定在底部居中：不进布局流，不挤压侧栏与内容区，也不会盖住顶部导航 */
.update-banner {
    position: fixed;
    left: 50%;
    bottom: 24px;
    transform: translateX(-50%);
    z-index: 3000; /* 高于 Element Plus 弹窗基准 2000 */
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    border-radius: 10px;
    background: #0f172a; /* 与 layout 侧栏同一套深色 */
    color: #f8fafc;
    font-size: 14px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.28);
}

.update-banner__later {
    padding: 0;
    border: none;
    background: transparent;
    color: #cbd5e1;
    font-size: 13px;
    cursor: pointer;
}

.update-banner__later:hover {
    color: #fff;
}
</style>
