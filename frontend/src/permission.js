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
    } catch (err) {
        // 只有明确拿到 401 才算「真未登录」。网络抖动、服务重启等临时故障
        // 不该把用户踹去登录页（会话 cookie 一直是好的，走进登录页却只能重新输密码）；
        // 放行页面，由页面自身的请求兜底：临时故障会重试成功，真掉线仍会被
        // request.js 的 401 拦截器跳登录页。
        if (err?.status !== 401) {
            return true;
        }
        if (whiteList.includes(to.path)) {
            return true;
        }
        return { path: "/login", query: { redirect: to.fullPath } };
    }
});
