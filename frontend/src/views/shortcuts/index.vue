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
                            <tr v-for="(row, index) in page.rows" :key="row.id">
                                <td
                                    v-if="isFeatureStart(page.rows, index)"
                                    class="shortcut-table__feature"
                                    :rowspan="featureRowSpan(page.rows, index)"
                                >
                                    {{ row.feature }}
                                </td>
                                <td class="shortcut-table__keys">
                                    <div class="shortcut-row__keys">
                                        <span v-if="isCleared(row.id)" class="shortcut-row__cleared">
                                            已关闭
                                        </span>
                                        <template v-else>
                                            <template
                                                v-for="(part, partIndex) in bindingParts(
                                                    shortcuts.bindingOf(row.id)
                                                )"
                                                :key="partIndex"
                                            >
                                                <span
                                                    v-if="partIndex > 0"
                                                    class="shortcut-row__plus"
                                                >+</span>
                                                <kbd class="keycap">{{ part }}</kbd>
                                            </template>
                                            <span
                                                v-if="isCustom(row.id)"
                                                class="shortcut-row__tag"
                                            >自定义</span>
                                        </template>
                                    </div>
                                </td>
                                <td class="shortcut-table__actions">
                                    <div class="shortcut-row__actions">
                                        <app-button
                                            size="sm"
                                            :disabled="busyId === row.id"
                                            @click="openCapture(row)"
                                        >
                                            设置
                                        </app-button>
                                        <app-button
                                            size="sm"
                                            :disabled="isCleared(row.id) || busyId === row.id"
                                            @click="clearShortcut(row)"
                                        >
                                            清除
                                        </app-button>
                                        <app-button
                                            size="sm"
                                            :disabled="!isOverridden(row.id) || busyId === row.id"
                                            @click="resetShortcut(row)"
                                        >
                                            重置
                                        </app-button>
                                    </div>
                                </td>
                                <td class="shortcut-table__desc">{{ row.desc }}</td>
                            </tr>
                        </tbody>
                    </table>
                </section>
            </article>
        </div>

        <!-- 设置键位：弹框打开后独占键盘，按下组合键即保存；只有校验失败时才留在弹框里 -->
        <app-dialog
            v-model="captureVisible"
            title="设置快捷键"
            width="min(420px, 92vw)"
            align-center
            footer-mode="none"
        >
            <div class="shortcut-capture">
                <p class="shortcut-capture__action">
                    {{ captureAction?.feature }} · {{ captureAction?.desc }}
                </p>
                <div
                    class="shortcut-capture__box"
                    :class="{ 'shortcut-capture__box--error': Boolean(captureError) }"
                >
                    <div
                        v-if="capturePreviewParts.length"
                        class="shortcut-row__keys shortcut-capture__keys"
                    >
                        <template
                            v-for="(part, partIndex) in capturePreviewParts"
                            :key="partIndex"
                        >
                            <span v-if="partIndex > 0" class="shortcut-row__plus">+</span>
                            <kbd class="keycap">{{ part }}</kbd>
                        </template>
                    </div>
                    <p v-else class="shortcut-capture__hint">请按下新的快捷键</p>
                </div>
                <p v-if="captureError" class="shortcut-capture__error">{{ captureError }}</p>
                <p class="shortcut-capture__tips">
                    支持字母、数字、方向键、功能键与常见符号，可组合 Ctrl / Alt / Shift /
                    Meta（Windows / Command 键）；按 Esc 取消。
                </p>
            </div>
        </app-dialog>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { appMessage } from "@/utils/overlay";
import AppDialog from "@components/common/AppDialog.vue";
import {
    SHORTCUT_PAGES,
    bindingFromEvent,
    bindingParts,
    shortcutAction,
} from "@/constants/shortcuts";
import { useShortcutsStore } from "@/store/shortcuts";

const shortcuts = useShortcutsStore();

const captureVisible = ref(false);
const captureActionId = ref("");
const captureError = ref("");
const capturePreviewParts = ref([]);
const busyId = ref("");

const captureAction = computed(() => shortcutAction(captureActionId.value));

onMounted(() => {
    // Layout 已经拉过一次；这里补一次是为了直接打开本页、或上次请求失败时能重试
    void shortcuts.ensureLoaded().catch(() => {});
});

function isOverridden(actionId) {
    return shortcuts.isOverridden(actionId);
}

function isCleared(actionId) {
    return shortcuts.isOverridden(actionId) && shortcuts.bindingOf(actionId) === "";
}

function isCustom(actionId) {
    return shortcuts.isOverridden(actionId) && shortcuts.bindingOf(actionId) !== "";
}

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

function openCapture(row) {
    captureActionId.value = row.id;
    captureError.value = "";
    capturePreviewParts.value = [];
    captureVisible.value = true;
}

/** 同一个 scope（同时生效的动作组）里不能撞键；跨页面复用同一个键是允许的。 */
function findConflict(actionId, binding) {
    const action = shortcutAction(actionId);
    if (!action) {
        return null;
    }
    for (const page of SHORTCUT_PAGES) {
        if (page.scope !== action.scope) {
            continue;
        }
        for (const row of page.rows) {
            if (row.id === actionId) {
                continue;
            }
            const current = shortcuts.bindingOf(row.id);
            if (current && current === binding) {
                return row;
            }
        }
    }
    return null;
}

async function commitCapture(binding) {
    const actionId = captureActionId.value;
    busyId.value = actionId;
    try {
        await shortcuts.setBinding(actionId, binding);
        captureVisible.value = false;
        appMessage.success("快捷键已更新。");
    } catch (err) {
        captureError.value = err?.message || "保存失败，请稍后重试。";
    } finally {
        busyId.value = "";
    }
}

function onCaptureKeydown(event) {
    if (!captureVisible.value || busyId.value || event.isComposing) {
        return;
    }
    // 捕获阶段独占：别让弹框自己的 Esc、浏览器的组合键先一步处理
    event.preventDefault();
    event.stopPropagation();
    if (
        event.key === "Escape" &&
        !event.ctrlKey &&
        !event.altKey &&
        !event.metaKey &&
        !event.shiftKey
    ) {
        captureVisible.value = false;
        return;
    }
    if (event.repeat) {
        return;
    }
    const result = bindingFromEvent(event);
    if (result === null) {
        // 只按下了修饰键：继续等主键，不报错
        return;
    }
    if (result.error) {
        captureError.value = result.error;
        capturePreviewParts.value = [];
        return;
    }
    captureError.value = "";
    capturePreviewParts.value = bindingParts(result.binding);
    const conflict = findConflict(captureActionId.value, result.binding);
    if (conflict) {
        captureError.value = `该键位已被「${conflict.feature} · ${conflict.desc}」占用。`;
        return;
    }
    void commitCapture(result.binding);
}

watch(captureVisible, (visible) => {
    if (visible) {
        window.addEventListener("keydown", onCaptureKeydown, true);
    } else {
        window.removeEventListener("keydown", onCaptureKeydown, true);
    }
});

onBeforeUnmount(() => {
    window.removeEventListener("keydown", onCaptureKeydown, true);
});

async function clearShortcut(row) {
    busyId.value = row.id;
    try {
        await shortcuts.setBinding(row.id, "");
        appMessage.success("已关闭该快捷键。");
    } catch (err) {
        if (!err?.reported) {
            appMessage.error("保存失败，请稍后重试。");
        }
    } finally {
        busyId.value = "";
    }
}

async function resetShortcut(row) {
    // 关闭某个动作后，它的默认键位可能已被同页其它动作占用；恢复前先查一遍，
    // 否则两个动作会同时响应同一个键。
    const defaultBinding = shortcutAction(row.id)?.defaultBinding || "";
    const conflict = defaultBinding ? findConflict(row.id, defaultBinding) : null;
    if (conflict) {
        appMessage.warning(
            `无法恢复默认键位：「${conflict.feature} · ${conflict.desc}」已在使用该键。`
        );
        return;
    }
    busyId.value = row.id;
    try {
        await shortcuts.resetBinding(row.id);
        appMessage.success("已恢复默认键位。");
    } catch (err) {
        if (!err?.reported) {
            appMessage.error("保存失败，请稍后重试。");
        }
    } finally {
        busyId.value = "";
    }
}
</script>

<style scoped>
/* 单栏限宽居中：正文连续排布成一列派生小表。
   上边距抵消外层 .content 的 28px 内边距，让组表顶边与常驻侧栏 XGAME 品牌块的
   顶边（视口顶）对齐；底部内边距维持原样。 */
.shortcuts-page {
    width: 100%;
    max-width: 820px;
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

/* 快捷键表格：功能（合并单元格）| 按键 | 操作 | 说明。外框由段落容器负责，
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
    width: 96px;
    font-size: 13px;
    font-weight: 500;
    color: #475569;
}

.shortcut-table__keys {
    width: 210px;
}

.shortcut-table__actions {
    width: 196px;
}

.shortcut-row__actions {
    display: flex;
    align-items: center;
    gap: 8px;
}

.shortcut-table__desc {
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

.shortcut-row__cleared {
    font-size: 13px;
    color: #94a3b8;
}

.shortcut-row__tag {
    margin-left: 3px;
    padding: 1px 7px;
    border-radius: 999px;
    background: #e0f2fe;
    color: #0369a1;
    font-size: 11px;
    line-height: 1.6;
    white-space: nowrap;
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

.shortcut-row__plus {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
}

/* ---------- 设置键位弹框 ---------- */

.shortcut-capture {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.shortcut-capture__action {
    margin: 0;
    font-size: 13px;
    color: #475569;
}

.shortcut-capture__box {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 96px;
    padding: 16px;
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
    background: #f8fafc;
}

.shortcut-capture__box--error {
    border-color: #ff3320;
    background: #fff7f6;
}

.shortcut-capture__keys {
    justify-content: center;
}

.shortcut-capture__hint {
    margin: 0;
    font-size: 14px;
    color: #94a3b8;
}

.shortcut-capture__error {
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
    color: #ff3320;
}

.shortcut-capture__tips {
    margin: 0;
    font-size: 12px;
    line-height: 1.6;
    color: #94a3b8;
}

/* 窄屏把表格拆成一列：功能 → 按键 → 操作 → 说明（表格头隐藏） */
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

    .shortcut-table__actions {
        padding: 0 0 7px;
    }

    .shortcut-row__actions {
        gap: 12px;
    }
}
</style>
