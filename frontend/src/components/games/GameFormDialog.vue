<template>
    <!-- 添加/编辑游戏：左右两栏——左边元数据、右边两个上传；整窗居中且一页放得下（不滚动）。
             新建要等全部填完才建条目，底部保留「取消 / 保存」；
             编辑时每个字段改完即存、文件选完即传，没有保存按钮，只留右上角关闭。 -->
    <app-dialog
        v-model="dialogVisible"
        :title="formMode === 'create' ? '添加游戏' : '编辑游戏'"
        width="880px"
        align-center
        :footer-mode="formMode === 'create' ? 'default' : 'none'"
        :confirm-loading="saving"
        confirm-text="保存"
        @confirm="onSave"
    >
        <el-form
            v-loading="formMode === 'edit' && !editingItem"
            label-width="88px"
            class="game-form__form"
        >
            <div class="game-form__form-cols">
                <div class="game-form__form-col">
                    <!-- 编辑时把卡带ID摆到最上面：它既是磁盘目录名、又是这盘卡的身份。
                             值旁边给一个「修改 ID」：改它会连磁盘目录与各账号的存档/截图一起搬，
                             所以单独一次请求、保存即生效 -->
                    <el-form-item v-if="formMode === 'edit'" label="卡带 ID">
                        <div class="game-form__cartridge">
                            <template v-if="!cartridgeEditing">
                                <span class="game-form__detail-key">
                                    {{ editingItem?.cartridge_id }}
                                </span>
                                <app-button variant="secondary" size="sm" @click="startEditCartridgeId">
                                    修改 ID
                                </app-button>
                            </template>
                            <template v-else>
                                <!-- esc 上的 .stop 不能少：el-dialog 默认按 ESC 关掉整个弹框，
                                         不拦住的话按一下就把编辑弹框关了 -->
                                <el-input
                                    ref="cartridgeInputRef"
                                    v-model="cartridgeDraft"
                                    class="game-form__cartridge-input"
                                    maxlength="64"
                                    placeholder="数字、字母、中划线、下划线，自动转大写"
                                    @keydown.enter.prevent="onConfirmCartridgeId"
                                    @keydown.esc.stop="cancelEditCartridgeId"
                                />
                                <app-button
                                    variant="secondary"
                                    size="sm"
                                    :disabled="cartridgeSaving"
                                    @click="cancelEditCartridgeId"
                                >
                                    取消
                                </app-button>
                                <app-button
                                    variant="secondary"
                                    size="sm"
                                    :loading="cartridgeSaving"
                                    @click="onConfirmCartridgeId"
                                >
                                    确认
                                </app-button>
                            </template>
                        </div>
                    </el-form-item>
                    <el-form-item label="游戏名称" required>
                        <el-input
                            v-model="form.name"
                            maxlength="255"
                            placeholder="请输入游戏名称"
                            @change="onMetaFieldChange"
                        />
                    </el-form-item>
                    <el-form-item v-if="formMode === 'create'" label="卡带 ID" required>
                        <el-input
                            v-model="form.cartridgeId"
                            maxlength="64"
                            placeholder="数字、字母、中划线、下划线，自动转大写"
                        />
                    </el-form-item>
                    <!-- 描述框按 200 字上限给足高度（12 行，中文一字一行的最坏情况也放得下）
                             且不许拖拽缩放，写满不用滚、右下角的字数也不压住最后一行 -->
                    <el-form-item label="游戏描述">
                        <el-input
                            v-model="form.description"
                            class="game-form__desc-input"
                            type="textarea"
                            :rows="12"
                            resize="none"
                            maxlength="200"
                            show-word-limit
                            placeholder="简要介绍玩法或来源"
                            @change="onMetaFieldChange"
                        />
                    </el-form-item>
                    <el-form-item
                        label="游戏类型"
                        :required="formMode === 'create' && !hasBodySource"
                    >
                        <!-- 创建：无本体时必须先选类型；有本体时后缀唯一则只读、多候选才下拉 -->
                        <app-type-select
                            v-if="formMode === 'create' && (bodyTypeCandidates.length > 1 || !hasBodySource)"
                            v-model="form.gameType"
                            placeholder="请选择游戏类型"
                            class="game-form__type-select"
                            :options="hasBodySource ? bodyTypeOptions : allTypeOptions"
                        />
                        <!-- 编辑：只有当前本体后缀有多个候选时才允许改类型 -->
                        <app-type-select
                            v-else-if="formMode === 'edit' && editingTypeCandidates.length > 1"
                            v-model="form.gameType"
                            :disabled="typeSaving"
                            class="game-form__type-select"
                            :options="editingTypeOptions"
                            @change="onChangeGameType"
                        />
                        <span v-else class="game-form__type-value">{{ typeFieldText }}</span>
                    </el-form-item>
                    <p v-if="bodyTypeHint" class="game-form__file-hint muted">
                        {{ bodyTypeHint }}
                    </p>
                    <!-- 封面类型：这盘封面被美化成的外观，值就是封面样式 id。
                             选项由「这次会落成的游戏类型」决定（见 coverTypeOptions）；
                             新建时不给这一行——新建一律留空，只有编辑能改、或美化封面时自动写。
                             不支持美化封面的类型（h5/snes/sega*）没有选项，整行也不显示。 -->
                    <el-form-item
                        v-if="formMode === 'edit' && coverTypeOptions.length"
                        label="封面类型"
                    >
                        <el-radio-group v-model="form.coverType" @change="onMetaFieldChange">
                            <el-radio
                                v-for="item in coverTypeOptions"
                                :key="item.id"
                                :value="item.id"
                            >
                                {{ item.label }}
                            </el-radio>
                        </el-radio-group>
                    </el-form-item>
                    <el-form-item v-if="formMode === 'edit'" label="CRC32">
                        <span v-if="editingItem?.crc32" class="game-form__detail-key">
                            {{ editingItem.crc32 }}
                        </span>
                        <span v-else class="game-form__file-hint muted">
                            尚未计算（上传或更换本体后写入）
                        </span>
                    </el-form-item>
                </div>
                <div class="game-form__form-col">
                    <el-form-item label="游戏本体">
                        <!-- 两个来源做成同款按钮：原生文件选择器藏起来，由「本地上传」代点 -->
                        <div class="game-form__source">
                            <input
                                ref="gameFileRef"
                                class="game-form__file-input"
                                type="file"
                                :accept="gameAccept"
                                :multiple="canSelectMultipleBodyFiles"
                                @change="onGameFileChange"
                            />
                            <app-button
                                variant="secondary"
                                :disabled="bodyUploading || saving"
                                @click="pickBodyFile"
                            >
                                本地上传
                            </app-button>
                            <app-button
                                variant="secondary"
                                :disabled="bodyUploading || saving"
                                @click="openRemoteBody"
                            >
                                网络上传
                            </app-button>
                        </div>
                        <template v-if="form.gameFile || form.gameFiles.length">
                            <p v-if="form.gameFiles.length" class="game-form__file-hint">
                                {{ bodyUploading || formMode === "edit" ? "正在上传：" : "已选：" }}{{ form.gameFiles.length }} 个文件，共 {{ formatSize(bodyFilesTotalSize) }}<template v-if="bodyUploading"> · {{ bodyProgress }}%</template>
                            </p>
                            <p v-else class="game-form__file-hint">
                                {{ bodyUploading || formMode === "edit" ? "正在上传：" : "已选：" }}{{ form.gameFile.name }}（{{ formatSize(form.gameFile.size) }}<template v-if="bodyUploading"> · {{ bodyProgress }}%</template>）
                            </p>
                            <p
                                v-if="form.gameFiles.length"
                                class="game-form__file-hint muted"
                            >
                                {{ form.gameFiles.map((file) => file.name).join("、") }}
                            </p>
                            <p
                                v-if="form.gameFiles.length && bodyFilesTotalSize > 1024 * 1024 * 1024"
                                class="game-form__file-hint muted"
                            >
                                多文件本体超过 1GB 时浏览器内存压力较大，世嘉 CD 建议优先用单个 .chd。
                            </p>
                            <el-progress
                                v-if="bodyUploading"
                                class="game-form__upload-progress"
                                :percentage="bodyProgress"
                                :show-text="false"
                                :stroke-width="4"
                            />
                        </template>
                        <!-- 网络来源与本地文件二选一：选了直链就把本地文件清掉（反之亦然） -->
                        <p v-else-if="form.bodyUrl" class="game-form__file-hint">
                            待上传：{{ form.bodyUrl }}（{{ typeLabel(form.bodyGameType) }}）
                            <app-button text size="sm" @click="clearRemoteBody">
                                清除
                            </app-button>
                        </p>
                        <p v-else-if="formMode === 'edit' && editingItem?.game_path" class="game-form__file-hint muted">
                            当前：{{ editingItem.game_path }}
                        </p>
                        <p v-if="formMode === 'create' && !hasBodySource" class="game-form__file-hint muted">
                            可稍后上传；未上传本体的游戏不会进入游玩页。
                        </p>
                    </el-form-item>
                    <el-form-item label="游戏封面">
                        <div class="game-form__source">
                            <input
                                ref="coverFileRef"
                                class="game-form__file-input"
                                type="file"
                                accept="image/*"
                                @change="onCoverFileChange"
                            />
                            <app-button
                                variant="secondary"
                                :disabled="coverUploading"
                                @click="pickCoverFile"
                            >
                                本地上传
                            </app-button>
                            <app-button
                                variant="secondary"
                                :disabled="coverUploading"
                                @click="openRemoteCover"
                            >
                                网络上传
                            </app-button>
                            <!-- 美化封面：把当前封面合成成光盘 / 卡带的外观后存回去。
                                     只在支持美化的类型（flash / gb / gba）出现，且要已有封面 -->
                            <app-button
                                v-if="canShowBeautify"
                                variant="secondary"
                                :disabled="!canBeautify || coverUploading"
                                @click="beautifyVisible = true"
                            >
                                美化封面
                            </app-button>
                        </div>
                        <p v-if="form.coverFile" class="game-form__file-hint">
                            {{ formMode === "edit" ? "正在上传：" : "已选：" }}{{ form.coverFile.name }}
                        </p>
                        <p v-else-if="form.coverUrl" class="game-form__file-hint">
                            待上传：{{ form.coverUrl }}
                            <app-button text size="sm" @click="form.coverUrl = ''">
                                清除
                            </app-button>
                        </p>
                        <p v-else-if="formMode === 'edit' && editingItem?.cover_path" class="game-form__file-hint muted">
                            当前：{{ editingItem.cover_path }}
                        </p>
                        <!-- 选了新封面就立刻显示新图（提交前先看效果），否则显示当前封面 -->
                        <div v-if="coverPreview" class="game-form__cover-preview">
                            <img :src="coverPreview.src" :alt="coverPreview.caption" />
                            <span class="game-form__cover-preview-tip">{{ coverPreview.caption }}</span>
                        </div>
                    </el-form-item>
                    <!-- 图集：只在编辑时出现（新建还没有卡带目录可落，图集又挂在游戏上）。
                             「上传」是快捷入口：选完图直接入库，不必先进管理弹框 -->
                    <el-form-item v-if="formMode === 'edit'" label="图集">
                        <div class="game-form__source">
                            <image-upload-button
                                :game-id="editingId"
                                :upload="uploadGalleryAPI"
                            />
                            <app-button variant="secondary" @click="galleryManagerVisible = true">
                                管理
                            </app-button>
                        </div>
                    </el-form-item>
                    <!-- 攻略：只在编辑时出现（新建还没有卡带目录可落）。上传 ZIP 或 PDF，选完立即上传 -->
                    <el-form-item v-if="formMode === 'edit'" label="游戏攻略">
                        <div class="game-form__source">
                            <input
                                ref="guideFileRef"
                                class="game-form__file-input"
                                type="file"
                                accept=".zip,.pdf,application/zip,application/pdf"
                                @change="onGuideFileChange"
                            />
                            <app-button
                                variant="secondary"
                                :disabled="guideUploading || guideDeleting"
                                @click="pickGuide"
                            >
                                上传攻略
                            </app-button>
                            <app-button
                                v-if="editingItem?.has_guide"
                                variant="danger"
                                :loading="guideDeleting"
                                :disabled="guideUploading || guideDeleting"
                                @click="onDeleteGuide"
                            >
                                删除攻略
                            </app-button>
                        </div>
                        <p v-if="guideUploading" class="game-form__file-hint">
                            正在上传攻略…
                        </p>
                        <p v-else-if="editingItem?.has_guide" class="game-form__file-hint muted">
                            当前：已有攻略（{{ editingItem.guide_kind === "pdf" ? "PDF" : "ZIP" }}，重新上传会整体替换）
                        </p>
                        <p v-else class="game-form__file-hint muted">
                            选择一个攻略 ZIP 或 PDF（ZIP 解压后根目录需含 index.html），重新上传会整体替换
                        </p>
                    </el-form-item>
                </div>
            </div>
        </el-form>
    </app-dialog>

    <!-- 网络上传本体：地址之外还要选类型——直链（尤其网盘那种）未必看得出是什么机种 -->
    <app-dialog
        v-model="remoteBodyVisible"
        title="网络上传本体"
        width="520px"
        :confirm-loading="bodyUploading"
        @confirm="confirmRemoteBody"
    >
        <el-form label-width="88px" class="game-form__form">
            <el-form-item label="下载地址">
                <el-input
                    v-model="remoteBody.url"
                    placeholder="https://example.com/roms/game.gba"
                    clearable
                    @blur="syncRemoteType"
                />
            </el-form-item>
            <el-form-item label="游戏类型">
                <app-type-select
                    v-model="remoteBody.gameType"
                    placeholder="请选择游戏类型"
                    class="game-form__remote-select"
                    :disabled="formMode === 'edit'"
                    :options="remoteTypeSelectOptions"
                />
            </el-form-item>
            <p v-if="formMode === 'edit'" class="game-form__file-hint muted">
                编辑时只能更换同一游戏类型的本体（同类型后缀可互换：.gb ↔ .gbc、.sfc ↔ .smc、.md ↔ .gen）；
                地址后缀属于其他类型会被拒绝。
            </p>
            <p v-else class="game-form__file-hint muted">
                地址能看出后缀时，下拉只列该后缀支持的机种（多候选取第一个，仍可改）；
                看不出（如网盘直链）就按这里选的类型入库。保存时才真正下载。
            </p>
        </el-form>
    </app-dialog>

    <app-dialog
        v-model="remoteCoverVisible"
        title="网络上传封面"
        width="520px"
        :confirm-loading="coverUploading"
        @confirm="confirmRemoteCover"
    >
        <el-form label-width="88px" class="game-form__form">
            <el-form-item label="图片地址">
                <el-input
                    v-model="remoteCoverUrl"
                    placeholder="https://example.com/cover.png"
                    clearable
                />
            </el-form-item>
            <p class="game-form__file-hint muted">
                支持 jpg、jpeg、png、gif、webp 图片直链。{{ formMode === "edit" ? "确定后立即下载。" : "保存时才真正下载。" }}
            </p>
        </el-form>
    </app-dialog>

    <!-- 图集管理：叠在编辑弹框之上的另一层，所以放在它外面（同为根节点） -->
    <gallery-manager-dialog v-model="galleryManagerVisible" :game-id="editingId" />

    <!-- 美化封面：同样叠在编辑弹框之上，确认后直接把合成图存成该游戏的新封面 -->
    <cover-beautify-dialog
        v-model="beautifyVisible"
        :game="editingItem"
        :confirm-loading="beautifySaving"
        @confirm="onBeautifyConfirm"
    />
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { dangerConfirm } from "@/utils/confirm";
import AppDialog from "@components/common/AppDialog.vue";
import CoverBeautifyDialog from "@components/games/CoverBeautifyDialog.vue";
import GalleryManagerDialog from "@components/games/GalleryManagerDialog.vue";
import ImageUploadButton from "@components/games/ImageUploadButton.vue";
import {
    abortGameUploadAPI,
    createManageGameAPI,
    deleteGuideAPI,
    getManageGameAPI,
    renameCartridgeIdAPI,
    updateManageGameAPI,
    updateManageGameTypeAPI,
    uploadGameAssetAPI,
    uploadGalleryAPI,
    uploadGuideAPI,
} from "@/api/games";
import { beautifyStylesFor } from "@/constants/coverStyles";
import {
    gameTypeCandidatesByFilename,
    gameTypeCandidatesByUrl,
    gameTypeLabel as typeLabel,
    gameTypeMeta,
} from "@/constants/gameTypes";
import { extensionOfFilename, useGameTypesStore } from "@/store/gameTypes";
import { gameCoverUrl } from "@/utils/gameAssetCache";
import {
    shouldUseChunkedUpload,
    uploadFileInChunks,
    uploadFilesInChunks,
} from "@/utils/chunkUpload";

// 添加/编辑游戏弹框：游戏管理页与游戏榜单共用同一份实现。
// 新建时等全部填完才建条目，底部保留「取消 / 保存」；
// 编辑时每个字段改完即存、文件选完即传，没有保存按钮，只留右上角关闭。
const props = defineProps({
    modelValue: { type: Boolean, default: false },
    mode: { type: String, default: "create" },
    gameId: { type: [Number, String], default: null },
    // 仅新建使用：{ name, cartridgeId, gameType }，在 resetForm 之后注入
    initial: { type: Object, default: null },
});

const emit = defineEmits(["update:modelValue", "saved", "changed"]);

const formMode = computed(() => (props.mode === "edit" ? "edit" : "create"));
const dialogVisible = computed({
    get: () => props.modelValue,
    set: (value) => emit("update:modelValue", value),
});

const saving = ref(false);
// 类型与可上传后缀都来自 /status（后端词表派生），这里只读缓存
const gameTypesStore = useGameTypesStore();
const gameTypes = computed(() => gameTypesStore.gameTypes);

function emitChanged() {
    emit("changed");
}

const editingId = ref(null);
const editingItem = ref(null);
const gameFileRef = ref(null);
const coverFileRef = ref(null);
const guideFileRef = ref(null);
const guideDeleting = ref(false);
// 编辑弹框里的三个上传都是选完即传；在途时禁用对应按钮，避免同一项并发提交
const bodyUploading = ref(false);
const coverUploading = ref(false);
const guideUploading = ref(false);
// 大本体分片上传的百分比；单文件上传保持原来的布尔状态
const bodyProgress = ref(0);
let bodyAbortController = null;
// 每次打开弹框都换一代：上一只游戏的上传晚到时，不能清掉这一只刚选的文件/预览
let uploadGen = 0;
const form = reactive({
    name: "",
    cartridgeId: "",
    // 游戏类型：创建时由后缀候选决定；多候选（Commodore）时由用户选
    gameType: "",
    // 封面类型（封面样式 id）：空 = 没有。新建一律留空，编辑里可随时改
    coverType: "",
    description: "",
    gameFile: null,
    // 多文件本体（cue+bin / m3u / 多盘）：与 gameFile 二选一
    gameFiles: [],
    coverFile: null,
    // 网络上传的暂存值：新建时等「保存」一起提交，编辑时确认后立即上传
    bodyUrl: "",
    bodyGameType: "",
    coverUrl: "",
});

// 卡带 ID 的就地改名：点「修改 ID」变输入框，回车/「确认」提交、ESC/「取消」放弃。
// 保存即生效（后端要搬磁盘目录）
const cartridgeEditing = ref(false);
const cartridgeDraft = ref("");
const cartridgeSaving = ref(false);
const cartridgeInputRef = ref(null);

// 图集管理弹框（编辑弹框里的「图集 → 管理」打开；按游戏共享，保存即生效）
const galleryManagerVisible = ref(false);

// 美化封面弹框：把当前封面合成成光盘 / 卡带外观后存回去。可用样式由游戏类型给
// （constants/coverStyles.js，有的类型不止一种样式，在弹框里选），不支持的类型整条不显示按钮
const beautifyVisible = ref(false);
const beautifySaving = ref(false);
const beautifyStyles = computed(() => beautifyStylesFor(editingItem.value?.game_type));
// 新建时游戏还没落库、也没有封面，不出现（图集、攻略两项同样是编辑专属）
const canShowBeautify = computed(
    () => formMode.value === "edit" && beautifyStyles.value.length > 0
);
// 支持美化的类型但还没有封面 → 按钮在、但点不动（美化的输入就是当前封面）
const canBeautify = computed(() => canShowBeautify.value && Boolean(editingItem.value?.cover_path));

// 网络上传的两个小弹框：本体要连类型一起选，封面只要地址
const remoteBodyVisible = ref(false);
const remoteBody = reactive({ url: "", gameType: "" });
// 直链类型下拉：地址能看出后缀时只列候选；看不出时列全部类型让用户自己选。
// 编辑态换本体不能改类型，只列当前类型（下拉本身也是禁用的）。
const remoteTypeOptions = computed(() => {
    if (formMode.value === "edit") {
        return editingItem.value?.game_type ? [editingItem.value.game_type] : [];
    }
    const candidates = gameTypesOfUrl(remoteBody.url);
    return candidates.length ? candidates : gameTypes.value;
});
const remoteTypeSelectOptions = computed(() =>
    remoteTypeOptions.value.map((type) => ({ value: type, label: typeLabel(type) }))
);
const remoteCoverVisible = ref(false);
const remoteCoverUrl = ref("");

// 封面允许的图片扩展名（与后端 _COVER_EXTENSIONS 一致）
const COVER_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp"];

// 封面预览：刚选的封面用本地 objectURL 即时显示（编辑时只会出现在上传途中），
// 否则显示该游戏当前封面。objectURL 要显式回收：换文件、重开弹窗、离开页面时都清掉。
const coverPreviewUrl = ref("");

function releaseCoverPreview() {
    if (coverPreviewUrl.value) {
        URL.revokeObjectURL(coverPreviewUrl.value);
        coverPreviewUrl.value = "";
    }
}

const coverPreview = computed(() => {
    if (coverPreviewUrl.value) {
        const caption = coverUploading.value
            ? "新封面（正在上传…）"
            : formMode.value === "create"
                ? "新封面（保存后生效）"
                : "新封面";
        return { src: coverPreviewUrl.value, caption };
    }
    const url = gameCoverUrl(editingItem.value);
    return url ? { src: url, caption: "当前封面" } : null;
});

// 本体来源：本地文件优先，其次是网络直链。
// 类型候选由后缀决定：唯一候选自动确定，多候选（Commodore 的 .d64 / .prg）由用户选。
// 多文件本体按「所有文件后缀的交集」求候选（cue+bin → 世嘉 CD，adf → Amiga）。
const bodyTypeCandidates = computed(() => {
    if (form.gameFile) {
        return gameTypeCandidatesByFilename(form.gameFile.name);
    }
    if (form.gameFiles.length) {
        return gameTypesStore
            .bundleCandidatesOfFiles(form.gameFiles)
            .map((item) => item.id);
    }
    if (form.bodyUrl) {
        return gameTypeCandidatesByUrl(form.bodyUrl);
    }
    return [];
});
const bodyTypeOptions = computed(() =>
    bodyTypeCandidates.value.map((type) => ({ value: type, label: typeLabel(type) }))
);
// 无本体新建时没有后缀可推断，类型由用户从全部机种里选
const allTypeOptions = computed(() =>
    gameTypes.value.map((type) => ({ value: type, label: typeLabel(type) }))
);
const bodySourceType = computed(() => {
    if (form.gameFile) {
        return (
            form.gameType ||
            gameTypesStore.defaultOfFilename(form.gameFile.name) ||
            bodyTypeCandidates.value[0] ||
            null
        );
    }
    if (form.gameFiles.length) {
        return form.gameType || bodyTypeCandidates.value[0] || null;
    }
    if (form.bodyUrl) {
        return (
            form.gameType ||
            form.bodyGameType ||
            gameTypesStore.defaultOfFilename(basenameOfUrl(form.bodyUrl)) ||
            bodyTypeCandidates.value[0] ||
            null
        );
    }
    return null;
});
const hasBodySource = computed(() =>
    Boolean(form.gameFile || form.gameFiles.length || form.bodyUrl)
);
// 类型选择后的准备提示：.zip 三义最容易选错，这里把三种包的区别直接写出来。
// 只做文案，不参与判型；真正的规则仍在后端 platforms / service。
const bodyTypeHint = computed(() => {
    const type = form.gameType || bodySourceType.value;
    if (type === "arcade") {
        return "街机本体必须是 FBNeo ROM 集合 zip，文件名就是集合名（如 mslug.zip），不能改名；只支持本地上传，不同引擎版本的集合不通用。Neo Geo 等 BIOS 可选 arcade.zip。";
    }
    if (type === "dos") {
        return "DOS 本体是 jsdos 压缩包：优先选 .jsdos；选 .zip 时请在这里明确选 DOS。包内需含 DOSBox 配置与游戏文件。";
    }
    if (type === "psp") {
        return "PSP 需要浏览器 WebGL2 与线程（页面须带 COOP/COEP），首次加载较慢；推荐 .iso 或体积更小的 .cso。";
    }
    if (type === "h5" && form.gameFile && extensionOfFilename(form.gameFile.name) === ".zip") {
        return "HTML5 本体是含 index.html 的静态站 zip；DOS 游戏请改选 DOS，街机 ROM 请改选街机。";
    }
    return "";
});
const gameAccept = computed(() => {
    if (formMode.value === "edit") {
        // 编辑只能换同类型本体：文件选择器直接收窄到当前类型（含多文件包内后缀）
        const extensions = gameTypeMeta(editingItem.value?.game_type)?.uploadExtensions;
        if (extensions?.length) {
            return extensions.join(",");
        }
    }
    return gameTypesStore.allUploadExtensions.join(",");
});

// 当前能否选多个文件：编辑看当前类型；新建始终允许先多选（候选由文件后缀反推）。
const bodyMultiFile = computed(() => {
    if (formMode.value === "edit") {
        return Boolean(gameTypeMeta(editingItem.value?.game_type)?.multiFile);
    }
    return bodyTypeCandidates.value.some(
        (id) => gameTypeMeta(id)?.multiFile,
    );
});
const bodyFilesTotalSize = computed(() =>
    form.gameFiles.reduce((sum, file) => sum + Number(file.size || 0), 0),
);
// 新建时还没选文件、候选为空，必须允许先多选；编辑时按当前类型决定。
const canSelectMultipleBodyFiles = computed(
    () => formMode.value === "create" || bodyMultiFile.value,
);

// 编辑弹框：当前本体后缀的候选。唯一候选时类型不可改，多候选时出现下拉。
const editingTypeCandidates = computed(() => {
    const item = editingItem.value;
    if (!item) {
        return [];
    }
    // 多文件本体不支持改类型（后端也会拒绝），下拉只保留当前类型
    if (item.body_kind === "bundle") {
        return item.game_type ? [item.game_type] : [];
    }
    // ZIP 在 HTML5 / DOS / 街机之间含义不同，后端拒绝改类型，编辑时不显示下拉
    if (["h5", "dos", "arcade"].includes(item.game_type)) {
        return item.game_type ? [item.game_type] : [];
    }
    const candidates = gameTypeCandidatesByFilename(item.game_path || "");
    return candidates.length ? candidates : item.game_type ? [item.game_type] : [];
});
const editingTypeOptions = computed(() =>
    editingTypeCandidates.value.map((type) => ({ value: type, label: typeLabel(type) }))
);

// 封面类型的候选：编辑态用当前（可能刚改过的）类型；新建态按待上传本体的候选。
// 不支持美化封面的类型与「新建还没选本体」都是空数组（那一行不显示）。
const effectiveGameType = computed(() => {
    if (formMode.value === "edit") {
        return form.gameType || editingItem.value?.game_type || "";
    }
    return form.gameType || bodySourceType.value || "";
});
const coverTypeOptions = computed(() => beautifyStylesFor(effectiveGameType.value));

// 新建时换了本体文件后，原来选的封面类型可能不再合法，清空它
// （表单里先清，避免留一个存不下去的值）
watch(coverTypeOptions, (options) => {
    if (form.coverType && !options.some((item) => item.id === form.coverType)) {
        form.coverType = "";
    }
});
const typeFieldText = computed(() => {
    if (formMode.value === "create") {
        if (!hasBodySource.value) {
            return "选择本体文件或填写下载地址后确定";
        }
        if (!bodyTypeCandidates.value.length) {
            return "无法识别该格式，请更换本体文件";
        }
        return typeLabel(bodySourceType.value || "");
    }
    const current = editingItem.value?.game_type;
    const currentLabel = current ? typeLabel(current) : "—";
    if (!hasBodySource.value) {
        return currentLabel;
    }
    if (!bodySourceType.value) {
        return `${currentLabel}（新本体格式无法识别）`;
    }
    return bodySourceType.value === current
        ? currentLabel
        : `${currentLabel}（新本体是「${typeLabel(bodySourceType.value)}」，类型不符，不能保存）`;
});

/** 取地址路径的最后一段（去掉查询串、URL 解码）；解析不出来返回空串。 */
function basenameOfUrl(url) {
    try {
        return decodeURIComponent(new URL(url.trim()).pathname.split("/").pop() || "");
    } catch {
        return "";
    }
}

/** 地址路径里的扩展名（小写、含点）；看不出返回空串。 */
function extensionOfUrl(url) {
    const name = basenameOfUrl(url);
    const dot = name.lastIndexOf(".");
    return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

/** 地址能认出的全部候选类型；认不出（没扩展名或是没收录的格式）返回空数组。 */
function gameTypesOfUrl(url) {
    const name = basenameOfUrl(url);
    return name ? gameTypeCandidatesByFilename(name) : [];
}

/** 地址能认出的默认类型（按后缀覆盖表优先）；认不出返回 null。 */
function gameTypeOfUrl(url) {
    const name = basenameOfUrl(url);
    return name ? gameTypesStore.defaultOfFilename(name) || null : null;
}

function isHttpUrl(url) {
    return /^https?:\/\//i.test(url.trim());
}

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

function clearGameFile() {
    form.gameFile = null;
    form.gameFiles = [];
    if (gameFileRef.value) {
        gameFileRef.value.value = "";
    }
}

function clearCoverFile() {
    form.coverFile = null;
    if (coverFileRef.value) {
        coverFileRef.value.value = "";
    }
}

function clearRemoteBody() {
    form.bodyUrl = "";
    form.bodyGameType = "";
}

/** 停掉在途的分片上传；分片工具会顺手 DELETE 服务端会话。 */
function cancelBodyUpload() {
    if (bodyAbortController) {
        bodyAbortController.abort();
        bodyAbortController = null;
    }
    bodyProgress.value = 0;
}

/** 把一个超过 30MB 的本体传到暂存区，返回 `{upload_id, filename, size}`。 */
async function stageBodyFile(file, gameType = "") {
    const controller = new AbortController();
    bodyAbortController = controller;
    bodyProgress.value = 0;
    try {
        return await uploadFileInChunks(file, {
            gameType,
            signal: controller.signal,
            onProgress: ({ loaded, total }) => {
                bodyProgress.value = total
                    ? Math.min(100, Math.round((loaded / total) * 100))
                    : 0;
            },
        });
    } finally {
        if (bodyAbortController === controller) {
            bodyAbortController = null;
        }
    }
}

/** 把一组多文件本体传到暂存区，返回 `{upload_ids, uploads, files}`。 */
async function stageBodyFiles(files, gameType = "") {
    const controller = new AbortController();
    bodyAbortController = controller;
    bodyProgress.value = 0;
    try {
        return await uploadFilesInChunks(files, {
            gameType,
            signal: controller.signal,
            onProgress: ({ loaded, total }) => {
                bodyProgress.value = total
                    ? Math.min(100, Math.round((loaded / total) * 100))
                    : 0;
            },
        });
    } finally {
        if (bodyAbortController === controller) {
            bodyAbortController = null;
        }
    }
}

// 打开：重置并加载（编辑取详情，新建注入预填）；关闭：停上传、编辑补一次落库。
// openGen 丢弃「关掉之后才返回」的详情请求，避免把旧游戏回填进新弹框。
let openGen = 0;
watch(
    () => props.modelValue,
    async (visible) => {
        if (!visible) {
            cancelBodyUpload();
            // 右上角关闭时输入框可能还没触发 change：补一次落库（空名称不提交）
            if (formMode.value === "edit" && form.name.trim()) {
                queueMetaSave();
            }
            return;
        }
        const gen = ++openGen;
        // 先清掉上一只游戏的状态：避免打开瞬间闪一下旧数据；编辑表单同时显示加载遮罩
        resetForm();
        // 榜单页没有自己的 onMounted：这里兜底加载类型表
        await gameTypesStore.ensureLoaded().catch(() => {});
        if (gen !== openGen || !props.modelValue) {
            return;
        }
        if (formMode.value === "edit") {
            // 上一只游戏关弹框时排队的元数据保存先落地，避免它的响应晚到覆盖这一只
            await metaSaveChain.catch(() => {});
            if (gen !== openGen || !props.modelValue) {
                return;
            }
            if (!props.gameId) {
                emit("update:modelValue", false);
                return;
            }
            editingId.value = props.gameId;
            try {
                const item = await getManageGameAPI(props.gameId);
                if (gen !== openGen || !props.modelValue) {
                    return;
                }
                editingItem.value = item;
                form.name = item.name;
                form.description = item.description;
                form.gameType = item.game_type;
                form.coverType = item.cover_type || "";
            } catch (err) {
                if (gen !== openGen) {
                    return;
                }
                emit("update:modelValue", false);
                if (!err?.reported) {
                    ElMessage.error("游戏详情加载失败，请稍后重试。");
                }
            }
            return;
        }
        const initial = props.initial || {};
        form.name = initial.name || "";
        form.cartridgeId = initial.cartridgeId || "";
        form.gameType = initial.gameType || "";
    },
    { immediate: true }
);

function resetForm() {
    cancelBodyUpload();
    form.name = "";
    form.cartridgeId = "";
    form.gameType = "";
    form.coverType = "";
    form.description = "";
    clearGameFile();
    clearCoverFile();
    clearGuide();
    guideDeleting.value = false;
    // 换了一只游戏：在途上传的 finally 认得旧 generation，不会来动新弹框的状态
    uploadGen += 1;
    bodyUploading.value = false;
    coverUploading.value = false;
    guideUploading.value = false;
    clearRemoteBody();
    form.coverUrl = "";
    remoteBody.url = "";
    remoteBody.gameType = "";
    remoteCoverUrl.value = "";
    galleryManagerVisible.value = false;
    releaseCoverPreview();
    editingId.value = null;
    editingItem.value = null;
    cancelEditCartridgeId();
}

async function startEditCartridgeId() {
    cartridgeDraft.value = editingItem.value?.cartridge_id || "";
    cartridgeEditing.value = true;
    await nextTick();
    cartridgeInputRef.value?.focus();
}

function cancelEditCartridgeId() {
    cartridgeEditing.value = false;
    cartridgeDraft.value = "";
}

/** 确认改卡带 ID：后端会搬磁盘目录，所以这里单独发一次请求、保存即生效。 */
async function onConfirmCartridgeId() {
    // 按钮上有 loading/disabled，但回车也能触发，所以在途时直接忽略
    if (cartridgeSaving.value) {
        return;
    }
    const next = cartridgeDraft.value.trim().toUpperCase();
    // 空着或没改动都当取消：不发请求，也不报错
    if (!next || next === editingItem.value?.cartridge_id) {
        cancelEditCartridgeId();
        return;
    }
    cartridgeSaving.value = true;
    try {
        editingItem.value = await renameCartridgeIdAPI(editingId.value, next);
        cancelEditCartridgeId();
        ElMessage.success("卡带 ID 已修改");
        emitChanged();
    } catch (err) {
        // 失败留在编辑态，改完再试；错误提示已由请求层 toast
        if (!err.reported) ElMessage.error(err.message || "修改失败");
    } finally {
        cartridgeSaving.value = false;
    }
}

// 改类型是显式迁移（后端要搬整个游戏目录与各账号的存档/截图），单独请求。
// 在途时下拉禁用，避免并发迁移。
const typeSaving = ref(false);

async function onChangeGameType(next) {
    const id = editingId.value;
    const current = editingItem.value?.game_type || "";
    if (!id || !next || next === current) {
        return;
    }
    typeSaving.value = true;
    try {
        // 名称 / 描述 / 封面类型的排队保存先落地，避免它们带着旧类型去校验 cover_type
        await metaSaveChain.catch(() => {});
        const updated = await updateManageGameTypeAPI(id, next);
        if (editingId.value === id) {
            editingItem.value = updated;
            form.gameType = updated.game_type;
            form.coverType = updated.cover_type || "";
        }
        ElMessage.success("游戏类型已修改");
        emitChanged();
    } catch (err) {
        if (editingId.value === id) {
            form.gameType = current;
        }
        if (!err.reported) {
            ElMessage.error(err.message || "修改游戏类型失败");
        }
    } finally {
        typeSaving.value = false;
    }
}
// 「本地上传」按钮代点隐藏的原生文件选择器（原生按钮没法套用站内按钮样式）
function pickBodyFile() {
    gameFileRef.value?.click();
}

function pickCoverFile() {
    coverFileRef.value?.click();
}

function isBundleFileSelection(files) {
    if (files.length > 1) {
        return true;
    }
    return Boolean(
        files.length &&
            gameTypesStore.isBundleOnlyExtension(
                extensionOfFilename(files[0].name),
            ),
    );
}

function onGameFileChange(event) {
    const files = Array.from(event.target.files || []);
    if (!files.length) {
        clearGameFile();
        return;
    }
    // 本地文件与网络地址二选一
    clearRemoteBody();

    const bundle = isBundleFileSelection(files);
    if (formMode.value === "edit") {
        const currentType = editingItem.value?.game_type;
        if (bundle) {
            if (!gameTypeMeta(currentType)?.multiFile) {
                ElMessage.warning(
                    `「${typeLabel(currentType)}」不支持多文件本体，请选择单个文件`,
                );
                clearGameFile();
                return;
            }
            const candidates = gameTypesStore.bundleCandidatesOfFiles(files);
            if (!candidates.some((item) => item.id === currentType)) {
                ElMessage.warning(
                    `这些文件与当前游戏类型「${typeLabel(currentType)}」不匹配`,
                );
                clearGameFile();
                return;
            }
            form.gameFiles = files;
            form.gameFile = null;
            uploadBodyNow({ files });
            return;
        }
        const file = files[0];
        form.gameFile = file;
        form.gameFiles = [];
        const candidates = gameTypeCandidatesByFilename(file.name);
        if (!candidates.length) {
            ElMessage.warning("无法识别游戏本体格式，请更换文件");
            clearGameFile();
            return;
        }
        // 编辑只能换同类型本体：当前类型必须在该后缀的候选集内
        if (currentType && !candidates.includes(currentType)) {
            ElMessage.warning(
                `只能更换同一游戏类型的本体：当前是「${typeLabel(currentType)}」，` +
                    `所选文件属于「${candidates.map((type) => typeLabel(type)).join("、")}」`,
            );
            clearGameFile();
            return;
        }
        uploadBodyNow({ file });
        return;
    }

    if (bundle) {
        const candidates = gameTypesStore.bundleCandidatesOfFiles(files);
        if (!candidates.length) {
            ElMessage.warning("无法识别多文件本体的游戏类型，请检查文件组合");
            clearGameFile();
            return;
        }
        form.gameFiles = files;
        form.gameFile = null;
        const ids = candidates.map((item) => item.id);
        if (ids.includes(form.gameType)) {
            // 保留用户已经选过的类型
        } else if (ids.length === 1) {
            form.gameType = ids[0];
        } else {
            // 只有 m3u 时世嘉 CD / Amiga 都匹配，必须由用户选
            form.gameType = "";
        }
        return;
    }

    const file = files[0];
    form.gameFile = file;
    form.gameFiles = [];
    const candidates = gameTypeCandidatesByFilename(file.name);
    if (!candidates.length) {
        ElMessage.warning("无法识别游戏本体格式，请更换文件");
        clearGameFile();
        return;
    }
    // 新建：多候选时按后缀覆盖表选默认项，用户仍可在类型下拉里改
    const preferred = gameTypesStore.defaultOfFilename(file.name) || candidates[0];
    form.gameType = candidates.includes(form.gameType) ? form.gameType : preferred;
}

function onCoverFileChange(event) {
    const file = event.target.files?.[0] || null;
    form.coverFile = file;
    if (file) {
        form.coverUrl = "";
    }
    releaseCoverPreview();
    if (!file) {
        return;
    }
    coverPreviewUrl.value = URL.createObjectURL(file);
    if (formMode.value === "edit") {
        uploadCoverNow({ file });
    }
}

function pickGuide() {
    guideFileRef.value?.click();
}

/** 攻略只收 ZIP 与 PDF（后端也校验，这里先挡一道，省一次上传） */
function isGuideFileName(name) {
    const lower = (name || "").toLowerCase();
    return lower.endsWith(".zip") || lower.endsWith(".pdf");
}

function onGuideFileChange(event) {
    const file = (event.target.files || [])[0] || null;
    if (!file) {
        return;
    }
    if (!isGuideFileName(file.name)) {
        ElMessage.warning("攻略只支持 ZIP 压缩包或 PDF 文件");
        clearGuide();
        return;
    }
    uploadGuideNow(file);
}

function clearGuide() {
    if (guideFileRef.value) {
        guideFileRef.value.value = "";
    }
}

function openRemoteBody() {
    remoteBody.url = form.bodyUrl;
    // 编辑态类型固定为当前游戏类型；新建态地址能看出类型就先替用户选上（多候选取默认）
    remoteBody.gameType =
        formMode.value === "edit"
            ? editingItem.value?.game_type || ""
            : form.bodyGameType || gameTypeOfUrl(remoteBody.url) || "";
    remoteBodyVisible.value = true;
}

function confirmRemoteBody() {
    const url = remoteBody.url.trim();
    if (!url) {
        ElMessage.warning("请填写本体下载地址");
        return;
    }
    if (!isHttpUrl(url)) {
        ElMessage.warning("请填写 http/https 开头的下载地址");
        return;
    }
    if (!remoteBody.gameType) {
        // 地址能看出候选就按覆盖表选默认；看不出必须手选
        remoteBody.gameType = gameTypeOfUrl(url) || "";
    }
    if (!remoteBody.gameType) {
        ElMessage.warning("请选择游戏类型");
        return;
    }
    // 地址能认出候选时先在前端拦一道；后端仍会按候选集再校验一次
    if (candidates.length && !candidates.includes(remoteBody.gameType)) {
        ElMessage.warning(
            formMode.value === "edit"
                ? `只能更换同一游戏类型的本体：当前是「${typeLabel(remoteBody.gameType)}」，` +
                    `该地址属于「${candidates.map((type) => typeLabel(type)).join("、")}」`
                : `该地址属于「${candidates.map((type) => typeLabel(type)).join("、")}」，` +
                    `与所选类型「${typeLabel(remoteBody.gameType)}」不符`
        );
        return;
    }
    if (formMode.value === "edit") {
        // 编辑弹框里确认即上传；上传成功再收起这个小弹框，失败留在原地改地址
        uploadBodyNow({ url, gameType: remoteBody.gameType }).then((ok) => {
            if (ok) {
                remoteBodyVisible.value = false;
            }
        });
        return;
    }
    form.bodyUrl = url;
    form.bodyGameType = remoteBody.gameType;
    form.gameType = remoteBody.gameType;
    clearGameFile();
    remoteBodyVisible.value = false;
}

/** 地址里能看出候选就替用户选上；已选值不在新候选里时重置为默认。 */
function syncRemoteType() {
    if (formMode.value === "edit") {
        return;
    }
    const candidates = gameTypesOfUrl(remoteBody.url);
    if (!candidates.length) {
        remoteBody.gameType = "";
        return;
    }
    if (!candidates.includes(remoteBody.gameType)) {
        remoteBody.gameType = candidates[0];
    }
}

function openRemoteCover() {
    remoteCoverUrl.value = form.coverUrl;
    remoteCoverVisible.value = true;
}

function confirmRemoteCover() {
    const url = remoteCoverUrl.value.trim();
    if (!url) {
        ElMessage.warning("请填写封面图片地址");
        return;
    }
    if (!isHttpUrl(url)) {
        ElMessage.warning("请填写 http/https 开头的图片地址");
        return;
    }
    if (!COVER_EXTENSIONS.includes(extensionOfUrl(url))) {
        ElMessage.warning("封面仅支持 jpg、jpeg、png、gif、webp 图片直链");
        return;
    }
    if (formMode.value === "edit") {
        uploadCoverNow({ url }).then((ok) => {
            if (ok) {
                remoteCoverVisible.value = false;
            }
        });
        return;
    }
    form.coverUrl = url;
    clearCoverFile();
    remoteCoverVisible.value = false;
}

// coverType 只有「美化封面」那条路会传：样式 id 与封面文件同一次提交写进去
async function uploadAsset(
    gameId,
    kind,
    { file = null, url = "", gameType = "", coverType = "", uploadId = "", uploadIds = [] }
) {
    const data = new FormData();
    data.append("kind", kind);
    if (uploadId) {
        data.append("upload_id", uploadId);
    }
    for (const id of uploadIds) {
        data.append("upload_ids", id);
    }
    if (file) {
        data.append("file", file);
    }
    if (url) {
        data.append("url", url);
        data.append("game_type", gameType);
    }
    if (coverType) {
        data.append("cover_type", coverType);
    }
    return uploadGameAssetAPI(gameId, data);
}

/**
 * 编辑弹框里的元数据（名称 / 描述 / 封面类型）改完即存。
 * 失焦、切换单选或关弹框时触发；请求串行排队，旧游戏的响应不会覆盖新打开的游戏。
 */
let metaSaveChain = Promise.resolve();

function queueMetaSave() {
    if (formMode.value !== "edit" || !editingId.value) {
        return;
    }
    const id = editingId.value;
    const payload = {
        name: form.name.trim(),
        description: form.description,
        cover_type: form.coverType || "",
    };
    // 在排队时就把基线快照下来：等真正发出请求时，编辑弹框可能已经换了一只游戏
    const baseline = editingItem.value;
    const base =
        baseline && baseline.id === id
            ? {
                name: baseline.name,
                description: baseline.description,
                cover_type: baseline.cover_type || "",
            }
            : null;
    metaSaveChain = metaSaveChain
        .then(() => saveMetaNow(id, payload, base))
        .catch(() => {});
}

/** 名称 / 描述 / 封面类型的变更入口：名称为空时还原成落库值，不提交。 */
function onMetaFieldChange() {
    if (formMode.value !== "edit") {
        return;
    }
    if (!form.name.trim()) {
        form.name = editingItem.value?.name || "";
        ElMessage.warning("游戏名称不能为空");
        return;
    }
    queueMetaSave();
}

async function saveMetaNow(id, payload, baseline) {
    if (
        baseline &&
        baseline.name === payload.name &&
        baseline.description === payload.description &&
        baseline.cover_type === payload.cover_type
    ) {
        return;
    }
    try {
        const updated = await updateManageGameAPI(id, payload);
        if (editingId.value === id && editingItem.value?.id === id) {
            editingItem.value = updated;
            // 服务端会去首尾空白：只把没被后续编辑改过的输入框同步成落库值
            if (form.name.trim() === payload.name) {
                form.name = updated.name;
            }
            if (form.description === payload.description) {
                form.description = updated.description;
            }
            if ((form.coverType || "") === payload.cover_type) {
                form.coverType = updated.cover_type || "";
            }
        }
        emitChanged();
    } catch (err) {
        if (!err.reported) {
            ElMessage.error(err.message || "保存失败");
        }
    }
}

/** 立即上传本体（编辑弹框专用）。成功返回 true，失败返回 false。 */
async function uploadBodyNow({ file = null, files = [], url = "", gameType = "" }) {
    const id = editingId.value;
    if (!id || bodyUploading.value) {
        return false;
    }
    const gen = uploadGen;
    bodyUploading.value = true;
    bodyProgress.value = 0;
    let stagedIds = [];
    try {
        let uploadIds = [];
        let plainFile = file;
        if (files.length) {
            const staged = await stageBodyFiles(
                files,
                form.gameType || editingItem.value?.game_type || "",
            );
            uploadIds = staged.upload_ids;
            stagedIds = uploadIds;
            plainFile = null;
        } else if (file && shouldUseChunkedUpload(file, gameTypesStore.singleFileMaxBytes)) {
            const staged = await stageBodyFile(
                file,
                form.gameType || editingItem.value?.game_type || "",
            );
            uploadIds = [staged.upload_id];
            stagedIds = uploadIds;
            plainFile = null;
        }
        const updated = await uploadAsset(id, "game", {
            file: plainFile,
            url,
            gameType,
            uploadIds,
        });
        if (editingId.value === id) {
            editingItem.value = updated;
        }
        if (gen === uploadGen) {
            clearRemoteBody();
        }
        ElMessage.success("游戏本体已更新");
        emitChanged();
        return true;
    } catch (err) {
        for (const uploadId of stagedIds) {
            abortGameUploadAPI(uploadId).catch(() => {});
        }
        if (err.aborted) {
            return false;
        }
        if (!err.reported) {
            ElMessage.error(err.message || "游戏本体上传失败");
        }
        return false;
    } finally {
        if (gen === uploadGen) {
            bodyUploading.value = false;
            bodyProgress.value = 0;
            // 清掉选择：同一个文件再选一次也能触发 change
            clearGameFile();
        }
    }
}

/** 立即上传封面（编辑弹框专用）。成功返回 true，失败返回 false。 */
async function uploadCoverNow({ file = null, url = "" }) {
    const id = editingId.value;
    if (!id || coverUploading.value) {
        return false;
    }
    const gen = uploadGen;
    coverUploading.value = true;
    try {
        const updated = await uploadAsset(id, "cover", { file, url });
        if (editingId.value === id) {
            editingItem.value = updated;
        }
        if (gen === uploadGen) {
            form.coverUrl = "";
        }
        ElMessage.success("封面已更新");
        emitChanged();
        return true;
    } catch (err) {
        if (!err.reported) {
            ElMessage.error(err.message || "封面上传失败");
        }
        return false;
    } finally {
        if (gen === uploadGen) {
            coverUploading.value = false;
            clearCoverFile();
            releaseCoverPreview();
        }
    }
}

/** 立即上传攻略（ZIP 只校验不解压、PDF 原样存；查看时才按需解到运行时目录）。 */
async function uploadGuideNow(file) {
    const id = editingId.value;
    if (!id || guideUploading.value) {
        clearGuide();
        return;
    }
    const gen = uploadGen;
    guideUploading.value = true;
    try {
        const data = new FormData();
        data.append("file", file);
        const updated = await uploadGuideAPI(id, data);
        if (editingId.value === id) {
            editingItem.value = updated;
        }
        ElMessage.success("攻略已上传");
        emitChanged();
    } catch (err) {
        if (!err.reported) {
            ElMessage.error(err.message || "攻略上传失败");
        }
    } finally {
        if (gen === uploadGen) {
            guideUploading.value = false;
            clearGuide();
        }
    }
}

/**
 * 美化封面弹框点「确认」：把合成出来的 PNG 传成该游戏的新封面。
 *
 * 合成图是 canvas 出来的 Blob，没有名字——后端靠文件名的后缀定扩展名（并决定落盘的
 * cover.{后缀}），所以必须包一层带 .png 的 File 再交给 uploadAsset。
 */
async function onBeautifyConfirm({ blob, styleId }) {
    beautifySaving.value = true;
    try {
        // 一次提交里把「换成哪种壳」也带上：封面类型就是这次选的样式 id
        await uploadAsset(editingId.value, "cover", {
            file: new File([blob], "cover.png", { type: "image/png" }),
            coverType: styleId,
        });
        beautifyVisible.value = false;
        ElMessage.success("封面已更新");
        // 封面路径与 updated_at 都变了：刷新编辑弹框里「当前：…」与预览，再刷新列表缩略图
        editingItem.value = await getManageGameAPI(editingId.value);
        form.coverType = editingItem.value.cover_type || "";
        emitChanged();
    } catch (err) {
        if (!err.reported) {
            ElMessage.error(err.message || "封面更新失败");
        }
    } finally {
        beautifySaving.value = false;
    }
}

/** 删除攻略：确认后立即生效。 */
async function onDeleteGuide() {
    const item = editingItem.value;
    if (!item?.has_guide || guideDeleting.value || guideUploading.value) {
        return;
    }
    const targetId = editingId.value;
    const confirmed = await dangerConfirm(
        `确定删除「${item.name}」的攻略？删除后无法恢复。`,
        { title: "删除攻略" },
    );
    if (!confirmed) {
        return;
    }
    guideDeleting.value = true;
    try {
        const updated = await deleteGuideAPI(targetId);
        // 请求在途时可能已经关掉弹框又打开别的游戏，别用旧响应覆盖
        if (editingId.value === targetId) {
            editingItem.value = updated;
        }
        ElMessage.success("攻略已删除");
        emitChanged();
    } catch (err) {
        if (!err.reported) ElMessage.error(err.message || "删除攻略失败");
    } finally {
        guideDeleting.value = false;
    }
}

async function onCreate() {
    // 类型由后缀候选 + 用户选择决定；后端会按候选集再校验一次
    const data = new FormData();
    data.append("name", form.name);
    data.append("cartridge_id", form.cartridgeId);
    data.append("description", form.description);
    let stagedIds = [];
    if (form.gameFiles.length) {
        bodyUploading.value = true;
        bodyProgress.value = 0;
        try {
            const staged = await stageBodyFiles(
                form.gameFiles,
                form.gameType || bodySourceType.value || "",
            );
            stagedIds = staged.upload_ids;
            for (const uploadId of stagedIds) {
                data.append("upload_ids", uploadId);
            }
        } finally {
            bodyUploading.value = false;
            bodyProgress.value = 0;
        }
    } else if (form.gameFile) {
        if (shouldUseChunkedUpload(form.gameFile, gameTypesStore.singleFileMaxBytes)) {
            bodyUploading.value = true;
            bodyProgress.value = 0;
            try {
                const staged = await stageBodyFile(
                    form.gameFile,
                    form.gameType || bodySourceType.value || ""
                );
                stagedIds = [staged.upload_id];
                data.append("upload_ids", staged.upload_id);
            } finally {
                bodyUploading.value = false;
                bodyProgress.value = 0;
            }
        } else {
            data.append("file", form.gameFile);
        }
    }
    if (form.bodyUrl) {
        data.append("body_url", form.bodyUrl);
    }
    if (form.gameType) {
        data.append("body_game_type", form.gameType);
    }
    if (form.coverFile) {
        data.append("cover", form.coverFile);
    }
    if (form.coverUrl) {
        data.append("cover_url", form.coverUrl);
    }
    try {
        return await createManageGameAPI(data);
    } catch (err) {
        // 游戏没建成：把已经传完的暂存会话删掉，别留到 24 小时 TTL
        for (const uploadId of stagedIds) {
            abortGameUploadAPI(uploadId).catch(() => {});
        }
        throw err;
    }
}

/** 新建：一次性提交名称 / 卡带 ID / 描述 / 本体（可选封面）。编辑没有保存按钮，不走这里。 */
async function onSave() {
    if (formMode.value !== "create") {
        return;
    }
    if (!form.name.trim()) {
        ElMessage.warning("请填写游戏名称");
        return;
    }
    if (!form.cartridgeId.trim()) {
        ElMessage.warning("请填写卡带 ID");
        return;
    }
    if (hasBodySource.value) {
        if (!bodySourceType.value) {
            ElMessage.warning("无法识别游戏本体格式，请更换文件或检查下载地址");
            return;
        }
        if (bodyTypeCandidates.value.length > 1 && !form.gameType) {
            ElMessage.warning("这些文件对应多个机种，请选择游戏类型");
            return;
        }
    } else if (!form.gameType) {
        // 没有本体时类型是唯一必选项：条目要靠它归入机种区块
        ElMessage.warning("请选择游戏类型");
        return;
    }

    saving.value = true;
    try {
        const item = await onCreate();
        ElMessage.success("游戏已添加");
        emit("update:modelValue", false);
        emit("saved", { id: item?.id ?? null, item });
    } catch (err) {
        if (!err.aborted && !err.reported) {
            ElMessage.error(err.message || "保存失败");
        }
    } finally {
        saving.value = false;
        bodyProgress.value = 0;
    }
}

onBeforeUnmount(() => {
    cancelBodyUpload();
    releaseCoverPreview();
});
</script>

<style scoped>
.game-form__form {
    padding-top: 4px;
}


/* 添加/编辑弹窗：左栏放元数据、右栏放两个上传，两栏等宽 */
.game-form__form-cols {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 0 24px;
}

.game-form__form-col {
    min-width: 0;
}

.game-form__file-hint {
    margin: 8px 0 0;
    font-size: 12px;
    color: #64748b;
}

.game-form__file-hint.muted {
    color: #94a3b8;
}

/* 大本体分片上传的细进度条：只占一行，不挤动表单布局 */
.game-form__upload-progress {
    margin-top: 6px;
    max-width: 320px;
}

/* 选了文件但还不合规时的提醒（缺 index.html、超过文件数上限） */
.game-form__file-warn {
    color: #d97706;
}

/* 本体/封面的来源行：「本地上传」与「网络上传」两个同款按钮并排 */
.game-form__source {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    width: 100%;
}

/* 原生文件选择器藏起来（样式没法统一），只由「本地上传」按钮代点 */
.game-form__file-input {
    display: none;
}

/* 卡带 ID 那一行：值占满左侧、按钮贴到左栏右边缘（改名时把值换成输入框，排版不跳） */
.game-form__cartridge {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
}

.game-form__cartridge .game-form__detail-key,
.game-form__cartridge-input {
    flex: 1 1 auto;
    min-width: 0;
}

/* 卡带 ID 是这盘卡的身份，值一律加粗；CRC32 共用同一个类，不在这里加 */
.game-form__cartridge .game-form__detail-key {
    font-weight: 600;
}

/* 描述框：高度交给 rows（不拖拽缩放），底部留出字数统计那一行的位置，免得压住最后一行 */
.game-form__desc-input :deep(.el-textarea__inner) {
    padding-bottom: 22px;
}

/* 「待上传」那行里的清除：做成行内文字按钮，不抢视线 */
.game-form__remote-select,
.game-form__type-select {
    width: 100%;
}

/* 封面类型的单选项是纯文字（样式名），与单选圆点垂直居中对齐 */
.game-form__form :deep(.el-radio) {
    margin-right: 20px;
    align-items: center;
}

.game-form__form :deep(.el-radio__label) {
    display: inline-flex;
    align-items: center;
}

.game-form__type-value {
    font-size: 13px;
    color: #0f172a;
}

/* 编辑弹窗里的封面预览：整图完整展示（contain 不裁切），便于确认选的图对不对。
   el-form-item__content 是 flex 行，width: 100% 让它独占一行，落在「当前：…」
   那行封面路径的下面，并靠左对齐。 */
.game-form__cover-preview {
    margin-top: 10px;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
}

.game-form__cover-preview img {
    width: 168px;
    height: 120px;
    object-fit: contain;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
}

.game-form__cover-preview-tip {
    font-size: 12px;
    color: #94a3b8;
}

/* 卡带 ID 与 CRC32 的值：窄了就省略 */
.game-form__detail-key {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>
