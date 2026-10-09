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
                            :disabled="!engineReady || working"
                            @click="onCapture"
                        >
                            {{ working ? "正在捕捉…" : "捕捉当前进度" }}
                        </button>
                        <button type="button" class="save-manager__btn" :disabled="working" @click="onUpload">
                            上传
                        </button>
                    </div>
                    <p v-if="!engineReady" class="save-manager__hint">
                        模拟器尚未就绪：先进入游戏后，才能捕捉/载入即时存档。
                    </p>
                    <p v-else-if="!localSave" class="save-manager__empty">
                        还没有本地存档。玩到想存的地方，点「捕捉当前进度」即可（只有一份，再捕捉会覆盖）。
                    </p>
                    <ul v-else class="save-manager__list">
                        <li class="save-manager__item">
                            <div class="save-manager__item-info">
                                <span class="save-manager__item-name">
                                    {{ localSave.name }}
                                </span>
                                <span class="save-manager__item-key">
                                    {{ formatDateTime(localSave.updatedAt) }} · {{ formatBytes(localSave.size) }}
                                </span>
                            </div>
                            <div class="save-manager__item-actions">
                                <!-- 载入另有回车快捷键（见 emulator-player.vue），按钮里带上这个键的回车符号 -->
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small"
                                    :disabled="!engineReady || working"
                                    title="载入（按回车键同效）"
                                    @click="onLoadLocal"
                                >
                                    载入
                                    <span class="save-manager__btn-key" aria-hidden="true">↵</span>
                                </button>
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small"
                                    :disabled="working"
                                    @click="onDownloadLocal"
                                >
                                    下载
                                </button>
                                <button
                                    type="button"
                                    class="save-manager__btn save-manager__btn--small save-manager__btn--danger"
                                    :disabled="working"
                                    @click="onDeleteLocal"
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
                            :disabled="!engineReady || cloudBusy"
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
                        还没有云端存档。点「同步至云端」把当前本地存档备份一份。
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
                                        <span class="save-manager__item-name">{{ file.name }}</span>
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
            accept=".state,application/octet-stream"
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
                    把当前本地存档备份到云端
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
import { formatBytes, formatDateTime } from "@/utils/fileDisplay";
import { downloadViaPath } from "@/utils/download";
import {
    cloudSaveDetailAPI,
    cloudSaveFileDownloadPath,
    deleteCloudSaveAPI,
    listCloudSavesAPI,
    updateCloudSaveAPI,
} from "@/api/games";
import {
    EMU_SAVE_FILENAME,
    deleteLocalEmuSave,
    emuBase64ToBlob,
    ensureSingleSlotModel,
    getEmuSaveBase64,
    getLocalEmuSave,
    writeLocalEmuSave,
} from "@/utils/emulatorSaves";

const props = defineProps({
    modelValue: { type: Boolean, default: false },
    gameId: { type: Number, default: 0 },
    // 引擎（模拟器）是否已开始运行；捕捉/载入即时存档依赖引擎已就绪
    engineReady: { type: Boolean, default: false },
});

const emit = defineEmits([
    "update:modelValue",
    "capture",
    "load-local",
    "upload-cloud",
    "sync-local",
]);

const activeTab = ref("local");
// 每个游戏固定只有一份本地存档；null = 还没有
const localSave = ref(null);
const working = ref(false);
const cloudSaves = ref([]);
const cloudBusy = ref(false);
const expandedId = ref(null);
const cloudDetails = ref({});
const detailLoading = ref(false);
const editingId = ref(null);
const descDraft = ref("");
const descInputRef = ref(null);
const uploadPromptVisible = ref(false);
const uploadDesc = ref("");
const fileInputRef = ref(null);

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

async function refreshLocal() {
    if (props.gameId) {
        // 首次调用顺带清掉旧版多槽位档（一次性）
        await ensureSingleSlotModel();
    }
    localSave.value = props.gameId ? getLocalEmuSave(props.gameId) : null;
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

// 捕捉：交由父组件调引擎 __ejsRpc.capture 并把结果写入本地档库
function onCapture() {
    if (!props.engineReady) {
        ElMessage.warning("请先开始游戏再捕捉进度。");
        return;
    }
    working.value = true;
    emit("capture");
}

// 载入：交由父组件把本地档写回引擎并读档
function onLoadLocal() {
    if (!props.engineReady) {
        ElMessage.warning("请先开始游戏再载入存档。");
        return;
    }
    emit("load-local");
}

async function onDeleteLocal() {
    if (!localSave.value) {
        return;
    }
    try {
        await ElMessageBox.confirm(`删除本地存档「${localSave.value.name}」？删除后无法恢复。`, "删除存档", {
            confirmButtonText: "删除",
            cancelButtonText: "取消",
            type: "warning",
        });
    } catch {
        return;
    }
    working.value = true;
    await deleteLocalEmuSave(props.gameId);
    await refreshLocal();
}

async function onDownloadLocal() {
    const base64 = await getEmuSaveBase64(props.gameId);
    if (!base64) {
        ElMessage.warning("该本地存档内容缺失。");
        await refreshLocal();
        return;
    }
    const blob = emuBase64ToBlob(base64);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = EMU_SAVE_FILENAME;
    anchor.click();
    URL.revokeObjectURL(url);
}

// 「上传」：把本机的 .state 即时存档文件导入为本地档（覆盖已有的那份）。
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
        if (!base64) {
            ElMessage.error("该文件为空。");
            return;
        }
        // 本地只有一份档（固定叫 save.state）：导入即覆盖
        const hasLocal = Boolean(localSave.value);
        try {
            await ElMessageBox.confirm(
                `将用「${file.name}」${hasLocal ? "覆盖当前本地存档" : "作为本地存档"}（存档固定叫 ${EMU_SAVE_FILENAME}），之后可在「本地存档」里载入。确定吗？`,
                hasLocal ? "覆盖存档" : "导入存档",
                {
                    confirmButtonText: hasLocal ? "覆盖" : "导入",
                    cancelButtonText: "取消",
                    type: hasLocal ? "warning" : "info",
                },
            );
        } catch {
            return;
        }
        working.value = true;
        await writeLocalEmuSave(props.gameId, { base64 });
        ElMessage.success(hasLocal ? "已覆盖本地存档。" : "已导入本地存档。");
        await refreshLocal();
    } catch (err) {
        // 取消或读文件失败：取消不提示，其余弹错
        if (err && err !== "cancel" && err !== "close") {
            ElMessage.error(err?.message || "读取文件失败。");
        }
        await refreshLocal();
    }
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

// 「同步至云端」先弹可选描述，父组件负责：捕捉 → 收集本地全部档 → 上传快照
function onUploadCloud() {
    if (cloudBusy.value || !props.engineReady) {
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
    const remark = uploadDesc.value.trim().slice(0, 100);
    uploadPromptVisible.value = false;
    uploadDesc.value = "";
    cloudBusy.value = true;
    emit("upload-cloud", { remark });
}

async function onSyncToLocal(snapshot) {
    if (cloudBusy.value) {
        return;
    }
    try {
        await ElMessageBox.confirm(
            "将用该云端存档覆盖本地存档，确定吗？",
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
    emit("sync-local", { snapshotId: snapshot.id });
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
        // 错误提示已由请求层 toast
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

/** 父组件完成捕捉/上传/恢复等异步编排后调用：复位忙碌态并刷新列表。 */
function afterOperation() {
    working.value = false;
    cloudBusy.value = false;
    void refreshLocal();
    refreshCloud();
}

watch(
    () => props.modelValue,
    (visible) => {
        if (visible) {
            activeTab.value = "local";
            void refreshLocal();
            window.addEventListener("keydown", onKeydown);
        } else {
            window.removeEventListener("keydown", onKeydown);
        }
    },
);

onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown);
});

defineExpose({ afterOperation, refreshLocal, refreshCloud });
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

.save-manager__hint {
    margin: 12px 20px;
    padding: 10px 14px;
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
    height: 112px;
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

/* 按钮里的快捷键符号（回车）：小一号、淡一点，与按钮文字留出间距 */
.save-manager__btn-key {
    margin-left: 6px;
    font-size: 12px;
    line-height: 1;
    opacity: 0.7;
}
</style>
