import request, { ensureCsrf } from "@/utils/request";

export function csrfAPI() {
    return ensureCsrf();
}

export function registerAPI(data) {
    return request({
        url: "/api/register",
        method: "post",
        data,
        notShowError: true,
        skipAuthRedirect: true,
    });
}

export function loginAPI(data) {
    return request({
        url: "/api/login",
        method: "post",
        data,
        notShowError: true,
        skipAuthRedirect: true,
    });
}

export function logoutAPI() {
    return request({ url: "/api/logout", method: "post", data: {} });
}

export function meAPI() {
    return request({ url: "/api/me", method: "get", notShowError: true, skipAuthRedirect: true });
}
