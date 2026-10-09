<template>
    <div class="games-page">
        <app-empty
            v-if="!loading && loadError"
            description="游戏列表加载失败，请检查网络后重试。"
        />
        <div v-else v-loading="loading" class="games-content">
            <!-- 最近游玩：只占一行，没记录时整块不出现 -->
            <section v-if="recentGames.length" class="games-section">
                <h2 class="games-section__title">最近游玩</h2>
                <div class="games-rail">
                    <!-- rail 用正方形框（CARD_ASPECT_RAIL）：整行高低一致；封面按
                         「正方形限制框」等比缩放居中，与「全部游戏」里一样大 -->
                    <game-card
                        v-for="game in recentGames"
                        :key="game.id"
                        :game="game"
                        :aspect="CARD_ASPECT_RAIL"
                        @contextmenu="openMenu($event, game)"
                    />
                </div>
            </section>

            <section class="games-section">
                <h2 class="games-section__title">全部游戏</h2>
                <div class="games-toolbar">
                    <el-select
                        v-model="activeProgress"
                        placeholder="游戏进度"
                        clearable
                        class="games-filter-progress"
                    >
                        <el-option label="全部进度" value="" />
                        <el-option
                            v-for="item in GAME_PROGRESS_LIST"
                            :key="item.value"
                            :label="item.label"
                            :value="item.value"
                        />
                    </el-select>
                    <el-select
                        v-model="activeType"
                        placeholder="游戏类型"
                        clearable
                        class="games-filter-type"
                    >
                        <el-option label="全部类型" value="" />
                        <el-option
                            v-for="type in typeOrder"
                            :key="type"
                            :label="gameTypeLabel(type)"
                            :value="type"
                        />
                    </el-select>
                    <el-input
                        v-model="keyword"
                        class="games-filter-keyword"
                        placeholder="搜索名称"
                        clearable
                    />
                </div>

                <!-- 一种「游戏类型 + 卡带类型」一个网格：同一行里只会有同一种类型的同一种卡带，
                    跨类型（含日版/美版/默认之间）自然换行。
                    不传 aspect = 卡片高度自适应：封面按正方形限制框缩放，卡片高就是封面高，
                    同一类型的封面形状一致，整行仍然齐平 -->
                <div class="games-groups">
                    <div v-for="row in gameRows" :key="row.key" class="games-grid">
                        <game-card
                            v-for="game in row.games"
                            :key="game.id"
                            :game="game"
                            @contextmenu="openMenu($event, game)"
                        />
                    </div>
                    <!-- 空态直接占据第一格封面位：不要图标，只有一行说明文字 -->
                    <div v-if="!loading && !filteredGames.length" class="games-grid">
                        <p class="games-empty">{{ emptyDescription }}</p>
                    </div>
                </div>
            </section>
        </div>

        <!-- 右键菜单：只在游戏卡上弹出，卡片外仍是浏览器原生菜单 -->
        <game-context-menu
            :visible="menu.visible"
            :x="menu.x"
            :y="menu.y"
            :progress="menu.game?.progress || ''"
            :has-guide="Boolean(menu.game?.has_guide)"
            @detail="openDetail"
            @guide="openGuide"
            @set-progress="setProgress"
            @set-hours="openHoursDialog"
        />

        <!-- 详情弹窗：与游戏管理页的「详情」共用同一个组件 -->
        <game-detail-dialog v-model="detailVisible" :game-id="detailId" />

        <app-dialog
            v-model="hoursDialog.visible"
            title="设置总时长"
            confirm-text="保存"
            :confirm-loading="saving"
            @confirm="saveHours"
        >
            <p class="games-dialog__hint">
                「{{ menu.game?.name }}」的总游玩时长（小时）
            </p>
            <el-input-number
                v-model="hoursDialog.value"
                :min="0"
                :max="100000"
                :step="0.5"
                :precision="1"
                controls-position="right"
            />
            <p class="games-dialog__tip">
                保存后总时长会替换为该数值，之后继续游玩会在此基础上累加。
            </p>
        </app-dialog>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
    gamesStatusAPI,
    guideEntryPath,
    listGamesAPI,
    listRecentGamesAPI,
    setGamePlaytimeAPI,
    setGameProgressAPI,
} from "@/api/games";
import {
    CARTRIDGE_TYPE_DEFAULT,
    cartridgeTypesFor,
} from "@/constants/cartridgeTypes";
import { CARD_ASPECT_RAIL } from "@/constants/gameCardAspect";
import { GAME_PROGRESS_LIST, PROGRESS_NOT_STARTED } from "@/constants/gameProgress";
import { GAME_TYPE_LIST, gameTypeLabel } from "@/constants/gameTypes";
import { ensureGameAssetSw } from "@/utils/gameAssetCache";
import { playSecondsToHours } from "@/utils/gamePlaytime";
import AppDialog from "@components/common/AppDialog.vue";
import GameCard from "@components/games/GameCard.vue";
import GameContextMenu from "@components/games/GameContextMenu.vue";
import GameDetailDialog from "@components/games/GameDetailDialog.vue";

const games = ref([]);
const recentGames = ref([]);
const loading = ref(false);
const loadError = ref(false);
const saving = ref(false);

// 类型筛选下拉的候选顺序：以 /status.game_types 为准（后端单一来源），兜底用前端常量顺序
const typeOrder = ref(GAME_TYPE_LIST.map((type) => type.slug));

// 空串 = 全部；keyword 仅按游戏名称本地实时过滤（数据已整体在本地，无需再请求后端）
const activeType = ref("");
const activeProgress = ref("");
const keyword = ref("");

// 右键菜单的锚点：菜单定位、详情弹窗与「设置时长」弹窗都围绕 menu.game
const menu = ref({ visible: false, x: 0, y: 0, game: null });
const hoursDialog = ref({ visible: false, value: 0 });

// 详情弹窗（内容见 components/games/GameDetailDialog.vue，游戏管理页也用它）
const detailVisible = ref(false);
const detailId = ref(null);

// 与游戏管理一致的类型 + 关键词联合筛选；这里只匹配名称、不分页
const filteredGames = computed(() => {
    const query = keyword.value.trim().toLowerCase();
    return games.value.filter((game) => {
        if (activeType.value && game.category !== activeType.value) {
            return false;
        }
        // 后端对没有统计记录的游戏给的是 not_started，前端也兜一层
        if (activeProgress.value && (game.progress || PROGRESS_NOT_STARTED) !== activeProgress.value) {
            return false;
        }
        if (query && !game.name.toLowerCase().includes(query)) {
            return false;
        }
        return true;
    });
});

// 「全部游戏」分行：CSS 网格是「按顺序填格」，混着放就会让一行里出现两种类型，
// 所以先在游戏类型内按卡带类型再分一层（同一种卡带严格同一行），一层装一个网格容器。
// 游戏类型顺序跟类型下拉一致（/status.game_types 的顺序），没见过的类型排最后；
// 卡带类型顺序用 cartridgeTypesFor()（日版、美版、默认），认不出的值兜到该类型末尾。
const gameRows = computed(() => {
    const groups = new Map();
    for (const game of filteredGames.value) {
        const slug = game.category || "";
        if (!groups.has(slug)) {
            groups.set(slug, new Map());
        }
        const byCartridge = groups.get(slug);
        const value = game.cartridge_type || CARTRIDGE_TYPE_DEFAULT;
        if (!byCartridge.has(value)) {
            byCartridge.set(value, []);
        }
        byCartridge.get(value).push(game);
    }
    const rank = (slug) => {
        const index = typeOrder.value.indexOf(slug);
        return index < 0 ? typeOrder.value.length : index;
    };
    return [...groups.entries()]
        .sort((a, b) => rank(a[0]) - rank(b[0]))
        .flatMap(([slug, byCartridge]) => {
            const order = cartridgeTypesFor(slug).map((item) => item.value);
            const extra = [...byCartridge.keys()].filter((value) => !order.includes(value));
            return [...order, ...extra]
                .filter((value) => byCartridge.has(value))
                .map((value) => ({
                    key: `${slug}:${value}`,
                    games: byCartridge.get(value),
                }));
        });
});

const emptyDescription = computed(() => {
    const rawKeyword = keyword.value.trim();
    if (rawKeyword) {
        return `没有匹配到名称含「${rawKeyword}」的游戏。`;
    }
    if (activeType.value) {
        return "该类型下暂无游戏。";
    }
    if (activeProgress.value) {
        return "该进度下暂无游戏。";
    }
    return "暂无游戏，去「游戏管理」里添加一个吧。";
});

// 菜单贴边时向内收，别跑到视口外。x 预留两个菜单的宽度：
// 「设置进度」的子菜单要向右滑出，否则会顶出视口。
const MENU_WIDTH = 156;
// 详情 / 攻略 / 设置进度 / 设置时长 四项（每项约 37px）＋两条分隔线＋上下内边距
const MENU_HEIGHT = 171;

function openMenu(event, game) {
    const maxX = window.innerWidth - MENU_WIDTH * 2 - 8;
    const maxY = window.innerHeight - MENU_HEIGHT - 8;
    menu.value = {
        visible: true,
        x: Math.min(event.clientX, maxX),
        y: Math.min(event.clientY, maxY),
        game,
    };
}

function closeMenu() {
    menu.value = { ...menu.value, visible: false };
}

// 右键「详情」：弹窗自己去按 id 取详情（列表载荷里没有 CRC32、创建时间这些字段）
function openDetail() {
    const game = menu.value.game;
    if (!game) {
        return;
    }
    closeMenu();
    detailId.value = game.id;
    detailVisible.value = true;
}

// 右键「攻略」：在新标签页顶层打开入口页。资源接口需登录，同源的新标签会带上 session cookie。
function openGuide() {
    const game = menu.value.game;
    if (!game) {
        return;
    }
    closeMenu();
    // noopener：断开新页面与本站的 window.opener 引用
    window.open(guideEntryPath(game.id), "_blank", "noopener");
}

function openHoursDialog() {
    const game = menu.value.game;
    if (!game) {
        return;
    }
    closeMenu();
    // 预填当前总时长，直接改数字即可
    hoursDialog.value = { visible: true, value: playSecondsToHours(game.play_seconds) };
}

/** 同一条游戏在两个列表里各有一份，改一处要同步另一处 */
function patchGame(gameId, patch) {
    for (const list of [games.value, recentGames.value]) {
        const target = list.find((item) => item.id === gameId);
        if (target) {
            Object.assign(target, patch);
        }
    }
}

/** 从右键子菜单直接设置进度：没有确认步骤，选完就存 */
async function setProgress(progress) {
    const game = menu.value.game;
    if (!game) {
        return;
    }
    closeMenu();
    try {
        const data = await setGameProgressAPI(game.id, progress);
        patchGame(game.id, { progress: data?.progress || progress });
    } catch (err) {
        if (!err.reported) {
            ElMessage.error("设置进度失败，请稍后重试。");
        }
    }
}

async function saveHours() {
    const game = menu.value.game;
    if (!game || saving.value) {
        return;
    }
    // 不能用 `|| 0` 兜底：输入框被清空时值是 null（中文输入法打字中途也会是 null），
    // 那样会悄悄把已有的几十小时记录清成 0
    const raw = hoursDialog.value.value;
    const hours = Number(raw);
    if (raw === null || raw === undefined || !Number.isFinite(hours) || hours < 0) {
        ElMessage.warning("请输入 0 到 100000 之间的小时数。");
        return;
    }
    saving.value = true;
    try {
        const data = await setGamePlaytimeAPI(game.id, hours);
        // 用后端回的秒数更新，别自己再换算一遍（舍入口径只留后端一处）
        patchGame(game.id, { play_seconds: data?.play_seconds ?? Math.round(hours * 3600) });
        hoursDialog.value = { ...hoursDialog.value, visible: false };
    } catch (err) {
        if (!err.reported) {
            ElMessage.error("设置时长失败，请稍后重试。");
        }
    } finally {
        saving.value = false;
    }
}

function onDocumentContextMenu(event) {
    // 右键点在菜单自己身上时别收起（捕获阶段先于菜单自身的 @contextmenu 触发）
    if (event.target?.closest?.(".game-context-menu")) {
        return;
    }
    // 必须在捕获阶段监听：冒泡阶段的话 document 会晚于卡片上的 openMenu 执行，
    // 菜单刚弹出就被自己关掉了。这里只收起菜单，不阻止浏览器原生右键菜单。
    closeMenu();
}

function onDocumentClick() {
    // 菜单自身的 @click.stop 会拦住点菜单项的那次点击，走到这里的就是点外面
    closeMenu();
}

function onDocumentKeydown(event) {
    if (event.key === "Escape") {
        closeMenu();
    }
}

onMounted(async () => {
    document.addEventListener("contextmenu", onDocumentContextMenu, true);
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onDocumentKeydown);
    window.addEventListener("scroll", closeMenu, true);
    loading.value = true;
    try {
        // SW 只用于封面/本体的缓存加速；初始化失败也不应挡住列表展示（见 gameAssetCache）
        await ensureGameAssetSw();
        const status = await gamesStatusAPI();
        if (Array.isArray(status.game_types) && status.game_types.length) {
            typeOrder.value = status.game_types;
        }
        games.value = await listGamesAPI();
        // 最近游玩是锦上添花：单独兜错，失败只丢这一块，不能把整页带进 loadError 空态
        const recent = await listRecentGamesAPI().catch(() => []);
        recentGames.value = Array.isArray(recent) ? recent : [];
    } catch {
        loadError.value = true;
    } finally {
        loading.value = false;
    }
});

onBeforeUnmount(() => {
    document.removeEventListener("contextmenu", onDocumentContextMenu, true);
    document.removeEventListener("click", onDocumentClick);
    document.removeEventListener("keydown", onDocumentKeydown);
    window.removeEventListener("scroll", closeMenu, true);
});
</script>

<style scoped>
/* 占满内容区宽度（与游戏管理页一致），不设窄幅居中 */
.games-page {
    width: 100%;
}

.games-content {
    min-height: 120px;
}

/* 顶部筛选工具栏：与游戏管理页一致的类型下拉 + 搜索框 */
.games-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
}

.games-filter-type {
    width: 240px;
}

.games-filter-progress {
    width: 160px;
}

.games-filter-keyword {
    width: 240px;
}

/* 右键弹出的两个小弹窗：标题行说明当前游戏，下面是选项与提示 */
.games-dialog__hint {
    margin: 0 0 12px;
    font-size: 13px;
    color: #475569;
}

.games-dialog__tip {
    margin: 12px 0 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-muted);
}

/* 「最近游玩」与「全部游戏」两个分区（卡片本身见 components/games/GameCard.vue） */
.games-section + .games-section {
    margin-top: 24px;
}

.games-section__title {
    margin: 0 0 12px;
    font-size: 15px;
    font-weight: 600;
    color: #334155;
}

/* 最近游玩：只展示一行，多出来的行高压成 0 并裁掉（不滚动、不换行）。
   列定义与下方「全部游戏」网格完全一致，卡片尺寸自然处处相同。 */
.games-rail {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    grid-template-rows: auto;
    grid-auto-rows: 0;
    column-gap: 14px;
    row-gap: 0;
    /* 顶部留出 hover 上移的那 4px（见 GameCard 的 translateY(-4px)）：
       裁剪区顶边就是内容盒上方，不留空隙的话卡片一抬起来封面顶部就被切掉。
       margin-top 抵消同样的距离，所以标题与卡片的间距、整块高度都不变。 */
    padding-top: 6px;
    margin-top: -6px;
    /* 用 clip 而不是 hidden：同样裁掉多余的行，但不会变成可滚动容器
       （hidden 下 Tab 聚焦到被裁掉的卡片会把容器滚走） */
    overflow: clip;
}

/* 类型分组：一个类型一个网格，组与组的间距与网格行距一致，
   整片看起来仍是一个连续网格，只是类型交界处一定会换行 */
.games-groups {
    display: flex;
    flex-direction: column;
    gap: 22px;
}

.games-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    /* 行间距要容得下封面下的名称与状态行 */
    column-gap: 14px;
    row-gap: 22px;
}

/* 空态：占住第一格（这里没有封面可按，给一块固定比例的文字区），
   文字在其中垂直靠上、水平靠左 */
.games-empty {
    margin: 0;
    aspect-ratio: 10 / 9;
    display: flex;
    align-items: flex-start;
    justify-content: flex-start;
    font-size: 13px;
    line-height: 1.6;
    color: #64748b;
}
</style>
