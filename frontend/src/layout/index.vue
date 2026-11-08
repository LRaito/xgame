<template>
    <div class="layout">
        <!-- 常驻侧栏：占据真实布局空间、不可收缩；播放页（meta.playerRoute）整体不渲染 -->
        <aside v-if="showSider" class="sider">
            <div class="brand">
                <div class="brand-name"><span class="brand-mark-x">X</span>GAME</div>
                <div class="brand-version">{{ DISPLAY_VERSION }}</div>
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
                <app-button variant="secondary" block @click="onLogout">
                    退出登录
                </app-button>
            </div>
        </aside>

        <div class="main">
            <section class="content">
                <router-view />
            </section>
        </div>
    </div>
</template>

<script setup>
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { DISPLAY_VERSION } from "@/constants/version";
import { buildMenuFromRoutes } from "@/router";
import { useAuthStore } from "@/store/auth";
import { useGameTypesStore } from "@/store/gameTypes";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const gameTypes = useGameTypesStore();
const menus = buildMenuFromRoutes();

// 类型注册表只拉一次：各页面直接读缓存；失败静默，页面各自有回退
onMounted(() => {
    void gameTypes.ensureLoaded();
});

// 播放页（模拟器 / Flash / H5，meta.playerRoute）要全屏沉浸，无侧栏；
// 其余页面（含不进菜单的机型详情页）侧栏常驻、无收缩态。
const showSider = computed(() => !route.meta.playerRoute);

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
/* flex 双列：侧栏占据真实宽度，内容区自然向右衔接；播放页 v-if 掉侧栏后自动铺满 */
.layout {
    display: flex;
    min-height: 100vh;
    background: #f1f5f9;
}

/* 侧栏固定在视口左列，长页面滚动时也不跟着走 */
.sider {
    position: sticky;
    top: 0;
    height: 100vh;
    flex-shrink: 0;
    width: var(--app-sider-width);
    box-sizing: border-box;
    padding: 0;
    display: flex;
    flex-direction: column;
    background: var(--app-sider-bg);
    border-right: 1px solid var(--app-sider-border);
}

.main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
}

/* 页头色带：整块比栏身深一档 + 底部细线，与下方面向内容的导航区拉开层次；
   XGAME 与版本号水平居中 */
.brand {
    padding: 18px 10px 14px;
    text-align: center;
    background: var(--app-sider-head-bg);
    border-bottom: 1px solid var(--app-sider-border);
    flex-shrink: 0;
}

/* 品牌字标：X 用主色加重做品牌点缀 */
.brand-name {
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #0f172a;
    white-space: nowrap;
}

.brand-mark-x {
    color: var(--brand-accent);
}

/* 版本号独立成行：只显示 vx.x.x（见 constants/version.js 的 DISPLAY_VERSION） */
.brand-version {
    margin-top: 3px;
    font-size: 11px;
    letter-spacing: 0.04em;
    font-variant-numeric: tabular-nums;
    color: var(--text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* 菜单多了就在侧栏内部滚动，不撑高侧栏、也不影响底部退出按钮 */
.nav {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-height: 0;
    padding: 12px 8px;
    overflow-y: auto;
    overscroll-behavior: contain;
}

/* 窄栏下的居中排版：一行一个菜单项，去掉大左右 padding */
.nav-link {
    display: block;
    padding: 10px 4px;
    border-radius: 8px;
    text-align: center;
    font-size: 14px;
    line-height: 1.4;
    text-decoration: none;
    color: var(--app-sider-fg);
    transition: background 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
    background: var(--app-sider-hover-bg);
    color: var(--app-sider-fg-hover);
}

/* 激活态：白底胶囊 + 主色字，靠阴影从浅灰底上浮起来 */
.nav-link.active {
    background: var(--app-sider-active-bg);
    color: var(--app-sider-fg-active);
    font-weight: 600;
    box-shadow: var(--shadow-sm);
}

.sider-footer {
    margin-top: auto;
    flex-shrink: 0;
    padding: 14px 8px 12px;
    border-top: 1px solid var(--app-sider-border);
    display: flex;
    align-items: center;
    justify-content: center;
}

.content {
    flex: 1;
    padding: 28px;
    min-height: 0;
}
</style>
