<template>
    <game-shell :title="gameTitle" @fullscreen-change="onFullscreenChange">
        <template #extra>
            <span class="emulator-player__hint">{{ platformHint }}</span>
        </template>
        <template #actions>
            <!-- 截当前画面（Ctrl+Shift+S 同效）：先弹确认框预览+填描述，确认后存入图库 -->
            <button
                v-if="game"
                type="button"
                class="emulator-player__action"
                :disabled="!engineReady || shooting"
                @click="onScreenshot"
            >
                {{ shooting ? "截图中…" : "截图" }}
            </button>
            <!-- 把当前键位/画面/音量等模拟器配置整块存到账号 -->
            <button
                v-if="game"
                type="button"
                class="emulator-player__action"
                :disabled="savingSettings"
                @click="saveEngineSettings"
            >
                {{ savingSettings ? "保存中…" : "保存配置" }}
            </button>
            <!-- 第一列（像素完美）恒用机种固有的帧缓冲；4:3 那一列自带另一套（见 WIDE_MODE） -->
            <emu-window-select
                v-if="baseNativeSize"
                v-model="windowMode"
                :native-size="baseNativeSize"
                :aspect="stageAspect"
                :wide="wideMode"
            />
            <!-- 有洞对齐图的平台（GBA、FC、GBC）：把机壳图盖在画面上，中间那个洞正好露出游戏画面 -->
            <button
                v-if="supportsShell"
                type="button"
                class="emulator-player__action"
                :class="{ 'emulator-player__action--on': shellOn }"
                :aria-pressed="shellOn"
                @click="toggleShell"
            >
                {{ shellOn ? "隐藏游戏机" : "显示游戏机" }}
            </button>
            <button
                v-if="game"
                type="button"
                class="emulator-player__action"
                @click="saveManagerVisible = true"
            >
                存档管理
            </button>
        </template>
        <start-gate
            v-if="needsGesture"
            @start="startFromGate"
        />
        <div
            v-else
            ref="areaRef"
            class="emulator-player"
            :class="{ 'emulator-player--fullscreen': isFullscreen }"
        >
            <!-- 舞台按所选窗口模式定宽高；EmulatorJS 引擎铺满 iframe 画布，
                因此舞台长宽比需与平台原始分辨率一致，否则画面会被拉伸变形。 -->
            <div v-if="iframeSrc" ref="stageEl" class="emulator-player__stage" :style="stageStyle">
                <iframe
                    ref="frameRef"
                    class="emulator-player__frame"
                    :src="iframeSrc"
                    title="游戏画面"
                    allowfullscreen
                    allow="autoplay; fullscreen"
                    referrerpolicy="same-origin"
                    @load="onFrameLoad"
                />
                <!-- 机壳盖在游戏画面上：洞外的部分是外壳本体，正好落在画面之外，
                     所以它不会挡住引擎自己的任何 UI；pointer-events: none 保证仍然能玩 -->
                <img
                    v-if="shellStyle"
                    class="emulator-player__shell"
                    :style="shellStyle"
                    :src="shell.url"
                    alt=""
                    draggable="false"
                />
            </div>
            <div v-else-if="!loading" class="emulator-player__empty">
                <app-empty :description="errorText || '未找到该游戏'" />
            </div>
        </div>

        <emu-save-manager
            ref="saveManagerRef"
            v-model="saveManagerVisible"
            :game-id="currentGameId"
            :engine-ready="engineReady"
            @capture="onCapture"
            @load-local="onLoadLocal"
            @upload-cloud="onUploadCloud"
            @sync-local="onSyncLocal"
        />

        <screenshot-confirm-dialog
            v-model="shotDialogVisible"
            :preview-url="shotPreviewUrl"
            :saving="shooting"
            @confirm="confirmScreenshot"
        />
    </game-shell>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
    cloudSaveDetailAPI,
    fetchCloudSaveFileBase64,
    getEmulatorSettingsAPI,
    getPlayableGameAPI,
    saveEmulatorSettingsAPI,
    uploadCloudSaveAPI,
    uploadScreenshotAPI,
} from "@/api/games";
import { gameTypeMeta } from "@/constants/gameTypes";
import {
    EMU_SAVE_FILENAME,
    emuBase64ToBlob,
    ensureSingleSlotModel,
    getEmuSaveBase64,
    getLocalEmuSave,
    writeLocalEmuSave,
} from "@/utils/emulatorSaves";
import {
    engineSettingsKey,
    readEngineSettingsRaw,
    writeEngineSettings,
} from "@/utils/emulatorSettings";
import GameShell from "@components/games/GameShell.vue";
import EmuSaveManager from "@components/games/EmuSaveManager.vue";
import EmuWindowSelect from "@components/games/EmuWindowSelect.vue";
import ScreenshotConfirmDialog from "@components/games/ScreenshotConfirmDialog.vue";
import StartGate from "@components/games/StartGate.vue";
import { hasUserGesture } from "@/utils/userActivation";
import { reportGamePlayed } from "@/utils/recentGames";
import { startGamePlaytime, stopGamePlaytime } from "@/utils/gamePlaytime";

const ENGINE_LOADER = "/emulatorjs/data/loader.js";

// 各主机平台的原始帧缓冲分辨率（像素）：窗口倍率按它换算，也是引擎就绪前的舞台比例兜底。
// 帧缓冲比例 ≠ 显示比例——内核会按像素宽高比（PAR）校正，舞台长宽比最终以引擎上报的
// aspect 为准（见 stageAspect）。
// NES 是 256 × 224：fceumm 默认裁掉上下各 8 行过扫描（Crop Vertical Top/Bottom Overscan = 8，
// 内核选项 fceumm_overscan_v_top/_bottom），宿主页默认把显示比例设成像素完美（见
// emulator-host.html），于是 1× 就是 256 × 224 个方像素。FC 还可以切到 4:3 那一列，
// 那用的是另一套帧缓冲（完整 240 行），见下面的 WIDE_MODE。
const EMU_NATIVE = {
    nes: { width: 256, height: 224 },
    snes: { width: 256, height: 224 },
    gb: { width: 160, height: 144 },
    gba: { width: 240, height: 160 },
    segaMD: { width: 320, height: 224 },
    segaGG: { width: 160, height: 144 },
    segaMS: { width: 256, height: 192 },
};

// 机壳图（frontend/public/ 下按 URL 引用的静态文件）：一张画好的机器外形图，
// 中间是**全透明的屏幕洞**。把图按「洞宽 = 画面宽」放大后盖在画面上，就是真机在玩。
// 每项里的两组数字是这张图与洞的像素几何，换图必须同步改（洞的位置变了就会错位）。
// 洞的比例还必须与画面比例一致，否则洞与画面会错开：
//   GBA 洞 1920×1280 = 3:2，正是 GBA 原生 240×160；
//   GBC 洞 1285×1156.5 = 10:9，正是 GB/GBC 原生 160×144（gambatte 上报的比例就是 160/144）；
//     原素材洞是 1285×1157、左右留白差 17px，入项目前从左边裁掉 17px 让屏幕左右对称，
//     剩下的半个像素差（10/9 的理论洞高 1156.5）按小数声明即可，不必真去拉伸图画；
//   FC 的电视机壳有两套，正好对应窗口选择器里的两列显示比例（见 WIDE_MODE）：
//   `pp`（像素完美 8:7）那套是原素材把**屏幕那段纵向拉长 7/6 倍**（原素材洞 1084×813 = 4:3，
//   拉长后 1084×948.5 = 8:7）得到的，下面 121 行的控制条（扬声器 / 按键）保持等比不变，
//   最后裁掉四周透明留白（只顶部有 10 行是空的）；`wide`（4:3）那套就是原素材本身
//   （4:3 的洞），只裁掉顶部 9 行留白。切比例时机壳跟着换成对应的那套，洞才与画面一致。
const SHELLS = {
    gba: {
        pp: {
            url: "/gba-shell.png",
            image: { width: 3840, height: 2160 },
            hole: { x: 960, y: 440, width: 1920, height: 1280 },
        },
    },
    gb: {
        pp: {
            url: "/gbc-shell.png",
            image: { width: 2131, height: 1996 },
            // 带小数：10/9 × 1285 = 1156.5，比画出来的洞矮半个像素（见上面的说明）
            hole: { x: 423, y: 338, width: 1285, height: 1156.5 },
        },
    },
    nes: {
        // 像素完美（8:7）：素材是把原图屏幕那段纵向拉长 7/6 得到的
        pp: {
            url: "/nes-shell.png",
            image: { width: 1326, height: 1237 },
            // 带小数：这两个值来自原素材的洞坐标 × 7/6（纵向拉伸倍率）再减去裁掉的那 10 行
            hole: { x: 121, y: 146.3333, width: 1084, height: 948.5 },
        },
        // 4:3：用**未拉伸的原素材**，洞本来就是 4:3，只裁掉了顶部 9 行透明留白
        wide: {
            url: "/nes-shell-43.png",
            image: { width: 1326, height: 1077 },
            hole: { x: 121, y: 125, width: 1084, height: 813 },
        },
    },
};

const WINDOW_STORAGE_KEY = "games.emu.window";
// 机壳开关也是本地偏好（纯观赏层，不随账号走），下次进有对应机壳的游戏沿用上次的选择
const SHELL_STORAGE_KEY = "games.emu.shell";

// 显示比例模式（窗口选择器里那一列）：pp = 像素完美（1:1 方像素，画面比例 = 帧缓冲比例）；
// wide = 4:3（真机 CRT 观感，把画面横向拉宽填满 4:3）。只有 FC 两种都提供
// （内核选项 fceumm_aspect 可切，两套比例各有一张机壳素材，见 WIDE_MODE / SHELLS）。
const ASPECT_PP = "pp";
const ASPECT_WIDE = "wide";
// 「4:3」那一列只有 FC 有，它同时改两件事（见 emulator-host.html 的 setDisplayMode）：
//   1) 内核显示比例 fceumm_aspect = 4:3；
//   2) **关掉上下过扫描裁切**，帧缓冲变成完整的 256×240。
// 必须用完整 240 行：224 行按内核的 4:3 摆放算出来是 ≈1.43（内核按完整帧归一化），
// 真填进 4:3 的电视屏幕会上下留黑边；完整帧按 4:3 摆放才正好铺满屏幕，
// 也正是 public/nes-shell-43.png（原素材，屏幕洞本来就 4:3）对应的画面。
const WIDE_MODE = {
    nes: { aspect: 4 / 3, native: { width: 256, height: 240 } },
};

// 窗口取值是 `<倍率>|<显示比例>`（如 "2|pp" / "1.5|wide" / "fit|pp"）。
// 早期版本只存倍率（"fit" / "2"），按像素完美读，所以这里容忍没有 "|" 的老值。
function parseWindowValue(raw) {
    const [scale, mode] = String(raw || "").split("|");
    const valid = scale === "fit" || (scale && Number(scale) > 0);
    return {
        scale: valid ? scale : "fit",
        mode: mode === ASPECT_WIDE ? ASPECT_WIDE : ASPECT_PP,
    };
}

function loadStoredWindow() {
    try {
        const value = localStorage.getItem(WINDOW_STORAGE_KEY);
        const parsed = parseWindowValue(value);
        return `${parsed.scale}|${parsed.mode}`;
    } catch {
        return "fit|pp";
    }
}

function loadStoredShell() {
    try {
        return localStorage.getItem(SHELL_STORAGE_KEY) === "1";
    } catch {
        return false;
    }
}

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const game = ref(null);
const meta = ref(null);
const errorText = ref("");
const iframeSrc = ref("");
const frameRef = ref(null);
const areaRef = ref(null);
const saveManagerRef = ref(null);
const saveManagerVisible = ref(false);
const engineReady = ref(false);
const savingSettings = ref(false);
const shooting = ref(false);
// 截图确认弹框：截下的图先在这里预览、可填描述，点「确认」才上传入库
const shotDialogVisible = ref(false);
const shotPreviewUrl = ref("");
const shotSizeText = ref("");
const isFullscreen = ref(false);
// 无用户手势（刷新/直链进入）时先展示「开始游戏」，由一次点击后再启动引擎
const needsGesture = ref(false);
const windowMode = ref(loadStoredWindow());
const stageSize = ref(null);
// 是否盖上机壳：本地记住的偏好，进游戏时按它恢复
const shellVisible = ref(loadStoredShell());
// 舞台在视口里的位置。机壳是 position: fixed（见样式里的说明），要用视口坐标，
// 而这只能从 DOM 现读，滚动 / 缩放窗口 / 全屏之后都得重新同步一次
const stageEl = ref(null);
const stageRect = ref(null);

// 云端模拟器配置：引擎只在启动时读一次设置键，所以「加载」必须在拉起 iframe 之前写完；
// 反过来「保存」由标题栏的「保存配置」按钮手动触发（见 saveEngineSettings）。
const SETTINGS_FETCH_TIMEOUT = 3000;

let enginePollTimer = null;
let resizeObserver = null;
let engineSettingsKeyValue = "";
let settingsPrefetch = null;
let launching = false;
// 本地档正在读档（回车快捷键会连发，用它挡掉重复的载入）
let loadingLocal = false;
let stageRaf = null;
// 就绪后只按选中比例纠正内核一次（见 refreshEngineReady）
let aspectSynced = false;
// 截下来的那张图（等确认框点「确认」时才上传）；previewUrl 是它的 objectURL
let shotBlob = null;
// 宿主 iframe 的 window：快捷键要挂在它上面，见 bindFrameHotkey
let hotkeyFrameWindow = null;

const gameTitle = computed(() => game.value?.name || "模拟器游戏");
const currentGameId = computed(() => (game.value?.id ? Number(game.value.id) : 0));
// 像素完美那一列的帧缓冲基准（机种固有）
const baseNativeSize = computed(() => {
    if (!game.value) {
        return null;
    }
    return EMU_NATIVE[game.value.category] || null;
});
const platformHint = computed(() =>
    meta.value?.label ? `（${meta.value.label}）` : "",
);
// 窗口取值拆成「倍率」与「显示比例」两部分（见 parseWindowValue）
const windowScale = computed(() => parseWindowValue(windowMode.value).scale);
// 该机种是否提供 4:3 那一列（null = 只能像素完美）；给出的是它那套配置
const wideMode = computed(() => WIDE_MODE[game.value?.category] || null);
const aspectMode = computed(() => {
    const mode = parseWindowValue(windowMode.value).mode;
    return wideMode.value ? mode : ASPECT_PP;
});
// 当前模式实际用的帧缓冲：宽模式用另一套（FC 是完整 240 行帧），倍率与舞台都按它算
const nativeSize = computed(() => {
    const base = baseNativeSize.value;
    if (!base) {
        return null;
    }
    return aspectMode.value === ASPECT_WIDE && wideMode.value ? wideMode.value.native : base;
});
/** 某个显示比例下画面应有的宽高比：引擎没上报时兜底，也是切模式那一刻的即时值 */
function aspectForMode(mode) {
    if (mode === ASPECT_WIDE && wideMode.value) {
        return wideMode.value.aspect;
    }
    const base = baseNativeSize.value;
    return base ? base.width / base.height : 0;
}
// 引擎上报的显示宽高比。**舞台必须按它定长宽比，不能拿帧缓冲分辨率相除**：引擎把画面
// 按这个比例等比摆进画布，画布（= 舞台）填不满的地方就是黑边，所以舞台必须按它定尺寸
// （例如 FC 在宿主页里设成像素完美，256 × 224 的帧缓冲就按 8:7 摆放；SNES 默认 4:3 同理）。
// 引擎就绪前、以及取不到 aspect 时，先用帧缓冲比例兜底。
const engineAspect = ref(null);
const stageAspect = computed(() => {
    if (engineAspect.value) {
        return engineAspect.value;
    }
    return aspectForMode(aspectMode.value);
});
// 舞台尺寸：fit=按可用空间等比缩放；否则按倍率放大原生分辨率（超出部分由容器滚动）
const stageStyle = computed(() => {
    if (!stageSize.value) {
        return null;
    }
    return { width: `${stageSize.value.width}px`, height: `${stageSize.value.height}px` };
});

// 机壳只有画过洞对齐图的平台有（其余类型没有这张图）。
// 每套比例一张素材（FC 是 pp / wide 两套），按当前显示比例取——洞的比例必须与画面一致，
// 所以切比例时机壳也跟着换图，否则洞会与画面错开。
const shell = computed(() => {
    const entry = SHELLS[game.value?.category];
    if (!entry) {
        return null;
    }
    return entry[aspectMode.value] || entry[ASPECT_PP] || null;
});
const supportsShell = computed(() => Boolean(shell.value));

// 真正生效的机壳状态。偏好是全局记的，所以换到没有机壳的游戏上即使上次开着也不盖
const shellOn = computed(() => supportsShell.value && shellVisible.value);

/**
 * 机壳在屏幕上的尺寸与位置：**洞宽 = 画面宽**定出比例，整张图按它放大，
 * 再按图里洞的偏移把整图挪到画面左上角，于是洞正好盖住画面。
 *
 * 洞本身的比例与舞台一致（GBA 3:2、FC 的电视机壳做成 8:7），所以只要舞台按引擎上报的
 * aspect 摆放，洞的上下左右会同时严丝合缝地对齐画面；画面一小（换倍率、缩窗口、全屏）
 * 这里就跟着重算，所以任何画面尺寸都适配。
 *
 * 机壳比浏览器窗口大就照大——同比放大、超出视口的部分看不见，不做裁剪也不弹提示。
 */
const shellStyle = computed(() => {
    const spec = shell.value;
    const stage = stageSize.value;
    const rect = stageRect.value;
    if (!shellOn.value || !spec || !stage?.width || !rect) {
        return null;
    }
    const scale = stage.width / spec.hole.width;
    return {
        left: `${rect.left - spec.hole.x * scale}px`,
        top: `${rect.top - spec.hole.y * scale}px`,
        width: `${spec.image.width * scale}px`,
        height: `${spec.image.height * scale}px`,
    };
});

function toggleShell() {
    shellVisible.value = !shellVisible.value;
    // 开与关都要重算：「适应窗口」下要塞进可用空间的东西在画面与整张机壳之间切换
    applyStage();
    syncStageRect();
    window.requestAnimationFrame(syncStageRect);
}

function syncStageRect() {
    const el = stageEl.value;
    if (!el) {
        stageRect.value = null;
        return;
    }
    const rect = el.getBoundingClientRect();
    const previous = stageRect.value;
    // 值没变就不写回：这个函数挂在高频事件上，无谓地赋值会让机壳反复重算
    if (
        previous &&
        previous.left === rect.left &&
        previous.top === rect.top &&
        previous.width === rect.width &&
        previous.height === rect.height
    ) {
        return;
    }
    stageRect.value = { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
}

function stopEnginePoll() {
    if (enginePollTimer) {
        window.clearInterval(enginePollTimer);
        enginePollTimer = null;
    }
}

function refreshEngineReady() {
    const rpc = frameRef.value?.contentWindow?.__ejsRpc;
    const ready = Boolean(rpc?.ready);
    if (engineReady.value !== ready) {
        engineReady.value = ready;
    }
    if (!ready) {
        return;
    }
    // 就绪时（以及之后每隔 1 秒）取一次引擎的显示宽高比：内核加载完才有值，
    // 用户在引擎设置里改了 aspect 也能跟着变；变了就重算舞台。
    const aspect = readEngineAspect(rpc);
    if (aspect && aspect !== engineAspect.value) {
        engineAspect.value = aspect;
        scheduleApplyStage();
    }
    // 就绪后按窗口选择器里选的那一列纠正一次显示比例：窗口选择器是显示比例的**唯一入口**，
    // 所以引擎自己存过的设置、或拉起 iframe 之后用户又改过比例，都在这里掰回来——机壳的洞
    // 是按选中的比例做的，比例不一致洞就会与画面错开。
    if (aspect && !aspectSynced) {
        aspectSynced = true;
        if (wideMode.value && Math.abs(aspect - aspectForMode(aspectMode.value)) > 0.02) {
            void callRpc("setDisplayMode", aspectMode.value);
        }
    }
}

function readEngineAspect(rpc) {
    try {
        const aspect = Number(rpc.videoInfo?.aspect);
        // 明显不合理的值当没读到，继续用帧缓冲比例兜底
        return Number.isFinite(aspect) && aspect > 0.5 && aspect < 4 ? aspect : null;
    } catch {
        return null;
    }
}

function startEnginePoll() {
    stopEnginePoll();
    refreshEngineReady();
    enginePollTimer = window.setInterval(refreshEngineReady, 1000);
}

function onFrameLoad() {
    engineReady.value = false;
    // iframe 每次重挂都要重新挂快捷键：焦点在引擎画布上时事件只在 iframe 内部走
    bindFrameHotkey();
    refreshEngineReady();
}

// 从可用区域算出“适应窗口”的舞台像素尺寸：按显示宽高比等比放下整个画面。
function fitInArea(areaWidth, areaHeight) {
    const aspect = stageAspect.value;
    if (!nativeSize.value || !aspect || !areaWidth || !areaHeight) {
        return null;
    }
    const spec = shellOn.value ? shell.value : null;
    if (spec) {
        // 开了机壳时，要塞进可用空间的是**整张机壳**而不是画面：机壳比例固定（就是图的比例），
        // 由它反推出中间的洞该多大，舞台取洞的尺寸。否则按画面算出来的舞台会让机壳顶着屏幕边缘溢出。
        const shellRatio = spec.image.width / spec.image.height;
        const shellHeight = Math.min(areaHeight, areaWidth / shellRatio);
        const scale = shellHeight / spec.image.height;
        return {
            width: Math.max(1, Math.floor(spec.hole.width * scale)),
            height: Math.max(1, Math.floor(spec.hole.height * scale)),
        };
    }
    const height = Math.min(areaHeight, areaWidth / aspect);
    return {
        width: Math.max(1, Math.floor(height * aspect)),
        height: Math.max(1, Math.floor(height)),
    };
}

function applyStage() {
    // 舞台尺寸/位置下一帧才生效，那时再校一次机壳的定位
    window.requestAnimationFrame(syncStageRect);
    if (!nativeSize.value) {
        stageSize.value = null;
        return;
    }
    const area = areaRef.value;
    const areaWidth = area?.clientWidth || window.innerWidth;
    const areaHeight = area?.clientHeight || window.innerHeight;
    if (windowScale.value === "fit") {
        stageSize.value = fitInArea(areaWidth, areaHeight);
        return;
    }
    const scale = Number(windowScale.value);
    if (!scale || scale <= 0) {
        stageSize.value = fitInArea(areaWidth, areaHeight);
        return;
    }
    // 倍率按帧缓冲高度算像素高度，宽度按显示宽高比推出来（否则上下留黑边）
    const height = Math.max(1, Math.round(nativeSize.value.height * scale));
    stageSize.value = {
        width: Math.max(1, Math.round(height * stageAspect.value)),
        height,
    };
}

function scheduleApplyStage() {
    if (stageRaf) {
        window.cancelAnimationFrame(stageRaf);
    }
    stageRaf = window.requestAnimationFrame(applyStage);
}

function observeArea() {
    stopAreaObserver();
    const area = areaRef.value;
    if (!area || typeof ResizeObserver === "undefined") {
        return;
    }
    resizeObserver = new ResizeObserver(() => scheduleApplyStage());
    resizeObserver.observe(area);
}

function stopAreaObserver() {
    if (resizeObserver) {
        resizeObserver.disconnect();
        resizeObserver = null;
    }
}

async function checkEngineAvailable() {
    try {
        const response = await fetch(ENGINE_LOADER, { method: "HEAD" });
        return response.ok;
    } catch {
        return false;
    }
}

/** 调 iframe 里 host 页暴露的 __ejsRpc；未就绪时返回统一错误，避免抛异常。 */
async function callRpc(method, ...args) {
    const rpc = frameRef.value?.contentWindow?.__ejsRpc;
    if (!rpc || !rpc.ready) {
        return { ok: false, message: "模拟器尚未就绪，请先进入游戏。" };
    }
    return rpc[method](...args);
}

// ---------- 云端设置同步（登录用户的键位/选项/金手指，按平台各一套） ----------

/** 带超时的等待：失败或超时都算 null，绝不拖着不让进游戏。 */
function withTimeout(promise, ms) {
    let timer = null;
    const timeout = new Promise((resolve) => {
        timer = window.setTimeout(() => resolve(null), ms);
    });
    return Promise.race([promise.catch(() => null), timeout]).finally(() => {
        if (timer) {
            window.clearTimeout(timer);
        }
    });
}

/** 切游戏/重进时清掉上一次的加载状态。 */
function resetSettingsSync() {
    engineSettingsKeyValue = "";
    settingsPrefetch = null;
}

/** 进游戏前就把云端设置拉起来（与其它加载并行），launchEngine 里再等它。 */
function prefetchCloudSettings(gameType) {
    settingsPrefetch = withTimeout(
        getEmulatorSettingsAPI(gameType),
        SETTINGS_FETCH_TIMEOUT,
    );
}

/**
 * 把云端配置写进引擎要读的那个键。必须赶在 iframe 设 src 之前完成——
 * 引擎只在启动流程里读一次设置，之后再写不会被采纳。
 */
async function applyCloudSettings() {
    const remote = settingsPrefetch ? await settingsPrefetch : null;
    if (remote?.settings) {
        writeEngineSettings(engineSettingsKeyValue, remote.settings);
    }
}

/** 「保存配置」：把当前引擎配置整块传到云端，之后进该平台的游戏会自动加载。 */
async function saveEngineSettings() {
    const category = game.value?.category;
    if (savingSettings.value || !category || !engineSettingsKeyValue) {
        return;
    }
    const raw = readEngineSettingsRaw(engineSettingsKeyValue);
    if (!raw) {
        ElMessage.warning("还没有可保存的配置：先在游戏里改点东西（键位、画面、音量等）再保存。");
        return;
    }
    savingSettings.value = true;
    try {
        await saveEmulatorSettingsAPI(category, JSON.parse(raw));
        ElMessage.success("模拟器配置已保存，下次进入该平台的游戏会自动加载");
    } catch {
        ElMessage.error("保存模拟器配置失败，请稍后重试。");
    } finally {
        savingSettings.value = false;
    }
}

function notifyManager() {
    saveManagerRef.value?.afterOperation();
}

// ---------- 截图（截宿主页里的引擎画布 → 确认框填描述 → 存入图库） ----------

/** 松开上一张截图的预览 URL 与字节（关闭确认框、卸载页面时都要收）。 */
function releaseShot() {
    if (shotPreviewUrl.value) {
        URL.revokeObjectURL(shotPreviewUrl.value);
    }
    shotPreviewUrl.value = "";
    shotSizeText.value = "";
    shotBlob = null;
}

async function onScreenshot() {
    if (shooting.value || shotDialogVisible.value) {
        return;
    }
    shooting.value = true;
    try {
        const result = await callRpc("screenshot");
        if (!result.ok) {
            ElMessage.error(result.message || "截图失败，请重试。");
            return;
        }
        // 只截下来先给确认框看，等确认了才上传（取消就整张丢掉）
        releaseShot();
        shotBlob = emuBase64ToBlob(result.base64, "image/png");
        shotPreviewUrl.value = URL.createObjectURL(shotBlob);
        shotSizeText.value = `${result.width} × ${result.height}`;
        shotDialogVisible.value = true;
    } catch {
        ElMessage.error("截图失败，请重试。");
    } finally {
        shooting.value = false;
    }
}

/** 确认框点「确认」：带着描述把这张 PNG 上传进图库。 */
async function confirmScreenshot(description) {
    if (!shotBlob || shooting.value) {
        return;
    }
    shooting.value = true;
    try {
        const form = new FormData();
        form.append("game_id", String(currentGameId.value));
        form.append("description", description || "");
        form.append("file", shotBlob, "screenshot.png");
        await uploadScreenshotAPI(form);
        ElMessage.success(`截图已存入图库（${shotSizeText.value}）`);
        shotDialogVisible.value = false;
    } catch (err) {
        // 拦截器已经弹过中文提示了，这里只兜一层没报过的
        if (!err?.reported) {
            ElMessage.error("截图上传失败，请稍后重试。");
        }
    } finally {
        shooting.value = false;
    }
}

// 快捷键 Ctrl+Shift+S（F12 是浏览器开发者工具的保留键，拦不住）：
// 焦点可能停在宿主 iframe 里的引擎画布上，所以两边的 window 都要挂一份
function onScreenshotHotkey(event) {
    if (takeHotkey(event, "s", () => !shooting.value)) {
        void onScreenshot();
    }
}

/**
 * 快捷键回车：直接载入本地存档（与存档管理里那个「载入」按钮同一条路）。
 * **没有本地存档就什么也不做**——不提示、也不拦这个键，回车照常传给引擎（引擎默认的 Start）。
 * 有存档时这一下会被读档吃掉：不再冒泡给引擎，免得同时还把 Start 按下去。
 */
function onLoadLocalHotkey(event) {
    if (takeHotkey(event, null, () => Boolean(getLocalEmuSave(currentGameId.value)))) {
        void onLoadLocal();
    }
}

/**
 * 两侧 window 共用的快捷键入口：认出来并拦下返回 true（调用方再去做事），否则返回 false 放行。
 * key 为 "s" 时认 Ctrl+Shift+S，为 null 时认回车（不带任何修饰键）。ready 是这一下对当前
 * 状态有没有意义（正在截图 / 本地根本没有存档）。不接管的场景还有：焦点在输入框里（引擎设置
 * 面板、描述框，那是在打字）、引擎尚未就绪、或弹框正开着（弹框里的回车有自己的含义）。
 */
function takeHotkey(event, key, ready) {
    const matches = key
        ? event.ctrlKey && event.shiftKey && String(event.key || "").toLowerCase() === key
        : event.key === "Enter" && !event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey;
    if (!matches || event.repeat) {
        return false;
    }
    const target = event.target;
    const tag = String(target?.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return false;
    }
    // 焦点停在标题栏按钮上时，回车是「按下这个按钮」，不跟它抢（点过按钮后焦点会留在那儿）
    if (!key && (tag === "BUTTON" || tag === "A" || tag === "SELECT")) {
        return false;
    }
    if (!engineReady.value || shotDialogVisible.value || saveManagerVisible.value || !ready()) {
        return false;
    }
    event.preventDefault();
    // 捕获阶段拦下：引擎自己也监听 keydown（在它的容器上），不拦住的话这一下会同时进游戏
    event.stopPropagation();
    return true;
}

function bindFrameHotkey() {
    let frameWindow = null;
    try {
        frameWindow = frameRef.value?.contentWindow || null;
    } catch {
        frameWindow = null;
    }
    if (!frameWindow) {
        return;
    }
    // 一律先解再挂：iframe 内导航会换掉 document，旧监听已经不在了，先解不会重复挂
    unbindFrameHotkey();
    hotkeyFrameWindow = frameWindow;
    // 用捕获阶段：引擎自己也监听 keydown（在它的容器上），要赶在它前面拿到
    frameWindow.addEventListener("keydown", onScreenshotHotkey, true);
    frameWindow.addEventListener("keydown", onLoadLocalHotkey, true);
}

function unbindFrameHotkey() {
    if (!hotkeyFrameWindow) {
        return;
    }
    try {
        hotkeyFrameWindow.removeEventListener("keydown", onScreenshotHotkey, true);
        hotkeyFrameWindow.removeEventListener("keydown", onLoadLocalHotkey, true);
    } catch {
        // 页面已经换过 iframe / 窗口已销毁，忽略即可
    }
    hotkeyFrameWindow = null;
}

// ---------- 存档管理编排（本地/云端，对应 EmuSaveManager 的双 tab） ----------

async function onCapture() {
    try {
        const result = await callRpc("capture");
        if (!result.ok) {
            ElMessage.error(result.message || "捕捉进度失败");
            return;
        }
        await writeLocalEmuSave(currentGameId.value, { base64: result.base64 });
        ElMessage.success("已把当前进度存为本地存档");
    } catch {
        ElMessage.error("捕捉进度失败");
    } finally {
        notifyManager();
    }
}

async function onLoadLocal() {
    // 回车快捷键可能被按住连发：读档期间不再受理第二下
    if (loadingLocal) {
        return;
    }
    loadingLocal = true;
    try {
        const base64 = await getEmuSaveBase64(currentGameId.value);
        if (!base64) {
            ElMessage.warning("该本地存档内容缺失。");
            return;
        }
        const result = await callRpc("load", base64);
        if (!result.ok) {
            ElMessage.error(result.message || "载入存档失败");
        } else {
            ElMessage.success("已载入该存档");
        }
    } catch {
        ElMessage.error("载入存档失败");
    } finally {
        loadingLocal = false;
        notifyManager();
    }
}

async function onUploadCloud(payload) {
    try {
        // 先捕捉当前进度覆盖本地档，保证云快照就是此刻的进度
        const result = await callRpc("capture");
        if (!result.ok) {
            ElMessage.error(result.message || "同步失败：无法捕捉当前进度");
            return;
        }
        const key = await writeLocalEmuSave(currentGameId.value, {
            base64: result.base64,
        });
        const base64 = await getEmuSaveBase64(currentGameId.value);
        if (!base64) {
            ElMessage.info("本地没有可同步的存档。");
            return;
        }
        const form = new FormData();
        form.append("game_id", String(currentGameId.value));
        form.append("remark", payload?.remark || "");
        form.append(
            "manifest",
            JSON.stringify([{ local_key: key, name: EMU_SAVE_FILENAME }]),
        );
        form.append("sols", emuBase64ToBlob(base64), EMU_SAVE_FILENAME);
        await uploadCloudSaveAPI(form);
        ElMessage.success("已同步至云端");
    } catch {
        // 错误已由请求层弹中文提示
    } finally {
        notifyManager();
    }
}

async function onSyncLocal(payload) {
    try {
        const detail = await cloudSaveDetailAPI(payload.snapshotId);
        const files = detail.files || [];
        if (!files.length) {
            ElMessage.info("该云端快照没有文件。");
            return;
        }
        // 本地只有一份档：取快照里那份直接覆盖
        const base64 = await fetchCloudSaveFileBase64(payload.snapshotId, files[0].id);
        await writeLocalEmuSave(currentGameId.value, { base64 });
        ElMessage.success("已用云端存档覆盖本地存档，可在「本地存档」里载入");
    } catch {
        // 错误已由请求层弹中文提示
    } finally {
        notifyManager();
    }
}

function onFullscreenChange(value) {
    isFullscreen.value = value;
    // 全屏会改变舞台在视口里的位置，机壳得跟着挪
    scheduleApplyStage();
    window.requestAnimationFrame(syncStageRect);
}

/**
 * 真正拉起 EmulatorJS：写入 iframe（host 页自动开始），再接管舞台布局与就绪轮询。
 * 自动开始（有手势）与「开始游戏」按钮（无手势）两条路径都汇聚到这里。
 */
async function launchEngine() {
    if (launching || !game.value || !meta.value) {
        return;
    }
    launching = true;
    try {
        needsGesture.value = false;
        const item = game.value;
        // 引擎只在启动时读一次设置：先把云端的写进 localStorage，再拉起 iframe
        engineSettingsKeyValue = engineSettingsKey(item.id, meta.value.core, item.name || "");
        await applyCloudSettings();
        // ROM 直连后端流式接口；带 updated_at 参数，重传本体后可让 EmulatorJS 缓存失效
        const params = new URLSearchParams({
            id: String(item.id),
            core: meta.value.core,
            name: item.name || "",
            v: item.updated_at || "",
            // 显示比例：宿主页据此设内核选项（只有 FC 认这个参数），与标题栏窗口选择器里选的那列一致
            ratio: aspectMode.value,
        });
        iframeSrc.value = `/emulator-host.html?${params.toString()}`;
        reportGamePlayed(item.id);
        startGamePlaytime(item.id);
        // iframe 随本轮渲染挂载后再接管舞台尺寸与引擎就绪轮询（按钮路径此时才出现舞台）
        window.setTimeout(() => {
            startEnginePoll();
            scheduleApplyStage();
            observeArea();
        }, 0);
    } finally {
        launching = false;
    }
}

function startFromGate() {
    void launchEngine();
}

async function loadGame() {
    // 换路由参数时先停表：新游戏加载失败的话旧游戏不能继续计时长
    stopGamePlaytime();
    const gameId = Number(route.params.gameId);
    if (!gameId) {
        game.value = null;
        meta.value = null;
        iframeSrc.value = "";
        saveManagerVisible.value = false;
        shotDialogVisible.value = false;
        unbindFrameHotkey();
        engineReady.value = false;
        engineAspect.value = null;
        aspectSynced = false;
        resetSettingsSync();
        stopAreaObserver();
        return;
    }
    loading.value = true;
    game.value = null;
    meta.value = null;
    iframeSrc.value = "";
    needsGesture.value = false;
    errorText.value = "";
    saveManagerVisible.value = false;
    shotDialogVisible.value = false;
    unbindFrameHotkey();
    engineReady.value = false;
    engineAspect.value = null;
    aspectSynced = false;
    resetSettingsSync();
    stopEnginePoll();
    try {
        // 历史遗留的多槽位本地档一次性清掉（幂等），此后每游戏只剩 state1
        await ensureSingleSlotModel();
        // 播放页只需要中心列表那几项字段，走中心接口而非管理详情接口
        const item = await getPlayableGameAPI(gameId);
        if (!item) {
            errorText.value = "未找到该游戏";
            return;
        }
        // 兜底：误入播放页的 Flash / H5 游戏改走各自播放页
        if (item.category === "flash") {
            router.replace(`/games/flash/${item.id}`);
            return;
        }
        if (item.category === "h5") {
            router.replace(`/games/h5/${item.id}`);
            return;
        }
        const typeMeta = gameTypeMeta(item.category);
        if (!typeMeta || typeMeta.kind !== "emulator" || !typeMeta.core) {
            errorText.value = "该类型暂不支持在浏览器内模拟";
            return;
        }
        if (!EMU_NATIVE[item.category]) {
            errorText.value = "该类型暂不支持窗口缩放";
            return;
        }
        if (!(await checkEngineAvailable())) {
            errorText.value =
                "模拟器引擎尚未就绪：请先在项目中运行 npm run fetch:emulatorjs（Docker 镜像会自动拉取）后重试";
            return;
        }
        game.value = item;
        meta.value = typeMeta;
        // 云端设置与游戏状态并行拉取；无手势时这段等待正好用来完成它
        prefetchCloudSettings(item.category);
        // 无用户手势（例如刷新页面、直接打开链接进入）时，浏览器会拦截音频自动开始
        // （AudioContext: not allowed to start）。此时不自动启动引擎，先展示居中的
        // 「开始游戏」，等一次真实点击（用户手势）后再启动，声音才能正常开启。
        if (!hasUserGesture()) {
            needsGesture.value = true;
            return;
        }
        await launchEngine();
    } catch {
        errorText.value = "游戏信息加载失败，请稍后重试";
    } finally {
        loading.value = false;
    }
}

watch(windowMode, (value) => {
    try {
        localStorage.setItem(WINDOW_STORAGE_KEY, value);
    } catch {
        // 隐私模式等写失败场景忽略即可
    }
    scheduleApplyStage();
});

// 切显示比例：立刻按新比例摆舞台（不等下一秒的轮询），并让宿主页把内核选项改掉——
// 引擎只在启动时读一次设置，所以运行中改只能走这条路；下次进游戏由 iframe 的 ratio 参数兜住。
watch(aspectMode, (mode) => {
    engineAspect.value = aspectForMode(mode);
    scheduleApplyStage();
    if (engineReady.value) {
        void callRpc("setDisplayMode", mode);
    }
});

watch(shellVisible, (value) => {
    try {
        localStorage.setItem(SHELL_STORAGE_KEY, value ? "1" : "0");
    } catch {
        // 隐私模式等写失败场景忽略即可
    }
});

// 关掉截图确认框（确认或取消）就把那张预览 URL 收掉，不留内存里的孤儿图
watch(shotDialogVisible, (visible) => {
    if (!visible) {
        releaseShot();
    }
});

onMounted(() => {
    // 机壳用视口坐标定位：窗口缩放、页面/游戏区滚动都要重新同步。
    // 滚动用捕获阶段监听：滚动发生在内层容器（.game-shell__body 等）上，不冒泡到 window
    window.addEventListener("resize", syncStageRect);
    window.addEventListener("scroll", syncStageRect, true);
    // 焦点在父页面（点标题栏按钮/弹框）时按快捷键也要能截图 / 载入存档
    window.addEventListener("keydown", onScreenshotHotkey);
    window.addEventListener("keydown", onLoadLocalHotkey);
    loadGame();
});
watch(() => route.params.gameId, loadGame);
onBeforeUnmount(() => {
    window.removeEventListener("resize", syncStageRect);
    window.removeEventListener("scroll", syncStageRect, true);
    window.removeEventListener("keydown", onScreenshotHotkey);
    window.removeEventListener("keydown", onLoadLocalHotkey);
    unbindFrameHotkey();
    releaseShot();
    stopGamePlaytime();
    stopEnginePoll();
    stopAreaObserver();
    if (stageRaf) {
        window.cancelAnimationFrame(stageRaf);
    }
});
</script>

<style scoped>
/* 舞台区：可用空间内等比缩放 + 居中；所选窗口超过可用空间时可滚动。
   min-height 保证非全屏也有一块足够大的画面区，不会塌成又宽又扁的横条。 */
.emulator-player {
    width: 100%;
    min-height: 60vh;
    display: flex;
    overflow: auto;
}

.emulator-player--fullscreen {
    height: 100%;
    min-height: 0;
}

.emulator-player__stage {
    flex: 0 0 auto;
    margin: auto;
}

/* 机壳：一张带透明洞的 PNG 盖在 iframe 上，尺寸/位置由 shellStyle 算，
   洞外的部分落在舞台之外，不遮引擎 UI；pointer-events: none 保证照常能玩。
   定位必须用 fixed 而不是 absolute：机壳比舞台大得多（宽是画面的两倍），absolute 会被
   .game-shell__body 的 overflow: auto 裁掉、还会顶出滚动条；fixed 不参与任何滚动容器的
   溢出计算，也不会被祖先裁剪——放不进浏览器窗口的情况在 JS 里已经直接不画了。
   z-index 压在标题栏(20)与侧栏(60)之下，盖着机壳也点得到按钮 */
.emulator-player__shell {
    position: fixed;
    z-index: 5;
    pointer-events: none;
    user-select: none;
    -webkit-user-drag: none;
}

.emulator-player__empty {
    margin: auto;
}

.emulator-player__frame {
    display: block;
    width: 100%;
    height: 100%;
    border: none;
    background: #000;
}

.emulator-player__hint {
    font-size: 13px;
    color: #94a3b8;
    white-space: nowrap;
}

/* 标题栏按钮（保存配置 / 存档管理），与 GameShell 自带按钮同款深色样式 */
.emulator-player__action {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 8px 14px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 10px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
    white-space: nowrap;
    flex-shrink: 0;
}

.emulator-player__action:hover:not(:disabled) {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}

.emulator-player__action:disabled {
    opacity: 0.6;
    cursor: default;
}

/* 「显示游戏机」开着时的状态：按钮点亮，一眼能看出当前盖着机壳 */
.emulator-player__action--on {
    background: rgba(37, 99, 235, 0.85);
    border-color: rgba(96, 165, 250, 0.6);
    color: #f8fafc;
}

.emulator-player__action--on:hover:not(:disabled) {
    background: rgba(37, 99, 235, 0.95);
    border-color: rgba(147, 197, 253, 0.8);
}
</style>
