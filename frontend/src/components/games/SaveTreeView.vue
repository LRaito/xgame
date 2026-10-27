<template>
    <div ref="rootRef" class="save-tree">
        <aside class="save-tree__sidebar">
            <div class="save-tree__side-head">
                <el-input
                    v-model="keyword"
                    class="save-tree__search"
                    size="small"
                    placeholder="搜索存档详情"
                />
            </div>
            <div v-if="canScrollUp" class="save-tree__side-page">
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
            <div
                ref="sideListRef"
                class="save-tree__side-list"
                @scroll="updateSideScroll"
            >
                <p v-if="!sidebarNodes.length" class="save-tree__empty-side">
                    {{ keyword.trim() ? "没有匹配的存档" : "还没有云端存档" }}
                </p>
                <div
                    v-for="node in sidebarNodes"
                    :key="node.id"
                    class="save-tree__node save-tree__node--side"
                    :class="{
                        'save-tree__node--dragging': dragId === node.id,
                        'save-tree__node--active': selectedId === node.id,
                    }"
                    :draggable="!locked && editingRemarkId !== node.id"
                    @dragstart="onDragStart($event, node)"
                    @dragend="onDragEnd"
                    @click.stop="selectNode(node)"
                    @dblclick.stop="startRemarkEdit(node, 'side')"
                    @contextmenu.prevent.stop="openDetail(node)"
                >
                    <input
                        v-if="editingRemarkId === node.id"
                        :ref="(el) => (remarkInputRef = el)"
                        v-model="remarkDraft"
                        class="save-tree__side-input"
                        maxlength="100"
                        placeholder="填写描述"
                        @click.stop
                        @dblclick.stop
                        @keydown.enter.prevent="onRemarkEnter($event, node)"
                        @keydown.esc.prevent.stop="cancelRemarkEdit"
                        @blur="saveRemark(node)"
                    />
                    <span v-else class="save-tree__node-text">{{ nodeText(node) }}</span>
                </div>
            </div>
            <div v-if="canScrollDown" class="save-tree__side-page">
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

        <section
            ref="canvasRef"
            class="save-tree__canvas"
            tabindex="0"
            @wheel.prevent="onWheel"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerEnd"
            @pointercancel="onPointerEnd"
            @keydown="onKeydown"
            @dragover.prevent
            @drop.prevent="onDropCanvas"
            @contextmenu.prevent
        >
            <div
                class="save-tree__toolbar"
                @dragover.prevent.stop
                @drop.prevent.stop
            >
                <app-button
                    variant="secondary"
                    tone="dark"
                    size="sm"
                    @click="fitToCanvas"
                >
                    适应视图
                </app-button>
                <app-button
                    variant="secondary"
                    tone="dark"
                    size="sm"
                    @click="toggleFullscreen"
                >
                    {{ isFullscreen ? "退出全屏" : "全屏" }}
                </app-button>
            </div>

            <p v-if="!nodes.length" class="save-tree__empty">
                还没有云端存档。先切到「本地存档」点「同步至云端」。
            </p>

            <div
                class="save-tree__viewport"
                :style="{
                    transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
                }"
            >
                <svg
                    v-if="layout.edges.length"
                    class="save-tree__edges"
                    :width="layout.width"
                    :height="layout.height"
                >
                    <path
                        v-for="edge in layout.edges"
                        :key="edge.key"
                        :d="edge.d"
                    />
                </svg>
                <div
                    v-for="node in layout.nodes"
                    :key="node.id"
                    class="save-tree__node"
                    :class="{
                        'save-tree__node--dragging': dragId === node.id,
                        'save-tree__node--drop': dropTargetId === node.id,
                        'save-tree__node--active': selectedId === node.id,
                    }"
                    :style="{
                        left: `${node.x}px`,
                        top: `${node.y}px`,
                        width: `${NODE_W}px`,
                        height: `${NODE_H}px`,
                    }"
                    :draggable="!locked"
                    @dragstart.stop="onDragStart($event, node)"
                    @dragend="onDragEnd"
                    @dragover.prevent.stop="onDragOverNode($event, node)"
                    @dragleave.stop="onDragLeaveNode(node)"
                    @drop.prevent.stop="onDropNode($event, node)"
                    @click.stop="selectNode(node)"
                    @dblclick.stop="onCanvasNodeDblClick(node)"
                    @contextmenu.prevent.stop="openDetail(node)"
                >
                    <span class="save-tree__node-text">{{ nodeText(node) }}</span>
                </div>
            </div>
        </section>

        <div
            v-if="notice"
            class="save-tree__notice"
            :class="`save-tree__notice--${notice.type}`"
            role="status"
            aria-live="polite"
        >
            <span class="save-tree__notice-text">{{ notice.text }}</span>
            <app-button
                text
                tone="dark"
                size="sm"
                icon-only
                round
                aria-label="关闭提示"
                @click="clearNotice"
            >
                ✕
            </app-button>
        </div>

        <!-- 右键详情弹框：必须留在 .save-tree 内（全屏时可见），且不能放进带 transform 的图层 -->
        <div
            v-if="detailNode"
            class="save-tree__detail"
            @click.self="closeDetail"
        >
            <section class="save-tree__detail-card">
                <header class="save-tree__detail-head">
                    <h3 class="save-tree__detail-title">存档详情</h3>
                    <app-button
                        text
                        tone="dark"
                        size="sm"
                        icon-only
                        round
                        aria-label="关闭"
                        @click="closeDetail"
                    >
                        ✕
                    </app-button>
                </header>
                <div class="save-tree__detail-body">
                    <textarea
                        v-if="editingRemarkId === detailNode.id"
                        :ref="(el) => (detailInputRef = el)"
                        v-model="remarkDraft"
                        class="save-tree__detail-input"
                        maxlength="100"
                        placeholder="填写描述"
                        @keydown.esc.stop.prevent="cancelRemarkEdit"
                        @keydown.enter.ctrl.prevent="saveRemark(detailNode)"
                        @keydown.enter.meta.prevent="saveRemark(detailNode)"
                        @blur="saveRemark(detailNode)"
                    ></textarea>
                    <p
                        v-else
                        class="save-tree__detail-remark"
                        :class="{
                            'save-tree__detail-remark--empty': !detailNode.remark,
                        }"
                        @dblclick.stop="startRemarkEdit(detailNode, 'detail')"
                    >
                        {{ detailNode.remark || "暂无描述" }}
                    </p>
                    <div
                        v-if="editingRemarkId === detailNode.id"
                        class="save-tree__detail-edit-foot"
                    >
                        <span>{{ remarkDraft.length }}/100</span>
                        <span>Ctrl+Enter 保存，Esc 取消</span>
                    </div>
                    <dl class="save-tree__detail-meta">
                        <div>
                            <dt>创建时间</dt>
                            <dd>{{ formatDateTime(detailNode.created_at) }}</dd>
                        </div>
                    </dl>
                    <ul v-if="detailLoading" class="save-tree__file-list">
                        <li class="save-tree__file-empty">加载中…</li>
                    </ul>
                    <ul v-else-if="detailFiles.length" class="save-tree__file-list">
                        <li
                            v-for="file in detailFiles"
                            :key="file.id"
                            class="save-tree__file-row"
                        >
                            <span class="save-tree__file-name">{{ file.name }}</span>
                            <span class="save-tree__file-size">
                                {{ formatBytes(file.size) }}
                            </span>
                            <app-button
                                variant="secondary"
                                tone="dark"
                                size="sm"
                                @click="downloadFile(detailNode, file)"
                            >
                                下载
                            </app-button>
                        </li>
                    </ul>
                </div>
                <footer class="save-tree__detail-actions">
                    <app-button
                        variant="secondary"
                        tone="dark"
                        :disabled="locked"
                        @click="onDetailSync"
                    >
                        同步至本地
                    </app-button>
                    <app-button
                        v-if="detailNode.parent_id != null"
                        variant="secondary"
                        tone="dark"
                        :disabled="locked"
                        @click="onDetailDetach"
                    >
                        设为顶层
                    </app-button>
                    <app-button
                        variant="danger"
                        tone="dark"
                        :disabled="locked"
                        @click="onDetailDelete"
                    >
                        删除
                    </app-button>
                </footer>
            </section>
        </div>
    </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import {
    cloudSaveDetailAPI,
    cloudSaveFileDownloadPath,
    moveCloudSaveAPI,
    setCloudSaveParentAPI,
    updateCloudSaveAPI,
} from "@/api/games";
import { downloadViaPath } from "@/utils/download";
import { formatBytes, formatDateTime } from "@/utils/fileDisplay";
import { appMessage } from "@/utils/overlay";

const NODE_W = 92;
const NODE_H = 48;
const GAP_X = 64;
const GAP_Y = 16;
const ROOT_GAP = 48;
const PAD = 40;
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 2.5;
const MOVE_SAVE_DELAY = 200; // 连按方向键时，停手后再落库

const props = defineProps({
    // 快照的扁平列表（含 parent_id），由父组件按展示顺序（sort_order 升序）给出
    snapshots: { type: Array, default: () => [] },
    // 父组件正在删除/同步等操作：禁止拖动与弹框按钮
    busy: { type: Boolean, default: false },
});

const emit = defineEmits([
    "sync-local",
    "delete",
    "parents-changed",
    "remark-changed",
    "order-changed",
    "refresh",
]);

const rootRef = ref(null);
const canvasRef = ref(null);
const sideListRef = ref(null);
const canScrollUp = ref(false);
const canScrollDown = ref(false);
const nodes = ref([]);
const zoom = ref(1);
const panX = ref(0);
const panY = ref(0);
const dragId = ref(null);
const dropTargetId = ref(null);
const mutating = ref(false);
const detailId = ref(null);
const detailFiles = ref([]);
const detailLoading = ref(false);
const isFullscreen = ref(false);
const hasFitted = ref(false);
const keyword = ref("");
const selectedId = ref(null);
const editingRemarkId = ref(null);
const remarkDraft = ref("");
const remarkSavingId = ref(null);
const remarkInputRef = ref(null);
const detailInputRef = ref(null);
const notice = ref(null);
let noticeTimer = null;
// 同级排序：本地先动、停手再落库；请求串行发送，队列里每个节点只保留最新目标位置
let moveTimer = null;
let moveSending = false;
const pendingMoves = new Map();

const locked = computed(() => props.busy || mutating.value);

const byId = computed(() => new Map(nodes.value.map((node) => [node.id, node])));

/**
 * 每个节点的有效父级：父级不存在、指向自己、或祖先链成环时一律降级为根，
 * 保证脏数据也能画出图来（后端已尽量不让这种数据产生）。
 */
const resolvedParents = computed(() => {
    const result = new Map();
    for (const node of nodes.value) {
        const parentId = node.parent_id;
        if (parentId == null || parentId === node.id || !byId.value.has(parentId)) {
            result.set(node.id, null);
            continue;
        }
        const seen = new Set([node.id]);
        let cursor = byId.value.get(parentId);
        let cyclic = false;
        while (cursor) {
            if (seen.has(cursor.id)) {
                cyclic = true;
                break;
            }
            seen.add(cursor.id);
            cursor =
                cursor.parent_id == null
                    ? null
                    : byId.value.get(cursor.parent_id) || null;
        }
        result.set(node.id, cyclic ? null : parentId);
    }
    return result;
});

const rootNodes = computed(() =>
    nodes.value.filter((node) => resolvedParents.value.get(node.id) == null),
);

const detailNode = computed(
    () => nodes.value.find((node) => node.id === detailId.value) || null,
);

const sidebarNodes = computed(() => {
    const q = keyword.value.trim().toLowerCase();
    if (!q) {
        return nodes.value;
    }
    return nodes.value.filter((node) =>
        String(node.remark || "").toLowerCase().includes(q),
    );
});

const selectedNode = computed(
    () => nodes.value.find((node) => node.id === selectedId.value) || null,
);

const nodesKey = computed(() =>
    nodes.value
        .map((node) => node.id)
        .sort((a, b) => a - b)
        .join(","),
);

/** 节点正文：换行折成空格，交给 CSS 截成最多两行（每行 5 个汉字）。 */
function nodeText(node) {
    return String(node.remark || "").replace(/\s+/g, " ").trim();
}

function blurActiveControl() {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== document.body) {
        active.blur();
    }
}

function selectNode(node) {
    selectedId.value = node.id;
    blurActiveControl();
}

function clearNotice() {
    notice.value = null;
    if (noticeTimer) {
        window.clearTimeout(noticeTimer);
        noticeTimer = null;
    }
}

function showNotice(text, type = "error") {
    clearNotice();
    notice.value = { text, type };
    noticeTimer = window.setTimeout(() => {
        notice.value = null;
        noticeTimer = null;
    }, 4000);
}

async function startRemarkEdit(node, source = "side") {
    if (locked.value || remarkSavingId.value != null) {
        return;
    }
    if (editingRemarkId.value === node.id) {
        return;
    }
    selectedId.value = node.id;
    editingRemarkId.value = node.id;
    remarkDraft.value = String(node.remark || "").slice(0, 100);
    await nextTick();
    const input = source === "detail" ? detailInputRef.value : remarkInputRef.value;
    input?.focus();
    input?.setSelectionRange?.(input.value.length, input.value.length);
}

function cancelRemarkEdit() {
    editingRemarkId.value = null;
    remarkDraft.value = "";
}

function onRemarkEnter(event, node) {
    if (event.isComposing) {
        return;
    }
    void saveRemark(node);
}

async function saveRemark(node) {
    if (editingRemarkId.value !== node.id || remarkSavingId.value != null) {
        return;
    }
    const previous = String(node.remark || "");
    const remark = remarkDraft.value.trim().slice(0, 100);
    if (remark === previous) {
        cancelRemarkEdit();
        return;
    }
    remarkSavingId.value = node.id;
    node.remark = remark;
    try {
        const detail = await updateCloudSaveAPI(node.id, remark, {
            notShowError: true,
        });
        node.remark = detail.remark || "";
        emit("remark-changed", { id: node.id, remark: node.remark });
        if (editingRemarkId.value === node.id) {
            editingRemarkId.value = null;
            remarkDraft.value = "";
        }
        appMessage.success("描述已更新。");
    } catch (err) {
        node.remark = previous;
        showNotice(err?.message || "描述保存失败。");
    } finally {
        remarkSavingId.value = null;
    }
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function edgePath(x1, y1, x2, y2) {
    const dx = Math.max(28, (x2 - x1) / 2);
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

/** 自动树形布局：叶子自上而下排，父节点纵向居中在自己的子级块上。 */
const layout = computed(() => {
    const children = new Map();
    for (const node of nodes.value) {
        children.set(node.id, []);
    }
    for (const node of nodes.value) {
        const parentId = resolvedParents.value.get(node.id);
        if (parentId != null) {
            children.get(parentId).push(node);
        }
    }

    const heights = new Map();
    function measure(node) {
        const kids = children.get(node.id) || [];
        if (!kids.length) {
            heights.set(node.id, NODE_H);
            return NODE_H;
        }
        let height = 0;
        kids.forEach((kid, index) => {
            height += measure(kid);
            if (index < kids.length - 1) {
                height += GAP_Y;
            }
        });
        heights.set(node.id, height);
        return height;
    }

    const positions = new Map();
    const edges = [];
    function place(node, depth, top) {
        const x = PAD + depth * (NODE_W + GAP_X);
        const height = heights.get(node.id) || NODE_H;
        const y = top + (height - NODE_H) / 2;
        positions.set(node.id, { x, y });
        const kids = children.get(node.id) || [];
        let childTop = top;
        for (const kid of kids) {
            place(kid, depth + 1, childTop);
            const childPos = positions.get(kid.id);
            edges.push({
                key: `${node.id}-${kid.id}`,
                d: edgePath(
                    x + NODE_W,
                    y + NODE_H / 2,
                    childPos.x,
                    childPos.y + NODE_H / 2,
                ),
            });
            childTop += (heights.get(kid.id) || NODE_H) + GAP_Y;
        }
    }

    let top = PAD;
    for (const root of rootNodes.value) {
        const height = measure(root);
        place(root, 0, top);
        top += height + ROOT_GAP;
    }

    let maxX = 0;
    let maxY = 0;
    positions.forEach(({ x, y }) => {
        maxX = Math.max(maxX, x + NODE_W);
        maxY = Math.max(maxY, y + NODE_H);
    });

    return {
        nodes: nodes.value.map((node) => ({
            ...node,
            ...(positions.get(node.id) || { x: PAD, y: PAD }),
        })),
        edges,
        width: maxX + PAD,
        height: maxY + PAD,
    };
});

function fitToCanvas() {
    const el = canvasRef.value;
    if (!el) {
        return;
    }
    const width = el.clientWidth;
    const height = el.clientHeight;
    if (!width || !height) {
        return;
    }
    const content = layout.value;
    const scale = clamp(
        Math.min(
            (width - PAD * 2) / content.width,
            (height - PAD * 2) / content.height,
            1,
        ),
        MIN_ZOOM,
        1.4,
    );
    zoom.value = scale;
    panX.value = (width - content.width * scale) / 2;
    panY.value = (height - content.height * scale) / 2;
    hasFitted.value = true;
}

watch(
    () => props.snapshots,
    (items) => {
        nodes.value = (items || []).map((item) => ({ ...item }));
        if (
            selectedId.value == null ||
            !nodes.value.some((node) => node.id === selectedId.value)
        ) {
            selectedId.value = nodes.value[0]?.id ?? null;
        }
        if (
            detailId.value != null &&
            !nodes.value.some((node) => node.id === detailId.value)
        ) {
            closeDetail();
        }
        if (
            editingRemarkId.value != null &&
            !nodes.value.some((node) => node.id === editingRemarkId.value)
        ) {
            cancelRemarkEdit();
        }
    },
    { immediate: true },
);

watch(
    nodesKey,
    () => {
        nextTick(() => {
            fitToCanvas();
            updateSideScroll();
        });
    },
    { immediate: true },
);

/** 侧栏还能往上/往下滚时，分别在列表上方/下方显示翻页箭头。 */
function updateSideScroll() {
    const el = sideListRef.value;
    if (!el) {
        canScrollUp.value = false;
        canScrollDown.value = false;
        return;
    }
    canScrollUp.value = el.scrollTop > 1;
    canScrollDown.value =
        el.scrollTop + el.clientHeight < el.scrollHeight - 1;
}

function scrollSideUp() {
    const el = sideListRef.value;
    if (!el) {
        return;
    }
    el.scrollBy({ top: -el.clientHeight, behavior: "smooth" });
}

function scrollSideDown() {
    const el = sideListRef.value;
    if (!el) {
        return;
    }
    el.scrollBy({ top: el.clientHeight, behavior: "smooth" });
}

// ---------- 缩放 / 平移 ----------

function onWheel(event) {
    const el = canvasRef.value;
    if (!el) {
        return;
    }
    const target = event.target;
    if (target instanceof Element && target.closest(".save-tree__toolbar")) {
        return;
    }
    const rect = el.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
    const next = clamp(
        zoom.value * Math.exp(-delta * 0.0015),
        MIN_ZOOM,
        MAX_ZOOM,
    );
    panX.value = px - ((px - panX.value) / zoom.value) * next;
    panY.value = py - ((py - panY.value) / zoom.value) * next;
    zoom.value = next;
}

let pointerStart = null;

function onPointerDown(event) {
    if (event.button !== 0) {
        return;
    }
    const target = event.target;
    if (!(target instanceof Element)) {
        return;
    }
    if (
        target.closest(".save-tree__node") ||
        target.closest(".save-tree__toolbar")
    ) {
        return;
    }
    pointerStart = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        panX: panX.value,
        panY: panY.value,
    };
    canvasRef.value?.focus();
    canvasRef.value?.setPointerCapture?.(event.pointerId);
}

function onPointerMove(event) {
    if (!pointerStart || event.pointerId !== pointerStart.pointerId) {
        return;
    }
    panX.value = pointerStart.panX + event.clientX - pointerStart.x;
    panY.value = pointerStart.panY + event.clientY - pointerStart.y;
}

function onPointerEnd(event) {
    if (!pointerStart || event.pointerId !== pointerStart.pointerId) {
        return;
    }
    pointerStart = null;
    try {
        canvasRef.value?.releasePointerCapture?.(event.pointerId);
    } catch {
        // 指针已经释放时忽略
    }
}

function onKeydown(event) {
    if (detailId.value != null) {
        return;
    }
    // Shift + ↑/↓ 是同级排序，交给 window 上的管理器处理，这里不能同时平移
    if (event.altKey || event.shiftKey) {
        return;
    }
    // 方向与内容移动一致：按哪个方向，画面就往哪边走（看起来像在挪节点）
    const step = 40;
    const deltas = {
        ArrowLeft: [-step, 0],
        ArrowRight: [step, 0],
        ArrowUp: [0, -step],
        ArrowDown: [0, step],
    };
    const delta = deltas[event.key];
    if (!delta) {
        return;
    }
    event.preventDefault();
    panX.value += delta[0];
    panY.value += delta[1];
}

// ---------- 拖动建树 ----------

function onDragStart(event, node) {
    if (locked.value) {
        event.preventDefault();
        return;
    }
    dragId.value = node.id;
    selectedId.value = node.id;
    event.dataTransfer.effectAllowed = "move";
    // Firefox 不 setData 就不会真正开始拖拽
    event.dataTransfer.setData("text/plain", String(node.id));
}

function onDragEnd() {
    dragId.value = null;
    dropTargetId.value = null;
}

function onDragOverNode(event, node) {
    if (dragId.value == null || dragId.value === node.id) {
        return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    dropTargetId.value = node.id;
}

function onDragLeaveNode(node) {
    if (dropTargetId.value === node.id) {
        dropTargetId.value = null;
    }
}

function readDragId(event) {
    if (dragId.value != null) {
        return dragId.value;
    }
    const raw = event.dataTransfer?.getData("text/plain");
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function isDescendantOf(targetId, ancestorId) {
    const seen = new Set();
    let cursor = byId.value.get(targetId);
    while (cursor) {
        if (cursor.id === ancestorId) {
            return true;
        }
        if (seen.has(cursor.id)) {
            return false;
        }
        seen.add(cursor.id);
        cursor =
            cursor.parent_id == null
                ? null
                : byId.value.get(cursor.parent_id) || null;
    }
    return false;
}

function onDropNode(event, node) {
    event.preventDefault();
    event.stopPropagation();
    const id = readDragId(event);
    dragId.value = null;
    dropTargetId.value = null;
    if (locked.value || id == null || id === node.id || !byId.value.has(id)) {
        return;
    }
    if (isDescendantOf(node.id, id)) {
        showNotice("不能把存档拖到它自己的子级下面。", "warning");
        return;
    }
    if (resolvedParents.value.get(id) === node.id) {
        return;
    }
    void applyParent(id, node.id);
}

function onDropCanvas(event) {
    const id = readDragId(event);
    dragId.value = null;
    dropTargetId.value = null;
    if (locked.value || id == null || !byId.value.has(id)) {
        return;
    }
    if (resolvedParents.value.get(id) == null) {
        return;
    }
    void applyParent(id, null);
}

async function applyParent(id, parentId) {
    const node = nodes.value.find((item) => item.id === id);
    if (!node) {
        return;
    }
    const previous = node.parent_id ?? null;
    if (previous === parentId) {
        return;
    }
    // 换了父级，之前排在同级里的目标位置就作废了
    pendingMoves.delete(id);
    node.parent_id = parentId;
    selectedId.value = id;
    mutating.value = true;
    try {
        const detail = await setCloudSaveParentAPI(id, parentId, {
            notShowError: true,
        });
        node.parent_id = detail.parent_id ?? null;
        emit("parents-changed", { id, parentId: node.parent_id });
    } catch (err) {
        node.parent_id = previous;
        showNotice(err?.message || "设置父子关系失败。");
        emit("refresh");
    } finally {
        mutating.value = false;
    }
}

// ---------- 同级排序（Shift + ↑/↓） ----------

/** 同一父级的兄弟节点，顺序与画布布局、左侧列表一致。 */
function siblingsOf(nodeId) {
    const parentId = resolvedParents.value.get(nodeId) ?? null;
    return nodes.value.filter(
        (node) => (resolvedParents.value.get(node.id) ?? null) === parentId,
    );
}

function moveSelected(delta) {
    const node = selectedNode.value;
    if (!node) {
        return false;
    }
    const siblings = siblingsOf(node.id);
    const from = siblings.findIndex((item) => item.id === node.id);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= siblings.length) {
        // 已经在同级首/尾：消费按键但不动作（不环绕）
        return true;
    }
    // 先本地乐观重排：摘出节点，插到目标兄弟之前（上移）或之后（下移）
    const reference = siblings[to];
    const next = nodes.value.filter((item) => item.id !== node.id);
    const refIndex = next.findIndex((item) => item.id === reference.id);
    next.splice(delta > 0 ? refIndex + 1 : refIndex, 0, node);
    nodes.value = next;

    pendingMoves.set(node.id, to);
    if (moveTimer != null) {
        clearTimeout(moveTimer);
    }
    moveTimer = setTimeout(() => {
        moveTimer = null;
        void flushMove();
    }, MOVE_SAVE_DELAY);
    return true;
}

/**
 * 按顺序把队列里的挪位落库：每次取队首的那一条，成功后再取下一批。
 * 同一个节点在等待期间被继续挪动时，只保留最新的目标位置。
 */
async function flushMove() {
    if (moveTimer != null) {
        clearTimeout(moveTimer);
        moveTimer = null;
    }
    if (moveSending || !pendingMoves.size) {
        return;
    }
    const [id, target] = pendingMoves.entries().next().value;
    moveSending = true;
    try {
        const items =
            (await moveCloudSaveAPI(id, target, { notShowError: true })) || [];
        if (pendingMoves.get(id) === target) {
            pendingMoves.delete(id);
        }
        // 期间若刚好有人删/加/挪了快照，列表成员已经变了，别用旧响应覆盖它
        const currentShape = new Map(
            nodes.value.map((node) => [node.id, node.parent_id ?? null]),
        );
        const sameNodes =
            items.length === currentShape.size &&
            items.every(
                (item) => currentShape.get(item.id) === (item.parent_id ?? null),
            );
        if (!pendingMoves.size && sameNodes) {
            // 队列清空才用后端返回的整份列表对齐（顺序的真相在后端）
            nodes.value = items.map((item) => ({ ...item }));
            emit("order-changed", items);
        }
    } catch (err) {
        pendingMoves.clear();
        showNotice(err?.message || "调整顺序失败。");
        emit("refresh");
    } finally {
        moveSending = false;
        if (pendingMoves.size) {
            void flushMove();
        }
    }
}

// ---------- 右键详情 ----------

function openDetail(node) {
    selectedId.value = node.id;
    blurActiveControl();
    if (detailId.value === node.id) {
        return;
    }
    detailId.value = node.id;
    detailFiles.value = [];
    detailLoading.value = true;
    void loadDetail(node.id);
}

function onCanvasNodeDblClick(node) {
    if (locked.value || dragId.value != null) {
        return;
    }
    openDetail(node);
    if (editingRemarkId.value !== node.id) {
        void startRemarkEdit(node, "detail");
    }
}

async function loadDetail(id) {
    try {
        const detail = await cloudSaveDetailAPI(id);
        if (detailId.value === id) {
            detailFiles.value = detail.files || [];
        }
    } catch {
        if (detailId.value === id) {
            detailFiles.value = [];
        }
    } finally {
        if (detailId.value === id) {
            detailLoading.value = false;
        }
    }
}

function closeDetail() {
    if (editingRemarkId.value != null && editingRemarkId.value === detailId.value) {
        cancelRemarkEdit();
    }
    detailId.value = null;
    detailFiles.value = [];
    detailLoading.value = false;
}

function downloadFile(node, file) {
    downloadViaPath(cloudSaveFileDownloadPath(node.id, file.id));
}

function onDetailSync() {
    const node = detailNode.value;
    if (!node) {
        return;
    }
    closeDetail();
    emit("sync-local", node);
}

async function onDetailDetach() {
    const node = detailNode.value;
    if (!node) {
        return;
    }
    closeDetail();
    await applyParent(node.id, null);
}

function onDetailDelete() {
    const node = detailNode.value;
    if (!node) {
        return;
    }
    closeDetail();
    emit("delete", node);
}

// ---------- 全屏 ----------

async function toggleFullscreen() {
    const el = rootRef.value;
    if (!el) {
        return;
    }
    if (document.fullscreenElement === el) {
        try {
            await document.exitFullscreen();
        } catch {
            // 已经是窗口态时忽略
        }
        return;
    }
    if (typeof el.requestFullscreen !== "function") {
        appMessage.warning("当前浏览器不支持全屏。");
        return;
    }
    try {
        await el.requestFullscreen();
    } catch {
        appMessage.warning("当前浏览器不支持全屏。");
    }
}

function onFullscreenChange() {
    isFullscreen.value = document.fullscreenElement === rootRef.value;
    nextTick(() => fitToCanvas());
}

// ---------- 生命周期 ----------

let resizeObserver = null;
let sideListObserver = null;

onMounted(() => {
    document.addEventListener("fullscreenchange", onFullscreenChange);
    if (typeof ResizeObserver === "function" && canvasRef.value) {
        resizeObserver = new ResizeObserver(() => {
            if (!hasFitted.value) {
                fitToCanvas();
            }
        });
        resizeObserver.observe(canvasRef.value);
    }
    if (typeof ResizeObserver === "function" && sideListRef.value) {
        sideListObserver = new ResizeObserver(updateSideScroll);
        sideListObserver.observe(sideListRef.value);
    }
    nextTick(() =>
        requestAnimationFrame(() => {
            fitToCanvas();
            updateSideScroll();
        }),
    );
});

onBeforeUnmount(() => {
    document.removeEventListener("fullscreenchange", onFullscreenChange);
    resizeObserver?.disconnect();
    sideListObserver?.disconnect();
    // 关弹框时把还没到点的排序请求立刻发出去，别丢掉最后一次挪位
    if (moveTimer != null) {
        void flushMove();
    }
    clearNotice();
    if (document.fullscreenElement === rootRef.value) {
        document.exitFullscreen?.().catch(() => {});
    }
});

/** 给管理器的 Enter/Delete 快捷键用；详情/编辑/拖动/忙碌时不响应。 */
function handleSaveHotkey(key) {
    if (
        locked.value ||
        dragId.value != null ||
        detailId.value != null ||
        editingRemarkId.value != null ||
        remarkSavingId.value != null
    ) {
        return false;
    }
    const node = selectedNode.value;
    if (!node) {
        return false;
    }
    if (key === "Enter") {
        emit("sync-local", node);
        return true;
    }
    if (key === "Delete") {
        emit("delete", node);
        return true;
    }
    if (key === "ArrowUp") {
        return moveSelected(-1);
    }
    if (key === "ArrowDown") {
        return moveSelected(1);
    }
    return false;
}

/** 给管理器的 ESC 分层用：先取消编辑，再关详情，再退全屏，都没有就交回管理器。 */
function handleEscape() {
    if (editingRemarkId.value != null) {
        cancelRemarkEdit();
        return true;
    }
    if (detailId.value != null) {
        closeDetail();
        return true;
    }
    if (isFullscreen.value) {
        document.exitFullscreen?.().catch(() => {});
        return true;
    }
    return false;
}

defineExpose({ handleEscape, handleSaveHotkey });
</script>

<style scoped>
.save-tree {
    position: relative;
    display: flex;
    flex: 1;
    min-height: 0;
    gap: 12px;
    overflow: hidden;
}

/* 全屏时把整个树区域铺满屏幕，深色底盖住原页面 */
.save-tree:fullscreen {
    width: 100vw;
    height: 100vh;
    background: #0f172a;
}

.save-tree__sidebar {
    /* 与本地存档按钮列同宽（变量由存档弹框写入） */
    box-sizing: border-box;
    flex: 0 0 var(--save-local-actions-width, 114px);
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    gap: 8px;
    /* 左右留给列表/搜索框自己控制，节点的左右留白才一致 */
    padding: 10px 0;
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.35);
}

.save-tree__side-head {
    display: flex;
    flex: 0 0 auto;
    flex-direction: column;
    gap: 8px;
    /* 与列表同宽：搜索框宽度 = 节点宽度 */
    padding: 0 10px;
}

.save-tree__search {
    width: 100%;
}

.save-tree__search :deep(.el-input__wrapper) {
    border-radius: 6px;
    /* 侧栏收窄后默认内边距会挤掉 placeholder，收紧左右留白 */
    padding-left: 6px;
    padding-right: 6px;
    background: rgba(15, 23, 42, 0.55);
    box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.28) inset;
}

.save-tree__search :deep(.el-input__wrapper.is-focus) {
    box-shadow: 0 0 0 1px #60a5fa inset;
}

.save-tree__search :deep(.el-input__inner) {
    color: #f8fafc;
    font-size: 12px;
}

.save-tree__search :deep(.el-input__inner::placeholder) {
    color: #64748b;
}

.save-tree__search :deep(.el-input__suffix) {
    color: #94a3b8;
}

.save-tree__side-list {
    position: relative;
    display: flex;
    flex: 1;
    min-height: 0;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    overflow-x: hidden;
    overflow-y: auto;
    /* 不显示滚动条，滚轮照常能滚；列表底部用箭头提示还有内容 */
    padding: 0;
    scrollbar-width: none;
}

.save-tree__side-list::-webkit-scrollbar {
    display: none;
}

.save-tree__side-page {
    display: flex;
    flex: 0 0 auto;
    justify-content: center;
    padding: 2px 0;
}

.save-tree__side-input {
    box-sizing: border-box;
    width: 100%;
    height: 30px;
    padding: 0 8px;
    border: 1px solid #60a5fa;
    border-radius: 6px;
    background: #0f172a;
    color: #f8fafc;
    font: inherit;
    font-size: 13px;
    outline: none;
}

.save-tree__empty-side {
    align-self: stretch;
    margin: 4px 4px;
    color: #64748b;
    font-size: 12px;
    line-height: 1.6;
}

.save-tree__canvas {
    position: relative;
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    outline: none;
    cursor: grab;
    background-image: radial-gradient(
        rgba(148, 163, 184, 0.16) 1px,
        transparent 1px
    );
    background-size: 22px 22px;
}

.save-tree__canvas:active {
    cursor: grabbing;
}

.save-tree__canvas:focus-visible {
    box-shadow: inset 0 0 0 2px rgba(96, 165, 250, 0.5);
}

.save-tree__toolbar {
    position: absolute;
    top: 10px;
    right: 12px;
    z-index: 2;
    display: flex;
    gap: 8px;
}

.save-tree__empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    padding: 24px;
    color: #64748b;
    font-size: 14px;
    text-align: center;
    pointer-events: none;
}

/* 全屏时树在浏览器 top layer 里，body 下的 ElMessage 看不到；
   错误提示放在树内部，保证全屏也能看见。 */
.save-tree__notice {
    position: absolute;
    top: 52px;
    left: 50%;
    z-index: 80;
    display: flex;
    align-items: center;
    gap: 8px;
    max-width: calc(100% - 32px);
    padding: 8px 10px;
    border: 1px solid transparent;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.5;
    transform: translateX(-50%);
    box-shadow: 0 8px 24px rgba(2, 6, 23, 0.35);
}

.save-tree__notice-text {
    min-width: 0;
}

.save-tree__notice--error {
    border-color: rgba(252, 165, 165, 0.4);
    background: rgba(127, 29, 29, 0.88);
    color: #fecaca;
}

.save-tree__notice--warning {
    border-color: rgba(252, 211, 77, 0.4);
    background: rgba(120, 53, 15, 0.88);
    color: #fde68a;
}

.save-tree__notice--info {
    border-color: rgba(147, 197, 253, 0.4);
    background: rgba(30, 58, 138, 0.88);
    color: #dbeafe;
}

.save-tree__viewport {
    position: absolute;
    top: 0;
    left: 0;
    transform-origin: 0 0;
    will-change: transform;
}

.save-tree__edges {
    position: absolute;
    top: 0;
    left: 0;
    overflow: visible;
    pointer-events: none;
}

.save-tree__edges path {
    fill: none;
    stroke: rgba(148, 163, 184, 0.45);
    stroke-width: 1.5;
}

.save-tree__node {
    position: absolute;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 12px;
    border-radius: 8px;
    border: 1px solid rgba(148, 163, 184, 0.42);
    background: linear-gradient(180deg, #334155, #26344a);
    color: #f1f5f9;
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: grab;
    user-select: none;
}

/* 节点正文：一行 5 个汉字，最多两行，满了直接裁断（不显示省略号）；
   单行时高度由内容决定，仍由节点 flex 垂直居中。 */
.save-tree__node-text {
    display: block;
    width: 5em;
    max-width: 100%;
    max-height: 2.6em;
    overflow: hidden;
    line-height: 1.3;
    white-space: normal;
    word-break: break-word;
}

.save-tree__node:hover {
    border-color: rgba(148, 163, 184, 0.65);
    background: linear-gradient(180deg, #3d4d66, #2f4059);
}

.save-tree__node--active,
.save-tree__node--active:hover {
    border-color: #93c5fd;
    background: linear-gradient(180deg, #475f83, #374b68);
    box-shadow:
        0 0 0 1px rgba(147, 197, 253, 0.45),
        0 6px 16px rgba(2, 6, 23, 0.35);
}

.save-tree__node--side {
    position: static;
    /* 与画布节点同一个宽度（NODE_W） */
    width: 92px;
    height: 38px;
    flex: 0 0 auto;
}

.save-tree__node--dragging {
    opacity: 0.45;
}

.save-tree__node--drop {
    border-color: #60a5fa;
    box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.55);
}

/* 详情弹框：深色自绘，和存档管理弹框同一套配色 */
.save-tree__detail {
    position: fixed;
    inset: 0;
    z-index: 70;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(2, 6, 23, 0.62);
}

.save-tree__detail-card {
    width: 480px;
    max-width: 100%;
    max-height: 78vh;
    display: flex;
    flex-direction: column;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, 0.24);
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    box-shadow: 0 24px 64px rgba(2, 6, 23, 0.5);
    color: #f8fafc;
    overflow: hidden;
}

.save-tree__detail-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px 8px;
}

.save-tree__detail-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
}

.save-tree__detail-body {
    min-height: 0;
    padding: 4px 18px 12px;
    overflow-y: auto;
}

.save-tree__detail-remark {
    max-height: 150px;
    margin: 0 0 12px;
    padding: 10px 12px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.18);
    background: rgba(255, 255, 255, 0.03);
    color: #e2e8f0;
    font-size: 13px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
}

.save-tree__detail-remark--empty {
    color: #64748b;
}

.save-tree__detail-remark {
    cursor: text;
}

.save-tree__detail-input {
    box-sizing: border-box;
    width: 100%;
    min-height: 84px;
    max-height: 150px;
    resize: vertical;
    margin: 0 0 8px;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid #60a5fa;
    background: rgba(15, 23, 42, 0.55);
    color: #f8fafc;
    font: inherit;
    font-size: 13px;
    line-height: 1.7;
    outline: none;
}

.save-tree__detail-edit-foot {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin: -4px 0 12px;
    color: #94a3b8;
    font-size: 12px;
}

.save-tree__detail-meta {
    display: grid;
    gap: 6px;
    margin: 0 0 12px;
    font-size: 12px;
}

.save-tree__detail-meta > div {
    display: flex;
    gap: 10px;
}

.save-tree__detail-meta dt {
    flex: 0 0 56px;
    color: #64748b;
}

.save-tree__detail-meta dd {
    margin: 0;
    color: #cbd5e1;
}

.save-tree__file-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0;
    padding: 8px 0 0;
    list-style: none;
    border-top: 1px dashed rgba(148, 163, 184, 0.18);
}

.save-tree__file-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
}

.save-tree__file-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.save-tree__file-size {
    color: #64748b;
}

.save-tree__file-empty {
    color: #64748b;
    font-size: 13px;
}

.save-tree__detail-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 18px 16px;
    border-top: 1px solid rgba(148, 163, 184, 0.12);
}
</style>
