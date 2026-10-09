import { addGamePlaytimeAPI } from "@/api/games";

/**
 * 游玩时长计时器：与游戏类型无关的通用方案。
 *
 * Flash（Ruffle 同页组件）、H5（沙箱 iframe）、主机 ROM（EmulatorJS 嵌套
 * iframe）三条播放路径共用这一份逻辑，调用方式完全一样：播放器真正拉起时
 * startGamePlaytime(gameId)，离开播放页时 stopGamePlaytime()。
 *
 * 上报策略：
 * - 每 30 秒发一次心跳，中途崩了最多丢 30 秒；
 * - 页面切到后台（document.hidden）不累计，回到前台再接着算——忘关标签页不会虚高；
 * - 离开播放页（路由切走）时把剩余的一次性发出，不足 1 秒丢弃。
 *
 * 上报一律 best-effort：走 axios（不是 sendBeacon），失败只丢这一段时长，
 * 绝不影响游玩。因为 visibilitychange → hidden 在页面真正卸载前就会触发、
 * 此时页面还活着，axios 来得及把请求送出去，所以不需要 keepalive。
 */

const TICK_INTERVAL_MS = 30000;
// 不足 1 秒的零头不值得发一次请求
const MIN_REPORT_MS = 1000;

let currentId = 0;
let lastTick = 0;
// 还没凑够一次心跳的零头（毫秒），停表时一并结算
let accMs = 0;
let timer = 0;
let listening = false;

function now() {
    return Date.now();
}

function addListeners() {
    if (listening) {
        return;
    }
    listening = true;
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pagehide", onPageHide);
}

function removeListeners() {
    if (!listening) {
        return;
    }
    listening = false;
    document.removeEventListener("visibilitychange", onVisibilityChange);
    window.removeEventListener("pagehide", onPageHide);
}

function onVisibilityChange() {
    if (document.hidden) {
        // 切后台：把已经攒下的时长结掉，之后不再累计
        flush();
    } else {
        // 回前台：重新起算，后台那段时间不算
        lastTick = now();
    }
}

function onPageHide() {
    // 已经切后台时 visibilitychange 结算过了，别把这段后台时间再算一遍
    if (document.hidden) {
        return;
    }
    flush();
}

function send(ms) {
    const id = currentId;
    if (!id || ms < MIN_REPORT_MS) {
        return;
    }
    // 秒数取整，交给后端去累加；失败只丢这一段
    addGamePlaytimeAPI(id, Math.round(ms / 1000)).catch(() => {});
}

function tick() {
    if (!currentId) {
        return;
    }
    const current = now();
    if (!document.hidden) {
        accMs += current - lastTick;
        if (accMs >= TICK_INTERVAL_MS) {
            send(accMs);
            accMs = 0;
        }
    }
    // 后台时只挪起点、不累计
    lastTick = current;
}

function flush() {
    if (!currentId) {
        return;
    }
    const current = now();
    // 无条件累计：从 lastTick 到现在这一段一定是「还在前台」的时间。
    // 可见性切换的那一刻 document.hidden 已经翻成 true 了，这里再判一次
    // 反而会把这次切走之前的零头丢掉（每切一次标签页就白丢最多 30 秒）。
    accMs += current - lastTick;
    lastTick = current;
    send(accMs);
    accMs = 0;
}

/** 开始给某个游戏计时。已在计时时先把上一段零头结算掉，避免重复调用丢时长。 */
export function startGamePlaytime(gameId) {
    const id = Number(gameId);
    if (!id) {
        return;
    }
    if (currentId) {
        // 换游戏（走 watch 换路由参数）或同游戏重新拉起都走这里：先结算再重开
        flush();
    }
    currentId = id;
    lastTick = now();
    if (!timer) {
        timer = window.setInterval(tick, TICK_INTERVAL_MS);
    }
    addListeners();
}

/** 停表并结算剩余时长（播放页卸载时调用）。 */
export function stopGamePlaytime() {
    if (!currentId) {
        return;
    }
    flush();
    currentId = 0;
    accMs = 0;
    lastTick = 0;
    if (timer) {
        window.clearInterval(timer);
        timer = 0;
    }
    removeListeners();
}

const SECONDS_PER_HOUR = 3600;

/**
 * 秒数格式化成「N 小时」：不到 10 小时保留 1 位小数，10 小时以上取整。
 * 0 返回空串——没时长时卡片上什么都不显示，不写「未玩过」之类的占位。
 */
export function formatPlayHours(playSeconds) {
    const hours = (Number(playSeconds) || 0) / SECONDS_PER_HOUR;
    if (hours <= 0) {
        return "";
    }
    return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)} 小时`;
}

/** 秒数换算成小时数，用于「设置时长」弹窗的初值。 */
export function playSecondsToHours(playSeconds) {
    const hours = (Number(playSeconds) || 0) / SECONDS_PER_HOUR;
    return hours < 10 ? Math.round(hours * 10) / 10 : Math.round(hours);
}
