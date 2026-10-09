<template>
    <game-shell :title="gameTitle" @fullscreen-change="onFullscreenChange">
        <template #actions>
            <flash-quality-select v-model="quality" />
            <flash-resolution-select v-model="resolution" :native-size="nativeSize" />
            <button type="button" class="save-manager-entry" @click="saveManagerVisible = true">
                存档管理
            </button>
        </template>
        <start-gate
            v-if="needsGesture"
            @start="startFromGate"
        />
        <flash-player
            v-else-if="playerActive && swfUrl"
            :swf-url="swfUrl"
            :resolution="resolution"
            :quality="quality"
            :fullscreen="isFullscreen"
            @native-size="onNativeSize"
        />
        <app-empty v-else-if="!swfUrl && !loading" description="未找到该 Flash 游戏" />
        <flash-save-manager
            ref="saveManagerRef"
            v-model="saveManagerVisible"
            :game-id="currentGameId"
            @sync="onSyncSave"
            @save-action="onSaveAction"
            @upload-cloud="onUploadCloud"
        />
    </game-shell>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { getPlayableGameAPI, uploadCloudSaveAPI } from "@/api/games";
import { ensureGameAssetSw, gameSwfUrl } from "@/utils/gameAssetCache";
import {
    collectLocalSaves,
    deleteLocalSave,
    solBase64ToBlob,
    writeLocalSave,
} from "@/utils/gameSaves";
import GameShell from "@components/games/GameShell.vue";
import FlashPlayer from "@components/games/FlashPlayer.vue";
import FlashResolutionSelect from "@components/games/FlashResolutionSelect.vue";
import FlashQualitySelect from "@components/games/FlashQualitySelect.vue";
import FlashSaveManager from "@components/games/FlashSaveManager.vue";
import StartGate from "@components/games/StartGate.vue";
import { hasUserGesture } from "@/utils/userActivation";
import { reportGamePlayed } from "@/utils/recentGames";
import { startGamePlaytime, stopGamePlaytime } from "@/utils/gamePlaytime";

const RESOLUTION_STORAGE_KEY = "games.flash.resolution";
const QUALITY_STORAGE_KEY = "games.flash.quality";

function loadStoredResolution() {
    try {
        return localStorage.getItem(RESOLUTION_STORAGE_KEY) || "native";
    } catch {
        return "native";
    }
}

function loadStoredQuality() {
    try {
        const value = localStorage.getItem(QUALITY_STORAGE_KEY);
        return value === "medium" || value === "low" ? value : "high";
    } catch {
        return "high";
    }
}

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const game = ref(null);
const swfUrl = ref("");
const resolution = ref(loadStoredResolution());
const quality = ref(loadStoredQuality());
const nativeSize = ref(null);
const isFullscreen = ref(false);
const saveManagerVisible = ref(false);
// 存档的读写都需要先卸载播放器让 Ruffle 落盘，再改 localStorage，最后重新加载游戏。
// playerActive 为 false 时暂停挂载 flash-player，留出写入窗口。
const playerActive = ref(true);
// 无用户手势（刷新/直链进入）时先展示「开始游戏」，由一次点击后再挂载播放器
const needsGesture = ref(false);
const saveManagerRef = ref(null);

function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function refreshSaveManager() {
    await nextTick();
    saveManagerRef.value?.refresh();
}

/**
 * 存档操作统一编排：Ruffle 只在播放器销毁时才把内存进度写回 localStorage（issue #798），
 * 因此「写档 / 同步最新档」都要先卸载播放器触发落盘，写入后再重启游戏从新档继续。
 * mutate 为空则只做一次「重启」用于同步最新档。
 */
async function reloadForSave(mutate) {
    const hadPlayer = Boolean(swfUrl.value);
    if (hadPlayer) {
        playerActive.value = false;
        await nextTick();
        // 等 Ruffle 元素真正从 DOM 移除、内部销毁并落盘完成。
        await wait(120);
    }
    try {
        mutate?.();
    } finally {
        if (hadPlayer) {
            playerActive.value = true;
        }
        await refreshSaveManager();
    }
}

function onSyncSave() {
    reloadForSave(null);
}

function onSaveAction(payload) {
    const gameId = Number(game.value?.id) || 0;
    if (payload.action === "replace") {
        reloadForSave(() => writeLocalSave(gameId, payload.key, payload.base64));
    } else if (payload.action === "delete") {
        reloadForSave(() => deleteLocalSave(payload.key));
    } else if (payload.action === "replace-many") {
        // “同步至本地”：一次停播放器窗口内写回所有文件，只重启一次游戏
        reloadForSave(() =>
            payload.writes.forEach((write) => writeLocalSave(gameId, write.key, write.base64)),
        );
    }
}

// 「同步至云端」：先把最新进度落盘，再收集当前游戏全部本地存档，整体上传成一个云端快照。
async function onUploadCloud(remark = "") {
    const manager = saveManagerRef.value;
    const gameId = Number(game.value?.id) || 0;
    if (!gameId) {
        manager?.afterCloudUploaded();
        return;
    }
    try {
        // reloadForSave(null) 触发一次“停播放器→落盘→重启”，末尾会刷新本地列表
        await reloadForSave(null);
        const items = collectLocalSaves(gameId, { withContent: true });
        if (!items.length) {
            ElMessage.info("本地没有可同步的存档。");
            manager?.afterCloudUploaded();
            return;
        }
        const form = new FormData();
        form.append("game_id", String(gameId));
        form.append("remark", remark);
        form.append(
            "manifest",
            JSON.stringify(items.map((item) => ({ local_key: item.key, name: item.name }))),
        );
        items.forEach((item) =>
            form.append("sols", solBase64ToBlob(item.base64), `${item.name}.sol`),
        );
        await uploadCloudSaveAPI(form);
        manager?.afterCloudUploaded();
    } catch {
        // 错误已由请求层弹中文提示，这里复位云端按钮状态
        manager?.afterCloudUploaded();
    }
}

// 记住窗口分辨率选择（默认 native 用 Flash 原生分辨率），下次进入自动恢复。
watch(resolution, (key) => {
    try {
        localStorage.setItem(RESOLUTION_STORAGE_KEY, key);
    } catch {
        // 隐私模式等写失败场景忽略即可
    }
});

// 记住画质选择（默认 high），下次进入自动恢复；变化后 FlashPlayer 会重建生效。
watch(quality, (value) => {
    try {
        localStorage.setItem(QUALITY_STORAGE_KEY, value);
    } catch {
        // 隐私模式等写失败场景忽略即可
    }
});

function onNativeSize(size) {
    nativeSize.value = size;
}

function onFullscreenChange(value) {
    isFullscreen.value = value;
}

const gameTitle = computed(() => game.value?.name || "Flash 游戏");
const currentGameId = computed(() => (game.value?.id ? Number(game.value.id) : 0));

function startFromGate() {
    // 这次点击即用户手势：挂载播放器后 Ruffle 开始，声音可正常开启
    needsGesture.value = false;
    reportGamePlayed(game.value?.id);
    startGamePlaytime(game.value?.id);
}

async function loadGame() {
    // 换路由参数时先停表：新游戏加载失败的话旧游戏不能继续计时长
    stopGamePlaytime();
    const gameId = Number(route.params.gameId);
    if (!gameId) {
        game.value = null;
        swfUrl.value = "";
        return;
    }
    loading.value = true;
    swfUrl.value = "";
    playerActive.value = true;
    needsGesture.value = false;
    try {
        await ensureGameAssetSw();
        // 播放页只需要中心列表那几项字段，走中心接口而非管理详情接口
        game.value = await getPlayableGameAPI(gameId);
        if (!game.value) {
            return;
        }
        // 兜底：误入本页的 H5 / 主机游戏改走各自播放页
        if (game.value.category === "h5") {
            router.replace(`/games/h5/${game.value.id}`);
            return;
        }
        if (game.value.category !== "flash") {
            router.replace(`/games/play/${game.value.id}`);
            return;
        }
        swfUrl.value = gameSwfUrl(game.value);
        // 无用户手势（例如刷新页面、直接打开链接进入）时，浏览器会拦截 Ruffle 的
        // 音频自动开始。此时先展示居中的「开始游戏」，等一次点击后再挂载播放器。
        needsGesture.value = !hasUserGesture();
        if (!needsGesture.value) {
            // 有手势 = 播放器立刻挂载开玩；无手势则等 startFromGate 里那次点击再上报
            reportGamePlayed(game.value.id);
            startGamePlaytime(game.value.id);
        }
    } catch {
        game.value = null;
        swfUrl.value = "";
    } finally {
        loading.value = false;
    }
}

onMounted(loadGame);
watch(() => route.params.gameId, loadGame);
onBeforeUnmount(stopGamePlaytime);
</script>

<style scoped>
/* 标题栏里的「存档管理」入口，与 GameShell 自带的按钮同款深色样式 */
.save-manager-entry {
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

.save-manager-entry:hover {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}
</style>
