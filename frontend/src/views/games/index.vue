<template>
    <div class="games-page">
        <app-empty
            v-if="!loading && loadError"
            description="游戏列表加载失败，请检查网络后重试。"
        />
        <div v-else v-loading="loading" class="games-shell">
            <!-- 类型导航侧栏：最近游玩 + 全部类型（带计数），上下翻页箭头翻行，
                 点条目即时跳到对应区块；主页面滚动不改变侧栏高亮 -->
            <aside class="games-side">
                <div v-show="sideCanUp" class="games-side__page games-side__page--up">
                    <app-button
                        text
                        tone="dark"
                        size="sm"
                        icon-only
                        aria-label="向上翻页"
                        @click="scrollSideUp"
                    >
                        <svg
                            viewBox="0 0 24 24"
                            width="20"
                            height="20"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="1.8"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            aria-hidden="true"
                        >
                            <path d="M4.5 14.5L12 9l7.5 5.5" />
                        </svg>
                    </app-button>
                </div>
                <nav
                    ref="sideNavRef"
                    class="games-side__nav"
                    @scroll.passive="updateSidePaging"
                >
                    <!-- 计数永远是裸数字：最近游玩与 36 个类型同款、0 不特殊化 -->
                    <a
                        class="games-side__link"
                        :class="{ 'games-side__link--active': activeSide === 'grp-recent' }"
                        href="javascript:void(0)"
                        @click="jumpTo('grp-recent')"
                    >
                        <span class="games-side__name">最近游玩</span>
                        <span class="games-side__count">{{ filteredRecent.length }}</span>
                    </a>
                    <a
                        v-for="type in typeOrder"
                        :key="type"
                        class="games-side__link"
                        :class="{ 'games-side__link--active': activeSide === `grp-${type}` }"
                        href="javascript:void(0)"
                        @click="jumpTo(`grp-${type}`)"
                    >
                        <span class="games-side__name">{{ gameTypeLabel(type) }}</span>
                        <span class="games-side__count">{{ countsByType.get(type) || 0 }}</span>
                    </a>
                </nav>
                <div v-show="sideCanDown" class="games-side__page games-side__page--down">
                    <app-button
                        text
                        tone="dark"
                        size="sm"
                        icon-only
                        aria-label="向下翻页"
                        @click="scrollSideDown"
                    >
                        <svg
                            viewBox="0 0 24 24"
                            width="20"
                            height="20"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="1.8"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            aria-hidden="true"
                        >
                            <path d="M4.5 9.5L12 15l7.5-5.5" />
                        </svg>
                    </app-button>
                </div>
            </aside>

            <!-- 内容区自己滚（独立滚动区）：滚到边界不影响侧栏，反之亦然 -->
            <div
                ref="mainRef"
                class="games-main"
                @scroll.passive="onMainScroll"
            >
                <!-- 统计块：进度 + 关键词联动（类型下拉不参与），块内纯数字无单位 -->
                <div class="games-stats">
                    <div class="games-stat">
                        <div class="games-stat__v">{{ statsData.total }}</div>
                        <div class="games-stat__l">游戏总数</div>
                    </div>
                    <div class="games-stat">
                        <div class="games-stat__v">{{ statsData.completed }}</div>
                        <div class="games-stat__l">已通关</div>
                    </div>
                    <div class="games-stat">
                        <div class="games-stat__v">{{ statsData.inProgress }}</div>
                        <div class="games-stat__l">进行中</div>
                    </div>
                    <div class="games-stat">
                        <div class="games-stat__v">{{ statsData.hours }}</div>
                        <div class="games-stat__l">累计小时数</div>
                    </div>
                </div>

                <!-- 筛选工具栏：样式与游戏管理一致，位置在统计下、最近游玩上 -->
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
                    <app-type-select
                        v-model="activeType"
                        placeholder="游戏类型"
                        clearable
                        class="games-filter-type"
                        :options="typeFilterOptions"
                    />
                    <el-input
                        v-model="keyword"
                        class="games-filter-keyword"
                        placeholder="搜索名称"
                        clearable
                    />
                </div>

                <!-- 最近游玩：只占一行，筛选后没记录时整块不出现 -->
                <section v-if="filteredRecent.length" id="grp-recent" class="games-sec">
                    <h2 class="games-gh">最近游玩</h2>
                    <div class="games-rail">
                        <!-- rail 用正方形框（CARD_ASPECT_RAIL）：整行高低一致；封面按
                             「正方形限制框」等比缩放居中，与「全部游戏」里一样大 -->
                        <game-card
                            v-for="game in filteredRecent"
                            :key="game.id"
                            :game="game"
                            :aspect="CARD_ASPECT_RAIL"
                            @contextmenu="openMenu($event, game)"
                            @missing-body="onGameBodyMissing"
                        />
                    </div>
                </section>

                <!-- 一个类型一个区块：数量为 0 的类型整块不渲染（默认态也一样）；
                     不传 aspect = 卡片高度自适应：封面按正方形限制框缩放，卡片高就是封面高，
                     同一类型的封面形状一致，整行仍然齐平。
                     区块内按封面类型分组（词表顺序）：换类型的那张卡强制从新的一行开始，
                     保证一行里都是同一种封面类型（见 sectionCardStyle） -->
                <section
                    v-for="sec in visibleSections"
                    :id="`grp-${sec.type}`"
                    :key="sec.type"
                    class="games-sec"
                >
                    <h2 class="games-gh">{{ gameTypeLabel(sec.type) }}</h2>
                    <div class="games-grid">
                        <game-card
                            v-for="(game, index) in sec.games"
                            :key="game.id"
                            :game="game"
                            :style="sectionCardStyle(sec, index)"
                            @contextmenu="openMenu($event, game)"
                            @missing-body="onGameBodyMissing"
                        />
                    </div>
                </section>

                <!-- 空态：直接一行说明文字（最近游玩与所有类型区块都为空时） -->
                <p v-if="pageEmpty && !loading" class="games-empty">{{ emptyDescription }}</p>
            </div>
        </div>

        <!-- 回到顶部：页面滚过一屏的 1/4 后出现在右下角，点击即时回顶 -->
        <button
            v-show="showTop"
            class="games-top-btn"
            type="button"
            aria-label="回到顶部"
            title="回到顶部"
            @click="backToTop"
        >
            <svg
                viewBox="0 0 24 24"
                width="20"
                height="20"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <path d="M4.5 14.5L12 9l7.5 5.5" />
            </svg>
        </button>

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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
    guideEntryPath,
    guidePdfPath,
    listGamesAPI,
    listRecentGamesAPI,
    setGamePlaytimeAPI,
    setGameProgressAPI,
} from "@/api/games";
import { CARD_ASPECT_RAIL } from "@/constants/gameCardAspect";
import { coverTypesFor } from "@/constants/coverStyles";
import {
    GAME_PROGRESS_LIST,
    PROGRESS_COMPLETED,
    PROGRESS_IN_PROGRESS,
    PROGRESS_NOT_STARTED,
} from "@/constants/gameProgress";
import { gameTypeLabel } from "@/constants/gameTypes";
import { useGameTypesStore } from "@/store/gameTypes";
import { ensureGameAssetSw } from "@/utils/gameAssetCache";
import { noticeAction } from "@/utils/confirm";
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

// 类型筛选下拉的候选顺序：以 /status.game_types 为准（后端单一来源）。
// 状态接口还没回来或失败时，用当前列表里实际出现的类型兜底，保证只读页面仍可用。
const gameTypesStore = useGameTypesStore();
const typeOrder = computed(() => {
    const order = [...gameTypesStore.gameTypes];
    const seen = new Set(order);
    for (const game of games.value) {
        if (game.category && !seen.has(game.category)) {
            seen.add(game.category);
            order.push(game.category);
        }
    }
    return order;
});

// 类型筛选下拉的选项：「全部」+ 当前类型；组件负责输入时的不区分大小写过滤
const typeFilterOptions = computed(() => [
    { value: "", label: "全部游戏类型" },
    ...typeOrder.value.map((type) => ({ value: type, label: gameTypeLabel(type) })),
]);

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

/** 侧栏计数、统计块、分组区块共用的筛选口径：进度 + 关键词。
    类型下拉不进这里——它只控制「显示哪一个类型区块」，不影响计数与统计。 */
function matchBase(game) {
    if (activeProgress.value && (game.progress || PROGRESS_NOT_STARTED) !== activeProgress.value) {
        return false;
    }
    const query = keyword.value.trim().toLowerCase();
    return !(query && !game.name.toLowerCase().includes(query));
}

/** 各类型命中数（进度 + 关键词口径），侧栏计数直接用；没出现的类型显式置 0 */
const countsByType = computed(() => {
    const counts = new Map();
    for (const type of typeOrder.value) {
        counts.set(type, 0);
    }
    for (const game of games.value) {
        if (matchBase(game)) {
            const type = game.category || "";
            counts.set(type, (counts.get(type) || 0) + 1);
        }
    }
    return counts;
});

// 统计块：总数 / 已通关 / 进行中 / 累计小时数（纯数字，无单位、无分母）
const statsData = computed(() => {
    let total = 0;
    let completed = 0;
    let inProgress = 0;
    let seconds = 0;
    for (const game of games.value) {
        if (!matchBase(game)) {
            continue;
        }
        total += 1;
        const progress = game.progress || PROGRESS_NOT_STARTED;
        if (progress === PROGRESS_IN_PROGRESS) {
            inProgress += 1;
        } else if (progress === PROGRESS_COMPLETED) {
            completed += 1;
        }
        if (progress !== PROGRESS_NOT_STARTED) {
            // 与 GameCard 同口径：只在标了进度后才有时长一说
            seconds += Number(game.play_seconds) || 0;
        }
    }
    return {
        total,
        completed,
        inProgress,
        hours: seconds > 0 ? Math.round(seconds / 3600) : 0,
    };
});

/** 最近游玩也吃同一套筛选：进度 + 关键词 + 类型下拉（搜索栏对最近游玩生效） */
const filteredRecent = computed(() =>
    recentGames.value.filter(
        (game) =>
            matchBase(game) &&
            (!activeType.value || game.category === activeType.value)
    )
);

/** 封面类型在一个类型区块内的排序位次：按 coverTypesFor 的词表顺序，
    没有封面类型（空）或词表外的 id 一律排最后。 */
function coverTypeRank(gameType, coverType) {
    const order = coverTypesFor(gameType);
    const index = order.indexOf(coverType || "");
    return index < 0 ? order.length : index;
}

// 页面区块：一个类型一个区块；数量为 0 的类型整块隐藏，类型下拉选中时只留该类型。
// 区块内按封面类型分组排序（词表顺序，空值最后），同一封面类型内保持原顺序——
// 数组 sort 是稳定的，同级不会被打乱。
const visibleSections = computed(() => {
    const sections = [];
    for (const type of typeOrder.value) {
        if (activeType.value && activeType.value !== type) {
            continue;
        }
        const matched = games.value.filter(
            (game) => matchBase(game) && (game.category || "") === type
        );
        if (!matched.length) {
            continue;
        }
        matched.sort(
            (a, b) =>
                coverTypeRank(type, a.cover_type) - coverTypeRank(type, b.cover_type)
        );
        sections.push({ type, games: matched });
    }
    return sections;
});

/** 卡片在网格里的额外样式：换封面类型的那张卡强制 grid-column-start: 1，
    网格自动布局会把它推到新的一行开头——这样一行内只会出现同一种封面类型。 */
function sectionCardStyle(section, index) {
    if (index === 0) {
        return null;
    }
    const prev = section.games[index - 1];
    const current = section.games[index];
    if ((prev.cover_type || "") !== (current.cover_type || "")) {
        return { gridColumnStart: 1 };
    }
    return null;
}

// 全空兜底：最近游玩与所有类型区块都不可见时才出现
const pageEmpty = computed(
    () => !filteredRecent.value.length && !visibleSections.value.length
);

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
    return "暂无游戏，去「库存管理」里添加一个吧。";
});

/* —— 类型侧栏：藏滚动条 + 上下翻页箭头（模式与 SaveTreeView 的存档侧栏一致） —— */
const sideNavRef = ref(null);
const mainRef = ref(null);
const sideCanUp = ref(false);
const sideCanDown = ref(false);

function updateSidePaging() {
    const el = sideNavRef.value;
    if (!el) {
        sideCanUp.value = false;
        sideCanDown.value = false;
        return;
    }
    sideCanUp.value = el.scrollTop > 1;
    sideCanDown.value = el.scrollTop + el.clientHeight < el.scrollHeight - 1;
}

function scrollSideUp() {
    const el = sideNavRef.value;
    if (el) {
        el.scrollBy({ top: -el.clientHeight, behavior: "smooth" });
    }
}

function scrollSideDown() {
    const el = sideNavRef.value;
    if (el) {
        el.scrollBy({ top: el.clientHeight, behavior: "smooth" });
    }
}

/** 点击侧栏条目才跳转：即时定位，无平滑动画，也与主页面滚动无联动；
    点过的条目保持浅灰高亮，直到点击下一个 */
const activeSide = ref("");
const showTop = ref(false);

function jumpTo(id) {
    document.getElementById(id)?.scrollIntoView();
    activeSide.value = id;
}

function backToTop() {
    mainRef.value?.scrollTo({ top: 0 });
}

/** 主面板自己的滚动：控制「回到顶部」按钮与右键菜单关闭，与侧栏滚动互不牵连 */
function onMainScroll() {
    showTop.value = (mainRef.value?.scrollTop || 0) > 240;
    closeMenu();
}

// 列表条数变化（首次加载、增删、按类型过滤改高度）后重测箭头可见性
watch(
    [() => games.value.length, () => recentGames.value.length, () => gameTypesStore.gameTypes.length],
    () => nextTick(updateSidePaging),
    { deep: false }
);

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

/** 无本体卡片：不跳播放页，只提示先上传（本体由游戏管理页补传）。 */
function onGameBodyMissing() {
    noticeAction("请先上传游戏本体");
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

// 右键「攻略」：在新标签页顶层打开。资源接口需登录，同源的新标签会带上 session cookie。
// ZIP 攻略打开静态站入口 index.html；PDF 攻略直接交给浏览器内置查看器就地展示。
function openGuide() {
    const game = menu.value.game;
    if (!game) {
        return;
    }
    closeMenu();
    const url =
        game.guide_kind === "pdf" ? guidePdfPath(game.id) : guideEntryPath(game.id);
    // noopener：断开新页面与本站的 window.opener 引用
    window.open(url, "_blank", "noopener");
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

    loading.value = true;
    try {
        // SW 只用于封面/本体的缓存加速；初始化失败也不应挡住列表展示（见 gameAssetCache）
        await ensureGameAssetSw();
        // 类型注册表失败不挡列表：typeOrder 会退回列表里实际出现的类型
        await gameTypesStore.ensureLoaded();
        games.value = await listGamesAPI();
        // 最近游玩是锦上添花：单独兜错，失败只丢这一块，不能把整页带进 loadError 空态
        const recent = await listRecentGamesAPI().catch(() => []);
        recentGames.value = Array.isArray(recent) ? recent : [];
    } catch {
        loadError.value = true;
    } finally {
        loading.value = false;
        nextTick(updateSidePaging);
    }
});

onBeforeUnmount(() => {
    document.removeEventListener("contextmenu", onDocumentContextMenu, true);
    document.removeEventListener("click", onDocumentClick);
    document.removeEventListener("keydown", onDocumentKeydown);

});
</script>

<style scoped>
/* 占满内容区宽度（与游戏管理页一致），不设窄幅居中 */
.games-page {
    width: 100%;
}

/* 页骨架：左侧类型导航色块 + 右侧内容。**两个纵向滚动区完全独立**——
   侧栏列表自己滚、右侧内容自己滚，任何一边滚到边界都不会牵连另一边。
   外层 .content 有 28px 内边距：负外边距把壳顶到内容区四边（含底部），
   壳高恰好一屏（100vh），页面本身（文档）不再产生滚动条，滚动都发生在壳里 */
.games-shell {
    display: grid;
    grid-template-columns: 152px minmax(0, 1fr);
    height: 100vh;
    margin: -28px 0 -28px -28px;
}

.games-main {
    min-width: 0;
    height: 100%;
    /* 内容区自己的滚动条：与侧栏滚动彻底隔离 */
    overflow-y: auto;
    overscroll-behavior: contain;
    /* 下移与侧栏首项（最近游玩）的起始线对齐：侧栏容器内上边距为 14px */
    padding: 14px 0 28px 20px;
}

/* —— 类型侧栏：蓝灰大色块（与常驻侧栏同家族、比它浅两档），右缘一条分隔线，无圆角无边框 ——
   壳已经是固定一屏高，侧栏不再用 sticky，直接占满壳高；
   relative 是给上下翻页箭头的绝对定位当基准（少了它箭头会钉到视口上） */
.games-side {
    position: relative;
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: #e4ebf5;
    border-right: 1px solid #d3dcea;
    padding: 14px 8px 0;
}

/* 列表：藏滚动条（滚轮照常滚），overscroll-behavior 隔断与主页面的滚动联动；
   底部留 110px：翻到最后一项（H5）时箭头/边缘不会压住它 */
.games-side__nav {
    display: flex;
    flex-direction: column;
    gap: 1px;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    scrollbar-width: none;
    overscroll-behavior: contain;
    padding-bottom: 110px;
}

.games-side__nav::-webkit-scrollbar {
    display: none;
}

.games-side__link {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 10px;
    border-radius: 9px;
    font-size: 13px;
    line-height: 1.4;
    color: #3f4552;
    text-decoration: none;
}

/* 悬浮与点选：蓝灰化，并抵消容器横向内边距、左右都贴到色块边界 */
.games-side__link:hover {
    margin: 0 -8px;
    padding: 7px 18px;
    border-radius: 0;
    background: rgba(15, 40, 90, 0.06);
}

.games-side__link--active {
    margin: 0 -8px;
    padding: 7px 18px;
    border-radius: 0;
    background: rgba(15, 40, 90, 0.09);
}

.games-side__link--active:hover {
    background: rgba(15, 40, 90, 0.1);
}

/* 选中项已经有深色底纹，不再额外画焦点环；否则浏览器默认的黑色外框会显得多余。 */
.games-side__link:focus-visible {
    outline: none;
}

/* 名称不换行，超长省略号 */
.games-side__name {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* 计数：裸数字（无边框无白底），等宽数字避免行尾跳动 */
.games-side__count {
    flex: none;
    font-size: 11px;
    line-height: 16px;
    color: #8b97ad;
    font-variant-numeric: tabular-nums;
    text-align: right;
}

/* 翻页箭头：浮在列表两端，不占行高；
   只在对应方向还能滚时出现（见 script 的 updateSidePaging）。
   不加渐变遮罩——遮罩会变成一条横贯列表的虚影条 */
.games-side__page {
    position: absolute;
    left: 8px;
    right: 8px;
    z-index: 2;
    display: flex;
    justify-content: center;
    padding: 2px 0;
}

.games-side__page--up {
    top: 0;
}

.games-side__page--down {
    bottom: 0;
}

/* —— 统计块：蓝雾面玻璃样式（半透明 + 模糊，与类型侧栏同族底色），块宽与搜索栏等宽 —— */
.games-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    width: 664px;
    max-width: 100%;
    margin-bottom: 14px;
}

.games-stat {
    background: rgba(232, 240, 250, 0.6);
    backdrop-filter: blur(6px);
    border: 1px solid #d3deee;
    /* 圆角与搜索栏控件一致 */
    border-radius: 4px;
    padding: 12px 14px;
    box-shadow: 0 3px 12px rgba(30, 60, 120, 0.09);
}

.games-stat__v {
    font-family: ui-monospace, Consolas, monospace;
    font-weight: 700;
    font-size: 20px;
    line-height: 1.2;
    color: #22314a;
    font-variant-numeric: tabular-nums;
}

.games-stat__l {
    margin-top: 2px;
    font-size: 11.5px;
    letter-spacing: 2px;
    color: #8593ab;
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

/* 游戏类型分隔标题：4px 品牌色竖条 + 标题，不带数量；
   「最近游玩」与各类型用同一份样式 */
.games-gh {
    /* 类型标题即分隔粗线：色带左缘拉到类型侧栏（抵消 .games-main 的左内边距），
       右缘到本列自己的滚动条为止（右侧不再用负外边距——内容区是独立滚动容器，
       负边距会撑出横向滚动条） */
    margin: 24px 0 14px -20px;
    display: flex;
    align-items: center;
    font-size: 16px;
    font-weight: 600;
    color: #3f4552;
    background: #e6e8ec;
    padding: 8px 14px;
}

/* 统计与搜索栏之间的第一个标题收一下上边距 */
.games-sec:first-of-type .games-gh {
    margin-top: 4px;
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

.games-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    /* 行间距要容得下封面下的名称与状态行 */
    column-gap: 14px;
    row-gap: 22px;
}

/* 空态：最近游玩与所有类型区块都为空时的一行说明 */
.games-empty {
    margin: 0;
    font-size: 13px;
    line-height: 1.6;
    color: #64748b;
}

/* 窄屏：侧栏退回顶部成横条，统计铺满 */
@media (max-width: 900px) {
    .games-shell {
        grid-template-columns: 1fr;
        grid-template-rows: auto minmax(0, 1fr);
        margin: -28px -28px -28px;
    }

    .games-side {
        height: auto;
        max-height: 220px;
        border-right: 0;
        border-bottom: 1px solid #d3dcea;
        flex-direction: column;
    }

    .games-side__nav {
        padding-bottom: 8px;
    }

    .games-main {
        padding-left: 0;
    }

    .games-stats {
        width: 100%;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    }
}

/* 回到顶部：固定在内容区右下角，白底圆钮与色块风格一致 */
.games-top-btn {
    position: fixed;
    right: 28px;
    bottom: 36px;
    z-index: 30;
    width: 40px;
    height: 40px;
    border: 1px solid #e2e5e9;
    border-radius: 50%;
    background: #ffffff;
    color: #5d6b7a;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 6px 16px rgba(20, 35, 60, 0.12);
    transition: color 0.15s ease, border-color 0.15s ease;
}

.games-top-btn:hover {
    color: var(--brand-accent);
    border-color: var(--brand-accent);
}
</style>
