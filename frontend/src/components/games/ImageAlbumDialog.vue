<template>
    <app-dialog
        :model-value="modelValue"
        :title="title"
        width="720px"
        align-center
        footer-mode="close-only"
        @update:model-value="emit('update:modelValue', $event)"
    >
        <div class="album">
            <div class="album__bar">
                <app-button
                    variant="secondary"
                    :disabled="busy"
                    @click="onPickFile"
                >
                    {{ uploadText }}
                </app-button>
                <!-- 右上角固定的删除入口：点一下进删除模式，选好再点一下才是真删 -->
                <div class="album__tools">
                    <span v-if="selectionMode" class="album__selected">已选 {{ selectedIds.size }} 张</span>
                    <app-button
                        v-if="selectionMode"
                        variant="secondary"
                        :disabled="busy"
                        @click="exitSelection"
                    >
                        取消
                    </app-button>
                    <app-button
                        variant="danger"
                        :disabled="busy || (selectionMode && !selectedIds.size)"
                        @click="onDeleteClick"
                    >
                        {{ selectionMode ? `删除 ${selectedIds.size} 张` : "删除" }}
                    </app-button>
                </div>
            </div>

            <div class="album__grid">
                <div
                    v-for="(item, index) in items"
                    :key="item.id"
                    class="album__tile"
                    :class="{
                        'album__tile--selected': selectedIds.has(item.id),
                        'album__tile--dragging': dragId === item.id,
                        'album__tile--drop': dragOverId === item.id,
                        'album__tile--picking': selectionMode,
                    }"
                    :draggable="canDrag(item)"
                    @dragstart="onDragStart($event, item)"
                    @dragover.prevent="onDragOver(item)"
                    @dragleave="onDragLeave(item)"
                    @drop.prevent="onDrop(item, index)"
                    @dragend="onDragEnd"
                    @click="onTileClick(item)"
                >
                    <!-- 上面图片（不加底色、不做圆角，整个方块都能拖）；
                         截图管理传入竖版比例，图集管理保持 1:1 -->
                    <div class="album__frame" :style="frameStyle">
                        <img
                            :src="imageUrl(item)"
                            :alt="item.description || altText"
                            draggable="false"
                        />
                    </div>

                    <!-- 下面描述：单击就地改（同高同字号，排版不动），回车/失焦存下，ESC 放弃 -->
                    <p
                        v-if="editingId !== item.id"
                        class="album__desc"
                        :class="{ 'album__desc--empty': !item.description }"
                        @click.stop="onCaptionClick(item)"
                    >
                        {{ item.description || "暂无描述" }}
                    </p>
                    <input
                        v-else
                        :ref="(el) => (descInputRef = el)"
                        v-model="descDraft"
                        class="album__desc album__desc--input"
                        maxlength="15"
                        placeholder="描述"
                        @click.stop
                        @keydown.enter.prevent="onCommitDesc(item)"
                        @keydown.esc="onCancelEditDesc"
                        @blur="onCommitDesc(item)"
                    />

                    <!-- 选择模式下右上角是勾选标记（删除入口在顶部工具条） -->
                    <span
                        v-if="selectionMode"
                        class="album__check"
                        :class="{ 'album__check--on': selectedIds.has(item.id) }"
                    >
                        ✓
                    </span>
                </div>
            </div>
        </div>

        <input
            ref="fileInputRef"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            class="album__file"
            @change="onFileChange"
        />
    </app-dialog>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import AppButton from "@components/common/AppButton.vue";
import AppDialog from "@components/common/AppDialog.vue";

/**
 * 相册式图片管理弹框：截图（按账号隔离）与图集（按游戏共享）共用这一份实现，
 * 差别只在标题、上传按钮文案与下面注入的这组接口，所以组件本身不认识任何业务 API。
 * `source` 需要提供 list / upload / update / move / remove / imagePath 六个函数。
 */
const props = defineProps({
    modelValue: { type: Boolean, default: false },
    gameId: { type: Number, default: null },
    title: { type: String, default: "图片管理" },
    uploadText: { type: String, default: "上传图片" },
    // 图片挂掉或读屏时的替代文字（描述为空时用）
    altText: { type: String, default: "图片" },
    // 图片框宽高比（宽 / 高）：截图管理按机种传（NDS 约 0.60），图集保持 1
    frameAspect: { type: Number, default: 1 },
    source: { type: Object, required: true },
});

const emit = defineEmits(["update:modelValue", "changed"]);

const items = ref([]);
const busy = ref(false);
const editingId = ref(null);
const descDraft = ref("");
const descInputRef = ref(null);
const fileInputRef = ref(null);
// 多选删除：顶部工具条的「删除」进入选择模式，逐张勾选后再点一次才删
const selectionMode = ref(false);
const selectedIds = ref(new Set());
// 拖动排序：正在拖的那张 + 当前悬停到的那张（用来画落点提示）
const dragId = ref(null);
const dragOverId = ref(null);

// 有比例时才内联覆盖（默认仍是样式里的 1/1），避免给图集多写一个无意义的属性
const frameStyle = computed(() =>
    props.frameAspect > 0 && props.frameAspect !== 1
        ? { aspectRatio: String(props.frameAspect) }
        : null
);

function imageUrl(item) {
    // 传整条记录而不是 id：地址函数要靠 created_at 当版本参数（主键会被复用，见 api/games.js）
    return props.source.imagePath(item);
}

async function reload() {
    if (!props.gameId) {
        items.value = [];
        return;
    }
    try {
        items.value = (await props.source.list(props.gameId)) || [];
    } catch {
        // 错误提示已由请求层 toast
        items.value = [];
    }
}

/** 任何改动都通知父组件重拉图片栏，免得弹框后面的图库数据陈旧 */
function notifyChanged() {
    emit("changed");
}

// ---------- 上传 ----------

function onPickFile() {
    if (!busy.value) {
        fileInputRef.value?.click();
    }
}

async function onFileChange(event) {
    const input = event.target;
    const file = input?.files?.[0];
    input.value = "";
    if (!file || !props.gameId) {
        return;
    }
    busy.value = true;
    try {
        const form = new FormData();
        form.append("game_id", String(props.gameId));
        form.append("description", "");
        form.append("file", file, file.name || "image.png");
        await props.source.upload(form);
        ElMessage.success("已上传图片。");
        await reload();
        notifyChanged();
    } catch {
        // 错误提示已由请求层 toast
    } finally {
        busy.value = false;
    }
}

// ---------- 多选删除（相册式） ----------

/** 顶部那个固定的「删除」按钮：第一下进删除模式，选好后再点一下才真删。 */
function onDeleteClick() {
    if (busy.value) {
        return;
    }
    if (!selectionMode.value) {
        onCancelEditDesc();
        selectionMode.value = true;
        selectedIds.value = new Set();
        return;
    }
    if (selectedIds.value.size) {
        void onDeleteSelected();
    }
}

function exitSelection() {
    selectionMode.value = false;
    selectedIds.value = new Set();
}

function onTileClick(item) {
    if (!selectionMode.value || busy.value) {
        return;
    }
    const next = new Set(selectedIds.value);
    if (next.has(item.id)) {
        next.delete(item.id);
    } else {
        next.add(item.id);
    }
    selectedIds.value = next;
}

async function onDeleteSelected() {
    const ids = [...selectedIds.value];
    if (!ids.length || busy.value) {
        return;
    }
    busy.value = true;
    try {
        for (const id of ids) {
            await props.source.remove(id);
        }
        ElMessage.success(`已删除 ${ids.length} 张图片。`);
    } catch {
        // 错误提示已由请求层 toast；下面统一重拉，把删到一半的状态对齐
    } finally {
        busy.value = false;
        exitSelection();
        await reload();
        notifyChanged();
    }
}

// ---------- 拖动排序 ----------

function canDrag(item) {
    return !busy.value && !selectionMode.value && editingId.value !== item.id;
}

function onDragStart(event, item) {
    if (!canDrag(item)) {
        event.preventDefault();
        return;
    }
    dragId.value = item.id;
    event.dataTransfer.effectAllowed = "move";
    // Firefox 必须设了数据才会真正开始拖
    event.dataTransfer.setData("text/plain", String(item.id));
}

function onDragOver(item) {
    if (dragId.value && item.id !== dragId.value) {
        dragOverId.value = item.id;
    }
}

function onDragLeave(item) {
    if (dragOverId.value === item.id) {
        dragOverId.value = null;
    }
}

function onDragEnd() {
    dragId.value = null;
    dragOverId.value = null;
}

async function onDrop(item, toIndex) {
    const draggedId = dragId.value;
    onDragEnd();
    if (!draggedId || draggedId === item.id || toIndex < 0) {
        return;
    }
    const fromIndex = items.value.findIndex((row) => row.id === draggedId);
    if (fromIndex < 0) {
        return;
    }
    // 先本地挪一下（与后端的「插到第 toIndex 位」同一套语义），再让后端给最终顺序
    const next = [...items.value];
    next.splice(toIndex, 0, next.splice(fromIndex, 1)[0]);
    items.value = next;
    busy.value = true;
    try {
        items.value = (await props.source.move(draggedId, toIndex)) || items.value;
        notifyChanged();
    } catch {
        // 错误提示已由请求层 toast：拉回服务端的真实顺序
        await reload();
    } finally {
        busy.value = false;
    }
}

// ---------- 描述 ----------

/** 单击描述进入编辑；选择模式下这一下算「勾中这张」（描述那层拦掉了冒泡）。 */
function onCaptionClick(item) {
    if (selectionMode.value) {
        onTileClick(item);
        return;
    }
    void onStartEditDesc(item);
}

async function onStartEditDesc(item) {
    if (busy.value || selectionMode.value) {
        return;
    }
    editingId.value = item.id;
    descDraft.value = (item.description || "").slice(0, 15);
    await nextTick();
    const input = descInputRef.value;
    if (input) {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
    }
}

function onCancelEditDesc() {
    editingId.value = null;
    descDraft.value = "";
}

/** 就地改完存下（回车或失焦触发；没改动就直接退出，不发请求）。 */
async function onCommitDesc(item) {
    if (editingId.value !== item.id) {
        // 回车已经提交过一次、ESC 已经取消，之后那次 blur 不再重复提交
        return;
    }
    const next = descDraft.value.trim();
    const current = item.description || "";
    if (next === current) {
        onCancelEditDesc();
        return;
    }
    editingId.value = null;
    busy.value = true;
    try {
        const updated = await props.source.update(item.id, next);
        item.description = updated?.description || "";
        notifyChanged();
    } catch {
        // 错误提示已由请求层 toast
    } finally {
        descDraft.value = "";
        busy.value = false;
    }
}

watch(
    () => props.modelValue,
    (visible) => {
        if (visible) {
            exitSelection();
            onCancelEditDesc();
            onDragEnd();
            void reload();
        }
    }
);
</script>

<style scoped>
.album__bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding-bottom: 12px;
}

.album__tools {
    display: flex;
    align-items: center;
    gap: 8px;
}

.album__selected {
    color: #64748b;
    font-size: 13px;
}

.album__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    align-items: end;
    gap: 12px;
    max-height: 58vh;
    overflow-y: auto;
    /* 给滚动条留出固定宽度：有没有滚动条，网格的可用宽度都一样，排版不跳 */
    scrollbar-gutter: stable;
    padding: 2px;
}

.album__tile {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px;
    border: 1px solid transparent;
    border-radius: 8px;
    transition: border-color 0.15s ease, background 0.15s ease;
}

/* 可拖动的整块给抓手；选择模式下改成点选 */
.album__tile[draggable="true"] {
    cursor: grab;
}

.album__tile--dragging {
    opacity: 0.45;
}

.album__tile--drop {
    border-color: var(--el-color-primary);
}

.album__tile--picking {
    cursor: pointer;
}

.album__tile--selected {
    background: rgba(64, 158, 255, 0.1);
}

/* 图片框：只限尺寸，不加底色也不做圆角 */
.album__frame {
    width: 100%;
    aspect-ratio: 1 / 1;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
}

.album__frame img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
}

/* 描述行与它的编辑态**同高同字号**：点进去就地改，排版一点不动 */
.album__desc {
    display: block;
    box-sizing: border-box;
    width: 100%;
    height: 20px;
    margin: 0;
    padding: 0 4px;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
    font-size: 12px;
    line-height: 18px;
    color: #0f172a;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: inherit;
}

.album__desc--empty {
    color: #94a3b8;
}

.album__desc--input {
    border-color: var(--el-color-primary);
}

.album__desc--input:focus {
    outline: none;
}

/* 选择模式下右上角的勾选标记（图片上不放删除按钮，删除入口在顶部工具条） */
.album__check {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: rgba(148, 163, 184, 0.5);
    color: #fff;
    font-size: 12px;
    line-height: 1;
}

.album__check--on {
    background: var(--el-color-primary);
}

.album__file {
    display: none;
}

</style>
