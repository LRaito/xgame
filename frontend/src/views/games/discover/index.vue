<template>
    <div class="game-discover">
        <!-- 页头标签：普通按钮 + aria-pressed，左右键留给当前标签里的分页条 -->
        <app-segmented
            v-model="activeTab"
            class="game-discover__tabs"
            :options="TABS"
            size="lg"
            aria-label="游戏名录或榜单"
        />

        <!-- 游戏名录 -->
        <section v-show="activeTab === 'search'" class="game-discover__panel">
            <div class="game-discover__toolbar">
                <app-type-select
                    v-model="searchConsole"
                    class="game-discover__console"
                    placeholder="游戏类型"
                    clearable
                    :options="searchTypeOptions"
                    @change="searchNow"
                />
                <el-input
                    v-model="keyword"
                    class="game-discover__keyword"
                    placeholder="搜索中文名或英文名"
                    clearable
                    @keyup.enter="searchNow"
                    @input="onKeywordInput"
                    @clear="onKeywordClear"
                />
            </div>

            <div
                ref="searchWrapEl"
                v-loading="searchLoading"
                class="game-discover__body"
                :style="{ height: searchWrapHeight }"
            >
                <table v-if="searchItems.length" class="game-discover__table">
                    <thead>
                        <tr>
                            <th class="game-discover__col-console">游戏类型</th>
                            <th class="game-discover__col-zh">中文名</th>
                            <th>英文名</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="item in searchItems" :key="item.id">
                            <td class="game-discover__nowrap">{{ item.console }}</td>
                            <td>
                                <app-truncatable-name>
                                    <template
                                        v-for="(seg, index) in highlight(item.zh)"
                                        :key="index"
                                    >
                                        <mark v-if="seg.hit">{{ seg.text }}</mark>
                                        <template v-else>{{ seg.text }}</template>
                                    </template>
                                </app-truncatable-name>
                            </td>
                            <td>
                                <app-truncatable-name>
                                    <template
                                        v-for="(seg, index) in highlight(item.en)"
                                        :key="index"
                                    >
                                        <mark v-if="seg.hit">{{ seg.text }}</mark>
                                        <template v-else>{{ seg.text }}</template>
                                    </template>
                                </app-truncatable-name>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <app-empty v-else :description="searchEmptyDescription" />
            </div>

            <!-- 翻页放在表格下面；只有一页时不出现（AppPagination 自己判）。
                 切到榜单标签时把键盘翻页关掉：分页条的左右键监听挂在 window 上，
                 隐藏着也会抢键（keyboard 就是为这种同页多列表/隐藏列表留的开关）。 -->
            <app-pagination
                v-model:page="page"
                :total="total"
                :page-size="pageSize"
                :keyboard="activeTab === 'search'"
                previous-shortcut="discover.page.prev"
                next-shortcut="discover.page.next"
                @change="loadSearch"
            />
        </section>

        <!-- 游戏榜单 -->
        <section v-show="activeTab === 'ranking'" class="game-discover__panel">
            <div class="game-discover__toolbar">
                <app-type-select
                    v-model="rankingConsole"
                    class="game-discover__console"
                    placeholder="全部类型"
                    clearable
                    :disabled="!rankingConsoles.length"
                    :options="rankingTypeOptions"
                    @change="rankingNow"
                />

                <!-- 榜单搜索走后端：300ms 防抖，回车立即请求；清空也回到第一页 -->
                <el-input
                    v-model="rankingKeyword"
                    class="game-discover__keyword"
                    placeholder="搜索中文名或英文名"
                    clearable
                    @input="onRankingKeywordInput"
                    @keyup.enter="rankingNow"
                    @clear="onRankingKeywordClear"
                />

                <app-select
                    v-model="rankingLibrary"
                    class="game-discover__library"
                    placeholder="库存类型"
                    clearable
                    :options="rankingLibraryOptions"
                    @change="rankingNow"
                />
            </div>

            <div
                ref="rankingWrapEl"
                v-loading="rankingLoading"
                class="game-discover__body"
                :style="{ height: rankingWrapHeight }"
            >
                <table
                    v-if="rankingItems.length"
                    class="game-discover__table"
                    :class="{ 'game-discover__table--all': !rankingConsole }"
                >
                    <thead>
                        <tr>
                            <th class="game-discover__col-rank">序号</th>
                            <th class="game-discover__col-score">评分</th>
                            <!-- 清空机种后是跨机种榜单，必须显示类型，否则看不出每行属于哪台机器 -->
                            <th
                                v-if="!rankingConsole"
                                class="game-discover__col-ranking-console"
                            >
                                游戏类型
                            </th>
                            <th class="game-discover__col-zh">中文名</th>
                            <th>英文名</th>
                            <th class="game-discover__col-ids">卡带ID</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="{ item, rank } in rankingPageRows"
                            :key="`${item.platform}-${rank}`"
                        >
                            <td class="game-discover__rank">{{ rank }}</td>
                            <td class="game-discover__score">
                                {{ formatRankingScore(item.score) }}
                            </td>
                            <td v-if="!rankingConsole" class="game-discover__nowrap">
                                {{ rankingPlatformLabel(item.platform) }}
                            </td>
                            <td>
                                <!-- 回填后仍可能没有中文名：显示 — -->
                                <span v-if="!item.zh" class="game-discover__none">—</span>
                                <app-truncatable-name v-else>{{ item.zh }}</app-truncatable-name>
                            </td>
                            <td>
                                <app-truncatable-name>{{ item.en }}</app-truncatable-name>
                            </td>
                            <td class="game-discover__ids-cell">
                                <span v-if="!item.cartridges.length" class="game-discover__none">
                                    —
                                </span>
                                <div v-else class="game-discover__ids">
                                    <!-- 每盘卡带一个按钮：在库按进度着色并直接进播放页；
                                         不在库就弹添加游戏弹框，名称/卡带 ID/类型自动填好 -->
                                    <app-button
                                        v-for="(cartridge, index) in item.cartridges"
                                        :key="`${cartridge.cartridge_id}-${index}`"
                                        variant="secondary"
                                        size="sm"
                                        block
                                        class="game-discover__cartridge-btn"
                                        :class="cartridgeToneClass(cartridge)"
                                        :title="cartridge.cartridge_id"
                                        @click="onCartridgeClick(item, cartridge)"
                                    >
                                        <span class="game-discover__cartridge-label">
                                            {{ cartridge.cartridge_id }}
                                        </span>
                                    </app-button>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <app-empty v-else :description="rankingEmptyDescription" />
            </div>

            <!-- 与名录区同款的分页条；翻页由后端重新取一页。
                 键盘翻页同样只在榜单标签亮着时开着（同页两个分页条，监听都挂在 window 上） -->
            <app-pagination
                v-model:page="rankingPage"
                :total="rankingPageTotal"
                :page-size="rankingPageSize"
                :keyboard="activeTab === 'ranking'"
                previous-shortcut="discover.page.prev"
                next-shortcut="discover.page.next"
                @change="loadRanking"
            />
        </section>

        <!-- 榜单里点「库存之外」的卡带：与游戏管理页同一个添加弹框，预填名称/卡带ID/类型 -->
        <game-form-dialog
            v-model="formVisible"
            mode="create"
            :initial="formInitial"
            @saved="loadRanking"
        />
    </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
    getGameRankingAPI,
    listRankingConsolesAPI,
    listSearchConsolesAPI,
    searchGamesAPI,
} from "@/api/games";
import { useAdaptiveRows } from "@/utils/adaptiveRows";
import { noticeAction } from "@/utils/confirm";
import GameFormDialog from "@components/games/GameFormDialog.vue";
import {
    PROGRESS_COMPLETED,
    PROGRESS_IN_PROGRESS,
} from "@/constants/gameProgress";

const TABS = [
    { label: "游戏名录", value: "search" },
    { label: "游戏榜单", value: "ranking" },
];
// 行高固定、行数自适应（见 utils/adaptiveRows.js）：行高 40px 与游戏管理一致，
// 后端两条接口的 page_size 上限都是 100。行之外的表格固定开销 = 表头 44 + 顶框/底线/行间线
// 合计 12；底部开销 = 分页条（上边距 20 + 高 32）+ 内容区下边距 28 = 80。
// 行高在样式里写死（行盒 20 + 上下各 10 内边距），全屏与非全屏行高完全一致，
// 只有行数不同；排不满整行的余量留在最后一行和分页条之间。
const ROW_HEIGHT = 40;
const TABLE_EXTRA = 56;
const PAGE_SIZE_MAX = 100;
// 量到之前的占位行数（与旧版每页条数一致，高度别闪跳）
const INITIAL_ROWS = 10;
// 防抖时长：与游戏管理页的关键词筛选一致
const KEYWORD_DEBOUNCE = 300;

const route = useRoute();
const router = useRouter();

/**
 * 标签状态完全由 URL 驱动：?tab=ranking 是榜单，其余（含缺失/非法值）是名录。
 * 切换用 replace，避免来回点标签堆一长串历史。
 */
const activeTab = computed({
    get: () => (route.query.tab === "ranking" ? "ranking" : "search"),
    set: (value) => {
        const query = { ...route.query };
        if (value === "ranking") {
            query.tab = "ranking";
        } else {
            delete query.tab;
        }
        router.replace({ path: "/games/discover", query });
    },
});

// --------------------------------------------------------------------------
// 游戏名录
// --------------------------------------------------------------------------

const keyword = ref("");
const searchConsole = ref("");
const searchConsoles = ref([]);
// 名录机种下拉：「全部」+ 后端机种；组件负责输入时的不区分大小写过滤
const searchTypeOptions = computed(() => [
    { value: "", label: "全部游戏类型" },
    ...searchConsoles.value.map((item) => ({ value: item.id, label: item.name })),
]);
const searchItems = ref([]);
const total = ref(0);
const page = ref(1);
const searchLoading = ref(false);
const searchIndexed = ref(true);
const searchError = ref(false);

let keywordTimer = 0;
// Element Plus 点 X 会先 emit clear、再 emit input：clear 已立即查询，跳过随后那次防抖
let skipKeywordInput = false;
// 请求序号：防抖 + 快速改条件时，慢的旧响应不能覆盖新结果
let searchSeq = 0;

const searchEmptyDescription = computed(() => {
    if (searchError.value) {
        return "检索失败，请稍后重试。";
    }
    if (!searchIndexed.value) {
        return "尚未构建游戏名录。请在项目根目录执行一次 make index，然后刷新本页。";
    }
    return "没有匹配的游戏。";
});

// 列表容器永远按「一页满行」定高：最后一页数据不满时高度也不缩，分页条位置固定不动；
// 行高全屏/非全屏一致，排不满整行的余量落在表格下方
const searchWrapHeight = computed(
    () => `${TABLE_EXTRA + pageSize.value * ROW_HEIGHT}px`
);
const rankingWrapHeight = computed(
    () => `${TABLE_EXTRA + rankingPageSize.value * ROW_HEIGHT}px`
);

// 名录区每页行数自适应。窗口尺寸变化导致行数变了就重新取当前页（页码交给请求自身收敛）
const searchWrapEl = ref(null);
const { rows: pageSize, measure: measureSearchRows } = useAdaptiveRows(
    {
        rowHeight: ROW_HEIGHT,
        extraHeight: TABLE_EXTRA,
        reservePx: 80,
        maxRows: PAGE_SIZE_MAX,
        initialRows: INITIAL_ROWS,
    },
    () => loadSearch()
);

/**
 * 命中片段高亮：把查询词里每个空白分隔的词按不区分大小写切成片段，
 * 命中的片段标记 hit=true，模板里渲染成 <mark>。
 * 刻意返回片段数组而不是拼 HTML 字符串——这里的文本来自外部 CSV 名录，绝不能走 v-html。
 */
function highlight(text) {
    const words = keyword.value
        .split(/\s+/)
        .map((word) => word.replace(/\*+$/, ""))
        .filter((word) => word.length > 0);
    const body = text || "";
    if (!body || !words.length) {
        return [{ text: body, hit: false }];
    }
    const lower = body.toLowerCase();
    const segments = [];
    let cursor = 0;
    while (cursor < body.length) {
        let hitAt = -1;
        let hitWord = "";
        for (const word of words) {
            const found = lower.indexOf(word.toLowerCase(), cursor);
            if (found >= 0 && (hitAt < 0 || found < hitAt)) {
                hitAt = found;
                hitWord = word;
            }
        }
        if (hitAt < 0) {
            segments.push({ text: body.slice(cursor), hit: false });
            break;
        }
        if (hitAt > cursor) {
            segments.push({ text: body.slice(cursor, hitAt), hit: false });
        }
        segments.push({ text: body.slice(hitAt, hitAt + hitWord.length), hit: true });
        cursor = hitAt + hitWord.length;
    }
    return segments;
}

async function loadSearch() {
    const seq = ++searchSeq;
    searchLoading.value = true;
    try {
        const data = await searchGamesAPI({
            q: keyword.value.trim(),
            console_id: searchConsole.value || undefined,
            page: page.value,
            page_size: pageSize.value,
        });
        if (seq !== searchSeq) {
            return;
        }
        searchIndexed.value = data.indexed;
        searchItems.value = data.items || [];
        total.value = data.total || 0;
        page.value = data.page || 1;
        // page_size 由本页自适应计算，后端不会改小（上限同是 100），别拿响应覆盖回来
        searchError.value = false;
    } catch {
        if (seq !== searchSeq) {
            return;
        }
        searchItems.value = [];
        total.value = 0;
        searchError.value = true;
    } finally {
        if (seq === searchSeq) {
            searchLoading.value = false;
        }
    }
}

/** 改条件都要回到第 1 页，否则会停在一个新结果里不存在的页码上。 */
function searchNow() {
    clearTimeout(keywordTimer);
    page.value = 1;
    loadSearch();
}

function onKeywordInput() {
    if (skipKeywordInput) {
        skipKeywordInput = false;
        return;
    }
    clearTimeout(keywordTimer);
    keywordTimer = setTimeout(searchNow, KEYWORD_DEBOUNCE);
}

/** 点 X 清空：立即查询；紧随其后的 input 已由 skipKeywordInput 跳过。 */
function onKeywordClear() {
    skipKeywordInput = true;
    searchNow();
}

// --------------------------------------------------------------------------
// 游戏榜单
// --------------------------------------------------------------------------

const rankingConsoles = ref([]);
const rankingTypeOptions = computed(() =>
    rankingConsoles.value.map((item) => ({ value: item.platform, label: item.label }))
);
// 跨机种榜单的「游戏类型」列：机种键 → 统一显示名（与下拉共用一份清单）
const rankingConsoleLabels = computed(() =>
    Object.fromEntries(
        rankingConsoles.value.map((item) => [item.platform, item.label])
    )
);
function rankingPlatformLabel(platform) {
    return rankingConsoleLabels.value[platform] || platform || "";
}

// 只有可玩机种才能直接当 game_type 预填；sega / mame 这类兜底键不开放上传
const rankingPlatformPlayable = computed(() =>
    Object.fromEntries(
        rankingConsoles.value.map((item) => [item.platform, Boolean(item.playable)])
    )
);
function canPrefillGameType(platform) {
    return Boolean(rankingPlatformPlayable.value[platform]);
}
// 评分只在这里格式化：后端返回原始 double，页面固定两位小数（四舍五入）。
function formatRankingScore(score) {
    if (score === null || score === undefined || score === "") {
        return "—";
    }
    const value = Number(score);
    return Number.isFinite(value) ? value.toFixed(2) : "—";
}
const rankingConsole = ref("");
// 当前页的榜单行（后端分页；不再整份取回）
const rankingItems = ref([]);
const rankingPage = ref(1);
// 库存类型："" = 全部；"in" = 库存之内；"out" = 库存之外
const rankingLibrary = ref("");
const rankingLibraryOptions = [
    { value: "in", label: "库存之内" },
    { value: "out", label: "库存之外" },
];
// 榜单搜索词走后端，输入防抖 300ms
const rankingKeyword = ref("");
// 后端返回的计数：分页总数、关键词命中数
const rankingPageTotal = ref(0);
const rankingMatchedTotal = ref(0);
const rankingLoading = ref(false);
const rankingIndexed = ref(true);
const rankingAvailable = ref(true);
const rankingError = ref(false);

// 榜单只在第一次切到榜单标签时拉清单，来回切标签不重复请求
let rankingLoaded = false;
let rankingSeq = 0;
let rankingKeywordTimer = null;
// 同名录框：clear 已立即查询，跳过其后的 input 防抖
let skipRankingKeywordInput = false;

// 添加游戏弹框：点「库存之外」的卡带时打开，保存后刷新当前页、不离开榜单
const formVisible = ref(false);
const formInitial = ref(null);

/** 卡带按钮的配色：不在库灰；在库按当前用户进度（未开始蓝 / 进行中紫 / 已通关绿）。 */
function cartridgeToneClass(cartridge) {
    if (!cartridge.in_library) {
        return "game-discover__cartridge-btn--out";
    }
    if (cartridge.progress === PROGRESS_COMPLETED) {
        return "game-discover__cartridge-btn--completed";
    }
    if (cartridge.progress === PROGRESS_IN_PROGRESS) {
        return "game-discover__cartridge-btn--in-progress";
    }
    return "game-discover__cartridge-btn--not-started";
}

/** 在库：有本体直接进播放页，无本体提示先上传；不在库：弹添加弹框并预填。 */
function onCartridgeClick(item, cartridge) {
    if (cartridge.in_library) {
        if (!cartridge.has_body || !cartridge.path) {
            noticeAction("请先上传游戏本体");
            return;
        }
        router.push(cartridge.path);
        return;
    }
    formInitial.value = {
        name: (item.zh || item.en || "").trim(),
        cartridgeId: cartridge.cartridge_id,
        gameType: canPrefillGameType(item.platform) ? item.platform : "",
    };
    formVisible.value = true;
}

// 每页行数自适应（与名录区同一套行高与开销）。行数变化时重新取当前页。
const rankingWrapEl = ref(null);
const { rows: rankingPageSize, measure: measureRankingRows } = useAdaptiveRows(
    {
        rowHeight: ROW_HEIGHT,
        extraHeight: TABLE_EXTRA,
        reservePx: 80,
        maxRows: PAGE_SIZE_MAX,
        initialRows: INITIAL_ROWS,
    },
    onRankingRowsChange
);

// 当前页的展示行：名次 = 前面的页 + 页内位置，不落库。
const rankingPageRows = computed(() =>
    rankingItems.value.map((item, index) => ({
        item,
        rank: (rankingPage.value - 1) * rankingPageSize.value + index + 1,
    }))
);

function onRankingRowsChange() {
    if (!rankingLoaded) {
        return;
    }
    const pages = Math.max(
        1,
        Math.ceil(rankingPageTotal.value / rankingPageSize.value)
    );
    if (rankingPage.value > pages) {
        rankingPage.value = pages;
    }
    loadRanking();
}

const rankingEmptyDescription = computed(() => {
    if (rankingError.value) {
        return "榜单加载失败，请稍后重试。";
    }
    if (!rankingIndexed.value) {
        return "尚未构建游戏名录与游戏榜单。请在项目根目录执行一次 make index，然后刷新本页。";
    }
    if (!rankingAvailable.value) {
        return "榜单尚未加载。请检查榜单 CSV 后执行 make index，然后刷新本页。";
    }
    if (!rankingConsoles.value.length) {
        return "榜单暂无数据。";
    }
    const rawKeyword = rankingKeyword.value.trim();
    const libraryLabel =
        rankingLibrary.value === "in"
            ? "库存之内"
            : rankingLibrary.value === "out"
                ? "库存之外"
                : "";
    if (rawKeyword && rankingMatchedTotal.value === 0) {
        return `没有匹配到中英文名含「${rawKeyword}」的游戏。`;
    }
    if (rawKeyword && libraryLabel && rankingPageTotal.value === 0) {
        return `匹配「${rawKeyword}」的游戏不在所选库存范围内。`;
    }
    if (libraryLabel && rankingPageTotal.value === 0) {
        return rankingConsole.value
            ? `这个类型下没有${libraryLabel}的游戏。`
            : `全机种下没有${libraryLabel}的游戏。`;
    }
    return rankingConsole.value ? "该游戏类型暂无榜单数据。" : "全部类型暂无榜单数据。";
});

/** 条件变化：回到第 1 页并重新请求。 */
function rankingNow() {
    clearTimeout(rankingKeywordTimer);
    rankingPage.value = 1;
    loadRanking();
}

function onRankingKeywordInput() {
    if (skipRankingKeywordInput) {
        skipRankingKeywordInput = false;
        return;
    }
    clearTimeout(rankingKeywordTimer);
    rankingKeywordTimer = setTimeout(rankingNow, KEYWORD_DEBOUNCE);
}

/** 点 X 清空：立即查询；紧随其后的 input 已由 skipRankingKeywordInput 跳过。 */
function onRankingKeywordClear() {
    skipRankingKeywordInput = true;
    rankingNow();
}

async function loadRankingConsoles() {
    if (rankingLoaded) {
        return;
    }
    rankingLoaded = true;
    rankingLoading.value = true;
    try {
        const data = await listRankingConsolesAPI();
        rankingIndexed.value = data.indexed;
        rankingAvailable.value = data.has_ranking;
        rankingConsoles.value = data.consoles || [];
        // 默认不选中任何类型：打开页面即看全部机种（跨机种榜单）
        rankingConsole.value = "";
        rankingError.value = false;
    } catch {
        rankingConsoles.value = [];
        rankingError.value = true;
        // 失败不算「加载过」：切走再切回来会重试一次
        rankingLoaded = false;
    } finally {
        rankingLoading.value = false;
    }
    // 页面默认不选类型；清单加载失败就不再打榜单接口
    if (!rankingError.value) {
        rankingPage.value = 1;
        await loadRanking();
    }
}

async function loadRanking() {
    const seq = ++rankingSeq;
    rankingLoading.value = true;
    try {
        const data = await getGameRankingAPI({
            console: rankingConsole.value || undefined,
            keyword: rankingKeyword.value.trim() || undefined,
            in_library:
                rankingLibrary.value === "in"
                    ? true
                    : rankingLibrary.value === "out"
                        ? false
                        : undefined,
            page: rankingPage.value,
            page_size: rankingPageSize.value,
        });
        if (seq !== rankingSeq) {
            return;
        }
        rankingIndexed.value = data.indexed;
        rankingAvailable.value = data.has_ranking;
        rankingItems.value = data.items || [];
        rankingPage.value = data.page || 1;
        rankingPageTotal.value = data.total || 0;
        rankingMatchedTotal.value = data.matched_total || 0;
        rankingError.value = false;
    } catch {
        if (seq !== rankingSeq) {
            return;
        }
        rankingItems.value = [];
        rankingPageTotal.value = 0;
        rankingMatchedTotal.value = 0;
        rankingError.value = true;
    } finally {
        if (seq === rankingSeq) {
            rankingLoading.value = false;
        }
    }
}

// 直接访问 ?tab=ranking 或前进/后退回到榜单时，同样要按需加载；
// 两个区块都重测一遍行数——v-show 藏着的那个会被 offsetParent 守卫跳过，
// 可见的那个按当前视口重算（浏览器全屏/非全屏切换后，再切标签必须跟上新行数）
watch(
    activeTab,
    (value) => {
        nextTick(() => {
            measureSearchRows(searchWrapEl.value);
            measureRankingRows(rankingWrapEl.value);
        });
        if (value === "ranking") {
            loadRankingConsoles();
        }
    },
    { immediate: true }
);

onMounted(async () => {
    try {
        const data = await listSearchConsolesAPI();
        searchConsoles.value = data.consoles || [];
        searchIndexed.value = data.indexed;
    } catch {
        searchConsoles.value = [];
    }
    // 先量视口算出每页行数，首屏请求才知道带多大 page_size
    measureSearchRows(searchWrapEl.value);
    await loadSearch();
});
</script>

<style scoped>
/* 页面纵向铺满：内容区上下各 28px 内边距，页面根按 100vh−56 占满后再不滚动；
   可见的那一列（名录/榜单二选一）填满剩余高度，把行数自适应的空间吃满 */
.game-discover {
    display: flex;
    flex-direction: column;
    min-height: calc(100vh - 56px);
}

.game-discover__panel {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
}

/* 页头标签共用 AppSegmented 的尺寸与选中态，这里只留与下方工具条的间距 */
.game-discover__tabs {
    margin-bottom: 20px;
}

.game-discover__toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    align-items: center;
}

/* 两个标签各有一个搜索框，共用这套宽度（机种下拉也一样宽） */
.game-discover__keyword,
.game-discover__console {
    width: 240px;
}

.game-discover__library {
    width: 160px;
}

/* 命中平台库存的榜单行不再给名称加链接效果：跳转与添加入口统一放到卡带按钮上 */

/* 列表高度由「实际显示的行数 × 固定行高」决定（模板 :style 绑定；min-height 兜空态）：
   行数按视口高度自适应（utils/adaptiveRows.js），行高全屏/非全屏一致 */
.game-discover__body {
    min-height: 200px;
}

/* 固定布局 + 百分比列宽：再长的名字也只在自己格子里省略，表格不会被撑宽。
   注意别在这里加 overflow: hidden——展开的名称浮层要能盖到表格外面去，
   四角圆角和游戏管理那张表一样靠表头/末行自己收 */
.game-discover__table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
}


/* 没有 overflow 兜底，四角靠表头/末行的圆角自己收（表头有底色，方角会顶出表格圆角） */
.game-discover__table thead th:first-child {
    border-top-left-radius: 11px;
}

.game-discover__table thead th:last-child {
    border-top-right-radius: 11px;
}

.game-discover__table tbody tr:last-child td:first-child {
    border-bottom-left-radius: 11px;
}

.game-discover__table tbody tr:last-child td:last-child {
    border-bottom-right-radius: 11px;
}

/* **行高固定 40px（行盒 20px + 上下各 10px 内边距），与游戏管理一致；
   全屏与非全屏行高相同，只有行数不同**。
   表头仍是 12px 内边距（行高 44px），算在 TABLE_EXTRA 里。
   line-height 显式写死，两张表才不会因为字体默认值不同而差几个像素；
   榜单那边唯一的变量是卡带 ID 药丸，它的高度压在 20px（见 CopyButton 的 pill 样式） */
.game-discover__table td {
    padding: 10px 16px;
    font-size: 14px;
    line-height: 20px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    word-break: break-word;
}

.game-discover__table th {
    padding: 12px 16px;
    font-size: 14px;
    line-height: 20px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    background: #f8fafc;
    color: var(--text-muted);
    font-weight: 500;
    white-space: nowrap;
}

.game-discover__table tbody tr:last-child td {
    border-bottom: none;
}

/* 够放下最长的游戏类型名「康懋达 VIC-20」（约 140px 文字 + 左右各 16px 内边距） */
.game-discover__col-console {
    width: 220px;
}

.game-discover__col-zh {
    width: 32%;
}

.game-discover__col-rank {
    width: 88px;
}

.game-discover__col-score {
    width: 76px;
}

/* 跨机种榜单才出现的「游戏类型」列；比名录区窄，给中英文名留空间 */
.game-discover__col-ranking-console {
    width: 150px;
}

.game-discover__col-ids {
    width: 30%;
}

/* 跨机种榜单多一列「游戏类型」，压缩中文名/卡带 ID，给英文名留空间 */
.game-discover__table--all .game-discover__col-zh {
    width: 26%;
}

.game-discover__table--all .game-discover__col-ids {
    width: 26%;
}

.game-discover__nowrap {
    color: var(--text-muted);
    white-space: nowrap;
}

.game-discover__table mark {
    background: #fde68a;
    color: inherit;
    border-radius: 2px;
}

.game-discover__rank {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}

.game-discover__score {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}

.game-discover__none {
    color: var(--text-muted);
}

/* 0~2 个卡带按钮：固定两等分，单按钮也只占左半边；列宽由表头固定，不随 ID 长短变化。
   按钮高 28px，所以这格上下内边距收到 6px，整行仍是 40px（6 + 28 + 6） */
.game-discover__table td.game-discover__ids-cell {
    padding-top: 6px;
    padding-bottom: 6px;
}

.game-discover__ids {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    align-items: center;
}

/* Element Plus 默认给相邻按钮加左边距，会把第二个按钮顶出半格 */
.game-discover__ids :deep(.el-button + .el-button) {
    margin-left: 0;
}

.game-discover__cartridge-btn {
    min-width: 0;
    --_btn-px: 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
}

.game-discover__cartridge-label {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
}

/* 白底描边、文字与边框同色；覆盖 AppButton 的私有配色变量。
   选择器带上父级与 .app-button，压过 .app-button--light 里的定义 */
.game-discover__ids .app-button.game-discover__cartridge-btn--in-progress {
    --_btn-secondary-fg: var(--app-color-in-progress);
    --_btn-secondary-border: var(--app-color-in-progress);
    --_btn-secondary-border-hover: var(--app-color-in-progress);
    --_btn-secondary-border-focus: var(--app-color-in-progress);
}

.game-discover__ids .app-button.game-discover__cartridge-btn--completed {
    --_btn-secondary-fg: var(--app-color-success);
    --_btn-secondary-border: var(--app-color-success);
    --_btn-secondary-border-hover: var(--app-color-success);
    --_btn-secondary-border-focus: var(--app-color-success);
}

.game-discover__ids .app-button.game-discover__cartridge-btn--not-started {
    --_btn-secondary-fg: var(--brand-accent);
    --_btn-secondary-border: var(--brand-accent);
    --_btn-secondary-border-hover: var(--brand-accent);
    --_btn-secondary-border-focus: var(--brand-accent);
}

/* 库存外：卡带 ID 与外框都用普通正文色 */
.game-discover__ids .app-button.game-discover__cartridge-btn--out {
    --_btn-secondary-fg: var(--app-text);
    --_btn-secondary-border: var(--app-text);
    --_btn-secondary-border-hover: var(--app-text);
    --_btn-secondary-border-focus: var(--app-text);
}
</style>
