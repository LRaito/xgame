<template>
    <div class="game-discover">
        <!-- 单选栏：页面上不再有「游戏检索」标题，这两个按钮本身就是页头。
             **刻意不用 el-radio-group / el-segmented**：它们是原生单选控件，焦点落在里面时
             按左右键浏览器会直接换选中项（同名 radio 的默认行为），而这页的左右键必须留给
             当前标签里的分页条——**标签只能点**，所以这里就是一对普通按钮。
             也不用任何「切换效果」，要的是一对更正式、更沉稳的大按钮。 -->
        <div class="game-discover__tabs">
            <button
                v-for="tab in TABS"
                :key="tab.value"
                type="button"
                class="game-discover__tab"
                :class="{ 'is-active': activeTab === tab.value }"
                :aria-pressed="activeTab === tab.value"
                @click="activeTab = tab.value"
            >
                {{ tab.label }}
            </button>
        </div>

        <!-- 游戏检索 -->
        <section v-show="activeTab === 'search'" class="game-discover__panel">
            <div class="game-discover__toolbar">
                <el-select
                    v-model="searchConsole"
                    class="game-discover__console"
                    placeholder="游戏类型"
                    clearable
                    @change="searchNow"
                >
                    <el-option label="全部游戏类型" value="" />
                    <el-option
                        v-for="item in searchConsoles"
                        :key="item.id"
                        :label="item.name"
                        :value="item.id"
                    />
                </el-select>
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

            <div v-loading="searchLoading" class="game-discover__body">
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
                                <template
                                    v-for="(seg, index) in highlight(item.zh)"
                                    :key="index"
                                >
                                    <mark v-if="seg.hit">{{ seg.text }}</mark>
                                    <template v-else>{{ seg.text }}</template>
                                </template>
                            </td>
                            <td>
                                <template
                                    v-for="(seg, index) in highlight(item.en)"
                                    :key="index"
                                >
                                    <mark v-if="seg.hit">{{ seg.text }}</mark>
                                    <template v-else>{{ seg.text }}</template>
                                </template>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <app-empty v-else :description="searchEmptyDescription" />

                <!-- 翻页放在表格下面；只有一页时不出现（AppPagination 自己判）。
                     切到榜单标签时把键盘翻页关掉：分页条的左右键监听挂在 window 上，
                     隐藏着也会抢键（keyboard 就是为这种同页多列表/隐藏列表留的开关）。 -->
                <app-pagination
                    v-model:page="page"
                    :total="total"
                    :page-size="pageSize"
                    :keyboard="activeTab === 'search'"
                    @change="loadSearch"
                />
            </div>
        </section>

        <!-- 游戏榜单 -->
        <section v-show="activeTab === 'ranking'" class="game-discover__panel">
            <div class="game-discover__toolbar">
                <el-select
                    v-model="rankingConsole"
                    class="game-discover__console"
                    placeholder="游戏类型"
                    :disabled="!rankingConsoles.length"
                    @change="loadRanking"
                >
                    <el-option
                        v-for="item in rankingConsoles"
                        :key="item.platform"
                        :label="item.label"
                        :value="item.platform"
                    />
                </el-select>

                <!-- 榜单搜索：与检索区那个同一个 class（样式、位置、清空按钮都一样），但**纯前端**过滤
                     ——榜单是一个机种整份取回来的，逐字即时筛，不需要防抖、也不需要回车或清空的处理
                     （裸 v-model + clearable，computed 自己会跟着变） -->
                <el-input
                    v-model="rankingKeyword"
                    class="game-discover__keyword"
                    placeholder="搜索游戏名称"
                    clearable
                />

                <!-- 已入库比例，同时是「只看已入库」的开关：单击按下，榜单就只留命中库存的行，再点一下恢复。
                     数字由前端按已整份取回的 rankingItems 现算（榜单不分页），不再多打一次接口。
                     加载中先藏起来：rankingItems 在请求成功前不会清空，否则切机种会闪一下上一个机种的数字 -->
                <button
                    v-if="rankingTotal && !rankingLoading"
                    type="button"
                    class="game-discover__stock"
                    :class="{ 'is-active': rankingInLibraryOnly }"
                    :aria-pressed="rankingInLibraryOnly"
                    @click="toggleInLibraryOnly"
                >
                    <span class="game-discover__stock-label">已入库</span>
                    <span class="game-discover__stock-value">
                        {{ rankingLinkedCount }} / {{ rankingTotal }}
                    </span>
                </button>
            </div>

            <div v-loading="rankingLoading" class="game-discover__body">
                <table v-if="rankingVisibleItems.length" class="game-discover__table">
                    <thead>
                        <tr>
                            <th class="game-discover__col-rank">排名</th>
                            <th>游戏名称</th>
                            <th class="game-discover__col-ids">卡带ID</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="item in rankingPagedItems" :key="item.rank">
                            <td class="game-discover__rank">{{ item.rank }}</td>
                            <td>
                                <!-- 卡带 ID 与平台库存对上的行：游戏名是**真链接**（router-link 渲染成
                                     原生 <a href>），单击进播放页，Ctrl+点击 / 中键由浏览器自己开新标签页。
                                     没对上的行就是纯文本 -->
                                <router-link
                                    v-if="item.path"
                                    class="game-discover__link"
                                    :to="item.path"
                                >
                                    {{ item.title }}
                                </router-link>
                                <template v-else>{{ item.title }}</template>
                            </td>
                            <td>
                                <span v-if="!item.cartridge_ids.length" class="game-discover__none">
                                    —
                                </span>
                                <span v-else class="game-discover__ids">
                                    <button
                                        v-for="cartridgeId in item.cartridge_ids"
                                        :key="cartridgeId"
                                        type="button"
                                        class="game-discover__id"
                                        @click="copyCartridgeId(cartridgeId)"
                                    >
                                        {{ cartridgeId }}
                                    </button>
                                </span>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <app-empty v-else :description="rankingEmptyDescription" />

                <!-- 与检索区同款的分页条：榜单也是一页 10 条。**分页在前端做**——一份榜单
                     （一个机种）一次全取回来，翻页只是换页码、不再打接口。
                     键盘翻页同样只在榜单标签亮着时开着（同页两个分页条，监听都挂在 window 上） -->
                <app-pagination
                    v-model:page="rankingPage"
                    :total="rankingVisibleTotal"
                    :page-size="RANKING_PAGE_SIZE"
                    :keyboard="activeTab === 'ranking'"
                />
            </div>
        </section>
    </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
    getGameRankingAPI,
    listRankingConsolesAPI,
    listSearchConsolesAPI,
    searchGamesAPI,
} from "@/api/games";
import { writeClipboard } from "@/utils/clipboard";

const TABS = [
    { label: "游戏检索", value: "search" },
    { label: "游戏榜单", value: "ranking" },
];
const PAGE_SIZE = 10;
// 榜单每页条数，与检索区一致
const RANKING_PAGE_SIZE = 10;
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
const searchItems = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(PAGE_SIZE);
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
        pageSize.value = data.page_size || PAGE_SIZE;
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
const rankingConsole = ref("");
// 当前机种的**整份**榜单（一个机种一次全取回来，前端分页的数据源）
const rankingItems = ref([]);
const rankingPage = ref(1);
// 「已入库」按钮按下时只展示命中库存的行（纯前端过滤，不再打接口）
const rankingInLibraryOnly = ref(false);
// 榜单搜索词。与检索区的 keyword **故意分成两个**：那边是服务端 FTS（搜中英文两列、分词、剥尾部
// 标签、支持 `mario*` 前缀），这边只是对游戏名称做不区分大小写的裸子串匹配，语义不同、别合并
const rankingKeyword = ref("");
const rankingNeedle = computed(() => rankingKeyword.value.trim().toLowerCase());
// 这份榜单里卡带 ID 命中平台库存的行数（后端下发的 path 非空即命中）。
// **按整份 rankingItems 算、不是当前页**——比例的口径是「这个机种的全部榜单行」；
// 榜单现在是整份取回、前端分页，以后若改成服务端分页，这个数要挪到后端算。
const rankingLinkedCount = computed(
    () => rankingItems.value.filter((item) => item.path).length
);
// 只按搜索词过一遍（名称的裸子串、不区分大小写）。单独拆出来是为了空态能分清
// 「是搜索没搜到」还是「搜到了但都没入库」——见 rankingEmptyDescription
const rankingKeywordMatches = computed(() => {
    const needle = rankingNeedle.value;
    if (!needle) {
        return rankingItems.value;
    }
    return rankingItems.value.filter((item) => item.title.toLowerCase().includes(needle));
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
// 当前这一页真正渲染的行
const rankingPagedItems = computed(() =>
    rankingVisibleItems.value.slice(
        (rankingPage.value - 1) * RANKING_PAGE_SIZE,
        rankingPage.value * RANKING_PAGE_SIZE
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
        return `没有匹配到名称含「${rawKeyword}」的游戏。`;
    }
    if (rankingInLibraryOnly.value && rankingItems.value.length) {
        return "这个类型下还没有已入库的游戏。";
    }
    return "该游戏类型暂无榜单数据。";
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
        rankingConsole.value =
            data.default_console || rankingConsoles.value[0]?.platform || "";
        rankingError.value = false;
    } catch {
        rankingConsoles.value = [];
        rankingError.value = true;
        // 失败不算「加载过」：切走再切回来会重试一次
        rankingLoaded = false;
    } finally {
        rankingLoading.value = false;
    }
    if (rankingConsole.value) {
        await loadRanking();
    }
}

async function loadRanking() {
    if (!rankingConsole.value) {
        return;
    }
    const seq = ++rankingSeq;
    rankingLoading.value = true;
    // 换了一个机种就回到第 1 页（换了份数据，旧页码未必还存在）
    rankingPage.value = 1;
    try {
        const data = await getGameRankingAPI({ console: rankingConsole.value });
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

async function copyCartridgeId(cartridgeId) {
    if (await writeClipboard(cartridgeId)) {
        ElMessage.success("已复制卡带ID。");
    } else {
        ElMessage.warning("浏览器不允许自动复制，请手动选中后复制。");
    }
}

// 直接访问 ?tab=ranking 或前进/后退回到榜单时，同样要按需加载
watch(
    activeTab,
    (value) => {
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
    await loadSearch();
});
</script>

<style scoped>
/* 页头的两个大单选（游戏检索 / 游戏榜单）。高 43px（行盒 15px + 上下各 13px 内边距 +
   上下各 1px 边框，与原来那对 el-radio-button 逐像素一致）、字 15px、左右各 48px 内边距，
   选中态用实心主色，未选中是白底描边——一眼看清现在在哪一块，也没有任何滑动动画。 */
.game-discover__tabs {
    display: flex;
    margin-bottom: 20px;
}

.game-discover__tab {
    /* 相邻两个按钮共用中间那条边线：后一个的左边界压在前一个的右边界上，
       看着仍是一整条分段控件 */
    margin-left: -1px;
    padding: 13px 48px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-muted);
    font-family: inherit;
    font-size: 15px;
    font-weight: 500;
    line-height: 1;
    letter-spacing: 1px;
    cursor: pointer;
    user-select: none;
    transition: none;
}

.game-discover__tab:first-child {
    margin-left: 0;
    border-radius: 4px 0 0 4px;
}

.game-discover__tab:last-child {
    border-radius: 0 4px 4px 0;
}

.game-discover__tab:hover {
    color: var(--brand-accent);
}

/* 选中的那个要压在相邻按钮之上，否则它那条主色边线会被后一个按钮的灰边盖掉 */
.game-discover__tab.is-active {
    position: relative;
    z-index: 1;
    border-color: var(--brand-accent);
    background: var(--brand-accent);
    color: #fff;
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

/* 「已入库比例」按钮：跟左边下拉框等高的一条描边小牌，走官方统计的观感——灰标签 + 深色等宽数字、
   细边框、不加底色与阴影，不跟下拉抢视线。数字用 tabular-nums：换机种时 25 / 100 → 3 / 100
   不会左右抖。按下（只看已入库）时点亮成实心主色，与页头那对标签的选中态同一套写法 */
.game-discover__stock {
    display: inline-flex;
    align-items: baseline;
    gap: 8px;
    padding: 5px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--surface);
    color: var(--text-muted);
    font-family: inherit;
    font-size: 13px;
    line-height: 18px;
    white-space: nowrap;
    cursor: pointer;
    transition: none;
}

.game-discover__stock:hover {
    border-color: var(--brand-accent);
}

.game-discover__stock.is-active {
    border-color: var(--brand-accent);
    background: var(--brand-accent);
    color: #fff;
}

.game-discover__stock-label {
    letter-spacing: 0.02em;
}

.game-discover__stock-value {
    color: var(--brand-dark);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
}

.game-discover__stock.is-active .game-discover__stock-value {
    color: #fff;
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
}

.game-discover__link:hover {
    text-decoration-color: currentColor;
}

.game-discover__body {
    min-height: 200px;
}

/* 固定布局 + 百分比列宽：再长的名字也只在自己格子里省略，表格不会被撑宽 */
.game-discover__table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
}

/* **行高 44px（行盒 20px + 上下各 12px 内边距），榜单那张表按这个数对齐**。
   line-height 显式写死，两张表才不会因为字体默认值不同而差几个像素；
   榜单那边唯一的变量是卡带 ID 药丸，它的高度压在 20px 以内（见 .game-discover__id） */
.game-discover__table th,
.game-discover__table td {
    padding: 12px 16px;
    font-size: 14px;
    line-height: 20px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    word-break: break-word;
}

.game-discover__table th {
    background: #f8fafc;
    color: var(--text-muted);
    font-weight: 500;
    white-space: nowrap;
}

.game-discover__table tbody tr:last-child td {
    border-bottom: none;
}

/* 够放下最长的游戏类型名「任天堂 Virtual Boy」（约 140px 文字 + 左右各 16px 内边距） */
.game-discover__col-console {
    width: 220px;
}

.game-discover__col-zh {
    width: 32%;
}

.game-discover__col-rank {
    width: 88px;
}

.game-discover__col-ids {
    width: 30%;
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

.game-discover__none {
    color: var(--text-muted);
}

/* 0~2 个卡带 ID 在同一格里并排；每个都是可点的按钮，点了复制；没有就显示 — */
.game-discover__ids {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

/* 药丸整体高 20px（行盒 14 + 上下各 2 + 上下边框各 1）——**榜单的行高是由它决定的**，
   撑高了整行就比检索区那张表高（检索区的格子只有文字，行盒就是 20px） */
.game-discover__id {
    padding: 2px 8px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--surface);
    color: inherit;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    line-height: 14px;
    cursor: pointer;
    transition: border-color 0.15s ease, color 0.15s ease;
}

.game-discover__id:hover {
    border-color: var(--brand-accent);
    color: var(--brand-accent);
}
</style>
