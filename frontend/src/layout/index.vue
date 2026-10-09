<template>
    <div class="layout">
        <aside
            class="sider"
            :class="{ 'sider--open': siderOpen }"
            @mouseenter="openSider"
            @mouseleave="closeSider"
        >
            <div class="brand">
                <span class="brand-mark">X</span>
                <span class="brand-name">GAME</span>
            </div>
            <nav class="nav">
                <router-link
                    v-for="item in menus"
                    :key="item.path"
                    :to="item.path"
                    class="nav-link"
                    :class="{ active: activePath === item.path }"
                >
                    {{ item.title }}
                </router-link>
            </nav>
            <div class="sider-footer">
                <app-button class="sider-logout" plain @click="onLogout">
                    退出登录
                </app-button>
            </div>
        </aside>

        <!-- 收起状态下贴着屏幕左边缘的感应区：鼠标靠近即滑出侧栏 -->
        <div class="sider-edge" @mouseenter="openSider"></div>

        <div class="main">
            <section class="content">
                <router-view />
            </section>
        </div>
    </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { buildMenuFromRoutes } from "@/router";
import { useAuthStore } from "@/store/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const menus = buildMenuFromRoutes();

// 侧栏常驻收起、以浮层形式盖在内容之上（不占位、不挤压页面），
// 鼠标靠近屏幕左边缘或移到侧栏上时滑出，移开即收起。
const siderOpen = ref(false);

function openSider() {
    siderOpen.value = true;
}

function closeSider() {
    siderOpen.value = false;
}

// 跳转后立即收起，避免浮层挡住刚打开的页面
watch(() => route.fullPath, closeSider);

// 取匹配到的「最长」菜单路径：/games/manage 下只高亮游戏管理，不再同时点亮游戏中心
const activePath = computed(() => {
    const matched = menus
        .map((item) => item.path)
        .filter((path) => route.path === path || route.path.startsWith(`${path}/`))
        .sort((a, b) => b.length - a.length);
    return matched[0] || "";
});

async function onLogout() {
    await auth.logout();
    router.push("/login");
}
</script>

<style scoped>
.layout {
    min-height: 100vh;
    background: #f1f5f9;
}

/* 浮层侧栏：平时整体移到屏幕外，展开时盖在内容之上 */
.sider {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 60;
    width: 232px;
    height: 100vh;
    padding: 24px 14px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    transform: translateX(-100%);
    transition: transform 0.22s ease, box-shadow 0.22s ease;
}

.sider--open {
    transform: translateX(0);
    box-shadow: 8px 0 28px rgba(15, 23, 42, 0.32);
}

/* 最左侧的悬停感应区（收起时才需要，展开后由侧栏自身的 mouseleave 负责收起） */
.sider-edge {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 59;
    width: 14px;
}

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 10px 28px;
}

.brand-mark {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 11px;
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.12);
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.brand-name {
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: #f8fafc;
}

/* 菜单多了就在侧栏内部滚动，不撑高侧栏、也不影响底部退出按钮 */
.nav {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
}

.nav::-webkit-scrollbar {
    width: 6px;
}

.nav::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.35);
    border-radius: 3px;
}

.nav::-webkit-scrollbar-thumb:hover {
    background: rgba(148, 163, 184, 0.55);
}

.nav-link {
    display: block;
    color: #cbd5e1;
    text-decoration: none;
    padding: 11px 14px;
    border-radius: 10px;
    font-size: 14px;
    transition: background 0.15s ease, color 0.15s ease;
}

.nav-link.active {
    background: rgba(37, 99, 235, 0.18);
    color: #fff;
    font-weight: 500;
}

.nav-link:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
}

.main {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 100vh;
}

.sider-footer {
    margin-top: auto;
    flex-shrink: 0;
    padding: 16px 10px 4px;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    display: flex;
    align-items: center;
    justify-content: center;
}

.sider-logout {
    width: 100%;
    border-color: rgba(255, 255, 255, 0.22) !important;
    color: #e2e8f0 !important;
    background: rgba(255, 255, 255, 0.06) !important;
}

.sider-logout:hover {
    color: #fff !important;
    border-color: rgba(255, 255, 255, 0.34) !important;
    background: rgba(255, 255, 255, 0.12) !important;
}

.content {
    flex: 1;
    padding: 28px;
    min-height: 0;
}
</style>
