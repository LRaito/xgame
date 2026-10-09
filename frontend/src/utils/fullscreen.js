/**
 * 全屏状态探测。两种全屏要分开看：
 *
 * - **元素全屏**：页面调 `element.requestFullscreen()` 进入。`document.fullscreenElement` 有值、
 *   `fullscreenchange` 会触发，状态是精确的。
 * - **浏览器全屏**：用户按 F11。**没有任何 API 能读到它**——`document.fullscreenElement` 仍是
 *   null、`fullscreenchange` 不触发，F11 的 keydown 也被浏览器保留、不派发给页面。唯一线索是
 *   窗口尺寸：全屏时窗口装饰（标题栏 / 标签栏 / 地址栏）消失，可视区高度顶到屏幕可用高度。
 *   所以只能启发式判断（见 detectBrowserFullscreen 注释），会有漏判。
 *
 * 只监听 resize 与 fullscreenchange：两者已覆盖 F11 进/出、元素全屏进/出、分辨率变化等场景
 * （F11 改变视口尺寸，必然触发 resize）。页面刷新时本就处于 F11 的情况，由 setup 期的首次计算兜住。
 */
import { onBeforeUnmount, onMounted, ref } from "vue";

// 全屏时 innerHeight / outerHeight ≈ 1（窗口装饰没了），窗口模式下明显更小。
// 用比值而非差值是为了不受浏览器缩放影响：缩放让 innerHeight / outerHeight 同步缩小，比值不变。
const OUTER_RATIO_MIN = 0.96;
// 高度按 CSS 像素比较，留几像素取整误差（系统 125% 缩放、小数像素等）
const SLACK_PX = 4;

/**
 * 浏览器是否处于 F11 全屏（启发式，尽力而为）。
 *
 * 已知漏判：**页面缩放不是 100%** 时（Ctrl +/-），innerHeight 按 CSS 像素被缩小，
 * 顶不到 screen.availHeight，会判为「非全屏」。系统显示缩放（Windows 125% 等）不受影响，
 * 因为 screen 尺寸与 innerHeight 同为 CSS 像素、一起缩放。
 */
export function detectBrowserFullscreen() {
    const screenMeta = window.screen;
    const availHeight = screenMeta?.availHeight || screenMeta?.height || 0;
    if (!availHeight) {
        return false;
    }
    const innerHeight = window.innerHeight;
    const outerHeight = window.outerHeight;
    // 比值不达标直接否掉：能挡掉「把窗口手动拉大到刚好铺满屏幕」之类的误判
    if (outerHeight > 0 && innerHeight / outerHeight < OUTER_RATIO_MIN) {
        return false;
    }
    // 窗口模式下窗口高度不可能顶到屏幕可用高度（差着一个浏览器工具栏），只有真全屏才会
    return innerHeight >= availHeight - SLACK_PX;
}

/**
 * 订阅全屏状态，返回两个来源各自的 ref：`elementFullscreen`（本页有元素处于 requestFullscreen）、
 * `browserFullscreen`（F11）。组件卸载时自动摘掉监听。
 */
export function useFullscreenState() {
    const elementFullscreen = ref(false);
    const browserFullscreen = ref(false);

    function sync() {
        elementFullscreen.value = Boolean(document.fullscreenElement);
        // 元素全屏时视口也顶满屏幕，启发式会一并判成 F11。两者分开报告、互斥，
        // 免得同一次全屏被当成「元素全屏 + F11」触发两轮逻辑。
        browserFullscreen.value = !elementFullscreen.value && detectBrowserFullscreen();
    }

    // 立即算一次：刷新时本就处于 F11 的话，首次渲染就得是正确状态，不能等 resize
    sync();

    onMounted(() => {
        window.addEventListener("resize", sync);
        document.addEventListener("fullscreenchange", sync);
    });

    onBeforeUnmount(() => {
        window.removeEventListener("resize", sync);
        document.removeEventListener("fullscreenchange", sync);
    });

    return { elementFullscreen, browserFullscreen };
}
