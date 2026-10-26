<template>
    <game-shell :title="gameTitle" @fullscreen-change="onFullscreenChange">
        <template #actions>
            <flash-quality-select v-model="quality" />
            <flash-resolution-select v-model="resolution" :native-size="nativeSize" />
            <app-button
                class="save-manager-entry"
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
import { confirmAction } from "@/utils/confirm";
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
// 「同步至云端」整段（含二次确认框）在跑：挡掉连发，也保证一次只弹一个确认框
let syncingCloud = false;

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
// 返回是否真的传上去了——快捷键那条路要据此决定弹不弹「已同步至云端」；
// 存档管理弹框那条路忽略返回值，行为不变。
async function onUploadCloud(remark = "") {
    const manager = saveManagerRef.value;
    const gameId = Number(game.value?.id) || 0;
    if (!gameId) {
        manager?.afterCloudUploaded();
        return false;
    }
    try {
        // reloadForSave(null) 触发一次“停播放器→落盘→重启”，末尾会刷新本地列表
        await reloadForSave(null);
        const items = collectLocalSaves(gameId, { withContent: true });
        if (!items.length) {
            ElMessage.info("本地没有可同步的存档。");
            manager?.afterCloudUploaded();
            return false;
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
        return true;
    } catch {
        // 错误已由请求层弹中文提示，这里复位云端按钮状态
        manager?.afterCloudUploaded();
        return false;
    }
}

/**
 * 快捷键 `·`（Backquote，数字 1 左边那个键）：立即把当前进度同步到云端。
 * Flash 的「落盘」必须先卸载 Ruffle 再重挂（等于重启游戏，见 reloadForSave），所以先弹二次确认。
 * 还没点「开始游戏」、游戏没加载出来、存档弹框开着、或已经在同步时不响应。
 */
function onSyncCloudHotkey(event) {
    if (
        event.code !== "Backquote" ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey ||
        event.shiftKey ||
        event.repeat
    ) {
        return;
    }
    const target = event.target;
    const tag = String(target?.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return;
    }
    if (
        syncingCloud ||
        !swfUrl.value ||
        needsGesture.value ||
        loading.value ||
        saveManagerVisible.value ||
        !currentGameId.value
    ) {
        return;
    }
    // 捕获阶段拦下：Ruffle 在同一个文档里也监听键盘，先拿到才不会让 `·` 同时进游戏
    event.preventDefault();
    event.stopPropagation();
    void syncCloudNow();
}

async function syncCloudNow() {
    if (syncingCloud) {
        return;
    }
    // 先置位再弹框：确认框开着时再按 `·` 不会再弹一个
    syncingCloud = true;
    try {
        const confirmed = await confirmAction(
            "同步会先让游戏把当前进度落盘，游戏将重新启动。确定现在同步吗？",
            { title: "同步至云端", confirmText: "同步" },
        );
        if (!confirmed) {
            // 取消 / 关闭：不重启也不提示
            return;
        }
        if (await onUploadCloud()) {
            ElMessage.success("已同步至云端");
        }
    } finally {
        syncingCloud = false;
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

onMounted(() => {
    // 捕获阶段：Ruffle 也在同一个文档里监听键盘，只有捕获阶段才拦得住 `·`
    window.addEventListener("keydown", onSyncCloudHotkey, true);
    loadGame();
});
watch(() => route.params.gameId, loadGame);
onBeforeUnmount(() => {
    window.removeEventListener("keydown", onSyncCloudHotkey, true);
    stopGamePlaytime();
});
</script>

<style scoped>
/* 标题栏里的「存档管理」入口只保留不收缩；外观交给 AppButton 的 dark 变体 */
.save-manager-entry {
    flex-shrink: 0;
}
</style>
