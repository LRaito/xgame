<template>
    <div class="game-search">
        <header class="page-header">
            <h1 class="page-title">游戏检索</h1>
        </header>

        <div class="game-search__toolbar">
            <el-select
                v-model="activeConsole"
                class="game-search__console"
                placeholder="机种"
                clearable
                @change="searchNow"
            >
                <el-option label="全部机种" value="" />
                <el-option
                    v-for="item in consoles"
                    :key="item.id"
                    :label="item.name"
                    :value="item.id"
                />
            </el-select>
            <el-input
                v-model="keyword"
                class="game-search__keyword"
                placeholder="搜索中文名或英文名"
                clearable
                @keyup.enter="searchNow"
                @input="onKeywordInput"
                @clear="searchNow"
            />
        </div>

        <div v-loading="loading" class="game-search__body">
            <table v-if="items.length" class="game-search__table">
                <thead>
                    <tr>
                        <th class="game-search__col-console">机种</th>
                        <th class="game-search__col-zh">中文名</th>
                        <th>英文名</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="item in items" :key="item.id">
                        <td class="game-search__nowrap">{{ item.console }}</td>
                        <td>
                            <template v-for="(seg, index) in highlight(item.zh)" :key="index">
                                <mark v-if="seg.hit">{{ seg.text }}</mark>
                                <template v-else>{{ seg.text }}</template>
                            </template>
                        </td>
                        <td>
                            <template v-for="(seg, index) in highlight(item.en)" :key="index">
                                <mark v-if="seg.hit">{{ seg.text }}</mark>
                                <template v-else>{{ seg.text }}</template>
                            </template>
                        </td>
                    </tr>
                </tbody>
            </table>
            <app-empty v-else :description="emptyDescription" />

            <!-- 翻页放在表格下面；只有一页时不出现 -->
            <div v-if="total > pageSize" class="game-search__pager">
                <el-pagination
                    v-model:current-page="page"
                    :page-size="pageSize"
                    :total="total"
                    layout="prev, pager, next, total"
                    background
                    @current-change="load"
                />
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { listSearchConsolesAPI, searchGamesAPI } from "@/api/games";

const PAGE_SIZE = 10;
// 防抖时长：与游戏管理页的关键词筛选一致
const KEYWORD_DEBOUNCE = 300;

const keyword = ref("");
const activeConsole = ref("");
const consoles = ref([]);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(PAGE_SIZE);
const loading = ref(false);
const indexed = ref(true);
const loadError = ref(false);

let keywordTimer = 0;
// 请求序号：防抖 + 快速改条件时，慢的旧响应不能覆盖新结果
let requestSeq = 0;

const emptyDescription = computed(() => {
    if (loadError.value) {
        return "检索失败，请稍后重试。";
    }
    if (!indexed.value) {
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

async function load() {
    const seq = ++requestSeq;
    loading.value = true;
    try {
        const data = await searchGamesAPI({
            q: keyword.value.trim(),
            console_id: activeConsole.value || undefined,
            page: page.value,
            page_size: pageSize.value,
        });
        if (seq !== requestSeq) {
            return;
        }
        indexed.value = data.indexed;
        items.value = data.items || [];
        total.value = data.total || 0;
        page.value = data.page || 1;
        pageSize.value = data.page_size || PAGE_SIZE;
        loadError.value = false;
    } catch {
        if (seq !== requestSeq) {
            return;
        }
        items.value = [];
        total.value = 0;
        loadError.value = true;
    } finally {
        if (seq === requestSeq) {
            loading.value = false;
        }
    }
}

/** 改条件都要回到第 1 页，否则会停在一个新结果里不存在的页码上。 */
function searchNow() {
    clearTimeout(keywordTimer);
    page.value = 1;
    load();
}

function onKeywordInput() {
    clearTimeout(keywordTimer);
    keywordTimer = setTimeout(searchNow, KEYWORD_DEBOUNCE);
}

onMounted(async () => {
    try {
        const data = await listSearchConsolesAPI();
        consoles.value = data.consoles || [];
        indexed.value = data.indexed;
    } catch {
        consoles.value = [];
    }
    await load();
});
</script>

<style scoped>
.game-search__toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    align-items: center;
}

.game-search__keyword,
.game-search__console {
    width: 240px;
}

.game-search__body {
    min-height: 200px;
}

/* 固定布局 + 百分比列宽：再长的名字也只在自己格子里省略，表格不会被撑宽 */
.game-search__table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
}

.game-search__table th,
.game-search__table td {
    padding: 12px 16px;
    text-align: left;
    font-size: 14px;
    border-bottom: 1px solid var(--border);
    word-break: break-word;
}

.game-search__table th {
    background: #f8fafc;
    color: var(--text-muted);
    font-weight: 500;
    white-space: nowrap;
}

.game-search__table tbody tr:last-child td {
    border-bottom: none;
}

/* 够放下最长的机种名「任天堂SFC - Sufami Turbo」（约 178px 文字 + 左右各 16px 内边距） */
.game-search__col-console {
    width: 220px;
}

.game-search__col-zh {
    width: 32%;
}

.game-search__nowrap {
    color: var(--text-muted);
    white-space: nowrap;
}

.game-search__table mark {
    background: #fde68a;
    color: inherit;
    border-radius: 2px;
}

.game-search__pager {
    display: flex;
    justify-content: center;
    margin-top: 20px;
}
</style>
