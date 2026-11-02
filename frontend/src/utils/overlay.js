import { ElMessage } from "element-plus";

/**
 * 浮层挂载点：全屏时挂到全屏元素内部，否则挂到 body。
 * 浏览器全屏会进入 top layer，body 下的 toast / 确认框即使 z-index 再高也会被盖住。
 */
export function overlayAppendTarget() {
    if (typeof document === "undefined") {
        return undefined;
    }
    return document.fullscreenElement || document.body;
}

function normalize(input, extra) {
    const base = typeof input === "string" ? { message: input } : { ...input };
    return { appendTo: overlayAppendTarget(), ...base, ...extra };
}

/** 带全屏感知的 ElMessage 快捷方法。 */
export const appMessage = {
    success(message, extra = {}) {
        return ElMessage.success(normalize(message, extra));
    },
    warning(message, extra = {}) {
        return ElMessage.warning(normalize(message, extra));
    },
    error(message, extra = {}) {
        return ElMessage.error(normalize(message, extra));
    },
    info(message, extra = {}) {
        return ElMessage.info(normalize(message, extra));
    },
};
