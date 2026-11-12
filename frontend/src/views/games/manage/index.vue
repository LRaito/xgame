<template>
    <div class="game-manage">
        <!-- 页头顶部标签：结构与游戏发现一致，同款 AppSegmented；现在只有一个标签，
             以后新列表就从这里加。标签状态由 URL ?tab 驱动（同游戏发现） -->
        <app-segmented
            v-model="activeTab"
            class="game-manage__tabs"
            :options="TABS"
            size="lg"
            aria-label="游戏库存"
        />

        <!-- 游戏库存 -->
        <section class="game-manage__panel">
            <div class="game-manage__toolbar">
                <app-type-select
                    v-model="filterType"
                    placeholder="游戏类型"
                    clearable
                    class="game-manage__filter-type"
                    :options="typeFilterOptions"
                    @change="applyFilter"
                />
                <el-input
                    v-model="filterKeyword"
                    placeholder="搜索名称或描述"
                    clearable
                    class="game-manage__filter-keyword"
                    @input="onKeywordInput"
                    @clear="onKeywordClear"
                />
                <app-select
                    v-model="filterRanking"
                    placeholder="榜单类型"
                    clearable
                    class="game-manage__filter-ranking"
                    :options="rankingFilterOptions"
                    @change="applyFilter"
                />
                <div class="game-manage__actions">
                    <app-button variant="secondary" @click="openImport">搬运游戏</app-button>
                    <app-button variant="secondary" @click="openCreate">添加游戏</app-button>
                </div>
            </div>

            <div
                ref="tableWrapEl"
                v-loading="loading"
                class="game-manage__table-wrap"
                :style="{ height: tableWrapHeight }"
            >
                <table v-if="items.length" class="game-manage__table">
                    <!-- 列宽走百分比/定宽（见样式里的 table-layout: fixed）：内容再长也只在
                         格子里省略，表格永远不超出内容区，页面不会出现水平滚动条 -->
                    <thead>
                        <tr>
                            <th class="game-manage__col-name">名称</th>
                            <th class="game-manage__col-type">类型</th>
                            <th class="game-manage__col-size">大小</th>
                            <th class="game-manage__col-time">更新时间</th>
                            <th class="game-manage__col-actions">操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="item in items" :key="item.id">
                            <td>
                                <app-truncatable-name>
                                    {{ item.name }}
                                    <!-- 名称被截断时展开层顺带给出描述：行高保持单行
                                         （40px 系），描述不再占列表行 -->
                                    <template #panel-extra>
                                        <div class="game-manage__panel-desc">
                                            {{ item.description }}
                                        </div>
                                    </template>
                                </app-truncatable-name>
                            </td>
                            <td class="game-manage__nowrap">{{ typeLabel(item.game_type) }}</td>
                            <td class="game-manage__nowrap">{{ formatSize(item.size) }}</td>
                            <td class="game-manage__nowrap">{{ formatDateTime(item.updated_at) }}</td>
                            <td>
                                <div class="game-manage__row-actions">
                                    <app-button
                                        variant="secondary"
                                        size="sm"
                                        @click="openDetail(item.id)"
                                    >
                                        详情
                                    </app-button>
                                    <app-button
                                        variant="secondary"
                                        size="sm"
                                        @click="openEdit(item.id)"
                                    >
                                        编辑
                                    </app-button>
                                    <app-button variant="danger" size="sm" @click="onDelete(item)">
                                        删除
                                    </app-button>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <app-empty v-else :description="emptyDescription" />
            </div>

            <!-- 翻页放在表格下面；只有一页时整块不渲染（AppPagination 自己判，左右键翻页也在它里面） -->
            <app-pagination
                v-model:page="page"
                :total="total"
                :page-size="pageSize"
                previous-shortcut="manage.page.prev"
                next-shortcut="manage.page.next"
                @change="reload"
            />
        </section>

        <!-- 添加/编辑游戏：与游戏榜单共用的同一份弹框 -->
        <game-form-dialog
            v-model="formVisible"
            :mode="formMode"
            :game-id="editingId"
            :initial="formInitial"
            @saved="reload"
            @changed="reload"
        />

        <!-- 详情弹窗：内容与游戏中心右键「详情」共用同一个组件 -->
        <game-detail-dialog v-model="detailVisible" :game-id="detailId" />

        <app-dialog
            v-model="importVisible"
            title="搬运游戏"
            width="560px"
            footer-mode="none"
        >
            <div class="game-import">
                <div class="game-import__field">
                    <label class="game-import__label" for="game-import-url">游戏页地址</label>
                    <div class="game-import__form">
                        <el-input
                            id="game-import-url"
                            v-model="importUrl"
                            clearable
                            :disabled="importing"
                            @keyup.enter="onImport"
                        />
                        <app-button variant="secondary" :loading="importing" @click="onImport">
                            搬运
                        </app-button>
                    </div>
                    <div class="game-import__example">
                        <span class="game-import__example-label">示例</span>
                        <div class="game-import__example-list">
                            <div class="game-import__example-item">
                                <span class="game-import__example-site">7k7k</span>
                                <code>https://www.7k7k.com/flash/205829.htm</code>
                            </div>
                            <div class="game-import__example-item">
                                <span class="game-import__example-site">4399</span>
                                <code>https://www.4399.com/flash/1172_1.htm</code>
                            </div>
                            <div class="game-import__example-item">
                                <span class="game-import__example-site">flash.homes</span>
                                <code>https://flash.homes/flash/F8YX-1DNE-JQG9</code>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="game-import__platforms">
                    <span class="game-import__platforms-label">前往游戏平台查找</span>
                    <div class="game-import__platform-list">
                        <a
                            class="game-import__platform"
                            href="https://www.7k7k.com"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <span class="game-import__platform-badge game-import__platform-badge--7k7k">7k7k</span>
                            <span class="game-import__platform-name">7k7k 小游戏</span>
                        </a>
                        <a
                            class="game-import__platform"
                            href="https://www.4399.com"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <span class="game-import__platform-badge game-import__platform-badge--4399">4399</span>
                            <span class="game-import__platform-name">4399 小游戏</span>
                        </a>
                        <a
                            class="game-import__platform"
                            href="https://flash.homes/flash"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <span class="game-import__platform-badge game-import__platform-badge--flashhomes">
                                flash
                            </span>
                            <span class="game-import__platform-name">flash.homes</span>
                        </a>
                    </div>
                </div>
            </div>
        </app-dialog>
    </div>
</template>

<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { dangerPrompt } from "@/utils/confirm";
import AppDialog from "@components/common/AppDialog.vue";
import CopyButton from "@components/common/CopyButton.vue";
import GameDetailDialog from "@components/games/GameDetailDialog.vue";
import GameFormDialog from "@components/games/GameFormDialog.vue";
import {
    deleteManageGameAPI,
    importGameAPI,
    listManageGamesAPI,
} from "@/api/games";
import { gameTypeLabel as typeLabel } from "@/constants/gameTypes";
import { useGameTypesStore } from "@/store/gameTypes";
import { formatDateTimeSeconds as formatDateTime } from "@/utils/fileDisplay";
import { useAdaptiveRows } from "@/utils/adaptiveRows";
import { useRoute, useRouter } from "vue-router";

// 行高固定、行数自适应（见 utils/adaptiveRows.js）：行高 40px 与游戏发现一致，
// 后端 backend/games/service.py 的 MANAGE_PAGE_SIZE_MAX = 100 是上限。
// 行内容是 28px 的按钮 + 上下各 6px 内边距 = 40；表头 44 + 分隔线合计 12 算在
// TABLE_EXTRA 里；底部开销 = 分页条（上边距 20 + 高 32）+ 内容区下边距 28 = 80。
// 行高全屏/非全屏一致，只有行数不同；排不满整行的余量留在最后一行与分页条之间。
const ROW_HEIGHT = 40;
const TABLE_EXTRA = 56;
const PAGE_SIZE_MAX = 100;

// 顶部标签：现在只有「游戏库存」一个，值与 URL ?tab 对齐（与游戏发现同一套写法），
// 以后加标签在这里追加即可
const TABS = [{ label: "游戏库存", value: "manage" }];

const route = useRoute();
const router = useRouter();

const activeTab = computed({
    get: () =>
        TABS.some((tab) => tab.value === route.query.tab)
            ? route.query.tab
            : TABS[0].value,
    set: (value) => {
        const query = { ...route.query };
        if (value === TABS[0].value) {
            delete query.tab;
        } else {
            query.tab = value;
        }
        router.replace({ path: "/games/manage", query });
    },
});

const { rows: pageSize, measure: measureRows } = useAdaptiveRows(
    {
        rowHeight: ROW_HEIGHT,
        extraHeight: TABLE_EXTRA,
        reservePx: 80,
        maxRows: PAGE_SIZE_MAX,
        // 量到之前按旧条数占位，高度别闪跳
        initialRows: 5,
    },
    () => reload()
);

// 列表容器永远按「一页满行」定高：最后一页数据不满时高度也不缩，分页条位置固定不动；
// 行高全屏/非全屏一致，排不满整行的余量落在表格下方
const tableWrapEl = ref(null);
const tableWrapHeight = computed(
    () => `${TABLE_EXTRA + pageSize.value * ROW_HEIGHT}px`
);


const loading = ref(false);
const items = ref([]);
const page = ref(1);
const total = ref(0);
// 类型与可上传后缀都来自 /status（后端词表派生），这里只读缓存
const gameTypesStore = useGameTypesStore();
const gameTypes = computed(() => gameTypesStore.gameTypes);
// 类型筛选下拉：「全部」+ 当前类型；输入过滤交给 AppTypeSelect
const typeFilterOptions = computed(() => [
    { value: "", label: "全部游戏类型" },
    ...gameTypes.value.map((type) => ({ value: type, label: typeLabel(type) })),
]);

const filterType = ref("");
const filterKeyword = ref("");
// 榜单类型："" = 全部；"in" = 榜单之内；"out" = 榜单之外
const filterRanking = ref("");
const rankingFilterOptions = [
    { value: "in", label: "榜单之内" },
    { value: "out", label: "榜单之外" },
];
const emptyDescription = computed(() =>
    filterType.value || filterKeyword.value.trim() || filterRanking.value
        ? "当前筛选下没有库存条目。"
        : "暂无库存条目，点击「添加游戏」开始录入。"
);
let keywordTimer = null;
// Element Plus 点 X 会先 emit clear、再 emit input：clear 已立即查询，跳过随后那次防抖
let skipKeywordInput = false;
// 请求序号：防抖 + 快速翻页时，慢的旧响应不能覆盖新结果（同游戏名录页）
let requestSeq = 0;

function listParams() {
    const params = { page: page.value, page_size: pageSize.value };
    if (filterType.value) {
        params.game_type = filterType.value;
    }
    if (filterKeyword.value.trim()) {
        params.q = filterKeyword.value.trim();
    }
    if (filterRanking.value === "in") {
        params.in_ranking = true;
    } else if (filterRanking.value === "out") {
        params.in_ranking = false;
    }
    return params;
}

/** 取当前页。**保持页码**——保存、删除、搬运之后都调它，别把用户从第 3 页踢回第 1 页。 */
async function reload() {
    const seq = ++requestSeq;
    loading.value = true;
    try {
        const data = await listManageGamesAPI(listParams());
        if (seq !== requestSeq) {
            return;
        }
        // 删掉本页最后一条后页码会越界：收敛到最后一页再取一次。
        // （服务端不收敛页码、只返回空 items + 真 total，与游戏名录页同一口径，收敛放前端）
        const pageCount = Math.max(
            1,
            Math.ceil((data.total || 0) / (data.page_size || pageSize.value))
        );
        if (page.value > pageCount) {
            page.value = pageCount;
            // 内层会 ++requestSeq，外层 finally 的 seq 判断自然跳过、不覆盖 loading
            await reload();
            return;
        }
        items.value = data.items || [];
        total.value = data.total || 0;
        page.value = data.page || 1;
    } finally {
        if (seq === requestSeq) {
            loading.value = false;
        }
    }
}

/** 改筛选条件要回到第 1 页，否则会停在一个新结果里不存在的页码上。 */
function applyFilter() {
    page.value = 1;
    reload();
}

function onKeywordInput() {
    if (skipKeywordInput) {
        skipKeywordInput = false;
        return;
    }
    clearTimeout(keywordTimer);
    keywordTimer = setTimeout(applyFilter, 300);
}

/** 点 X 清空：立即查询；紧随其后的 input 已由 skipKeywordInput 跳过。 */
function onKeywordClear() {
    skipKeywordInput = true;
    clearTimeout(keywordTimer);
    applyFilter();
}

const formVisible = ref(false);
const formMode = ref("create");
const editingId = ref(null);
const formInitial = ref(null);
// 详情弹窗（内容见 components/games/GameDetailDialog.vue，游戏中心右键也用它）
const detailVisible = ref(false);
const detailId = ref(null);

const importVisible = ref(false);
const importUrl = ref("");
const importing = ref(false);

function formatSize(bytes) {
    if (!bytes) {
        return "—";
    }
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function openDetail(id) {
    detailId.value = id;
    detailVisible.value = true;
}

function openCreate() {
    formMode.value = "create";
    editingId.value = null;
    formInitial.value = null;
    formVisible.value = true;
}

function openEdit(id) {
    formMode.value = "edit";
    editingId.value = id;
    formInitial.value = null;
    formVisible.value = true;
}

function openImport() {
    importUrl.value = "";
    importVisible.value = true;
}

async function onImport() {
    const url = importUrl.value.trim();
    if (!url) {
        ElMessage.warning("请填写要搬运的游戏地址");
        return;
    }
    importing.value = true;
    try {
        // 服务端要解析页面并下载全部资源，耗时较长，按钮保持 loading 即可
        const item = await importGameAPI(url);
        ElMessage.success(`已搬运「${item.name}」`);
        importVisible.value = false;
        await reload();
    } catch (err) {
        // 拦截器已经弹过提示，只有它没弹（如本地抛错）时才补一次
        if (!err.reported) ElMessage.error(err.message || "搬运失败");
    } finally {
        importing.value = false;
    }
}

// 删除确认的正文：警示文案下面再单列一行卡带ID（带复制按钮）。要手打的确认串就是它，
// 摆在眼前省得用户先去别处抄一遍。message 传 VNode 渲染，这条弹框挂在 body 下，
// 拿不到组件的 scoped 样式，所以它的样式写在 styles/index.css 里。
function buildDeleteMessage(item) {
    return h("div", null, [
        h(
            "p",
            { class: "game-manage__delete-confirm-text" },
            `确定删除游戏「${item.name}」？此操作会同时删掉该游戏在磁盘上的全部文件，` +
                "以及所有账号在它上面的云端存档，且无法撤销。",
        ),
        h("div", { class: "game-manage__delete-confirm-id" }, [
            h("span", { class: "game-manage__delete-confirm-label" }, "卡带 ID"),
            h("span", { class: "game-manage__delete-confirm-value" }, item.cartridge_id),
            h(CopyButton, { text: item.cartridge_id }),
        ]),
    ]);
}

// 删游戏会连磁盘文件与所有账号在该游戏上的云端存档一起清掉，且不可撤销，
// 所以要求手打一次卡带ID——它建后不可改，是最不会认错游戏的那个标识。
async function onDelete(item) {
    const confirmed = await dangerPrompt(buildDeleteMessage(item), {
        title: "删除确认",
        inputPlaceholder: `输入卡带 ID「${item.cartridge_id}」以确认`,
        inputValidator: (value) =>
            String(value || "").trim().toUpperCase() === item.cartridge_id ||
            `请输入卡带 ID「${item.cartridge_id}」以确认`,
    });
    if (!confirmed) {
        return;
    }
    try {
        await deleteManageGameAPI(item.id);
        ElMessage.success("已删除");
        await reload();
    } catch (err) {
        if (!err.reported) ElMessage.error(err.message || "删除失败");
    }
}

onMounted(async () => {
    // 先量视口算出每页行数，首屏请求才知道带多大 page_size
    measureRows(tableWrapEl.value);
    loading.value = true;
    try {
        // 类型与后缀来自 /status；失败时页面仍能列出游戏，只是下拉候选为空
        await gameTypesStore.ensureLoaded();
        await reload();
    } finally {
        loading.value = false;
    }
});

onBeforeUnmount(() => {
    // 挂起的防抖别再触发一次请求（序号防竞态兜得住，但清掉更干净）
    clearTimeout(keywordTimer);
});
</script>

<style scoped>
/* 页面纵向铺满：内容区上下各 28px 内边距，页面根按 100vh−56 占满后再不滚动；
   面板（tab 栏 + 工具条 + 列表 + 分页）填满剩余高度，行数自适应的空间吃满 */
.game-manage {
    display: flex;
    flex-direction: column;
    min-height: calc(100vh - 56px);
}

.game-manage__panel {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
}

/* 页头标签共用 AppSegmented 的尺寸与选中态，这里只留与下方工具条的间距 */
.game-manage__tabs {
    margin-bottom: 20px;
}

.game-manage__toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    align-items: center;
}

.game-manage__filter-type {
    /* 足够放下最长的类型名（如 “任天堂 GB/GBC”），避免选中值被截断 */
    width: 240px;
}

.game-manage__filter-keyword {
    width: 240px;
}

.game-manage__filter-ranking {
    width: 160px;
}

.game-manage__actions {
    margin-left: auto;
}

/* 列表高度直接占量出的可用高度（模板 :style 绑定 available，覆盖下面的 min-height）：
   行数按视口高度自适应（utils/adaptiveRows.js），取整后不足一行的余量由表格行均摊消化 */
.game-manage__table-wrap {
    min-height: 200px;
}

/* 固定布局 + 定宽/百分比列宽：列宽只跟表格宽度走，跟内容长短无关，
   所以再长的名称也只在自己格子里省略，表格永远不会被撑宽（页面不会出水平滚动条）。
   注意别在这里加 overflow: hidden——展开的名称浮层要能盖到表格外面去 */
.game-manage__table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
}


/* 没有 overflow 兜底，四角靠表头/末行的圆角自己收（表头有底色，方角会顶出表格圆角） */
.game-manage__table thead th:first-child {
    border-top-left-radius: 11px;
}

.game-manage__table thead th:last-child {
    border-top-right-radius: 11px;
}

.game-manage__table tbody tr:last-child td:first-child {
    border-bottom-left-radius: 11px;
}

.game-manage__table tbody tr:last-child td:last-child {
    border-bottom-right-radius: 11px;
}

/* 名称列不给定宽：吃掉其余定宽列剩下的全部宽度（table-layout: fixed 语义）。
   定宽列按内容最宽需要给（如更新时间那串 19 个字、三个操作按钮并排） */
.game-manage__col-type {
    width: 180px;
}

.game-manage__col-size {
    width: 96px;
}

.game-manage__col-time {
    width: 180px;
}

/* 操作列：三个 sm 按钮（高 28、左右内边距各 10、短字约 26）= 每个约 46px，
   加两个 8px 间距再算上单元格左右各 16 的内边距 ≈ 186，给 200 留余量——
   少了按钮会顶出格子 */
.game-manage__col-actions {
    width: 200px;
}

/* 与游戏发现同款：行高固定 40px（28px 按钮 + 上下各 6px 内边距），
   全屏与非全屏行高一致，只有行数不同。
   line-height 显式写死，两张表不会因为字体默认值不同而差几个像素 */
.game-manage__table th,
.game-manage__table td {
    border-bottom: 1px solid var(--border);
    text-align: left;
    vertical-align: middle;
}

.game-manage__table td {
    padding: 6px 16px;
    font-size: 14px;
    line-height: 20px;
}

/* 表头没有内容撑着，上下留 12px 就够——别白占一屏的竖向预算。
   行高显式写死 20px，表格定高（见 __table-wrap）才能算准 */
.game-manage__table th {
    padding: 12px 16px;
    line-height: 20px;
}

/* 除名称列外都只占一行，超长（如 任天堂 GB/GBC）就地省略 */
.game-manage__nowrap {
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.game-manage__table th {
    background: #f8fafc;
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 600;
}

/* 名称被截断时展开层里的描述段落：小一号的灰字，跟浮层自身的白底配 */
.game-manage__panel-desc {
    margin-top: 6px;
    font-size: 12px;
    line-height: 1.7;
    color: #64748b;
    white-space: normal;
}

/* 三个操作按钮左对齐（和「操作」表头对齐）；列宽按它们的实际宽度给，
   所以删除右边也不会剩下大片空白。
   Element Plus 默认给相邻按钮加 12px 左边距，这里间距统一由 flex gap 管，
   去掉它，否则三个按钮会把内容顶出格子右边 */
.game-manage__row-actions {
    display: flex;
    gap: 8px;
}

.game-manage__row-actions :deep(.el-button + .el-button) {
    margin-left: 0;
}

/* 搬运游戏弹窗 */
.game-import__field {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.game-import__label {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
}

.game-import__form {
    display: flex;
    align-items: center;
    gap: 10px;
}

.game-import__form :deep(.el-input) {
    flex: 1;
    min-width: 0;
}

.game-import__form :deep(.el-input__wrapper) {
    border-radius: 10px;
}

.game-import__example {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.game-import__example-label {
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
}

.game-import__example-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 12px;
    border: 1px solid #eef2f7;
    border-radius: 10px;
    background: #f8fafc;
}

.game-import__example-item {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    font-size: 12px;
}

.game-import__example-site {
    flex-shrink: 0;
    width: 76px;
    font-weight: 600;
    color: #64748b;
}

.game-import__example-item code {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #475569;
    font-family: inherit;
}

@media (max-width: 520px) {
    .game-import__example-item {
        flex-direction: column;
        align-items: flex-start;
        gap: 2px;
    }

    /* 窄屏放不下三个平台块，改为竖排 */
    .game-import__platform-list {
        grid-template-columns: 1fr;
    }

    .game-import__platform {
        justify-content: flex-start;
    }
}

.game-import__platforms {
    margin-top: 22px;
    padding-top: 18px;
    border-top: 1px solid #eef2f7;
}

.game-import__platforms-label {
    display: block;
    margin-bottom: 12px;
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
}

.game-import__platform-list {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
}

.game-import__platform {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-width: 0;
    padding: 10px 12px;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    background: #fff;
    text-decoration: none;
    transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.game-import__platform:hover {
    border-color: #bfdbfe;
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.08);
    transform: translateY(-1px);
}

.game-import__platform-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 9px;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
}

.game-import__platform-badge--7k7k {
    background: linear-gradient(135deg, #fb923c, #ea580c);
}

.game-import__platform-badge--4399 {
    background: linear-gradient(135deg, #60a5fa, #0098ee);
}

/* flash.homes 的徽标字比 7k7k / 4399 长，单独缩一号字 */
.game-import__platform-badge--flashhomes {
    background: linear-gradient(135deg, #2dd4bf, #0f766e);
    font-size: 10px;
    letter-spacing: 0;
}

.game-import__platform-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
    font-weight: 600;
    color: #0f172a;
}
</style>
