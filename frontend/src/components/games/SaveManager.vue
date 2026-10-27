<template>
    <save-manager-dialog
        :model-value="modelValue"
        @update:model-value="emit('update:modelValue', $event)"
    >
        <template #local-actions>
            <app-button
                variant="secondary"
                tone="dark"
                :disabled="captureDisabled"
                @click="onCapture"
            >
                {{ captureLabel }}
            </app-button>
            <app-button
                variant="secondary"
                tone="dark"
                :disabled="cloudButtonDisabled"
                @click="onUploadCloud"
            >
                {{ cloudButtonLabel }}
            </app-button>
            <app-button
                variant="secondary"
                tone="dark"
                :disabled="working || syncing"
                @click="onUpload"
            >
                从本地上传
            </app-button>
            <app-button
                v-if="isFlash"
                variant="secondary"
                tone="dark"
                :disabled="working || syncing"
                @click="refreshLocal"
            >
                刷新
            </app-button>
        </template>

        <template #local>
            <p v-if="isEmulator && !engineReady" class="save-manager__hint">
                模拟器尚未就绪：先进入游戏后，才能捕捉/载入即时存档。
            </p>
            <p v-else-if="!localSaves.length" class="save-manager__empty">
                {{ emptyText }}
            </p>
            <ul v-else class="save-manager__list">
                <li
                    v-for="save in localSaves"
                    :key="save.key || save.name"
                    class="save-manager__item"
                >
                    <div class="save-manager__item-info">
                        <span class="save-manager__item-name">{{ localName(save) }}</span>
                        <span class="save-manager__item-key">
                            {{ formatDateTime(save.updatedAt) }} ·
                            {{ formatBytes(save.size) }}
                        </span>
                    </div>
                    <div class="save-manager__item-actions">
                        <app-button
                            v-if="isEmulator"
                            variant="secondary"
                            tone="dark"
                            size="sm"
                            :disabled="!engineReady || working"
                            @click="onLoadLocal"
                        >
                            载入
                        </app-button>
                        <app-button
                            variant="secondary"
                            tone="dark"
                            size="sm"
                            :disabled="working || syncing"
                            @click="onDownloadLocal(save)"
                        >
                            下载
                        </app-button>
                        <app-button
                            variant="danger"
                            tone="dark"
                            size="sm"
                            :disabled="working || syncing"
                            @click="onDeleteLocal(save)"
                        >
                            删除
                        </app-button>
                    </div>
                </li>
            </ul>
        </template>

        <template #cloud>
            <cloud-save-panel
                ref="cloudPanelRef"
                :game-id="gameId"
                :busy="cloudBusy || working || syncing"
                :sync-confirm-message="syncConfirmMessage"
                @sync-local="onSyncLocal"
            />
        </template>
    </save-manager-dialog>

    <input
        ref="fileInputRef"
        type="file"
        :accept="importAccept"
        class="save-manager__file"
        @change="onFileChange"
    />

    <save-upload-prompt
        v-model="uploadPromptVisible"
        :busy="cloudBusy"
        :hint="uploadHint"
        @confirm="onConfirmUpload"
    />
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { confirmAction, dangerConfirm } from "@/utils/confirm";
import { appMessage } from "@/utils/overlay";
import { formatBytes, formatDateTime } from "@/utils/fileDisplay";
import { downloadLocalSave, isB64SOL } from "@/utils/ruffle";
import {
    buildKeyFromReference,
    buildKeyFromSwfOrigin,
    collectLocalSaves,
} from "@/utils/gameSaves";
import { cloudSaveDetailAPI, fetchCloudSaveFileBase64 } from "@/api/games";
import {
    EMU_SAVE_FILENAME,
    deleteLocalEmuSave,
    emuBase64ToBlob,
    ensureSingleSlotModel,
    getEmuSaveBase64,
    getLocalEmuSave,
    writeLocalEmuSave,
} from "@/utils/emulatorSaves";
import SaveManagerDialog from "@components/games/SaveManagerDialog.vue";
import CloudSavePanel from "@components/games/CloudSavePanel.vue";
import SaveUploadPrompt from "@components/games/SaveUploadPrompt.vue";

const props = defineProps({
    modelValue: { type: Boolean, default: false },
    gameId: { type: Number, default: 0 },
    // emulator：单一 save.state、可载入；flash：多份 .sol、写档后重启
    platform: { type: String, default: "emulator" },
    // 引擎（模拟器）是否已开始运行；捕捉/载入即时存档依赖引擎已就绪
    engineReady: { type: Boolean, default: false },
});

const emit = defineEmits([
    "update:modelValue",
    "capture",
    "sync",
    "load-local",
    "upload-cloud",
    "sync-local",
    "save-action",
]);

const isFlash = computed(() => props.platform === "flash");
const isEmulator = computed(() => !isFlash.value);

const localSaves = ref([]);
const working = ref(false);
const syncing = ref(false);
const cloudBusy = ref(false);
const uploadPromptVisible = ref(false);
const fileInputRef = ref(null);
const cloudPanelRef = ref(null);

const emptyText = computed(() =>
    isFlash.value
        ? "还没有本地存档。先在游戏里保存一次吧。"
        : "还没有本地存档。玩到想存的地方，点「捕捉当前进度」即可（只有一份，再捕捉会覆盖）。",
);

const uploadHint = computed(() =>
    isFlash.value
        ? "把当前游戏此刻的本地存档整体备份到云端"
        : "把当前本地存档备份到云端",
);

const syncConfirmMessage = computed(() =>
    isFlash.value
        ? "将用该云端存档覆盖本地对应存档并重启游戏，确定吗？"
        : "将用该云端存档覆盖本地存档，确定吗？",
);

const importAccept = computed(() =>
    isFlash.value ? ".sol,application/octet-stream" : ".state,application/octet-stream",
);

const captureLabel = computed(() => {
    if (isFlash.value) {
        return syncing.value ? "正在同步…" : "重启游戏以同步最新存档";
    }
    return working.value ? "正在捕捉…" : "捕捉当前进度";
});

const captureDisabled = computed(() =>
    isFlash.value
        ? working.value || syncing.value
        : !props.engineReady || working.value,
);

const cloudButtonDisabled = computed(
    () =>
        cloudBusy.value ||
        working.value ||
        syncing.value ||
        (isEmulator.value && !props.engineReady),
);

const cloudButtonLabel = computed(() =>
    cloudBusy.value ? "正在同步…" : "同步至云端",
);

function localName(save) {
    return isFlash.value ? `${save.name}.sol` : save.name;
}

async function refreshLocal() {
    working.value = false;
    syncing.value = false;
    if (!props.gameId) {
        localSaves.value = [];
        return;
    }
    if (isEmulator.value) {
        // 首次调用顺带清掉旧版多槽位档（一次性）
        await ensureSingleSlotModel();
        const save = getLocalEmuSave(props.gameId);
        localSaves.value = save ? [save] : [];
    } else {
        localSaves.value = collectLocalSaves(props.gameId);
    }
}

function onCapture() {
    if (isFlash.value) {
        if (working.value || syncing.value) {
            return;
        }
        syncing.value = true;
        emit("sync");
        return;
    }
    if (!props.engineReady) {
        appMessage.warning("请先开始游戏再捕捉进度。");
        return;
    }
    if (working.value) {
        return;
    }
    working.value = true;
    emit("capture");
}

function onLoadLocal() {
    if (!isEmulator.value) {
        return;
    }
    if (!props.engineReady) {
        appMessage.warning("请先开始游戏再载入存档。");
        return;
    }
    emit("load-local");
}

async function onDownloadLocal(save) {
    if (isFlash.value) {
        if (!downloadLocalSave(save.key, save.name)) {
            appMessage.warning("没有读到该存档的数据，可能已被删除。");
            await refreshLocal();
        }
        return;
    }
    const base64 = await getEmuSaveBase64(props.gameId);
    if (!base64) {
        appMessage.warning("该本地存档内容缺失。");
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

async function onDeleteLocal(save) {
    if (isFlash.value) {
        const confirmed = await dangerConfirm(
            `删除存档「${save.name}.sol」？删除后无法恢复。`,
            { title: "删除存档" },
        );
        if (!confirmed) {
            return;
        }
        working.value = true;
        emit("save-action", { action: "delete", key: save.key });
        return;
    }
    const confirmed = await dangerConfirm(
        `删除本地存档「${save.name}」？删除后无法恢复。`,
        { title: "删除存档" },
    );
    if (!confirmed) {
        return;
    }
    working.value = true;
    await deleteLocalEmuSave(props.gameId);
    await refreshLocal();
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
        if (isFlash.value) {
            await importFlashSave(file, base64);
        } else {
            await importEmulatorSave(file, base64);
        }
    } catch (err) {
        // 取消或读文件失败：取消不提示，其余弹错
        if (err && err !== "cancel" && err !== "close") {
            appMessage.error(err?.message || "读取文件失败。");
        }
        await refreshLocal();
    }
}

async function importEmulatorSave(file, base64) {
    if (!base64) {
        appMessage.error("该文件为空。");
        return;
    }
    // 本地只有一份档（固定叫 save.state）：导入即覆盖
    const hasLocal = localSaves.value.length > 0;
    const confirmed = await confirmAction(
        `将用「${file.name}」${hasLocal ? "覆盖当前本地存档" : "作为本地存档"}（存档固定叫 ${EMU_SAVE_FILENAME}），之后可在「本地存档」里载入。确定吗？`,
        {
            title: hasLocal ? "覆盖存档" : "导入存档",
            confirmText: hasLocal ? "覆盖" : "导入",
            danger: hasLocal,
            type: hasLocal ? "warning" : "info",
        },
    );
    if (!confirmed) {
        return;
    }
    working.value = true;
    await writeLocalEmuSave(props.gameId, { base64 });
    appMessage.success(hasLocal ? "已覆盖本地存档。" : "已导入本地存档。");
    await refreshLocal();
}

async function importFlashSave(file, base64) {
    if (!isB64SOL(base64)) {
        appMessage.error("该文件不是有效的 Ruffle 存档（.sol）文件。");
        return;
    }
    const name = normalizeSolName(file.name);
    const existing = localSaves.value.find((save) => save.name === name);
    let key;
    if (existing) {
        const confirmed = await confirmAction(
            `本地已有同名存档「${name}.sol」，覆盖后当前游戏会重启以读取新存档。确定覆盖吗？`,
            {
                title: "覆盖存档",
                confirmText: "覆盖",
                danger: true,
            },
        );
        if (!confirmed) {
            return;
        }
        key = existing.key;
    } else {
        const confirmed = await confirmAction(
            `将把「${name}.sol」导入为本地新存档，导入后当前游戏会重启以读取。确定吗？`,
            {
                title: "导入存档",
                confirmText: "导入",
                type: "info",
            },
        );
        if (!confirmed) {
            return;
        }
        key = localSaves.value.length
            ? buildKeyFromReference(localSaves.value[0].key, name)
            : buildKeyFromSwfOrigin(props.gameId, name);
    }
    working.value = true;
    emit("save-action", { action: "replace", key, base64 });
}

function normalizeSolName(filename) {
    const raw = String(filename || "").trim();
    if (!raw) {
        return "存档";
    }
    return raw.toLowerCase().endsWith(".sol") ? raw.slice(0, -4) : raw;
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

function onUploadCloud() {
    if (cloudBusy.value) {
        return;
    }
    if (isEmulator.value && !props.engineReady) {
        return;
    }
    uploadPromptVisible.value = true;
}

function onConfirmUpload({ remark }) {
    uploadPromptVisible.value = false;
    cloudBusy.value = true;
    emit("upload-cloud", { remark });
}

async function onSyncLocal(snapshot) {
    if (cloudBusy.value) {
        return;
    }
    if (isEmulator.value) {
        cloudBusy.value = true;
        emit("sync-local", { snapshotId: snapshot.id });
        return;
    }
    cloudBusy.value = true;
    try {
        const detail = await cloudSaveDetailAPI(snapshot.id);
        const writes = [];
        for (const file of detail.files || []) {
            const base64 = await fetchCloudSaveFileBase64(detail.id, file.id);
            writes.push({ key: file.local_key, base64 });
        }
        if (!writes.length) {
            appMessage.info("该云端存档没有可还原的文件。");
            return;
        }
        // 多文件在一次停播放器窗口内写回，父组件只重启一次
        emit("save-action", { action: "replace-many", writes });
    } catch {
        // 错误提示已由请求层 toast
    } finally {
        cloudBusy.value = false;
    }
}

function afterOperation() {
    working.value = false;
    syncing.value = false;
    cloudBusy.value = false;
    void refreshLocal();
    cloudPanelRef.value?.refresh();
}

function afterCloudUploaded() {
    cloudBusy.value = false;
    void refreshLocal();
    cloudPanelRef.value?.refresh();
}

async function refreshAfterParent() {
    await nextTick();
    await refreshLocal();
}

function refreshCloud() {
    cloudPanelRef.value?.refresh();
}

function handleEscape() {
    if (cloudPanelRef.value?.handleEscape?.()) {
        return true;
    }
    if (uploadPromptVisible.value) {
        uploadPromptVisible.value = false;
        return true;
    }
    return false;
}

function onKeydown(event) {
    if (event.key === "Escape") {
        if (handleEscape()) {
            return;
        }
        emit("update:modelValue", false);
        return;
    }
    if (event.key !== "Enter" && event.key !== "Delete") {
        return;
    }
    if (
        event.repeat ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey ||
        event.shiftKey
    ) {
        return;
    }
    const target = event.target;
    const tag = String(target?.tagName || "").toUpperCase();
    if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        tag === "BUTTON" ||
        tag === "A" ||
        target?.isContentEditable
    ) {
        return;
    }
    if (uploadPromptVisible.value || cloudBusy.value || working.value || syncing.value) {
        return;
    }
    if (document.querySelector(".el-message-box, .el-overlay-message-box")) {
        return;
    }
    if (cloudPanelRef.value?.handleSaveHotkey?.(event.key)) {
        event.preventDefault();
    }
}

watch(
    () => props.modelValue,
    (visible) => {
        if (visible) {
            uploadPromptVisible.value = false;
            void refreshLocal();
            window.addEventListener("keydown", onKeydown);
        } else {
            uploadPromptVisible.value = false;
            window.removeEventListener("keydown", onKeydown);
        }
    },
);

watch(
    () => props.gameId,
    () => {
        if (props.modelValue) {
            void refreshLocal();
        }
    },
);

onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown);
});

defineExpose({
    afterOperation,
    afterCloudUploaded,
    refresh: refreshAfterParent,
    refreshCloud,
    handleEscape,
});
</script>

<style>
.save-manager__hint,
.save-manager__empty {
    margin: 10px 0 0;
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.7;
}

.save-manager__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-flow: row nowrap;
    gap: 8px;
    min-width: 100%;
}

.save-manager__item {
    box-sizing: border-box;
    /* 固定宽度 = 云端存档左侧列表的外框宽（sidebar 184 + 左右 padding 20 + 边框 2） */
    flex: 0 0 206px;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    justify-content: flex-start;
    gap: 6px;
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    background: rgba(30, 41, 59, 0.55);
}

.save-manager__item-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
}

.save-manager__item-name {
    color: #f8fafc;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.save-manager__item-key {
    color: #94a3b8;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.save-manager__item-actions {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    justify-content: center;
    gap: 4px;
}

.save-manager__file {
    display: none;
}
</style>
