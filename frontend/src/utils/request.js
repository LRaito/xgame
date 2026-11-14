import axios from "axios";
import { ElMessage } from "element-plus";
import { clearSession } from "./auth";
import { overlayAppendTarget } from "./overlay";

let csrfToken = "";
let isRedirectingToLogin = false;

const request = axios.create({
    baseURL: "",
    withCredentials: true,
    timeout: 60000,
});

export function setCsrfToken(token) {
    csrfToken = token || "";
}

export async function ensureCsrf() {
    const res = await request({ url: "/api/csrf", method: "get", notShowError: true });
    setCsrfToken(res.csrf_token);
    return res.csrf_token;
}

/**
 * 统一的失败 Error。reported=true 表示拦截器已经弹过提示，
 * 页面的 catch 里别再弹一次（判断 `if (!err.reported)`）。
 * status 是 HTTP 状态码（网络错误等没有响应时为 undefined），
 * 路由守卫用它区分「真未登录(401)」与「网络抖动等临时故障」。
 */
function fail(message, reported, status) {
    const error = new Error(message);
    error.reported = reported;
    error.status = status;
    return error;
}

request.interceptors.request.use((config) => {
    if (csrfToken) {
        config.headers["X-CSRFToken"] = csrfToken;
    }
    const data = config.data;
    const isPlainObject = data && typeof data === "object" && !(data instanceof FormData);
    if (isPlainObject && !config.headers["Content-Type"]) {
        config.headers["Content-Type"] = "application/json";
    }
    return config;
});

request.interceptors.response.use(
    (response) => {
        const payload = response.data;
        if (payload && typeof payload === "object" && "ok" in payload) {
            if (payload.ok) {
                return payload.data;
            }
            const message = payload.message || "请求失败。";
            const silent = Boolean(response.config.notShowError);
            if (!silent) {
                ElMessage.error({ message, appendTo: overlayAppendTarget() });
            }
            return Promise.reject(fail(message, !silent, response.status));
        }
        return payload;
    },
    (error) => {
        const status = error.response?.status;
        const payload = error.response?.data;
        const message =
            (payload && payload.message) ||
            (error.code === "ECONNABORTED" ? "请求超时。" : "网络错误，请稍后重试。");

        if (status === 401) {
            if (!error.config?.skipAuthRedirect && !isRedirectingToLogin) {
                isRedirectingToLogin = true;
                clearSession();
                const redirect = encodeURIComponent(window.location.pathname + window.location.search);
                window.location.href = `/login?redirect=${redirect}`;
                setTimeout(() => {
                    isRedirectingToLogin = false;
                }, 1500);
            }
            const silent401 = Boolean(error.config?.notShowError);
            if (!silent401) {
                ElMessage.error({ message, appendTo: overlayAppendTarget() });
            }
            return Promise.reject(fail(message, !silent401, 401));
        }

        const silent = Boolean(error.config?.notShowError);
        if (!silent) {
            ElMessage.error({ message, appendTo: overlayAppendTarget() });
        }
        return Promise.reject(fail(message, !silent, status));
    }
);

export default request;
