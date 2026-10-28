<template>
    <div class="shortcuts-page">
        <header class="page-header">
            <h1 class="page-title">按键管理</h1>
        </header>

        <div class="shortcuts-page__body">
            <!-- 本页大纲：滚动时高亮当前页面，点击平滑跳转 -->
            <nav class="shortcuts-toc" aria-label="本页大纲">
                <a
                    v-for="page in SHORTCUT_PAGES"
                    :key="page.id"
                    :href="`#${page.id}`"
                    class="shortcuts-toc__link"
                    :class="{ active: activeId === page.id }"
                    @click.prevent="jumpTo(page.id)"
                >
                    {{ page.title }}
                </a>
            </nav>

            <!-- 正文：一个页面一张表，第一列按功能分组合并单元格 -->
            <article class="shortcuts-doc">
                <section
                    v-for="page in SHORTCUT_PAGES"
                    :id="page.id"
                    :key="page.id"
                    class="shortcut-section"
                >
                    <h2 class="shortcut-section__title">{{ page.title }}</h2>
                    <table class="shortcut-table">
                        <tbody>
                            <tr v-for="(row, index) in page.rows" :key="index">
                                <td
                                    v-if="isFeatureStart(page.rows, index)"
                                    class="shortcut-table__feature"
                                    :rowspan="featureRowSpan(page.rows, index)"
                                >
                                    {{ row.feature }}
                                </td>
                                <td class="shortcut-table__keys">
                                    <div class="shortcut-row__keys">
                                        <template
                                            v-for="(combo, comboIndex) in row.keys"
                                            :key="comboIndex"
                                        >
                                            <span
                                                v-if="comboIndex > 0"
                                                class="shortcut-row__or"
                                            >/</span>
                                            <template
                                                v-for="(key, keyIndex) in combo"
                                                :key="keyIndex"
                                            >
                                                <span
                                                    v-if="keyIndex > 0"
                                                    class="shortcut-row__plus"
                                                >+</span>
                                                <kbd class="keycap">{{ key }}</kbd>
                                            </template>
                                        </template>
                                    </div>
                                </td>
                                <td class="shortcut-table__desc">{{ row.desc }}</td>
                            </tr>
                        </tbody>
                    </table>
                </section>
            </article>
        </div>
    </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

// 快捷键的权威来源是各页面里的监听代码；这里只做展示，改键位时记得同步这张表
// （模拟器：views/games/emulator-player.vue，Flash：views/games/flash-player.vue，
//  存档管理：components/games/SaveManager.vue + SaveTreeView.vue，
//  分页：components/common/AppPagination.vue，大图预览：components/games/GameScreenshotGallery.vue）。
// 每个页面一张表；feature 相同的连续行会在「功能」列合并成一个单元格。
// 同一页内的行按键帽长度从短到长排列（短的在上，如 ` 在 Enter 上面），
// 相同功能的行保持相邻，便于合并单元格。
const SHORTCUT_PAGES = [
    {
        id: "shortcut-manage",
        title: "游戏管理",
        rows: [
            {
                feature: "分页",
                keys: [["←"], ["→"]],
                desc: "切换上一页 / 下一页",
            },
        ],
    },
    {
        id: "shortcut-discover",
        title: "游戏发现",
        rows: [
            {
                feature: "分页",
                keys: [["←"], ["→"]],
                desc: "切换上一页 / 下一页",
            },
        ],
    },
    {
        id: "shortcut-play",
        title: "游玩页面",
        rows: [
            {
                feature: "存档",
                keys: [["`"]],
                desc: "将当前进度同步至云端",
            },
            {
                feature: "存档",
                keys: [["Enter"]],
                desc: "载入本地存档并选中游戏画面",
            },
            {
                feature: "存档",
                keys: [["Alt", "`"]],
                desc: "打开存档管理面板",
            },
            {
                feature: "截图",
                keys: [["Ctrl", "Shift", "S"]],
                desc: "截取当前画面并保存到截图图库",
            },
        ],
    },
    {
        id: "shortcut-saves",
        title: "存档管理",
        rows: [
            {
                feature: "节点操作",
                keys: [["Delete"]],
                desc: "删除选中的云端节点",
            },
            {
                feature: "节点操作",
                keys: [["Shift", "↑"], ["Shift", "↓"]],
                desc: "调整选中节点的同级顺序",
            },
        ],
    },
    {
        id: "shortcut-preview",
        title: "图片预览",
        rows: [
            {
                feature: "大图预览",
                keys: [["←"], ["→"]],
                desc: "切换上一张 / 下一张",
            },
        ],
    },
];

/** 连续同功能的行里，只有第一行渲染「功能」单元格（其余靠 rowspan 合并）。 */
function isFeatureStart(rows, index) {
    return index === 0 || rows[index - 1].feature !== rows[index].feature;
}

function featureRowSpan(rows, index) {
    let span = 1;
    while (index + span < rows.length && rows[index + span].feature === rows[index].feature) {
        span += 1;
    }
    return span;
}

// ---------- 大纲：滚动高亮 + 平滑跳转 ----------
// 页面随窗口滚动（布局没有内层滚动容器），所以监听 window 的 scroll。
// 越过视口顶部 96px 的最后一个页面就是「当前所在」。
const activeId = ref(SHORTCUT_PAGES[0].id);
let scrollTicking = false;

function updateActiveSection() {
    const threshold = 96;
    let current = SHORTCUT_PAGES[0].id;
    for (const page of SHORTCUT_PAGES) {
        const el = document.getElementById(page.id);
        if (el && el.getBoundingClientRect().top <= threshold) {
            current = page.id;
        }
    }
    activeId.value = current;
}

function onWindowScroll() {
    if (scrollTicking) {
        return;
    }
    scrollTicking = true;
    window.requestAnimationFrame(() => {
        scrollTicking = false;
        updateActiveSection();
    });
}

function jumpTo(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

onMounted(() => {
    window.addEventListener("scroll", onWindowScroll, { passive: true });
    updateActiveSection();
});

onBeforeUnmount(() => {
    window.removeEventListener("scroll", onWindowScroll);
});
</script>

<style scoped>
/* 博客式单栏：整体限宽居中，左侧大纲 + 右侧连续正文 */
.shortcuts-page {
    width: 100%;
    max-width: 1040px;
    margin: 0 auto;
}

.shortcuts-page__body {
    display: grid;
    grid-template-columns: 188px minmax(0, 1fr);
    gap: 56px;
    align-items: start;
}

.shortcuts-toc {
    position: sticky;
    top: 24px;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    padding: 2px 0 2px 12px;
    border-left: 1px solid var(--border);
}

.shortcuts-toc__link {
    position: relative;
    margin-left: -13px;
    padding: 5px 10px 5px 12px;
    border-left: 2px solid transparent;
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-muted);
    text-decoration: none;
    border-radius: 0 6px 6px 0;
    transition: color 0.15s ease, background 0.15s ease;
}

.shortcuts-toc__link:hover {
    color: #0f172a;
    background: #eef2f7;
}

.shortcuts-toc__link.active {
    color: var(--brand-accent);
    border-left-color: var(--brand-accent);
    font-weight: 600;
}

.shortcuts-doc {
    min-width: 0;
}

.shortcut-section {
    scroll-margin-top: 24px;
}

/* 页面之间只留间距，不再画分隔线 */
.shortcut-section + .shortcut-section {
    margin-top: 34px;
}

.shortcut-section__title {
    margin: 0;
    font-size: 17px;
    font-weight: 600;
    color: #0f172a;
    line-height: 1.4;
}

/* 快捷键表格：功能（合并单元格）| 按键 | 说明。全框线（每个单元格四周都有边），
   固定布局保证三列对齐，单元格内容竖直居中、水平靠左。 */
.shortcut-table {
    width: 570px;
    max-width: 100%;
    margin-top: 10px;
    border-collapse: collapse;
    table-layout: fixed;
}

.shortcut-table td {
    box-sizing: border-box;
    padding: 9px 12px;
    border: 1px solid #e6ebf2;
    vertical-align: middle;
    text-align: left;
}

.shortcut-table__feature {
    width: 110px;
    font-size: 13px;
    font-weight: 500;
    color: #475569;
}

.shortcut-table__keys {
    width: 250px;
}

.shortcut-table__desc {
    width: 210px;
    font-size: 13px;
    line-height: 1.55;
    color: #475569;
}

.shortcut-row__keys {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px;
}

/* 键帽：边框 + 浅底 + 底部 2px 实体阴影（参考 flash.homes 的按键样式），
   小尺寸、等宽字体，组合键之间用 + 分隔。 */
.keycap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
    min-width: 30px;
    height: 28px;
    padding: 0 8px;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    box-shadow:
        0 2px 0 #d8e0ea,
        inset 0 -2px 0 rgba(15, 23, 42, 0.04);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    font-weight: 600;
    line-height: 1;
    color: #334155;
    white-space: nowrap;
}

.shortcut-row__plus,
.shortcut-row__or {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
}

.shortcut-row__or {
    margin: 0 1px;
    font-weight: 400;
}

@media (max-width: 900px) {
    .shortcuts-page__body {
        grid-template-columns: 1fr;
        gap: 22px;
    }

    /* 窄屏把大纲折成顶部的一排胶囊，不再吸顶 */
    .shortcuts-toc {
        position: static;
        flex-direction: row;
        flex-wrap: wrap;
        gap: 6px;
        padding: 0;
        border-left: 0;
    }

    .shortcuts-toc__link {
        margin-left: 0;
        padding: 4px 11px;
        border: 1px solid var(--border);
        border-radius: 999px;
        background: var(--surface);
    }

    .shortcuts-toc__link.active {
        border-color: var(--app-color-selected-border);
        background: var(--app-color-selected-bg);
    }
}

/* 窄屏把表格拆成一列：功能 → 按键 → 说明（表格头隐藏） */
@media (max-width: 640px) {
    .shortcut-table,
    .shortcut-table tbody,
    .shortcut-table tr,
    .shortcut-table td {
        display: block;
        width: 100%;
    }

    .shortcut-table tbody tr {
        padding: 10px 12px;
        border: 1px solid #e6ebf2;
    }

    .shortcut-table tbody tr + tr {
        margin-top: 8px;
    }

    .shortcut-table td {
        padding: 0;
        border: 0;
    }

    .shortcut-table__feature {
        width: 100%;
        padding: 0 0 4px;
        font-size: 12px;
        color: #94a3b8;
    }

    .shortcut-table__keys {
        padding: 0 0 7px;
    }
}
</style>
