<template>
    <div class="shortcuts-page">
        <div class="shortcuts-page__body">
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
                feature: "屏幕布局",
                keys: [["-"], ["="]],
                desc: "Backspace 左边两个键：减号上一个 / 等号下一个，NDS 循环切换屏幕布局",
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

</script>

<style scoped>
/* 单栏限宽居中：正文连续排布成一列派生小表。
   上边距抵消外层 .content 的 28px 内边距，让组表顶边与常驻侧栏 XGAME 品牌块的
   顶边（视口顶）对齐；底部内边距维持原样。 */
.shortcuts-page {
    width: 100%;
    max-width: 720px;
    margin: -14px auto 0;
}

.shortcuts-doc {
    min-width: 0;
}

.shortcut-section {
    scroll-margin-top: 24px;
    border: 1px solid #e6ecf3;
    border-bottom: 0;
    background: #fff;
}

/* 紧凑组表：段落之间零间距贴合堆叠，共享一条分隔线（各自不带底边框） */
.shortcut-section:first-child {
    border-top: 1px solid #e6ecf3;
}

.shortcut-section:last-child {
    border-bottom: 1px solid #e6ecf3;
}

/* 段落标题变成灰底分组头带，标题下压一条与行分隔线同色的细线 */
.shortcut-section__title {
    margin: 0;
    padding: 7px 14px;
    font-size: 17px;
    font-weight: 600;
    color: #0f172a;
    line-height: 1.4;
    background: #eef2f8;
    border-bottom: 1px solid #e6ecf3;
}

/* 快捷键表格：功能（合并单元格）| 按键 | 说明。外框由段落容器负责，
   单元格只画行分隔线（横向细线），高度紧凑、单屏能放整套内容。 */
.shortcut-table {
    width: 100%;
    max-width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}

.shortcut-table td {
    box-sizing: border-box;
    padding: 7px 14px;
    border: 0;
    border-bottom: 1px solid #f1f4f9;
    vertical-align: middle;
    text-align: left;
}

/* 组内最后一行不再压分隔线，底部交给段落容器自己 */
.shortcut-table tr:last-child td {
    border-bottom: 0;
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
