<template>
    <div class="cloud-save-panel">
        <header class="cloud-save-panel__head">
            <h2 class="cloud-save-panel__title">云端存档</h2>
        </header>
        <save-tree-view
            ref="treeRef"
            :snapshots="snapshots"
            :busy="busy || loading || deleting"
            @sync-local="onSyncLocal"
            @delete="onDelete"
            @parents-changed="onParentsChanged"
            @remark-changed="onRemarkChanged"
            @order-changed="onOrderChanged"
            @refresh="refresh"
        />
    </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { confirmAction, dangerConfirm } from "@/utils/confirm";
import { appMessage } from "@/utils/overlay";
import {
    deleteCloudSaveAPI,
    listCloudSavesAPI,
} from "@/api/games";
import SaveTreeView from "@components/games/SaveTreeView.vue";

const props = defineProps({
    gameId: { type: Number, default: 0 },
    busy: { type: Boolean, default: false },
    syncConfirmMessage: {
        type: String,
        default: "将用该云端存档覆盖本地存档，确定吗？",
    },
});

const emit = defineEmits(["sync-local"]);

const treeRef = ref(null);
const snapshots = ref([]);
const loading = ref(false);
const deleting = ref(false);

async function refresh() {
    if (!props.gameId) {
        snapshots.value = [];
        return;
    }
    loading.value = true;
    try {
        snapshots.value = (await listCloudSavesAPI(props.gameId)) || [];
    } catch {
        snapshots.value = [];
    } finally {
        loading.value = false;
    }
}

watch(() => props.gameId, refresh, { immediate: true });

function patchSnapshot(id, changes) {
    const target = snapshots.value.find((item) => item.id === id);
    if (target) {
        Object.assign(target, changes);
    }
}

function onParentsChanged({ id, parentId }) {
    patchSnapshot(id, { parent_id: parentId });
}

function onRemarkChanged({ id, remark }) {
    patchSnapshot(id, { remark });
}

/** 排序落库成功后，用后端给的整份有序列表替换本地快照（顺序以后端为准）。 */
function onOrderChanged(items) {
    if (Array.isArray(items)) {
        snapshots.value = items;
    }
}

async function onSyncLocal(node) {
    if (props.busy || deleting.value) {
        return;
    }
    const confirmed = await confirmAction(props.syncConfirmMessage, {
        title: "同步至本地",
        confirmText: "同步",
        danger: true,
    });
    if (!confirmed) {
        return;
    }
    emit("sync-local", node);
}

async function onDelete(node) {
    if (props.busy || deleting.value) {
        return;
    }
    const childCount = snapshots.value.filter(
        (item) => item.parent_id === node.id,
    ).length;
    const childHint = childCount
        ? `其 ${childCount} 个子存档会变为顶层。`
        : "";
    const confirmed = await dangerConfirm(
        `删除这份云端存档？${childHint}删除后无法恢复。`,
        { title: "删除云端存档" },
    );
    if (!confirmed) {
        return;
    }
    deleting.value = true;
    try {
        await deleteCloudSaveAPI(node.id);
        appMessage.success("已删除。");
        await refresh();
    } catch {
        // 错误提示已由请求层 toast
    } finally {
        deleting.value = false;
    }
}

function handleEscape() {
    return treeRef.value?.handleEscape?.() || false;
}

function handleSaveHotkey(key) {
    return treeRef.value?.handleSaveHotkey?.(key) || false;
}

defineExpose({ refresh, handleEscape, handleSaveHotkey });
</script>

<style>
.cloud-save-panel {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
}

.cloud-save-panel__head {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    height: 32px;
    margin-bottom: 8px;
    padding: 0 2px;
}

.cloud-save-panel__title {
    margin: 0;
    color: #f8fafc;
    font-size: 16px;
    font-weight: 600;
    line-height: 1.4;
}
</style>
