import router from "./router";
import { useAuthStore } from "./store/auth";

const whiteList = ["/login"];

router.beforeEach(async (to) => {
    const auth = useAuthStore();

    // 已登录用户：仅登录页回首页，其余放行
    if (auth.username) {
        return to.path === "/login" ? "/" : true;
    }

    // 未登录：若会话 cookie 仍在则直接进入，否则去登录页
    try {
        await auth.fetchMe();
        return whiteList.includes(to.path) ? "/" : true;
    } catch {
        if (whiteList.includes(to.path)) {
            return true;
        }
        return { path: "/login", query: { redirect: to.fullPath } };
    }
});
