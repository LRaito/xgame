/**
 * 顶层页面是否已获得过用户手势（sticky user activation）。
 *
 * 浏览器（尤其 Chrome）会用它在“无手势”时拦截页面自动出声：
 * AudioContext 在无手势时创建会报 “not allowed to start”，需要一次点击后
 * 才能开始。点击游戏进入时那次点击会记下手势 → 可自动开始；刷新页面或直接
 * 打开播放链接时手势被重置 → 引擎应先停下，等一次点击再启动。
 *
 * 浏览器不支持 userActivation（极老版本）时按“已有手势”处理，保持旧行为自动开始。
 */
export function hasUserGesture() {
    if (typeof navigator === "undefined") {
        return true;
    }
    const activation = navigator.userActivation;
    if (!activation) {
        return true;
    }
    return activation.hasBeenActive === true;
}
