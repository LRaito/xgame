<template>
    <div class="game-discover">
        <!-- 页头标签：普通按钮 + aria-pressed，左右键留给当前标签里的分页条 -->
        <app-segmented
            v-model="activeTab"
            class="game-discover__tabs"
            :options="TABS"
            size="lg"
            aria-label="游戏检索或榜单"
        />

        <!-- 游戏检索 -->
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
                    @clear="searchNow"
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
                    @change="loadRanking"
                />

                <!-- 榜单搜索：与检索区那个同一个 class（样式、位置、清空按钮都一样），但**纯前端**过滤
                     ——榜单是一个机种整份取回来的，逐字即时筛，不需要防抖、也不需要回车或清空的处理
                     （裸 v-model + clearable，computed 自己会跟着变） -->
                <el-input
                    v-model="rankingKeyword"
                    class="game-discover__keyword"
                    placeholder="搜索中文名或英文名"
                    clearable
                />

                <!-- 已入库比例，同时是「只看已入库」的开关：单击按下，榜单就只留命中库存的行，再点一下恢复。
                     数字由前端按已整份取回的 rankingItems 现算（榜单不分页），不再多打一次接口。
                     加载中先藏起来：rankingItems 在请求成功前不会清空，否则切机种会闪一下上一个机种的数字 -->
                <app-button
                    v-if="rankingTotal && !rankingLoading"
                    class="game-discover__stock"
                    variant="secondary"
                    size="sm"
                    :pressed="rankingInLibraryOnly"
                    @click="toggleInLibraryOnly"
                >
                    <span class="game-discover__stock-label">已入库</span>
                    <span class="game-discover__stock-value">
                        {{ rankingLinkedCount }} / {{ rankingTotal }}
                    </span>
                </app-button>
            </div>

            <div
                ref="rankingWrapEl"
                v-loading="rankingLoading"
                class="game-discover__body"
                :style="{ height: rankingWrapHeight }"
            >
                <table
                    v-if="rankingVisibleItems.length"
                    class="game-discover__table"
                    :class="{ 'game-discover__table--all': !rankingConsole }"
                >
                    <thead>
                        <tr>
                            <th class="game-discover__col-rank">排名</th>
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
                            v-for="item in rankingPagedItems"
                            :key="`${item.platform}-${item.rank}`"
                        >
                            <td class="game-discover__rank">{{ rankingDisplayRank(item) }}</td>
                            <td class="game-discover__score">
                                {{ formatRankingScore(item.score) }}
                            </td>
                            <td v-if="!rankingConsole" class="game-discover__nowrap">
                                {{ rankingPlatformLabel(item.platform) }}
                            </td>
                            <td>
                                <!-- 回填后仍可能没有中文名：显示 —，不渲染空链接 -->
                                <span v-if="!item.zh" class="game-discover__none">—</span>
                                <!-- 卡带 ID 与平台库存对上的行：中英文名是**真链接**（router-link 渲染成
                                     原生 <a href>），没截断时单击进播放页，Ctrl+点击 / 中键由浏览器自己开新标签页；
                                     截断时单击优先展开全名（AppTruncatableName 在捕获阶段拦掉默认跳转）。
                                     对上但还没上传本体的行保持链接样式，单击只弹提示、不进播放页；
                                     没对上的行就是纯文本 -->
                                <app-truncatable-name v-else>
                                    <router-link
                                        v-if="item.path && item.has_body"
                                        class="game-discover__link"
                                        :to="item.path"
                                    >
                                        {{ item.zh }}
                                    </router-link>
                                    <span
                                        v-else-if="item.path"
                                        class="game-discover__link"
                                        role="button"
                                        tabindex="0"
                                        @click="onMissingBodyLink"
                                        @keydown.enter.prevent="onMissingBodyLink"
                                    >
                                        {{ item.zh }}
                                    </span>
                                    <template v-else>{{ item.zh }}</template>
                                </app-truncatable-name>
                            </td>
                            <td>
                                <app-truncatable-name>
                                    <router-link
                                        v-if="item.path && item.has_body"
                                        class="game-discover__link"
                                        :to="item.path"
                                    >
                                        {{ item.en }}
                                    </router-link>
                                    <span
                                        v-else-if="item.path"
                                        class="game-discover__link"
                                        role="button"
                                        tabindex="0"
                                        @click="onMissingBodyLink"
                                        @keydown.enter.prevent="onMissingBodyLink"
                                    >
                                        {{ item.en }}
                                    </span>
                                    <template v-else>{{ item.en }}</template>
                                </app-truncatable-name>
                            </td>
                            <td>
                                <span v-if="!item.cartridge_ids.length" class="game-discover__none">
                                    —
                                </span>
                                <span v-else class="game-discover__ids">
                                    <copy-button
                                        v-for="cartridgeId in item.cartridge_ids"
                                        :key="cartridgeId"
                                        :text="cartridgeId"
                                        variant="pill"
                                    />
                                </span>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <app-empty v-else :description="rankingEmptyDescription" />
            </div>

            <!-- 与检索区同款的分页条：每页行数同样由视口高度自适应。**分页在前端做**——
                 一份榜单（一个机种）一次全取回来，翻页只是换页码、不再打接口。
                 键盘翻页同样只在榜单标签亮着时开着（同页两个分页条，监听都挂在 window 上） -->
            <app-pagination
                v-model:page="rankingPage"
                :total="rankingVisibleTotal"
                :page-size="rankingPageSize"
                :keyboard="activeTab === 'ranking'"
                previous-shortcut="discover.page.prev"
                next-shortcut="discover.page.next"
            />
        </section>
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

const TABS = [
    { label: "游戏检索", value: "search" },
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
 * 标签状态完全由 URL 驱动：?tab=ranking 是榜单，其余（含缺失/非法值）是检索。
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
// 游戏检索
// --------------------------------------------------------------------------

const keyword = ref("");
const searchConsole = ref("");
const searchConsoles = ref([]);
// 检索机种下拉：「全部」+ 后端机种；组件负责输入时的不区分大小写过滤
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
// 请求序号：防抖 + 快速改条件时，慢的旧响应不能覆盖新结果
let searchSeq = 0;

const searchEmptyDescription = computed(() => {
    if (searchError.value) {
        return "检索失败，请稍后重试。";
    }
    if (!searchIndexed.value) {
        return "尚未构建游戏索引。请在项目根目录执行一次 make index，然后刷新本页。";
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

// 检索区每页行数自适应。窗口尺寸变化导致行数变了就重新取当前页（页码交给请求自身收敛）
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
    clearTimeout(keywordTimer);
    keywordTimer = setTimeout(searchNow, KEYWORD_DEBOUNCE);
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
// 评分只在这里格式化：后端返回原始 double，页面固定两位小数（四舍五入）。
function formatRankingScore(score) {
    if (score === null || score === undefined || score === "") {
        return "—";
    }
    const value = Number(score);
    return Number.isFinite(value) ? value.toFixed(2) : "—";
}
const rankingConsole = ref("");
// 当前取回的榜单：选了机种就是该机种，清空后是**全部机种**（跨机种）
const rankingItems = ref([]);
// 跨机种时的「整个榜单排名」：按后端返回的整份顺序编号（评分降序）。
// 必须按整份 rankingItems 算，搜索与「只看已入库」只过滤展示，不改变这条记录在总榜里的名次。
const rankingOverallRanks = computed(() => {
    const ranks = new Map();
    rankingItems.value.forEach((item, index) => {
        ranks.set(`${item.platform}-${item.rank}`, index + 1);
    });
    return ranks;
});
// 选了机种显示机种内序号；清空机种显示整个榜单的连续名次。
function rankingDisplayRank(item) {
    if (rankingConsole.value) {
        return item.rank;
    }
    return rankingOverallRanks.value.get(`${item.platform}-${item.rank}`) ?? item.rank;
}
const rankingPage = ref(1);// 「已入库」按钮按下时只展示命中库存的行（纯前端过滤，不再打接口）
const rankingInLibraryOnly = ref(false);
// 榜单搜索词。与检索区的 keyword **故意分成两个**：那边是服务端 FTS（搜中英文两列、分词、剥尾部
// 标签、支持 `mario*` 前缀），这边只是对中文名/英文名做不区分大小写的裸子串匹配，语义不同、别合并
const rankingKeyword = ref("");
const rankingNeedle = computed(() => rankingKeyword.value.trim().toLowerCase());
// 这份榜单里卡带 ID 命中平台库存的行数（后端下发的 path 非空即命中）。
// **按整份 rankingItems 算、不是当前页**——比例的口径是「这个机种的全部榜单行」；
// 榜单现在是整份取回、前端分页，以后若改成服务端分页，这个数要挪到后端算。
const rankingLinkedCount = computed(
    () => rankingItems.value.filter((item) => item.path).length
);

/** 榜单关联到的游戏还没有本体：不进播放页，提示先上传。 */
function onMissingBodyLink() {
    noticeAction("请先上传游戏本体");
}
// 只按搜索词过一遍（中文名/英文名的裸子串、不区分大小写）。单独拆出来是为了空态能分清
// 「是搜索没搜到」还是「搜到了但都没入库」——见 rankingEmptyDescription
const rankingKeywordMatches = computed(() => {
    const needle = rankingNeedle.value;
    if (!needle) {
        return rankingItems.value;
    }
    return rankingItems.value.filter(
        (item) =>
            item.zh.toLowerCase().includes(needle) ||
            item.en.toLowerCase().includes(needle)
    );
});
// 搜索与「只看已入库」是 **AND**（先按词筛、再按库存筛），真正参与分页的就是它；
// 而按钮上的比例仍按整份 rankingItems 算（分母是这份榜单的总行数，不随过滤变）
const rankingVisibleItems = computed(() =>
    rankingInLibraryOnly.value
        ? rankingKeywordMatches.value.filter((item) => item.path)
        : rankingKeywordMatches.value
);
const rankingVisibleTotal = computed(() => rankingVisibleItems.value.length);
const rankingTotal = computed(() => rankingItems.value.length);
// 每页行数自适应（与检索区同一套行高与开销；榜单在前端分页，直接随行数重切即可）
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

// 行数变了页码可能越界：收敛到最后一页。榜单整份在前端有，不必重新请求
function onRankingRowsChange() {
    const pages = Math.max(
        1,
        Math.ceil(rankingVisibleTotal.value / rankingPageSize.value)
    );
    if (rankingPage.value > pages) {
        rankingPage.value = pages;
    }
}

// 当前这一页真正渲染的行
const rankingPagedItems = computed(() =>
    rankingVisibleItems.value.slice(
        (rankingPage.value - 1) * rankingPageSize.value,
        rankingPage.value * rankingPageSize.value
    )
);
const rankingLoading = ref(false);
const rankingIndexed = ref(true);
const rankingAvailable = ref(true);
const rankingError = ref(false);

// 榜单只在第一次切到榜单标签时拉一次，来回切标签不重复请求
let rankingLoaded = false;
let rankingSeq = 0;

const rankingEmptyDescription = computed(() => {
    if (rankingError.value) {
        return "榜单加载失败，请稍后重试。";
    }
    if (!rankingIndexed.value) {
        return "尚未构建游戏索引。请在项目根目录执行一次 make index，然后刷新本页。";
    }
    if (!rankingAvailable.value) {
        return "榜单尚未加载。请检查榜单 CSV 后执行 make index，或重启服务。";
    }
    if (!rankingConsoles.value.length) {
        return "榜单暂无数据。";
    }
    // 搜索与「已入库」是 AND：搜到了、但都被「只看已入库」挡掉时要明说，
    // 否则用户看着按钮上的「已入库 25 / 100」会以为是搜索词的问题
    const rawKeyword = rankingKeyword.value.trim();
    if (rawKeyword) {
        if (rankingInLibraryOnly.value && rankingKeywordMatches.value.length) {
            return `匹配「${rawKeyword}」的游戏都还没入库。`;
        }
        return `没有匹配到中英文名含「${rawKeyword}」的游戏。`;
    }
    if (rankingInLibraryOnly.value && rankingItems.value.length) {
        return rankingConsole.value
            ? "这个类型下还没有已入库的游戏。"
            : "全机种下还没有已入库的游戏。";
    }
    return rankingConsole.value ? "该游戏类型暂无榜单数据。" : "全部类型暂无榜单数据。";
});

function toggleInLibraryOnly() {
    rankingInLibraryOnly.value = !rankingInLibraryOnly.value;
    // 行数变了，页码回到第一页（否则可能停在一个已经不存在的页上）
    rankingPage.value = 1;
}

// 搜索词一变也回第一页（同上；打字/点 X 清空都走这里，不用再挂 @input / @clear）
watch(rankingKeyword, () => {
    rankingPage.value = 1;
});

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
        await loadRanking();
    }
}

async function loadRanking() {
    const seq = ++rankingSeq;
    rankingLoading.value = true;
    // 换机种 / 清空机种都回到第 1 页（换了份数据，旧页码未必还存在）
    rankingPage.value = 1;
    try {
        // 清空下拉时不再传 console：后端返回全部机种（跨机种榜单）
        const data = await getGameRankingAPI({
            console: rankingConsole.value || undefined,
        });
        if (seq !== rankingSeq) {
            return;
        }
        rankingIndexed.value = data.indexed;
        rankingAvailable.value = data.has_ranking;
        rankingItems.value = data.items || [];
        rankingError.value = false;
    } catch {
        if (seq !== rankingSeq) {
            return;
        }
        rankingItems.value = [];
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
   可见的那一列（检索/榜单二选一）填满剩余高度，把行数自适应的空间吃满 */
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

/* 「已入库比例」是 AppButton 的开关态：上下居中交给 .el-button 默认的 center。
   EP 会把 slot 包进一个内层 span，这里再写 align-items: baseline 会把整块文字贴到上边；
   标签与数字的间距由 __stock-value 的 margin-left 负责。 */

.game-discover__stock-label {
    letter-spacing: 0.02em;
}

.game-discover__stock-value {
    margin-left: 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
}

/* 命中平台库存的榜单行：游戏名是真 <a>（router-link 渲染），走全局的主色；
   下划线做成 1px 细线并抬高 2px，比浏览器默认那条粗线克制，指上去才转成实色。
   链接是 inline 元素，不影响格子里写死的 20px 行盒 */
.game-discover__link {
    color: var(--brand-accent);
    text-decoration: underline;
    text-decoration-thickness: 1px;
    text-decoration-color: #bfdbfe;
    text-underline-offset: 2px;
    /* 无本体的关联行用 span 渲染，同样要手型 */
    cursor: pointer;
}

.game-discover__link:hover {
    text-decoration-color: currentColor;
}

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

/* 跨机种榜单才出现的「游戏类型」列；比检索区窄，给中英文名留空间 */
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

/* 0~2 个卡带 ID 在同一格里并排；每个都是 CopyButton 的药丸样式；没有就显示 — */
.game-discover__ids {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
</style>
