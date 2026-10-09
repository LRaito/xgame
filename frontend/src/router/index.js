import { createRouter, createWebHistory } from "vue-router";
import Layout from "@/layout/index.vue";

const routes = [
    {
        path: "/login",
        name: "login",
        component: () => import("@/views/login/index.vue"),
        meta: { hiddenInMenu: true, title: "登录" },
    },
    {
        path: "/",
        component: Layout,
        children: [
            // 首页即游戏中心：菜单顺序按 children 声明顺序生成，见 buildMenuFromRoutes()
            {
                path: "",
                redirect: "/games",
            },
            {
                path: "games",
                name: "games",
                component: () => import("@/views/games/index.vue"),
                meta: { title: "游戏中心" },
            },
            {
                path: "games/manage",
                name: "games-manage",
                component: () => import("@/views/games/manage/index.vue"),
                meta: { title: "游戏管理" },
            },
            {
                path: "games/flash/:gameId",
                name: "games-flash",
                component: () => import("@/views/games/flash-player.vue"),
                meta: { title: "Flash 游戏", hiddenInMenu: true },
            },
            {
                path: "games/h5/:gameId",
                name: "games-h5",
                component: () => import("@/views/games/h5-player.vue"),
                meta: { title: "HTML5 游戏", hiddenInMenu: true },
            },
            {
                path: "games/play/:gameId",
                name: "games-play",
                component: () => import("@/views/games/emulator-player.vue"),
                meta: { title: "模拟器游戏", hiddenInMenu: true },
            },
        ],
    },
];

const router = createRouter({
    history: createWebHistory(),
    routes,
});

export function buildMenuFromRoutes() {
    const layout = routes.find((item) => item.path === "/");
    return (layout?.children || [])
        .filter((item) => item.meta && item.meta.title && !item.meta.hiddenInMenu)
        .map((item) => ({
            path: item.path === "" ? "/" : `/${item.path}`,
            title: item.meta.title,
        }));
}

export default router;
