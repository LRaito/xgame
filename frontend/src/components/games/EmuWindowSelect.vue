<template>
    <div ref="rootRef" class="emu-window-select">
        <span class="emu-window-select__text">窗口</span>
        <button
            type="button"
            class="emu-window-select__button"
            :aria-expanded="open ? 'true' : 'false'"
            @click="open = !open"
        >
            {{ currentLabel }}
        </button>

        <!-- 面板就地渲染在标题栏里（不 teleport）：鼠标移进面板仍算在标题栏内，
             标题栏不会收起把它一起带走 -->
        <div v-if="open" class="emu-window-select__panel">
            <button
                type="button"
                class="emu-window-select__fit"
                :class="{ 'is-active': scale === FIT }"
                @click="pick(FIT, mode)"
            >
                适应窗口
            </button>
            <!-- 两列矩阵：行是倍率，列是显示比例。只有这台机器有两种比例（FC）时才画表头 -->
            <div class="emu-window-select__grid" :class="{ 'emu-window-select__grid--wide': wide }">
                <template v-if="wide">
                    <span />
                    <span class="emu-window-select__head">像素完美</span>
                    <span class="emu-window-select__head">4:3</span>
                </template>
                <template v-for="row in rows" :key="row.value">
                    <span class="emu-window-select__scale">{{ row.label }}</span>
                    <button
                        type="button"
                        class="emu-window-select__cell"
                        :class="{ 'is-active': isActive(row.value, PP) }"
                        @click="pick(row.value, PP)"
                    >
                        {{ row.pp }}
                    </button>
                    <button
                        v-if="wide"
                        type="button"
                        class="emu-window-select__cell"
                        :class="{ 'is-active': isActive(row.value, WIDE) }"
                        @click="pick(row.value, WIDE)"
                    >
                        {{ row.wide }}
                    </button>
                </template>
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

// 窗口模式的取值：`<倍率>|<显示比例>`，如 `2|pp`、`1.5|wide`、`fit|pp`。
// 显示比例只有 pp（像素完美，1:1 方像素）与 wide（4:3，真机 CRT 观感，画面横向拉宽填满 4:3）两种，
// 且只有 FC 会画第二列（传了 wide）——别的机种的内核没有可切的显示比例选项。
const FIT = "fit";
const PP = "pp";
const WIDE = "wide";

const props = defineProps({
    // 默认值与下面的 FIT 常量同一个字面量（defineProps 的默认值不能引用局部变量）
    modelValue: { type: String, default: "fit" },
    // 该平台的帧缓冲分辨率（像素）：倍率按它的高度换算窗口像素高度
    nativeSize: { type: Object, default: null },
    // 引擎上报的显示宽高比：窗口宽度按它推出（与播放页舞台同一套算法，否则显示的尺寸对不上）
    aspect: { type: Number, default: 0 },
    // 第二列（4:3）的配置 { aspect, native }；null 表示这台机器只有一种显示比例，不画第二列。
    // native 是这一列的**帧缓冲分辨率**（可能和第一列不同：FC 的 4:3 模式用完整 240 行帧）
    wide: { type: Object, default: null },
});

const emit = defineEmits(["update:modelValue"]);

// 可选窗口倍率：1× 用帧缓冲像素高度，往上（含半档）放大；「适应窗口」在另一个选项里。
const SCALES = [1, 1.5, 2, 2.5, 3, 3.5, 4];

const rootRef = ref(null);
const open = ref(false);

// 取值解析：早期只存过倍率（没有 "|"），一律当作像素完美
const parsed = computed(() => {
    const [value, mode] = String(props.modelValue || FIT).split("|");
    return {
        scale: value || FIT,
        mode: mode === WIDE && props.wide ? WIDE : PP,
    };
});
const scale = computed(() => parsed.value.scale);
const mode = computed(() => parsed.value.mode);
const wide = computed(() => Boolean(props.wide?.aspect && props.wide?.native?.height));

// 第一列恒是 1:1 方像素（比例 = 帧缓冲比例）；没有第二列的平台沿用引擎上报的显示比例，
// 免得 SNES 那种内核按 4:3 摆放的机种在菜单里显示成帧缓冲比例。
const ppRatio = computed(() => {
    const native = props.nativeSize;
    const framebuffer = native?.height ? native.width / native.height : 0;
    return wide.value ? framebuffer : props.aspect || framebuffer;
});

function sizeText(height, ratio) {
    const h = Math.max(1, Math.round(height));
    return `${Math.max(1, Math.round(h * ratio))} × ${h}`;
}

// 与播放页 applyStage() 同一算法：高度取整后再推宽度
const rows = computed(() => {
    const native = props.nativeSize;
    // 倍率一律带一位小数（1.0×/1.5×/2.0×…）：列里宽度对齐，比 1×/2× 混排更好扫
    const label = (value) => `${value.toFixed(1)}×`;
    if (!native?.height) {
        return SCALES.map((value) => ({ value: String(value), label: label(value), pp: "", wide: "" }));
    }
    return SCALES.map((value) => {
        const height = native.height * value;
        return {
            value: String(value),
            label: label(value),
            pp: sizeText(height, ppRatio.value),
            // 第二列的高度可能来自另一套帧缓冲（FC 的 4:3 模式用完整 240 行帧）
            wide: wide.value
                ? sizeText(props.wide.native.height * value, props.wide.aspect)
                : "",
        };
    });
});

// 收起状态下按钮上的文字 = 当前选择（真实窗口尺寸）
const currentLabel = computed(() => {
    const prefix = mode.value === WIDE ? "4:3 " : "";
    if (scale.value === FIT) {
        return mode.value === WIDE ? "适应窗口（4:3）" : "适应窗口";
    }
    const row = rows.value.find((item) => item.value === scale.value);
    const size = row ? (mode.value === WIDE ? row.wide : row.pp) : "";
    const value = scale.value;
    return size ? `${prefix}${value}× （${size}）` : `${prefix}${value}×`;
});

function isActive(value, target) {
    return scale.value === value && mode.value === target;
}

function pick(nextScale, nextMode) {
    emit("update:modelValue", `${nextScale}|${nextMode}`);
    open.value = false;
}

function onDocumentPointerDown(event) {
    if (!rootRef.value?.contains(event.target)) {
        open.value = false;
    }
}

function onDocumentKeydown(event) {
    if (event.key === "Escape") {
        open.value = false;
    }
}

// 只在面板打开期间挂全局监听（点外面/按 ESC 收起）
watch(open, (value) => {
    if (value) {
        document.addEventListener("pointerdown", onDocumentPointerDown, true);
        document.addEventListener("keydown", onDocumentKeydown);
    } else {
        document.removeEventListener("pointerdown", onDocumentPointerDown, true);
        document.removeEventListener("keydown", onDocumentKeydown);
    }
});

onBeforeUnmount(() => {
    document.removeEventListener("pointerdown", onDocumentPointerDown, true);
    document.removeEventListener("keydown", onDocumentKeydown);
});
</script>

<style scoped>
.emu-window-select {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
}

.emu-window-select__text {
    font-size: 13px;
    color: #94a3b8;
    white-space: nowrap;
}

/* 与标题栏的按钮（.game-shell__btn / .emulator-player__action）同一套盒模型：
   8px 上下内边距 + 14px 字号 + 1.6 行高 = 40px 高，并排时上下沿对齐 */
.emu-window-select__button {
    padding: 8px 10px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 8px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 14px;
    line-height: 1.6;
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
    white-space: nowrap;
}

.emu-window-select__button:hover {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}

.emu-window-select__button:focus-visible {
    outline: none;
    border-color: #38bdf8;
}

/* 面板挂在按钮下方、右对齐：标题栏靠右，右对齐才不会被视口切掉 */
.emu-window-select__panel {
    position: absolute;
    top: calc(100% + 10px);
    right: 0;
    z-index: 30;
    padding: 8px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 10px;
    background: rgba(15, 23, 42, 0.96);
    box-shadow: 0 14px 34px rgba(2, 6, 23, 0.55);
    backdrop-filter: blur(8px);
}

.emu-window-select__fit {
    display: block;
    width: 100%;
    margin-bottom: 6px;
    padding: 8px 10px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 13px;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
}

.emu-window-select__grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px;
    align-items: center;
}

.emu-window-select__grid--wide {
    grid-template-columns: auto 1fr 1fr;
}

.emu-window-select__head {
    padding: 0 8px;
    font-size: 12px;
    color: #94a3b8;
    text-align: center;
    white-space: nowrap;
}

.emu-window-select__scale {
    padding-right: 8px;
    font-size: 13px;
    color: #94a3b8;
    text-align: right;
    white-space: nowrap;
}

.emu-window-select__cell {
    padding: 7px 10px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s ease, border-color 0.15s ease;
}

.emu-window-select__fit:hover,
.emu-window-select__cell:hover {
    background: rgba(51, 65, 85, 0.95);
    border-color: rgba(148, 163, 184, 0.4);
}

/* 当前生效的那一格点亮，一眼看出选的是倍率 + 哪种显示比例 */
.emu-window-select__fit.is-active,
.emu-window-select__cell.is-active {
    background: rgba(37, 99, 235, 0.85);
    border-color: rgba(96, 165, 250, 0.6);
    color: #f8fafc;
}
</style>
