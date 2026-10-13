<template>
    <game-shell
        ref="shellRef"
        :title="gameTitle"
        @fullscreen-change="onFullscreenChange"
        @cursor-idle-change="onCursorIdleChange"
    >
        <template #extra>
            <span class="emulator-player__hint">{{ platformHint }}</span>
        </template>
        <template #actions>
            <!-- 持续加速：按一次一直加速、再按恢复。开关的就是引擎自己的「Fast Forward」设置项，
                 所以与设置菜单里那一项同步、也会随「保存配置」进账号；关着时用户自己绑的
                 快进快捷键行为不变 -->
            <app-button
                v-if="game"
                class="emulator-player__action"
                variant="secondary"
                tone="dark"
                size="lg"
                :pressed="fastForwardOn"
                :disabled="!engineReady"
                @click="toggleFastForward"
            >
                加速模式
            </app-button>
            <!-- 截当前画面（Ctrl+Shift+S 同效）：先弹确认框预览+填描述，确认后存入图库 -->
            <app-button
                v-if="game"
                class="emulator-player__action"
                variant="secondary"
                tone="dark"
                size="lg"
                :disabled="!engineReady || shooting"
                @click="onScreenshot"
            >
                {{ shooting ? "截图中…" : "截图" }}
            </app-button>
            <!-- 把当前键位/画面/音量等模拟器配置整块存到账号 -->
            <app-button
                v-if="game"
                class="emulator-player__action"
                variant="secondary"
                tone="dark"
                size="lg"
                :disabled="savingSettings"
                @click="saveEngineSettings"
            >
                {{ savingSettings ? "保存中…" : "保存配置" }}
            </app-button>
            <!-- 第一列（像素完美）恒用机种固有的帧缓冲；4:3 那一列自带另一套（见 WIDE_MODE） -->
            <emu-window-select
                v-if="baseNativeSize"
                v-model="windowMode"
                :native-size="baseNativeSize"
                :aspect="stageAspect"
                :wide="wideMode"
                :modes="ndsModeColumns"
                :mode-scales="ndsModeScales"
                :active-mode="ndsScreenMode"
                @pick-mode="onPickNdsWindowMode"
            />
            <!-- 复古滤镜（只有配了滤镜清单的机种显示）：内核选项 + 引擎内置着色器，
                 清单见 constants/emuFilters.js，运行中切换走宿主页的 setFilter -->
            <emu-filter-select
                v-if="filters"
                v-model="filterId"
                :filters="filters"
            />
            <!-- 有洞对齐图的平台（GBA、FC、GBC、NDS）：把机壳图盖在画面上，洞正好露出游戏画面 -->
            <app-button
                v-if="supportsShell"
                class="emulator-player__action"
                variant="secondary"
                tone="dark"
                size="lg"
                :pressed="shellOn"
                @click="toggleShell"
            >
                显示机壳
            </app-button>
            <app-button
                v-if="game"
                class="emulator-player__action"
                variant="secondary"
                tone="dark"
                size="lg"
                @click="saveManagerVisible = true"
            >
                存档管理
            </app-button>
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
            <div
                v-if="iframeSrc"
                ref="stageEl"
                class="emulator-player__stage"
                :class="{ 'emulator-player__stage--nds': isNds }"
                :style="stageStyle"
            >
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
                     所以它不会挡住引擎自己的任何 UI；pointer-events: none 保证仍然能玩。
                     NDS 例外：iframe 被抬到机壳之上、只把画布的两块屏幕遮出来（见样式与
                     emulator-host.html），这样引擎的设置弹框跨过铰链时显示在机壳上面。
                     每块机壳用外层 div（overflow:hidden）+ 内层 img 裁出 part 的 crop 区域。 -->
                <div
                    v-for="part in shellLayers"
                    :key="part.key"
                    class="emulator-player__shell-part"
                    :style="part.layerStyle"
                >
                    <img
                        class="emulator-player__shell-image"
                        :style="part.imageStyle"
                        :src="part.src"
                        alt=""
                        draggable="false"
                    />
                </div>
            </div>
            <div v-else-if="!loading" class="emulator-player__empty">
                <app-empty :description="errorText || '未找到该游戏'" />
            </div>
        </div>

        <save-manager
            ref="saveManagerRef"
            v-model="saveManagerVisible"
            platform="emulator"
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
            :preview-width="shotWidth"
            :preview-height="shotHeight"
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
import { EMU_NATIVE, NDS_NATIVE, NDS_SCREEN_MODES } from "@/constants/emulatorScreens";
import { gameTypeMeta } from "@/constants/gameTypes";
import {
    EMU_FILTER_NONE,
    EMU_FILTER_SETTING_KEYS,
    emuFilterResets,
    emuFiltersFor,
    filterForShader,
} from "@/constants/emuFilters";
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
    stripNdsDisplayOptions,
    writeEngineSettings,
} from "@/utils/emulatorSettings";
import GameShell from "@components/games/GameShell.vue";
import EmuFilterSelect from "@components/games/EmuFilterSelect.vue";
import SaveManager from "@components/games/SaveManager.vue";
import EmuWindowSelect from "@components/games/EmuWindowSelect.vue";
import ScreenshotConfirmDialog from "@components/games/ScreenshotConfirmDialog.vue";
import StartGate from "@components/games/StartGate.vue";
import { hasUserGesture } from "@/utils/userActivation";
import { reportGamePlayed } from "@/utils/recentGames";
import { startGamePlaytime, stopGamePlaytime } from "@/utils/gamePlaytime";
// 机壳图用 import 取 URL（带内容哈希），几何见下面 SHELLS 表的说明
import gbaShellUrl from "@/assets/shells/gba-shell.png";
import gbcShellUrl from "@/assets/shells/gbc-shell.png";
import nesShellUrl from "@/assets/shells/nes-shell.png";
import nesShell43Url from "@/assets/shells/nes-shell-43.png";
import ndsShellUrl from "@/assets/shells/nds-shell.png";
import ndsSideShellUrl from "@/assets/shells/nds-side-shell.png";

const ENGINE_LOADER = "/emulatorjs/data/loader.js";

// 机壳图（frontend/src/assets/shells/ 下、**用 import 取 URL**，见下面的 import 区）：
// 一张画好的机器外形图，中间是**全透明的屏幕洞**。把图按「洞（多洞取外接矩形）宽 = 画面宽」
// 放大后盖在画面上，就是真机在玩。**必须 import、不要写回 "/xxx-shell.png"**：import 出来的 URL 带内容哈希，
// 重跑机壳图后缓存自动失效；放 public/ 下文件名固定，而 nginx 的 location /（与 Windows 包的
// static_site.py）对这些文件不带 Cache-Control，浏览器会一直用启发式缓存里的旧图。
// 每项里的数字是这张图与洞的像素几何，换图必须同步改（洞的位置变了就会错位）。
// **洞统一用 `holes` 数组**：单屏机种只有一个元素，NDS 有两个（上下屏，两洞之间留出
// 屏幕间隙）。机壳只按所有洞的**外接矩形**对齐舞台，洞内部怎么排它不关心。
// 洞的比例（NDS 是外接矩形的比例）还必须与画面比例一致，否则洞与画面会错开：
//   GBA 洞 1920×1280 = 3:2，正是 GBA 原生 240×160；
//   GBC 洞 1285×1156.5 = 10:9，正是 GB/GBC 原生 160×144（gambatte 上报的比例就是 160/144）；
//     原素材洞是 1285×1157、左右留白差 17px，入项目前从左边裁掉 17px 让屏幕左右对称，
//     剩下的半个像素差（10/9 的理论洞高 1156.5）按小数声明即可，不必真去拉伸图画；
//   NDS 是真实机壳 1080×1920：两个 840×630 的透明洞（x=120，上屏 y=177、下屏 y=984），
//     中间 177px 铰链带；外接矩形 840×1437 = 256:438，对应双屏帧缓冲（192 + 54 gap + 192）。
//     840×630 正好 4:3，所以 256×192 能精确铺满每个洞；54 是按外接矩形比例反推的
//     melonds_screen_gap（256×1437/840 − 384 ≈ 53.94，取 54），最大误差约 0.06px。
//     原素材每块屏幕左右各有 8px 被补成了机身色（洞从 856 宽收到 840），洞才变成 4:3。
//     素材已换成真实机壳，换图时同步改这里与 EMU_NATIVE.nds；
//   FC 的电视机壳有两套，正好对应窗口选择器里的两列显示比例（见 WIDE_MODE）：
//   `pp`（像素完美 8:7）那套是原素材把**屏幕那段纵向拉长 7/6 倍**（原素材洞 1084×813 = 4:3，
//   拉长后 1084×948.5 = 8:7）得到的，下面 121 行的控制条（扬声器 / 按键）保持等比不变，
//   最后裁掉四周透明留白（只顶部有 10 行是空的）；`wide`（4:3）那套就是原素材本身
//   （4:3 的洞），只裁掉顶部 9 行留白。切比例时机壳跟着换成对应的那套，洞才与画面一致。
const SHELLS = {
    gba: {
        pp: {
            url: gbaShellUrl,
            image: { width: 3840, height: 2160 },
            holes: [{ x: 960, y: 440, width: 1920, height: 1280 }],
        },
    },
    gb: {
        pp: {
            url: gbcShellUrl,
            image: { width: 2131, height: 1996 },
            // 带小数：10/9 × 1285 = 1156.5，比画出来的洞矮半个像素（见上面的说明）
            holes: [{ x: 423, y: 338, width: 1285, height: 1156.5 }],
        },
    },
    // NDS 有三种屏幕布局（- / = 循环，见 NDS_NATIVE / ndsScreenMode），机壳跟着换：
    //   dual = 上下两屏 + 中间铰链带，整图一块（nds-shell.png）；
    //   top  = 只显示上屏：取上半身到距图底 975px 处（y 0..945，含整条铰链带），
    //          比屏幕洞底边多留 138px 机身，上屏下沿不会和机壳底边齐平；
    //   side = 左右布局用一张独立素材 nds-side-shell.png（1274×700，整机正视图，
    //          两块 460×345 的 4:3 透明洞，洞间距 92px），一块整图直出。
    //          注意 melonDS 的 Left/Right 不吃 gap（帧缓冲固定 512×192、两屏紧贴），
    //          51px 的屏幕间隙由宿主页拆屏合成后上报（见 emulator-host.html 的
    //          setupNdsSideScreen），播放页拿到的对外几何才是 563×192。
    // 每块都用 parts 的 crop/offset 描述：
    //   crop  = 原图里要显示的那块矩形；offset = 这块的左上角在合成坐标系里的位置。
    // 合成坐标系（canvas）只用于「适应窗口」时把整张机壳塞进可用区域；holes 写在合成坐标里。
    nds: {
        modes: {
            dual: {
                url: ndsShellUrl,
                image: { width: 1080, height: 1920 },
                canvas: { width: 1080, height: 1920 },
                // 上洞底边 807、下洞顶边 984：中间 177px 正好是铰链带；840×630 = 精确 4:3
                holes: [
                    { x: 120, y: 177, width: 840, height: 630 },
                    { x: 120, y: 984, width: 840, height: 630 },
                ],
                parts: [
                    { crop: { x: 0, y: 0, width: 1080, height: 1920 }, offset: { x: 0, y: 0 } },
                ],
            },
            top: {
                url: ndsShellUrl,
                image: { width: 1080, height: 1920 },
                canvas: { width: 1080, height: 945 },
                holes: [{ x: 120, y: 177, width: 840, height: 630 }],
                parts: [
                    { crop: { x: 0, y: 0, width: 1080, height: 945 }, offset: { x: 0, y: 0 } },
                ],
            },
            side: {
                url: ndsSideShellUrl,
                image: { width: 1274, height: 700 },
                canvas: { width: 1274, height: 700 },
                // 两洞各 460×345（精确 4:3），洞间距 92px：92×256/460 ≈ 51.2，
                // 宿主页据此把内核的 512×192 拆成两屏并插入 51px 间隙，
                // 对外按 563×192 上报（见 NDS_NATIVE.side 与 emulator-host.html）
                holes: [
                    { x: 131, y: 100, width: 460, height: 345 },
                    { x: 683, y: 100, width: 460, height: 345 },
                ],
                parts: [
                    { crop: { x: 0, y: 0, width: 1274, height: 700 }, offset: { x: 0, y: 0 } },
                ],
            },
        },
    },
    nes: {
        // 像素完美（8:7）：素材是把原图屏幕那段纵向拉长 7/6 得到的
        pp: {
            url: nesShellUrl,
            image: { width: 1326, height: 1237 },
            // 带小数：这两个值来自原素材的洞坐标 × 7/6（纵向拉伸倍率）再减去裁掉的那 10 行
            holes: [{ x: 121, y: 146.3333, width: 1084, height: 948.5 }],
        },
        // 4:3：用**未拉伸的原素材**，洞本来就是 4:3，只裁掉了顶部 9 行透明留白
        wide: {
            url: nesShell43Url,
            image: { width: 1326, height: 1077 },
            holes: [{ x: 121, y: 125, width: 1084, height: 813 }],
        },
    },
};

/**
 * 所有洞的外接矩形。单洞条目的结果就等于那个洞本身，所以 GBA/GBC/FC 的行为逐像素不变；
 * NDS 用它把「两屏 + 中间的铰链带」当成一整块对齐舞台。
 */
function shellBounds(spec) {
    const left = Math.min(...spec.holes.map((hole) => hole.x));
    const top = Math.min(...spec.holes.map((hole) => hole.y));
    const right = Math.max(...spec.holes.map((hole) => hole.x + hole.width));
    const bottom = Math.max(...spec.holes.map((hole) => hole.y + hole.height));
    return { x: left, y: top, width: right - left, height: bottom - top };
}

const WINDOW_STORAGE_KEY = "games.emu.window";
// 机壳开关也是本地偏好（纯观赏层，不随账号走），下次进有对应机壳的游戏沿用上次的选择
const SHELL_STORAGE_KEY = "games.emu.shell";
// NDS 屏幕布局（dual / top / side）同样是本地偏好，- / = 切换后记住
const NDS_SCREEN_STORAGE_KEY = "games.emu.nds.screen";
// NDS 三种布局各自的窗口倍率（互相独立）：{ dual: "fit"|"1.5"|…, top: …, side: … }
const NDS_WINDOW_STORAGE_KEY = "games.emu.nds.window";
// 滤镜也按游戏类型各记一条（GBA 想用液晶、FC 想用 CRT），整张表存一个 JSON 里
const FILTER_STORAGE_KEY = "games.emu.filter";
// 引擎自带菜单里试出来的着色器：自动进表的那几条（同样按游戏类型各记一份）
const FILTER_CUSTOM_STORAGE_KEY = "games.emu.filter.custom";

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
// 也正是 nes-shell-43.png（原素材，屏幕洞本来就 4:3）对应的画面。
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

function loadStoredNdsScreen() {
    try {
        const value = localStorage.getItem(NDS_SCREEN_STORAGE_KEY);
        return NDS_SCREEN_MODES.includes(value) ? value : "dual";
    } catch {
        return "dual";
    }
}

function persistNdsScreenMode(mode) {
    try {
        localStorage.setItem(NDS_SCREEN_STORAGE_KEY, mode);
    } catch {
        // 隐私模式等写失败场景忽略即可
    }
}

/** 读该游戏类型记住的滤镜 id；没记过、内容坏了都返回「无」，越界取值由 emuFilterFor 回落。 */
function loadStoredFilter(gameType) {
    if (!gameType) {
        return "none";
    }
    try {
        const raw = localStorage.getItem(FILTER_STORAGE_KEY);
        const map = raw ? JSON.parse(raw) : null;
        return typeof map?.[gameType] === "string" ? map[gameType] : "none";
    } catch {
        return "none";
    }
}

function saveStoredFilter(gameType, id) {
    if (!gameType) {
        return;
    }
    try {
        const raw = localStorage.getItem(FILTER_STORAGE_KEY);
        const map = raw ? JSON.parse(raw) : null;
        const next = map && typeof map === "object" && !Array.isArray(map) ? map : {};
        next[gameType] = id;
        localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(next));
    } catch {
        // 隐私模式等写失败场景忽略即可
    }
}

/** 三种布局各自的倍率；缺省/非法值一律回落到「适应窗口」。 */
function loadStoredNdsWindowScales() {
    const defaults = { dual: "fit", top: "fit", side: "fit" };
    try {
        const raw = JSON.parse(localStorage.getItem(NDS_WINDOW_STORAGE_KEY) || "{}");
        for (const mode of NDS_SCREEN_MODES) {
            const value = raw?.[mode];
            if (value === "fit" || (value !== undefined && Number(value) > 0)) {
                defaults[mode] = String(value);
            }
        }
    } catch {
        // 坏 JSON / 无痕模式：用默认值
    }
    return defaults;
}

function persistNdsWindowScales(value) {
    try {
        localStorage.setItem(NDS_WINDOW_STORAGE_KEY, JSON.stringify(value));
    } catch {
        // 隐私模式等写失败场景忽略即可
    }
}

/** 读该类型自动进表的滤镜（引擎自带菜单里试出来的着色器）；结构不对的条目丢掉。 */
function loadStoredCustomFilters(gameType) {
    if (!gameType) {
        return [];
    }
    try {
        const raw = localStorage.getItem(FILTER_CUSTOM_STORAGE_KEY);
        const map = raw ? JSON.parse(raw) : null;
        const stored = map ? map[gameType] : null;
        if (!Array.isArray(stored)) {
            return [];
        }
        return stored.filter(
            (item) =>
                item &&
                typeof item.id === "string" &&
                typeof item.label === "string" &&
                typeof item.shader === "string" &&
                (item.options === null || typeof item.options === "object"),
        );
    } catch {
        return [];
    }
}

function saveStoredCustomFilters(gameType, list) {
    if (!gameType) {
        return;
    }
    try {
        const raw = localStorage.getItem(FILTER_CUSTOM_STORAGE_KEY);
        const map = raw ? JSON.parse(raw) : null;
        const next = map && typeof map === "object" && !Array.isArray(map) ? map : {};
        next[gameType] = list;
        localStorage.setItem(FILTER_CUSTOM_STORAGE_KEY, JSON.stringify(next));
    } catch {
        // 隐私模式等写失败场景忽略即可
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
const shellRef = ref(null);
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
// 这张截图的真实像素尺寸：确认框按它决定预览框是横版还是竖版（NDS 双屏）
const shotWidth = ref(0);
const shotHeight = ref(0);
const isFullscreen = ref(false);
// 无用户手势（刷新/直链进入）时先展示「开始游戏」，由一次点击后再启动引擎
const needsGesture = ref(false);
const windowMode = ref(loadStoredWindow());
const stageSize = ref(null);
// 是否盖上机壳：本地记住的偏好，进游戏时按它恢复
const shellVisible = ref(loadStoredShell());
// NDS 屏幕布局（dual / top / side）：- / = 循环切换，本地记住；
// switchingNdsMode 挡住切换过程中重复按键
const ndsScreenMode = ref(loadStoredNdsScreen());
const switchingNdsMode = ref(false);
// NDS 三种布局各自的窗口倍率（互相独立，见窗口选择器的三列矩阵）
const ndsModeScales = ref(loadStoredNdsWindowScales());
// 是否处于持续加速（引擎自己的 Fast Forward 设置项）。真相在引擎里，这里只是它的镜像：
// 进游戏时按引擎读到的值点亮，用户在引擎设置菜单里改过也会在下一秒跟上
const fastForwardOn = ref(false);
// 当前滤镜 id：进游戏时按该类型的记忆恢复（见 loadGame），取不到就是「无」
const filterId = ref("none");
// 引擎自带菜单里试出来、自动进表的滤镜（按游戏类型，见 loadStoredCustomFilters）
const customFilters = ref([]);
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
// 「捕捉并同步至云端」整段在跑：挡掉连发，也保证一次只发一份快照
let syncingCloud = false;
let stageRaf = null;
// 就绪后只按选中比例纠正内核一次（见 refreshEngineReady）
let aspectSynced = false;
// 截下来的那张图（等确认框点「确认」时才上传）；previewUrl 是它的 objectURL
let shotBlob = null;
// 宿主 iframe 的 window：快捷键要挂在它上面，见 bindFrameHotkey
let hotkeyFrameWindow = null;
// 宿主 iframe 的 window：指针活动监听挂在它上面，见 bindFramePointerActivity
let pointerFrameWindow = null;
// GameShell 最近一次通知的光标闲置状态；iframe 重载后要按它重新挂类
let frameCursorHidden = false;

const gameTitle = computed(() => game.value?.name || "模拟器游戏");
const currentGameId = computed(() => (game.value?.id ? Number(game.value.id) : 0));
const isNds = computed(() => game.value?.category === "nds");
// 像素完美那一列的帧缓冲基准（机种固有；NDS 按当前屏幕布局取）
const baseNativeSize = computed(() => {
    if (!game.value) {
        return null;
    }
    if (game.value.category === "nds") {
        return NDS_NATIVE[ndsScreenMode.value] || NDS_NATIVE.dual;
    }
    return EMU_NATIVE[game.value.category] || null;
});
const platformHint = computed(() =>
    meta.value?.label ? `（${meta.value.label}）` : "",
);
// 窗口选择器的 NDS 三列（列 = 屏幕布局，每列独立倍率），顺序与 NDS_SCREEN_MODES 一致。
// 非 NDS 返回 null，选择器维持原来的「倍率 × 显示比例」矩阵。
const ndsModeColumns = computed(() => {
    if (!isNds.value) {
        return null;
    }
    return [
        { id: "dual", label: "上下", native: NDS_NATIVE.dual },
        { id: "top", label: "单屏", native: NDS_NATIVE.top },
        { id: "side", label: "左右", native: NDS_NATIVE.side },
    ];
});
// 窗口取值拆成「倍率」与「显示比例」两部分（见 parseWindowValue）。
// NDS 例外：倍率按**当前屏幕布局**从三份独立设置里取（窗口选择器的三列矩阵），
// 显示比例仍只有 pp（NDS 没有 4:3 那一列）。
const windowScale = computed(() => {
    if (isNds.value) {
        const value = ndsModeScales.value[ndsScreenMode.value];
        return value && value !== "" ? String(value) : "fit";
    }
    return parseWindowValue(windowMode.value).scale;
});
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
// 左右布局的机壳上下不对称：洞在上方留 100px，下方还留 255px 的按键区（1274×700 素材）。
// 舞台默认在可用区域垂直居中，整张机壳的视觉中心就会偏下 (255−100)/2 个图像 px；
// 开着机壳时把舞台相对上移同样的比例，让整张机壳在可用区域里垂直居中。
const NDS_SIDE_SHIFT_RATIO = (255 - 100) / 2 / 345;

// 舞台尺寸：fit=按可用空间等比缩放；否则按倍率放大原生分辨率（超出部分由容器滚动）
const stageStyle = computed(() => {
    if (!stageSize.value) {
        return null;
    }
    const style = { width: `${stageSize.value.width}px`, height: `${stageSize.value.height}px` };
    // 注意用 position: relative 而不是 transform：transform 会把 fixed 定位的机壳
    // 变成相对舞台定位，整张机壳会错位。relative 只挪视觉位置，机壳读 getBoundingClientRect
    // 仍能跟着走。
    if (isNds.value && ndsScreenMode.value === "side" && shellOn.value) {
        style.position = "relative";
        style.top = `${-Math.round(stageSize.value.height * NDS_SIDE_SHIFT_RATIO)}px`;
    }
    return style;
});

// 机壳只有画过洞对齐图的平台有（其余类型没有这张图）。
// 每套比例一张素材（FC 是 pp / wide 两套），按当前显示比例取——洞的比例必须与画面一致，
// 所以切比例时机壳也跟着换图，否则洞会与画面错开。
// NDS 不再按比例分，而是按屏幕布局（dual / top / side）分三套，见 SHELLS.nds.modes。
const shell = computed(() => {
    const entry = SHELLS[game.value?.category];
    if (!entry) {
        return null;
    }
    if (game.value.category === "nds") {
        return entry.modes[ndsScreenMode.value] || entry.modes.dual;
    }
    return entry[aspectMode.value] || entry[ASPECT_PP] || null;
});
const supportsShell = computed(() => Boolean(shell.value));

// 该机种的滤镜清单（没配就是 null → 标题栏不出现滤镜入口）：内置表 + 自动进表的那几条
const filters = computed(() => {
    const builtin = emuFiltersFor(game.value?.category);
    if (!builtin) {
        return null;
    }
    const extra = customFilters.value.filter((item) => !builtin.some((base) => base.id === item.id));
    return [...builtin, ...extra];
});
// 当前生效的滤镜：id 找不到（换了清单、手改过 localStorage）就回落到「无」，
// 所以运行中切换与设置块覆写都可以放心用它的 options/shader
const filter = computed(() => {
    const list = filters.value || [];
    return list.find((item) => item.id === filterId.value) || list[0] || EMU_FILTER_NONE;
});

// 真正生效的机壳状态。偏好是全局记的，所以换到没有机壳的游戏上即使上次开着也不盖
const shellOn = computed(() => supportsShell.value && shellVisible.value);

/**
 * 机壳的每一块（parts）：**外接矩形（所有 holes 的并集）宽 = 画面宽**定出比例，
 * 整张图按同一比例放大，再按每块的 crop/offset 摆放；外层 overflow:hidden 把 crop
 * 之外的部分裁掉。
 *
 * 没有 parts 的机种（GBA/GBC/FC）就是「整图一块」，布局与旧版单个 img 完全一致；
 * NDS 每种布局也都是一块整图（side 用独立的双屏素材，见上）。
 *
 * 外接矩形的比例与舞台一致（GBA 3:2、FC 8:7、NDS 256:438 / 4:3 / 563:192），所以只要
 * 舞台按引擎上报的 aspect 摆放，洞的上下左右会同时严丝合缝地对齐画面；画面一小（换倍率、
 * 缩窗口、全屏）这里就跟着重算，所以任何画面尺寸都适配。
 *
 * 定位必须用 position: fixed（坐标是视口坐标）：机壳比舞台大得多，absolute 会被
 * .game-shell__body 的 overflow: auto 裁掉并顶出滚动条。
 */
const shellLayers = computed(() => {
    const spec = shell.value;
    const stage = stageSize.value;
    const rect = stageRect.value;
    if (!shellOn.value || !spec || !stage?.width || !rect) {
        return [];
    }
    const bounds = shellBounds(spec);
    const scale = stage.width / bounds.width;
    const parts = spec.parts || [
        {
            crop: { x: 0, y: 0, width: spec.image.width, height: spec.image.height },
            offset: { x: 0, y: 0 },
        },
    ];
    return parts.map((part, index) => {
        const { crop, offset } = part;
        return {
            key: index,
            src: spec.url,
            layerStyle: {
                // 外层只按 offset 摆在合成坐标里；crop 由图内偏移（imageStyle）裁出，
                // 这里不能再减一次 crop，否则有 crop 的部件会整体偏移 crop×scale。
                left: `${rect.left + (offset.x - bounds.x) * scale}px`,
                top: `${rect.top + (offset.y - bounds.y) * scale}px`,
                width: `${crop.width * scale}px`,
                height: `${crop.height * scale}px`,
            },
            imageStyle: {
                left: `${-crop.x * scale}px`,
                top: `${-crop.y * scale}px`,
                width: `${spec.image.width * scale}px`,
                height: `${spec.image.height * scale}px`,
            },
        };
    });
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
    // 引擎自带菜单里换了着色器就跟着选中（试衣间 → 选择器），见 syncFilterFromEngine
    syncFilterFromEngine();
    // 就绪时（以及之后每隔 1 秒）取一次引擎的显示宽高比：内核加载完才有值，
    // 用户在引擎设置里改了 aspect 也能跟着变；变了就重算舞台。
    // NDS 切换屏幕布局的过程中跳过：这时引擎可能还没换完，先按新模式的比例摆着，
    // 由 setNdsLayout 返回的真实几何收尾（否则会把旧比例又写回来）。
    const aspect = switchingNdsMode.value ? null : readEngineAspect(rpc);
    if (aspect && aspect !== engineAspect.value) {
        engineAspect.value = aspect;
        scheduleApplyStage();
    }
    // 加速状态同理以引擎为准：设置文件里本来就开着（上次点过「保存配置」同步过来的），
    // 或者用户刚在引擎设置菜单里改过，按钮都在这里跟上
    const fastForward = readEngineFastForward(rpc);
    if (fastForward !== null && fastForward !== fastForwardOn.value) {
        fastForwardOn.value = fastForward;
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

/** 读引擎的加速状态；未开始游戏时宿主页返回 null，就当没读到（保留当前显示）。 */
function readEngineFastForward(rpc) {
    try {
        return typeof rpc.fastForward === "boolean" ? rpc.fastForward : null;
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
    // 新引擎起来之前加速状态无从谈起，先灭灯，就绪后由轮询按引擎实际值点亮
    fastForwardOn.value = false;
    // iframe 每次重挂都要重新挂快捷键：焦点在引擎画布上时事件只在 iframe 内部走
    bindFrameHotkey();
    // 指针活动（全屏闲置计时）与光标类同理，新文档要重新挂
    bindFramePointerActivity();
    applyFrameCursorHidden();
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
        // 由它反推出洞的外接矩形该多大，舞台取外接矩形的尺寸。否则按画面算出来的舞台会让
        // 机壳顶着屏幕边缘溢出。NDS 的两个洞 + 铰链带取外接矩形；top/side 模式用合成后的
        // canvas（NDS top 只有上半身、side 是两半左右拼起来，整图尺寸不再是可见范围）。
        const canvas = spec.canvas || spec.image;
        const shellRatio = canvas.width / canvas.height;
        const shellHeight = Math.min(areaHeight, areaWidth / shellRatio);
        const scale = shellHeight / canvas.height;
        const bounds = shellBounds(spec);
        return {
            width: Math.max(1, Math.floor(bounds.width * scale)),
            height: Math.max(1, Math.floor(bounds.height * scale)),
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
async function applyCloudSettings(gameType) {
    const remote = settingsPrefetch ? await settingsPrefetch : null;
    if (remote?.settings) {
        // NDS 的双屏布局固定，云端旧值不能盖掉宿主页的默认值
        const settings = gameType === "nds"
            ? stripNdsDisplayOptions(remote.settings)
            : remote.settings;
        writeEngineSettings(engineSettingsKeyValue, settings);
    }
}

/**
 * NDS：本机 localStorage 里已存的设置块同样剔除双屏布局选项后写回。
 * 云端没有配置时引擎会直接读这份本机值，不剔除就带回旧布局。
 */
function sanitizeLocalNdsOptions(gameType) {
    if (gameType !== "nds" || !engineSettingsKeyValue) {
        return;
    }
    const raw = readEngineSettingsRaw(engineSettingsKeyValue);
    if (!raw) {
        return;
    }
    try {
        writeEngineSettings(engineSettingsKeyValue, stripNdsDisplayOptions(JSON.parse(raw)));
    } catch {
        // 坏 JSON 交给引擎自己判定，不在这里覆盖
    }
}

/** 该类型记住的滤镜：合并清单里找得到就用它，否则「无」（进游戏时恢复选择用）。 */
function filterForStored() {
    const list = filters.value || [];
    const stored = loadStoredFilter(game.value?.category);
    return list.find((item) => item.id === stored) || EMU_FILTER_NONE;
}

/** 当前滤镜交给宿主页的参数：内核选项串（`k=v,k=v`）与着色器键名。 */
function filterQuery() {
    const current = filter.value;
    return {
        copts: Object.entries(current.options || {})
            .map(([name, value]) => `${name}=${value}`)
            .join(","),
        shader: current.shader || "",
    };
}

/**
 * 把当前滤镜写进引擎设置块。
 *
 * 只在设置块**已经存在**时改写：没玩过就没必要凭一个滤镜给这个游戏留一份半成品配置。
 * 先按滤镜清单里出现过的所有键清一遍——上次选的滤镜留下的值不清就会跟着这一局
 * （比如上次选「真机液晶」留下的色彩校正，这次换成 CRT 还照旧生效）；
 * 清完再写入本次的键值。引擎启动时会重放这块设置，所以引擎自带菜单里显示的也是我们这份选择。
 */
function applyFilterToEngineSettings() {
    const raw = engineSettingsKeyValue ? readEngineSettingsRaw(engineSettingsKeyValue) : null;
    if (!raw) {
        return;
    }
    const blob = JSON.parse(raw);
    for (const name of EMU_FILTER_SETTING_KEYS) {
        delete blob.settings[name];
    }
    const current = filter.value;
    if (current.shader) {
        blob.settings.shader = current.shader;
    }
    for (const [name, value] of Object.entries(current.options || {})) {
        blob.settings[name] = value;
    }
    writeEngineSettings(engineSettingsKeyValue, blob);
}

/**
 * 把引擎自带菜单里选的着色器同步到滤镜选择器。
 *
 * 引擎那个菜单（底部工具栏 → 图形设置 → 着色器）当「试衣间」用：在那里换一个，这里就跟着
 * 选中；表里没有的会**自动进表**（沿用当前滤镜的内核选项，名字用着色器名）并记住，
 * 于是下次进游戏照样套用——不这么做的话，引擎菜单里的改动会被本页启动时的重置逻辑丢掉。
 * 引擎不发设置变更事件，所以只能每秒读一次它写的设置块（菜单里改完会立刻落盘）。
 */
function syncFilterFromEngine() {
    if (!filters.value) {
        return;
    }
    const raw = engineSettingsKeyValue ? readEngineSettingsRaw(engineSettingsKeyValue) : null;
    if (!raw) {
        return;
    }
    let settings = null;
    try {
        settings = JSON.parse(raw).settings;
    } catch {
        return;
    }
    // 引擎首次写设置块时 settings 里可能根本没有 shader 键（比如只调过音量、改过按键）：
    // 缺键表示「没意见」，不能当成用户选了「禁用」——否则会把本页选中的着色器滤镜
    // 静默改回「无」，并关掉着色器。
    if (typeof settings?.shader !== "string") {
        return;
    }
    const shader = settings.shader === "disabled" ? "" : settings.shader;
    if (shader === (filter.value.shader || "")) {
        return;
    }
    const { entry, created } = filterForShader(filters.value, filter.value, shader);
    if (created) {
        const next = [...customFilters.value, entry];
        customFilters.value = next;
        saveStoredCustomFilters(game.value?.category, next);
    }
    if (entry.id !== filterId.value) {
        // 选中它：watch 会记住这次选择，并把状态（幂等地）再下发一次给引擎
        filterId.value = entry.id;
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

// ---------- 加速模式（持续快进） ----------

/**
 * 「加速模式」：按一次一直加速、再按恢复。开关的是引擎自己的 Fast Forward 设置项，
 * 因此与引擎设置菜单里那一项是同一份状态，也会随「保存配置」进账号（下次进游戏直接加速）。
 * 关着时引擎原有的快进快捷键行为不受影响——这里从头到尾不碰按键。
 */
async function toggleFastForward() {
    if (!engineReady.value) {
        return;
    }
    try {
        const result = await callRpc("setFastForward", !fastForwardOn.value);
        if (!result.ok) {
            ElMessage.error(result.message || "切换加速模式失败。");
            return;
        }
        // 以引擎实际状态为准（引擎可能因为别的原因没切成）
        fastForwardOn.value = result.fastForward === true;
    } catch {
        ElMessage.error("切换加速模式失败。");
    }
}

// ---------- 截图（截宿主页里的引擎画布 → 确认框填描述 → 存入图库） ----------

/** 松开上一张截图的预览 URL 与字节（关闭确认框、卸载页面时都要收）。 */
function releaseShot() {
    if (shotPreviewUrl.value) {
        URL.revokeObjectURL(shotPreviewUrl.value);
    }
    shotPreviewUrl.value = "";
    shotSizeText.value = "";
    shotWidth.value = 0;
    shotHeight.value = 0;
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
        shotWidth.value = Number(result.width) || 0;
        shotHeight.value = Number(result.height) || 0;
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
 * 快捷键回车：直接载入本地存档（与存档管理里那个「载入」按钮同一条路），
 * 并顺手选中模拟器——不管有没有存档，按完回车都能直接接着玩。
 * **有存档时这一下会被读档吃掉**：不再冒泡给引擎，免得同时还把 Start 按下去；
 * 没有存档时不拦这个键，回车照常传给引擎（引擎默认的 Start）。
 */
function onLoadLocalHotkey(event) {
    if (takeHotkey(event, null, () => Boolean(getLocalEmuSave(currentGameId.value)))) {
        void onLoadLocal();
        focusEngineIfNeeded();
        return;
    }
    // 没有存档时 takeHotkey 会放行（焦点在按钮/链接/下拉上时也一样）。
    // 这里只补「选中模拟器」，不拦键，回车仍然照原来的路径走。
    if (
        !isBareEnter(event) ||
        !hotkeyUsable(event, () => true) ||
        isInteractiveTarget(event.target)
    ) {
        return;
    }
    focusEngineIfNeeded();
}

/** 不带任何修饰键的回车。 */
function isBareEnter(event) {
    return (
        event.key === "Enter" &&
        !event.ctrlKey &&
        !event.altKey &&
        !event.metaKey &&
        !event.shiftKey
    );
}

/** 回车/空格在这些元素上有原生含义（按下按钮、展开下拉），别抢焦点。 */
function isInteractiveTarget(target) {
    const tag = String(target?.tagName || "").toUpperCase();
    return tag === "BUTTON" || tag === "A" || tag === "SELECT";
}

/** 引擎是否已经拿到键盘焦点：宿主 iframe 处于激活状态，且焦点在 #ejs 里。 */
function isEngineFocused() {
    try {
        const frame = frameRef.value;
        if (!frame || document.activeElement !== frame) {
            return false;
        }
        const active = frame.contentWindow?.document?.activeElement;
        return Boolean(active && (active.id === "ejs" || active.closest?.("#ejs")));
    } catch {
        return false;
    }
}

/**
 * 没选中模拟器就把焦点交给引擎，之后按键直接进游戏（回车之后不用再点画面）。
 * 已经选中时不重复聚焦，免得把引擎菜单 / 输入框里的焦点抢走。
 */
function focusEngineIfNeeded() {
    const frame = frameRef.value;
    if (!frame || isEngineFocused()) {
        return;
    }
    try {
        frame.focus({ preventScroll: true });
        const frameWindow = frame.contentWindow;
        frameWindow?.focus();
        frameWindow?.document?.getElementById("ejs")?.focus({ preventScroll: true });
    } catch {
        // iframe 正在换文档 / 已卸载，忽略
    }
}

/**
 * 快捷键 `·`（Backquote，数字 1 左边那个键）：立刻捕捉当前进度并同步至云端。
 * 捕捉与上传由 onUploadCloud 顺次完成、成功提示也在里面，这里只认键与防重入。
 */
function onSyncCloudHotkey(event) {
    if (takeBareCode(event, "Backquote", () => !syncingCloud)) {
        void syncCloudNow();
    }
}

/**
 * 快捷键 Alt + `（Backquote，数字 1 左边那个键）：打开存档管理。
 * 与标题栏的「存档管理」按钮同一条路；游戏还没加载、弹框开着时不响应。
 * 注意和 `·` 区分：那个不带修饰键，这个必须按住 Alt。
 */
function onSaveManagerHotkey(event) {
    if (
        event.code !== "Backquote" ||
        !event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        event.repeat
    ) {
        return;
    }
    const target = event.target;
    const tag = String(target?.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable) {
        return;
    }
    if (!game.value || saveManagerVisible.value || shotDialogVisible.value) {
        return;
    }
    // 捕获阶段拦下：引擎自己也监听 keydown，Alt+` 不该同时进游戏
    event.preventDefault();
    event.stopPropagation();
    saveManagerVisible.value = true;
}

async function syncCloudNow() {
    if (syncingCloud) {
        return;
    }
    syncingCloud = true;
    try {
        await onUploadCloud();
    } finally {
        syncingCloud = false;
    }
}

// ---------- NDS 屏幕布局（- / = 循环） ----------

function isTypingTarget(target) {
    const tag = String(target?.tagName || "").toUpperCase();
    return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        Boolean(target?.isContentEditable)
    );
}

/** 引擎自己的菜单/设置面板/弹层里不抢键（那里有自己的键盘操作）。 */
function isEngineChromeTarget(target) {
    return Boolean(
        target?.closest?.(
            ".ejs_menu_bar, .ejs_settings_parent, .ejs_popup_container, " +
                ".ejs_context_menu, .ejs_control_body, .ejs_control_player_bar",
        ),
    );
}

function stepNdsScreenMode(mode, step) {
    const index = NDS_SCREEN_MODES.indexOf(mode);
    const length = NDS_SCREEN_MODES.length;
    return NDS_SCREEN_MODES[(index + step + length) % length];
}

/**
 * 点窗口选择器三列里的格子：记下**这一列布局自己的**倍率；点的是别的布局就顺便切过去。
 * 三种布局的倍率互相独立，切换布局时各用各的。
 */
function onPickNdsWindowMode({ mode, scale: value }) {
    if (!NDS_SCREEN_MODES.includes(mode)) {
        return;
    }
    if (value !== "fit" && !(Number(value) > 0)) {
        return;
    }
    ndsModeScales.value = { ...ndsModeScales.value, [mode]: String(value) };
    if (mode !== ndsScreenMode.value) {
        void switchNdsScreenMode(mode);
        return;
    }
    scheduleApplyStage();
    syncStageRect();
}

/**
 * 切换 NDS 屏幕布局。先本地切（舞台/机壳立刻按新比例摆好），再让宿主页改内核变量；
 * 宿主页会等到引擎真的上报新几何才返回成功，失败就回滚到原来的模式。
 *
 * **不自动重启内核**：万一 melonDS 的布局选项要重启才生效，宿主页返回 needsRestart，
 * 这里只提示、不重建 iframe——重启会丢当前进度。
 */
async function switchNdsScreenMode(next) {
    if (switchingNdsMode.value || !isNds.value || !engineReady.value) {
        return;
    }
    if (!NDS_SCREEN_MODES.includes(next) || next === ndsScreenMode.value) {
        return;
    }
    switchingNdsMode.value = true;
    const previous = ndsScreenMode.value;
    ndsScreenMode.value = next;
    persistNdsScreenMode(next);
    // 立刻按新模式的比例重排（不等引擎下一秒的轮询；引擎上报后还会再校一次）
    engineAspect.value = null;
    scheduleApplyStage();
    try {
        const result = await callRpc("setNdsLayout", next);
        if (!result?.ok) {
            ndsScreenMode.value = previous;
            persistNdsScreenMode(previous);
            engineAspect.value = null;
            scheduleApplyStage();
            ElMessage.warning(result?.message || "切换屏幕布局失败。");
            return;
        }
        if (result.videoInfo?.aspect) {
            engineAspect.value = result.videoInfo.aspect;
        }
        scheduleApplyStage();
        window.setTimeout(() => {
            refreshEngineReady();
            syncStageRect();
        }, 120);
    } catch {
        ndsScreenMode.value = previous;
        persistNdsScreenMode(previous);
        engineAspect.value = null;
        scheduleApplyStage();
        ElMessage.error("切换屏幕布局失败。");
    } finally {
        switchingNdsMode.value = false;
    }
}

/**
 * 快捷键 - / =：NDS 屏幕布局循环（- 上一个、= 下一个：dual → top → side → dual）。
 *
 * 认的是 **Backspace 左边那两个物理键**（event.code 的 Minus / Equal），不是主键盘
 * 字符、也不是小键盘（NumpadSubtract / NumpadAdd）：`+` 就是 Shift+=，按不按 Shift
 * 都算下一个。不带 Ctrl/Alt/Meta 才生效；焦点在输入框、引擎菜单/设置面板里时不抢。
 */
function onNdsScreenHotkey(event) {
    const isPrevious = event.code === "Minus";
    const isNext = event.code === "Equal";
    if (!isPrevious && !isNext) {
        return;
    }
    if (event.ctrlKey || event.altKey || event.metaKey || event.repeat) {
        return;
    }
    if (!isNds.value || switchingNdsMode.value) {
        return;
    }
    if (isTypingTarget(event.target) || isEngineChromeTarget(event.target)) {
        return;
    }
    if (!hotkeyUsable(event, () => true)) {
        return;
    }
    event.preventDefault();
    // 捕获阶段拦下：引擎自己也监听 keydown，这两个键不该同时进游戏
    event.stopPropagation();
    const step = isNext ? 1 : -1;
    void switchNdsScreenMode(stepNdsScreenMode(ndsScreenMode.value, step));
}

/**
 * 快捷键共用的守卫：连发、焦点在输入框里、引擎未就绪、弹框开着、或这一下对当前状态没意义时不接管。
 */
function hotkeyUsable(event, ready) {
    if (event.repeat) {
        return false;
    }
    const target = event.target;
    const tag = String(target?.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return false;
    }
    return (
        engineReady.value && !shotDialogVisible.value && !saveManagerVisible.value && ready()
    );
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
    if (!matches) {
        return false;
    }
    // 焦点停在标题栏按钮上时，回车是「按下这个按钮」，不跟它抢（点过按钮后焦点会留在那儿）
    const tag = String(event.target?.tagName || "").toUpperCase();
    if (!key && (tag === "BUTTON" || tag === "A" || tag === "SELECT")) {
        return false;
    }
    if (!hotkeyUsable(event, ready)) {
        return false;
    }
    event.preventDefault();
    // 捕获阶段拦下：引擎自己也监听 keydown（在它的容器上），不拦住的话这一下会同时进游戏
    event.stopPropagation();
    return true;
}

/**
 * 裸键按 event.code 匹配、且不带任何修饰键：给 `·`（Backquote）这种不该看布局字符的键用
 * （同一物理键在别的布局/输入法下 event.key 可能是 ` / ~ / ·）。守卫与 takeHotkey 相同。
 */
function takeBareCode(event, code, ready) {
    if (
        event.code !== code ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey ||
        event.shiftKey ||
        !hotkeyUsable(event, ready)
    ) {
        return false;
    }
    event.preventDefault();
    event.stopPropagation();
    return true;
}

// ---------- 全屏闲置：iframe 内的指针活动与光标 ----------
// GameShell 只管得到外层 DOM：iframe 里的 pointermove 不冒泡出来，光标也得进到
// 它自己的文档里才藏得住。所以这里把内部活动转给 GameShell，并按闲置状态给
// 宿主页的 <html> 挂 x-cursor-hidden（样式在 emulator-host.html）。
function onFramePointerActivity() {
    shellRef.value?.notifyActivity?.();
}

function bindFramePointerActivity() {
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
    unbindFramePointerActivity();
    pointerFrameWindow = frameWindow;
    // 捕获阶段：控制条/引擎浮层上停止冒泡也不影响活动判定
    frameWindow.addEventListener("pointermove", onFramePointerActivity, true);
    frameWindow.addEventListener("pointerdown", onFramePointerActivity, true);
    frameWindow.addEventListener("wheel", onFramePointerActivity, { capture: true, passive: true });
}

function unbindFramePointerActivity() {
    if (!pointerFrameWindow) {
        return;
    }
    try {
        pointerFrameWindow.removeEventListener("pointermove", onFramePointerActivity, true);
        pointerFrameWindow.removeEventListener("pointerdown", onFramePointerActivity, true);
        pointerFrameWindow.removeEventListener("wheel", onFramePointerActivity, true);
    } catch {
        // 窗口已销毁，忽略
    }
    pointerFrameWindow = null;
}

function applyFrameCursorHidden() {
    let root = null;
    try {
        root = frameRef.value?.contentWindow?.document?.documentElement || null;
    } catch {
        root = null;
    }
    if (root) {
        root.classList.toggle("x-cursor-hidden", frameCursorHidden);
    }
}

function onCursorIdleChange(hidden) {
    frameCursorHidden = hidden;
    applyFrameCursorHidden();
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
    frameWindow.addEventListener("keydown", onSyncCloudHotkey, true);
    frameWindow.addEventListener("keydown", onSaveManagerHotkey, true);
    frameWindow.addEventListener("keydown", onNdsScreenHotkey, true);
}

function unbindFrameHotkey() {
    if (!hotkeyFrameWindow) {
        return;
    }
    try {
        hotkeyFrameWindow.removeEventListener("keydown", onScreenshotHotkey, true);
        hotkeyFrameWindow.removeEventListener("keydown", onLoadLocalHotkey, true);
        hotkeyFrameWindow.removeEventListener("keydown", onSyncCloudHotkey, true);
        hotkeyFrameWindow.removeEventListener("keydown", onSaveManagerHotkey, true);
        hotkeyFrameWindow.removeEventListener("keydown", onNdsScreenHotkey, true);
    } catch {
        // 页面已经换过 iframe / 窗口已销毁，忽略即可
    }
    hotkeyFrameWindow = null;
}

// ---------- 存档管理编排（统一 SaveManager 的本地/云端） ----------

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
        await applyCloudSettings(item.category);
        sanitizeLocalNdsOptions(item.category);
        // 滤镜：内核选项既要进内核设置文件（内核加载前就得在，见宿主页），也要进引擎设置块
        // （引擎自己的重放路径）；设置块里的值优先级更高，所以顺序必须是「先云端的、再本局的
        // 滤镜」，反过来就会被云端或上一次的选择顶掉。
        applyFilterToEngineSettings();
        // ROM 直连后端流式接口；带 updated_at 参数，重传本体后可让 EmulatorJS 缓存失效
        const params = new URLSearchParams({
            id: String(item.id),
            core: meta.value.core,
            name: item.name || "",
            v: item.updated_at || "",
            // 显示比例：宿主页据此设内核选项（只有 FC 认这个参数），与标题栏窗口选择器里选的那列一致
            ratio: aspectMode.value,
        });
        // NDS 屏幕布局：宿主页据此在启动前写 melonds_screen_layout / melonds_screen_gap
        if (item.category === "nds") {
            params.set("nds", ndsScreenMode.value);
        }
        // 滤镜：内核选项串在加载前落进内核设置文件，着色器键名在引擎起来后启用
        const filterParams = filterQuery();
        if (filterParams.copts) {
            params.set("copts", filterParams.copts);
        }
        if (filterParams.shader) {
            params.set("shader", filterParams.shader);
        }
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
        filterId.value = "none";
        iframeSrc.value = "";
        saveManagerVisible.value = false;
        shotDialogVisible.value = false;
        unbindFrameHotkey();
        unbindFramePointerActivity();
        engineReady.value = false;
        fastForwardOn.value = false;
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
    unbindFramePointerActivity();
    engineReady.value = false;
    fastForwardOn.value = false;
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
        // 滤镜：按该类型记住的选择恢复（含引擎菜单里试出来、自动进表的条目）；
        // 清单里已经没有它了就回落到「无」
        customFilters.value = loadStoredCustomFilters(item.category);
        filterId.value = filterForStored().id;
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

// 生效倍率变了就重排舞台：NDS 的三份独立倍率、切换布局都经由它
watch(windowScale, () => scheduleApplyStage());

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

// NDS 三种布局各自的倍率：改了就记下来（点窗口选择器的格子 / 以后扩展都走这里）
watch(ndsModeScales, (value) => persistNdsWindowScales(value), { deep: true });

// 滤镜：记住选择（按游戏类型），运行中切换就立刻推给引擎——引擎只在启动时读一次设置，
// 所以运行中改走宿主页的 setFilter；下次进游戏由 iframe 的 copts / shader 参数兜住。
watch(filterId, (value) => {
    saveStoredFilter(game.value?.category, value);
    if (!engineReady.value) {
        return;
    }
    // 设置块也跟上：中途按「保存配置」时传的就是当下这份选择，而不是启动时那份
    applyFilterToEngineSettings();
    const current = filter.value;
    void callRpc("setFilter", {
        options: current.options || {},
        shader: current.shader || "",
        // 本类型滤镜涉及的内核选项及各自的关闭值：宿主页先把它们复位，再下发本次的取值
        reset: emuFilterResets(game.value?.category),
    });
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
    // 焦点在父页面（点标题栏按钮/弹框）时按快捷键也要能截图 / 载入存档 / 同步云端
    window.addEventListener("keydown", onScreenshotHotkey);
    window.addEventListener("keydown", onLoadLocalHotkey);
    window.addEventListener("keydown", onSyncCloudHotkey);
    window.addEventListener("keydown", onSaveManagerHotkey);
    // 捕获阶段：标题栏/弹框里若有元素停止冒泡，- / = 也要能切布局
    window.addEventListener("keydown", onNdsScreenHotkey, true);
    loadGame();
});
watch(() => route.params.gameId, loadGame);
onBeforeUnmount(() => {
    window.removeEventListener("resize", syncStageRect);
    window.removeEventListener("scroll", syncStageRect, true);
    window.removeEventListener("keydown", onScreenshotHotkey);
    window.removeEventListener("keydown", onLoadLocalHotkey);
    window.removeEventListener("keydown", onSyncCloudHotkey);
    window.removeEventListener("keydown", onSaveManagerHotkey);
    window.removeEventListener("keydown", onNdsScreenHotkey, true);
    unbindFrameHotkey();
    unbindFramePointerActivity();
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

/* NDS：iframe 抬到机壳之上（z-index 6 > 机壳 5），并把 iframe 背景交给宿主页做成透明、
   由宿主页把引擎画布遮成两块屏幕区域。这样引擎的设置弹框（iframe 里的 z-index 9999）
   跨过铰链时显示在机壳上面；机壳仍留在父页面，洞外的机身照常可见、不会被 iframe 视口裁掉。
   只对 NDS 生效：其他机种的 iframe 保持不透明、照旧被机壳盖住。 */
.emulator-player__stage--nds {
    background: #000;
}

.emulator-player__stage--nds .emulator-player__frame {
    position: relative;
    z-index: 6;
    background: transparent;
}

/* 机壳：每块一个 fixed 外层 + overflow:hidden，内层 img 负偏移裁出 crop 区域，
   尺寸/位置由 shellLayers 算。定位必须用 fixed 而不是 absolute：机壳比舞台大得多
   （宽是画面的两倍），absolute 会被 .game-shell__body 的 overflow: auto 裁掉、
   还会顶出滚动条；fixed 不参与任何滚动容器的溢出计算，也不会被祖先裁剪。
   z-index 压在标题栏(20)与侧栏(60)之下，盖着机壳也点得到按钮。 */
.emulator-player__shell-part {
    position: fixed;
    z-index: 5;
    overflow: hidden;
    pointer-events: none;
    user-select: none;
}

.emulator-player__shell-image {
    position: absolute;
    display: block;
    max-width: none;
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

/* 标题栏按钮只保留不收缩；外观交给 AppButton 的 dark 变体 */
.emulator-player__action {
    flex-shrink: 0;
}
</style>
