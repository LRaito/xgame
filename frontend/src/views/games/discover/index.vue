<template>
    <div class="game-discover">
        <!-- 单选栏：页面上不再有「游戏检索」标题，这两个按钮本身就是页头。
             刻意不用 el-segmented —— 它那块跟着选项滑动的底片就是一种「切换效果」，
             这里要的是一对更正式、更沉稳的大按钮。 -->
        <el-radio-group v-model="activeTab" class="game-discover__tabs" size="large">
            <el-radio-button v-for="tab in TABS" :key="tab.value" :value="tab.value">
                {{ tab.label }}
            </el-radio-button>
        </el-radio-group>

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
            </div>

            <div v-loading="rankingLoading" class="game-discover__body">
                <table v-if="rankingItems.length" class="game-discover__table">
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
                            <td>{{ item.title }}</td>
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
                    :total="rankingTotal"
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
// 当前这一页真正渲染的行
const rankingPagedItems = computed(() =>
    rankingItems.value.slice(
        (rankingPage.value - 1) * RANKING_PAGE_SIZE,
        rankingPage.value * RANKING_PAGE_SIZE
    )
);
const rankingTotal = computed(() => rankingItems.value.length);
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
    return "该游戏类型暂无榜单数据。";
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
/* 页头的两个大单选（游戏检索 / 游戏榜单）。比 Element Plus 的默认尺寸再放大一档：
   高 46px、字 15px、左右各 48px 内边距，选中态用实心主色，未选中是白底描边——一眼看清
   现在在哪一块，也没有任何滑动动画。 */
.game-discover__tabs {
    margin-bottom: 20px;
}

.game-discover__tabs :deep(.el-radio-button__inner) {
    padding: 13px 48px;
    border-color: var(--border);
    color: var(--text-muted);
    font-size: 15px;
    font-weight: 500;
    letter-spacing: 1px;
    box-shadow: none;
    transition: none;
}

.game-discover__tabs :deep(.el-radio-button__inner:hover) {
    color: var(--brand-accent);
}

.game-discover__tabs :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
    background: var(--brand-accent);
    border-color: var(--brand-accent);
    color: #fff;
    box-shadow: none;
}

.game-discover__toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    align-items: center;
}

.game-discover__keyword,
.game-discover__console {
    width: 240px;
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
