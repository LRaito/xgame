<template>
    <game-shell :title="gameTitle" @fullscreen-change="onFullscreenChange">
        <template #extra>
            <span class="h5-player__hint">{{ typeHint }}</span>
        </template>
        <start-gate v-if="needsGesture" @start="startFromGate" />
        <div v-else class="h5-player" :class="{ 'h5-player--fullscreen': isFullscreen }">
            <div v-if="iframeSrc" class="h5-player__stage">
                <!-- sandbox 不带 allow-same-origin：游戏进入不透明源，读不到本站 cookie/DOM，
                     也无法调用 /api；代价是 localStorage/Web Worker 不可用（见文档）。 -->
                <iframe
                    class="h5-player__frame"
                    :src="iframeSrc"
                    title="游戏画面"
                    sandbox="allow-scripts allow-forms allow-modals allow-popups allow-pointer-lock allow-downloads"
                    allowfullscreen
                    allow="autoplay; fullscreen; gamepad"
                    referrerpolicy="no-referrer"
                />
            </div>
            <div v-else-if="!loading" class="h5-player__empty">
                <app-empty :description="errorText || '未找到该游戏'" />
            </div>
        </div>
    </game-shell>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getPlayableGameAPI, h5EntryPath } from "@/api/games";
import { gameTypeMeta } from "@/constants/gameTypes";
import GameShell from "@components/games/GameShell.vue";
import StartGate from "@components/games/StartGate.vue";
import { hasUserGesture } from "@/utils/userActivation";
import { reportGamePlayed } from "@/utils/recentGames";
import { startGamePlaytime, stopGamePlaytime } from "@/utils/gamePlaytime";

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const game = ref(null);
const errorText = ref("");
const iframeSrc = ref("");
const isFullscreen = ref(false);
// 无用户手势（刷新/直链进入）时先展示「开始游戏」，由一次点击后再挂载 iframe 启动音频
const needsGesture = ref(false);

const gameTitle = computed(() => game.value?.name || "HTML5 游戏");
const typeHint = computed(() => {
    const meta = game.value ? gameTypeMeta(game.value.category) : null;
    return meta?.label ? `（${meta.label}）` : "";
});

function onFullscreenChange(value) {
    isFullscreen.value = value;
}

function startFromGate() {
    // 这次点击即用户手势：挂载 iframe 后游戏可正常播放音频
    needsGesture.value = false;
    if (game.value) {
        iframeSrc.value = h5EntryPath(game.value.id, game.value.updated_at);
        reportGamePlayed(game.value.id);
        startGamePlaytime(game.value.id);
    }
}

function loadGame() {
    // 换路由参数时先停表：新游戏加载失败的话旧游戏不能继续计时长
    stopGamePlaytime();
    const gameId = Number(route.params.gameId);
    if (!gameId) {
        game.value = null;
        iframeSrc.value = "";
        return;
    }
    loading.value = true;
    game.value = null;
    iframeSrc.value = "";
    errorText.value = "";
    needsGesture.value = false;
    getPlayableGameAPI(gameId)
        .then((item) => {
            if (!item) {
                errorText.value = "未找到该游戏";
                return;
            }
            // 误入本页的其它类型按各自播放页跳转
            if (item.category === "flash") {
                router.replace(`/games/flash/${item.id}`);
                return;
            }
            if (item.category !== "h5") {
                router.replace(`/games/play/${item.id}`);
                return;
            }
            game.value = item;
            if (!hasUserGesture()) {
                needsGesture.value = true;
                return;
            }
            iframeSrc.value = h5EntryPath(item.id, item.updated_at);
            reportGamePlayed(item.id);
            startGamePlaytime(item.id);
        })
        .catch(() => {
            errorText.value = "游戏信息加载失败，请稍后重试";
        })
        .finally(() => {
            loading.value = false;
        });
}

onMounted(loadGame);
watch(() => route.params.gameId, loadGame);
onBeforeUnmount(stopGamePlaytime);
</script>

<style scoped>
/* 游戏区铺满可用空间；H5 无固定分辨率，不做等比舞台缩放 */
.h5-player {
    width: 100%;
    min-height: 70vh;
    display: flex;
}

.h5-player--fullscreen {
    height: 100%;
    min-height: 0;
}

.h5-player__stage {
    flex: 1;
    display: flex;
    min-width: 0;
}

.h5-player__frame {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 70vh;
    border: none;
    background: #000;
    border-radius: 12px;
}

.h5-player--fullscreen .h5-player__frame {
    min-height: 0;
}

.h5-player__empty {
    margin: auto;
}

.h5-player__hint {
    font-size: 13px;
    color: #94a3b8;
    white-space: nowrap;
}
</style>
