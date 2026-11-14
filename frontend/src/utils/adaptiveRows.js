import { onBeforeUnmount, onMounted, ref } from "vue";

/**
 * 列表一页行数自适应：行高固定（各页样式里写死），行数按视口高度算出来——
 * 「可用高度」= 视口高 − 列表顶部偏移 − 列表底部固定开销，行数 = floor(可用高度 / 行高)。
 * 超出整行的那点余量留在最后一行与分页条之间（不拉伸行高，全屏与非全屏行高一致）。
 *
 * 用法：列表容器挂成 ref，首屏请求前 `measure(el)` 量一次；窗口尺寸变化时
 * 本工具自己重测，行数变化就回调 `onRowsChange`（调用方在那里重新请求）。
 * 同一页上有多个列表（如游戏发现的名录/榜单）时各配一个实例；v-show 隐藏的
 * 区块量不到几何信息会被跳过，切回可见时要由调用方再 `measure` 一次。
 *
 * 参数：
 * - rowHeight：一行的固定像素高（含上下内边距，各页样式里写死）；
 * - extraHeight：一行之外表格的固定开销（表头 + 外框 + 分隔线，两层样式里算了数）；
 * - reservePx：列表底部给分页条、页面底部边距的实际开销（照样式里的数给，不带缓冲）；
 * - minRows/maxRows：行数下限（太矮的窗口至少显示 1 行；上限对齐后端 page_size 的 100）；
 * - initialRows：量到之前的占位行数（首帧渲染/首屏等待响应时的高度兜底，别给 0）。
 *
 * 量的是「容器顶部到文档顶的距离」而不是 rect.top——后者随页面滚动变化，量出来的
 * 行数会跟着误动。
 */
export function useAdaptiveRows(options, onRowsChange) {
    const {
        rowHeight,
        extraHeight = 0,
        reservePx = 96,
        minRows = 1,
        maxRows = 100,
        initialRows = maxRows,
    } = options;

    const rows = ref(initialRows);
    let el = null;
    let docTop = 0;
    let measured = false;
    let timer = 0;

    function measure(target) {
        if (target) {
            el = target;
        }
        // v-show 藏着的区块（display:none）没有几何信息，别把它的 rect 当真
        if (!el || el.offsetParent === null) {
            return;
        }
        docTop = el.getBoundingClientRect().top + window.scrollY;
        const available = Math.max(0, Math.floor(window.innerHeight - docTop - reservePx));
        const room = available - extraHeight;
        const next = Math.min(maxRows, Math.max(minRows, Math.floor(room / rowHeight)));
        // 首次测量只赋值不回调：调用方量的就是首屏请求之前，行数回调会变成多发一次请求
        const first = !measured;
        measured = true;
        if (first || next !== rows.value) {
            rows.value = next;
            if (!first) {
                onRowsChange?.(next);
            }
        }
    }

    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(() => measure(), 200);
    }

    function onResize() {
        clearTimeout(timer);
        // 已量过的立即重算（全屏切换要马上跟上）；还没量到的走防抖，别丢首帧
        if (measured) {
            measure();
        } else {
            schedule();
        }
    }

    onMounted(() => window.addEventListener("resize", onResize));
    onBeforeUnmount(() => {
        clearTimeout(timer);
        window.removeEventListener("resize", onResize);
    });

    return { rows, measure };
}
