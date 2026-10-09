<template>
    <div v-if="modelValue" class="save-manager" @click.self="onClose">
        <section class="save-manager__card">
            <header class="save-manager__head">
                <h2 class="save-manager__title">存档管理</h2>
                <button type="button" class="save-manager__close" @click="onClose">
                    ✕
                </button>
            </header>

            <nav class="save-manager__tabs">
                <button
                    type="button"
                    class="save-manager__tab"
                    :class="{ 'save-manager__tab--active': activeTab === 'local' }"
                    @click="switchTab('local')"
                >
                    本地存档
                </button>
                <button
                    type="button"
                    class="save-manager__tab"
                    :class="{ 'save-manager__tab--active': activeTab === 'cloud' }"
                    @click="switchTab('cloud')"
                >
                    云端存档
                </button>
            </nav>

            <div class="save-manager__body">
                <!-- 本地存档 -->
                <template v-if="activeTab === 'local'">
                    <div class="save-manager__toolbar">
                        <button
                            type="button"
                            class="save-manager__btn save-manager__btn--primary"
                            :disabled="working"
                            @click="onSync"
                        >
                            {{ syncing ? "正在同步…" : "重启游戏以同步最新存档" }}
                        </button>
                        <button
                            type="button"
                            class="save-manager__btn"
                            :disabled="working"
                            @click="onUpload"
                        >
                            上传
                        </button>
                        <button type="button" class="save-manager__btn" :disabled="working" @click="refresh">
                            刷新
                        </button>
                    </div>
                    <p v-if="!saves.length" class="save-manager__empty">
                        还没有本地存档。先在游戏里保存一次吧。
                    </p>
                    <ul v-else class="save-manager__list">
                        <li v-for="save in saves" :key="save.key" class="save-manager__item">
                            <div class="save-manager__item-info">
                                <span class="save-manager__item-name">{{ save.name }}.sol</span>
                                <span class="save-manager__item-key">
                                    {{ formatDateTime(save.updatedAt) }}
                                </span>
                            </div>
                            <div class="save-manager__item-actions">
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small"
                                    :disabled="working"
                                    @click="onDownload(save)"
                                >
                                    下载
                                </button>
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small save-manager__btn--danger"
                                    :disabled="working"
                                    @click="onDelete(save)"
                                >
                                    删除
                                </button>
                            </div>
                        </li>
                    </ul>
                </template>

                <!-- 云端存档 -->
                <template v-else>
                    <div class="save-manager__toolbar">
                        <button
                            type="button"
                            class="save-manager__btn save-manager__btn--primary"
                            :disabled="cloudBusy"
                            @click="onUploadCloud"
                        >
                            {{ cloudBusy ? "正在同步…" : "同步至云端" }}
                        </button>
                        <button
                            type="button"
                            class="save-manager__btn"
                            :disabled="cloudBusy"
                            @click="refreshCloud"
                        >
                            刷新
                        </button>
                    </div>
                    <p v-if="!cloudSaves.length" class="save-manager__empty">
                        还没有云端存档。点「同步至云端」把当前本地存档整体备份一份。
                    </p>
                    <ul v-else class="save-manager__list">
                        <li v-for="snapshot in cloudSaves" :key="snapshot.id" class="save-manager__item save-manager__cloud-item">
                            <div class="save-manager__item-info">
                                <div class="save-manager__cloud-title">
                                    <span class="save-manager__item-name save-manager__cloud-time">
                                        {{ formatDateTime(snapshot.created_at) }}
                                    </span>
                                    <span class="save-manager__item-key save-manager__cloud-meta">
                                        {{ snapshot.file_count }} 个文件 · {{ formatBytes(snapshot.total_size) }}
                                    </span>
                                </div>
                                <span class="save-manager__cloud-desc">
                                    {{ snapshot.remark }}
                                </span>
                            </div>
                            <div class="save-manager__item-actions">
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small save-manager__btn--primary"
                                    :disabled="cloudBusy"
                                    @click="onSyncToLocal(snapshot)"
                                >
                                    同步至本地
                                </button>
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small"
                                    :disabled="cloudBusy"
                                    @click="onToggleDetail(snapshot)"
                                >
                                    {{ expandedId === snapshot.id ? "收起" : "详情" }}
                                </button>
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small save-manager__btn--danger"
                                    :disabled="cloudBusy"
                                    @click="onDeleteSnapshot(snapshot)"
                                >
                                    删除
                                </button>
                            </div>
                            <ul v-if="expandedId === snapshot.id" class="save-manager__files">
                                <li v-if="detailLoading" class="save-manager__files-loading">加载中…</li>
                                <template v-else>
                                    <li class="save-manager__desc-item">
                                        <div
                                            class="save-manager__desc-box"
                                            :class="{ 'save-manager__desc-box--editable': editingId !== snapshot.id }"
                                            @click="onDescBoxClick(snapshot)"
                                        >
                                            <p
                                                v-if="editingId !== snapshot.id"
                                                class="save-manager__desc-content"
                                                :class="{ 'save-manager__desc-content--empty': !(cloudDetails[snapshot.id] || {}).remark }"
                                            >
                                                {{ (cloudDetails[snapshot.id] || {}).remark || "暂无描述" }}
                                            </p>
                                            <textarea
                                                v-else
                                                :ref="(el) => (descInputRef = el)"
                                                v-model="descDraft"
                                                class="save-manager__desc-input"
                                                maxlength="100"
                                                placeholder="填写描述"
                                            ></textarea>
                                        </div>
                                        <div class="save-manager__desc-foot">
                                            <span v-if="editingId === snapshot.id" class="save-manager__desc-count">
                                                {{ descDraft.length }}/100
                                            </span>
                                            <span v-else class="save-manager__desc-hint">单击描述框即可编辑</span>
                                            <div v-if="editingId === snapshot.id" class="save-manager__desc-actions">
                                                <button
                                                    type="button"
                                                    class="save-manager__btn save-manager__btn--small"
                                                    :disabled="cloudBusy"
                                                    @click="onCancelEditDesc"
                                                >
                                                    取消
                                                </button>
                                                <button
                                                    type="button"
                                                    class="save-manager__btn save-manager__btn--small save-manager__btn--primary"
                                                    :disabled="cloudBusy"
                                                    @click="onSaveDesc(snapshot)"
                                                >
                                                    保存
                                                </button>
                                            </div>
                                        </div>
                                    </li>
                                    <li v-if="!detailFilesOf(snapshot).length" class="save-manager__files-loading">
                                        该快照没有文件。
                                    </li>
                                    <li
                                        v-for="file in detailFilesOf(snapshot)"
                                        :key="file.id"
                                        class="save-manager__files-row"
                                    >
                                        <span class="save-manager__item-name">{{ file.name }}.sol</span>
                                        <span class="save-manager__item-key">{{ formatBytes(file.size) }}</span>
                                        <button
                                            type="button"
                                            class="save-manager__btn save-manager__btn--small"
                                            :disabled="cloudBusy"
                                            @click="onDownloadCloudFile(snapshot, file)"
                                        >
                                            下载
                                        </button>
                                    </li>
                                </template>
                            </ul>
                        </li>
                    </ul>
                </template>
            </div>
        </section>
        <input
            ref="fileInputRef"
            type="file"
            accept=".sol,application/octet-stream"
            class="save-manager__file"
            @change="onFileChange"
        />

        <!-- “同步至云端”的描述填写面板 -->
        <div v-if="uploadPromptVisible" class="save-manager__prompt" @click.self="cancelUploadPrompt">
            <div class="save-manager__prompt-card">
                <header class="save-manager__prompt-head">
                    <h3 class="save-manager__prompt-title">同步至云端</h3>
                    <button type="button" class="save-manager__close" @click="cancelUploadPrompt">
                        ✕
                    </button>
                </header>
                <p class="save-manager__prompt-desc">
                    把当前游戏此刻的本地存档整体备份到云端
                </p>
                <textarea
                    v-model="uploadDesc"
                    class="save-manager__prompt-input"
                    rows="4"
                    maxlength="100"
                    placeholder="描述（可选）"
                ></textarea>
                <div class="save-manager__desc-count-row">
                    <span class="save-manager__desc-count">{{ uploadDesc.length }}/100</span>
                </div>
                <div class="save-manager__prompt-actions">
                    <button type="button" class="save-manager__btn" @click="cancelUploadPrompt">取消</button>
                    <button
                        type="button"
                        class="save-manager__btn save-manager__btn--primary"
                        @click="confirmUploadCloud"
                    >
                        同步
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { downloadLocalSave, isB64SOL } from "@/utils/ruffle";
import { buildKeyFromReference, buildKeyFromSwfOrigin, collectLocalSaves } from "@/utils/gameSaves";
import { formatBytes, formatDateTime } from "@/utils/fileDisplay";
import { downloadViaPath } from "@/utils/download";
import {
    cloudSaveDetailAPI,
    cloudSaveFileDownloadPath,
    deleteCloudSaveAPI,
    fetchCloudSaveFileBase64,
    listCloudSavesAPI,
    updateCloudSaveAPI,
} from "@/api/games";

const props = defineProps({
    modelValue: { type: Boolean, default: false },
    gameId: { type: Number, default: 0 },
});

const emit = defineEmits(["update:modelValue", "sync", "save-action", "upload-cloud"]);

const activeTab = ref("local");
const saves = ref([]);
const syncing = ref(false);
const working = ref(false);
const cloudSaves = ref([]);
const cloudBusy = ref(false);
const expandedId = ref(null);
const cloudDetails = ref({});
const detailLoading = ref(false);
const editingId = ref(null);
const descDraft = ref("");
const descInputRef = ref(null);
const fileInputRef = ref(null);
// “同步至云端”的描述填写面板
const uploadPromptVisible = ref(false);
const uploadDesc = ref("");

function onClose() {
    emit("update:modelValue", false);
}

// Esc 由内到外逐层收：先结束描述编辑，再收「同步至云端」面板，最后关弹窗
function onKeydown(event) {
    if (event.key !== "Escape") {
        return;
    }
    if (editingId.value !== null) {
        onCancelEditDesc();
        return;
    }
    if (uploadPromptVisible.value) {
        cancelUploadPrompt();
        return;
    }
    onClose();
}

function switchTab(tab) {
    activeTab.value = tab;
    if (tab === "cloud") {
        refreshCloud();
    }
}

function refresh() {
    saves.value = props.gameId ? collectLocalSaves(props.gameId) : [];
    syncing.value = false;
    working.value = false;
}

async function refreshCloud() {
    if (!props.gameId) {
        cloudSaves.value = [];
        return;
    }
    try {
        cloudSaves.value = (await listCloudSavesAPI(props.gameId)) || [];
    } catch {
        cloudSaves.value = [];
    }
}

function onDownload(save) {
    if (!downloadLocalSave(save.key, save.name)) {
        ElMessage.warning("没有读到该存档的数据，可能已被删除。");
        refresh();
    }
}

// 「重启游戏同步」由父组件触发播放器重载：Ruffle 卸载时才会把最新进度写回
// localStorage，稍候自动刷新列表即可看到新档。
function onSync() {
    syncing.value = true;
    emit("sync");
}

// 「同步至云端」由父组件编排：先停播放器落盘最新档 → 收集本游戏本地存档 →
// 上传成云端快照 → 成功后回调 afterCloudUploaded()。上传前先弹描述面板（可选）。
function onUploadCloud() {
    if (cloudBusy.value) {
        return;
    }
    uploadDesc.value = "";
    uploadPromptVisible.value = true;
}

function cancelUploadPrompt() {
    uploadPromptVisible.value = false;
    uploadDesc.value = "";
}

function confirmUploadCloud() {
    if (cloudBusy.value) {
        return;
    }
    const remark = uploadDesc.value.trim().slice(0, 100);
    uploadPromptVisible.value = false;
    uploadDesc.value = "";
    cloudBusy.value = true;
    emit("upload-cloud", remark);
}

async function onSyncToLocal(snapshot) {
    if (cloudBusy.value) {
        return;
    }
    try {
        await ElMessageBox.confirm(
            "将用该云端存档覆盖本地对应存档并重启游戏，确定吗？",
            "同步至本地",
            {
                confirmButtonText: "同步",
                cancelButtonText: "取消",
                type: "warning",
            },
        );
    } catch {
        return;
    }
    cloudBusy.value = true;
    try {
        const detail = await cloudSaveDetailAPI(snapshot.id);
        const writes = [];
        for (const file of detail.files) {
            const base64 = await fetchCloudSaveFileBase64(detail.id, file.id);
            writes.push({ key: file.local_key, base64 });
        }
        if (!writes.length) {
            ElMessage.info("该云端存档没有可还原的文件。");
            return;
        }
        // 多文件在一次停播放器窗口内写回，父组件只重启一次
        emit("save-action", { action: "replace-many", writes });
    } catch {
        // 错误提示已由请求层 toast，这里兜底
    } finally {
        cloudBusy.value = false;
    }
}

async function onDeleteSnapshot(snapshot) {
    try {
        await ElMessageBox.confirm(
            `删除这份云端存档？删除后无法恢复。`,
            "删除云端存档",
            {
                confirmButtonText: "删除",
                cancelButtonText: "取消",
                type: "warning",
            },
        );
    } catch {
        return;
    }
    cloudBusy.value = true;
    try {
        await deleteCloudSaveAPI(snapshot.id);
        if (expandedId.value === snapshot.id) {
            expandedId.value = null;
            delete cloudDetails.value[snapshot.id];
        }
        ElMessage.success("已删除。");
        await refreshCloud();
    } catch {
        // 已 toast
    } finally {
        cloudBusy.value = false;
    }
}

async function onToggleDetail(snapshot) {
    if (expandedId.value === snapshot.id) {
        expandedId.value = null;
        editingId.value = null;
        return;
    }
    expandedId.value = snapshot.id;
    editingId.value = null;
    if (cloudDetails.value[snapshot.id]) {
        return;
    }
    detailLoading.value = true;
    try {
        const detail = await cloudSaveDetailAPI(snapshot.id);
        cloudDetails.value[snapshot.id] = detail;
    } catch {
        expandedId.value = null;
    } finally {
        detailLoading.value = false;
    }
}

function detailFilesOf(snapshot) {
    const detail = cloudDetails.value[snapshot.id];
    return detail && Array.isArray(detail.files) ? detail.files : [];
}

// 描述框：单击即可进入编辑（读模式与编辑模式共用同一固定高度的框，切换不跳动）
function onDescBoxClick(snapshot) {
    if (editingId.value === snapshot.id) {
        return;
    }
    onStartEditDesc(snapshot);
}

async function onStartEditDesc(snapshot) {
    if (cloudBusy.value) {
        return;
    }
    editingId.value = snapshot.id;
    const detail = cloudDetails.value[snapshot.id];
    descDraft.value = ((detail && detail.remark) || "").slice(0, 100);
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

async function onSaveDesc(snapshot) {
    cloudBusy.value = true;
    try {
        const remark = descDraft.value.trim().slice(0, 100);
        const detail = await updateCloudSaveAPI(snapshot.id, remark);
        cloudDetails.value[snapshot.id] = detail;
        const target = cloudSaves.value.find((item) => item.id === snapshot.id);
        if (target) {
            target.remark = detail.remark || "";
        }
        ElMessage.success("描述已更新。");
    } catch {
        // 错误提示已由请求层 toast
    } finally {
        editingId.value = null;
        descDraft.value = "";
        cloudBusy.value = false;
    }
}

function onDownloadCloudFile(snapshot, file) {
    downloadViaPath(cloudSaveFileDownloadPath(snapshot.id, file.id));
}

function onUpload() {
    fileInputRef.value?.click();
}

async function onFileChange(event) {
    const input = event.target;
    const file = input?.files?.[0];
    input.value = "";
    if (!file) {
        return;
    }
    try {
        const base64 = await readFileAsBase64(file);
        if (!isB64SOL(base64)) {
            ElMessage.error("该文件不是有效的 Ruffle 存档（.sol）文件。");
            return;
        }
        const name = normalizeSolName(file.name);
        const existing = saves.value.find((save) => save.name === name);
        let key;
        if (existing) {
            // 同名存档：询问是否覆盖
            try {
                await ElMessageBox.confirm(
                    `本地已有同名存档「${name}.sol」，覆盖后当前游戏会重启以读取新存档。确定覆盖吗？`,
                    "覆盖存档",
                    {
                        confirmButtonText: "覆盖",
                        cancelButtonText: "取消",
                        type: "warning",
                    },
                );
            } catch {
                return;
            }
            key = existing.key;
        } else {
            // 新存档：以既有存档的 key 为基座派生同名槽位；
            // 一条本地档都没有时，直接按「站点 origin + 本游戏 SWF 路径 + 存档名」构造。
            try {
                await ElMessageBox.confirm(
                    `将把「${name}.sol」导入为本地新存档，导入后当前游戏会重启以读取。确定吗？`,
                    "导入存档",
                    {
                        confirmButtonText: "导入",
                        cancelButtonText: "取消",
                        type: "info",
                    },
                );
            } catch {
                return;
            }
            key = saves.value.length
                ? buildKeyFromReference(saves.value[0].key, name)
                : buildKeyFromSwfOrigin(props.gameId, name);
        }
        working.value = true;
        emit("save-action", { action: "replace", key, base64 });
    } catch (err) {
        // 用户取消或读文件失败：取消不提示；其余错误提示
        if (err && err !== "cancel" && err !== "close") {
            ElMessage.error(err?.message || "读取文件失败。");
        }
        refresh();
    }
}

function normalizeSolName(filename) {
    const raw = String(filename || "").trim();
    if (!raw) {
        return "存档";
    }
    return raw.toLowerCase().endsWith(".sol") ? raw.slice(0, -4) : raw;
}

async function onDelete(save) {
    try {
        await ElMessageBox.confirm(`删除存档「${save.name}.sol」？删除后无法恢复。`, "删除存档", {
            confirmButtonText: "删除",
            cancelButtonText: "取消",
            type: "warning",
        });
    } catch {
        return;
    }
    working.value = true;
    emit("save-action", { action: "delete", key: save.key });
}

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result;
            if (typeof result === "string") {
                resolve(result.replace(/^data:[^;]*;base64,/, ""));
            } else {
                reject(new Error("读取文件失败。"));
            }
        };
        reader.onerror = () => reject(reader.error || new Error("读取文件失败。"));
        reader.readAsDataURL(file);
    });
}

watch(
    () => props.modelValue,
    (visible) => {
        if (visible) {
            activeTab.value = "local";
            refresh();
            window.addEventListener("keydown", onKeydown);
        } else {
            window.removeEventListener("keydown", onKeydown);
        }
    },
);

onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown);
});

// 父组件完成「停播放器 → 改写 localStorage → 重启」后调用，重新拉取本地列表。
async function refreshAfterParent() {
    await nextTick();
    refresh();
}

// 父组件完成「落盘 → 上传云端快照」后调用：复位并切到云端 tab 展示结果。
async function afterCloudUploaded() {
    cloudBusy.value = false;
    activeTab.value = "cloud";
    await refreshCloud();
}

defineExpose({
    refresh: refreshAfterParent,
    refreshCloud,
    afterCloudUploaded,
});
</script>

<style scoped>
.save-manager {
    position: fixed;
    inset: 0;
    z-index: 60;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(2, 6, 23, 0.62);
    backdrop-filter: blur(2px);
}

.save-manager__file {
    display: none;
}

.save-manager__card {
    width: 620px;
    max-width: 100%;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, 0.24);
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    box-shadow: 0 24px 64px rgba(2, 6, 23, 0.5);
    color: #f8fafc;
    overflow: hidden;
}

.save-manager__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px 12px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.save-manager__title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
}

.save-manager__close {
    border: 0;
    background: transparent;
    color: #94a3b8;
    font-size: 16px;
    line-height: 1;
    cursor: pointer;
    padding: 6px;
    border-radius: 8px;
}

.save-manager__close:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
}

.save-manager__tabs {
    display: flex;
    gap: 6px;
    padding: 14px 20px 0;
}

.save-manager__tab {
    padding: 7px 16px;
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-radius: 999px;
    background: rgba(30, 41, 59, 0.6);
    color: #cbd5e1;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.save-manager__tab:hover {
    color: #fff;
    border-color: rgba(148, 163, 184, 0.4);
}

.save-manager__tab--active {
    background: rgba(37, 99, 235, 0.85);
    border-color: rgba(96, 165, 250, 0.5);
    color: #fff;
}

.save-manager__cloud-disabled {
    margin: 18px 20px;
    padding: 12px 16px;
    border-radius: 10px;
    border: 1px dashed rgba(148, 163, 184, 0.35);
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.7;
}

.save-manager__toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 20px;
}

.save-manager__body {
    padding: 0 20px 20px;
    overflow: auto;
    min-height: 0;
    border-top: 1px solid rgba(148, 163, 184, 0.12);
    margin-top: 14px;
    padding-top: 4px;
}

.save-manager__empty {
    margin: 18px 0;
    text-align: center;
    color: #64748b;
    font-size: 14px;
}

.save-manager__list {
    margin: 0;
    padding: 0 0 6px;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.save-manager__item {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.16);
    background: rgba(255, 255, 255, 0.04);
}

.save-manager__item:hover {
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(148, 163, 184, 0.3);
}

.save-manager__item-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
}

.save-manager__item-name {
    font-size: 14px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.save-manager__item-key {
    font-size: 12px;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.save-manager__item-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
}

.save-manager__cloud-item {
    align-items: flex-start;
}

.save-manager__cloud-title {
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
}

.save-manager__cloud-time {
    flex: 0 0 auto;
}

.save-manager__cloud-meta {
    flex-shrink: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
}

.save-manager__cloud-desc {
    display: block;
    min-width: 0;
    color: #64748b;
    font-size: 12px;
    line-height: 1.5;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.save-manager__files {
    flex-basis: 100%;
    margin: 2px 0 0;
    padding: 6px 0 2px 12px;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 4px;
    border-top: 1px dashed rgba(148, 163, 184, 0.18);
}

.save-manager__files-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
}

.save-manager__files-row .save-manager__item-name {
    flex: 1;
    font-weight: 400;
}

.save-manager__files-loading {
    padding: 4px 0;
    color: #64748b;
    font-size: 13px;
}

/* 云端详情：描述框读/写共用同一固定高度（约 3 行），单击框即进入编辑，切换时尺寸不变 */
.save-manager__desc-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 2px 0 8px;
}

.save-manager__desc-box {
    box-sizing: border-box;
    height: 84px; /* 固定约 3 行（13px × 1.7 行高 + 内边距与边框） */
    padding: 8px 10px;
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.03);
    overflow: auto;
    transition: border-color 0.15s ease, background 0.15s ease;
}

.save-manager__desc-box--editable {
    cursor: text;
}

.save-manager__desc-box--editable:hover {
    border-color: rgba(148, 163, 184, 0.45);
    background: rgba(255, 255, 255, 0.06);
}

.save-manager__desc-box:focus-within {
    border-color: rgba(96, 165, 250, 0.6);
}

.save-manager__desc-content {
    margin: 0;
    color: #e2e8f0;
    font-size: 13px;
    line-height: 1.7;
    word-break: break-word;
    white-space: pre-wrap;
}

.save-manager__desc-content--empty {
    color: #64748b;
}

.save-manager__desc-input {
    display: block;
    width: 100%;
    height: 100%;
    box-sizing: border-box;
    padding: 0;
    border: 0;
    background: transparent;
    color: #e2e8f0;
    font-size: 13px;
    line-height: 1.7;
    resize: none;
    font-family: inherit;
}

.save-manager__desc-input:focus {
    outline: none;
}

.save-manager__desc-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    min-height: 26px;
}

.save-manager__desc-hint {
    color: #64748b;
    font-size: 12px;
}

.save-manager__desc-actions {
    display: flex;
    gap: 6px;
}

.save-manager__desc-count-row {
    display: flex;
    justify-content: flex-end;
    padding-top: 4px;
}

.save-manager__desc-count {
    color: #64748b;
    font-size: 12px;
}

/* “同步至云端”的描述填写面板 */
.save-manager__prompt {
    position: fixed;
    inset: 0;
    z-index: 70;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(2, 6, 23, 0.55);
}

.save-manager__prompt-card {
    width: 480px;
    max-width: 100%;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, 0.24);
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    box-shadow: 0 24px 64px rgba(2, 6, 23, 0.55);
    color: #f8fafc;
    padding: 16px 20px 20px;
}

.save-manager__prompt-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 6px;
}

.save-manager__prompt-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
}

.save-manager__prompt-desc {
    margin: 0;
    padding-bottom: 12px;
    font-size: 13px;
    line-height: 1.7;
    color: #cbd5e1;
}

.save-manager__prompt-input {
    display: block;
    width: 100%;
    height: 112px; /* 固定约 4 行，不允许拉伸 */
    box-sizing: border-box;
    padding: 8px 10px;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(2, 6, 23, 0.5);
    color: #e2e8f0;
    font-size: 13px;
    line-height: 1.7;
    resize: none;
    font-family: inherit;
}

.save-manager__prompt-input:focus {
    outline: none;
    border-color: rgba(96, 165, 250, 0.6);
}

.save-manager__prompt-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding-top: 12px;
}

/* 深色风格按钮，与游戏外壳标题栏按钮同款 */
.save-manager__btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 8px 14px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 10px;
    background: rgba(30, 41, 59, 0.8);
    color: #e2e8f0;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease, opacity 0.15s ease;
    white-space: nowrap;
}

.save-manager__btn:hover:not(:disabled) {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(148, 163, 184, 0.5);
}

.save-manager__btn:disabled {
    opacity: 0.55;
    cursor: default;
}

.save-manager__btn--primary {
    background: rgba(37, 99, 235, 0.85);
    border-color: rgba(96, 165, 250, 0.5);
    color: #fff;
}

.save-manager__btn--primary:hover:not(:disabled) {
    background: rgba(37, 99, 235, 1);
}

.save-manager__btn--danger {
    color: #fca5a5;
    border-color: rgba(248, 113, 113, 0.35);
}

.save-manager__btn--danger:hover:not(:disabled) {
    background: rgba(127, 29, 29, 0.4);
    border-color: rgba(248, 113, 113, 0.55);
    color: #fecaca;
}

.save-manager__btn--small {
    padding: 6px 10px;
    font-size: 13px;
}
</style>
