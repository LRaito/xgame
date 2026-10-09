<template>
    <div class="game-manage">
        <div class="game-manage__toolbar">
            <el-select
                v-model="filterType"
                placeholder="游戏类型"
                clearable
                class="game-manage__filter-type"
                @change="reload"
            >
                <el-option label="全部类型" value="" />
                <el-option
                    v-for="type in gameTypes"
                    :key="type"
                    :label="typeLabel(type)"
                    :value="type"
                />
            </el-select>
            <el-input
                v-model="filterKeyword"
                placeholder="搜索名称或描述"
                clearable
                class="game-manage__filter-keyword"
                @input="onKeywordInput"
            />
            <div class="game-manage__actions">
                <app-button @click="openImport">搬运游戏</app-button>
                <app-button type="primary" @click="openCreate">添加游戏</app-button>
            </div>
        </div>

        <div v-loading="loading" class="game-manage__table-wrap">
            <table v-if="items.length" class="game-manage__table">
                <!-- 列宽走百分比（见样式里的 table-layout: fixed）：内容再长也只在格子里省略，
                     表格永远不超出内容区，页面不会出现水平滚动条 -->
                <thead>
                    <tr>
                        <th class="game-manage__col-cover">封面</th>
                        <th class="game-manage__col-name">名称</th>
                        <th class="game-manage__col-type">类型</th>
                        <th class="game-manage__col-size">大小</th>
                        <th class="game-manage__col-time">更新时间</th>
                        <th class="game-manage__col-actions">操作</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="item in items" :key="item.id">
                        <td>
                            <div class="game-manage__cover">
                                <img
                                    v-if="item.cover_path"
                                    :src="gameCoverUrl(item)"
                                    :alt="item.name"
                                />
                                <span v-else class="game-manage__cover-fallback">⚡</span>
                            </div>
                        </td>
                        <td class="game-manage__desc-cell">
                            <div class="game-manage__name">{{ item.name }}</div>
                            <!-- 没有描述就整行不渲染（不留「—」，行高由封面撑着，不会变） -->
                            <template v-if="item.description">
                                <!-- 收起时单行省略；单击展开的那层绝对定位盖住下面的行 -->
                                <div
                                    class="game-manage__desc"
                                    @click="toggleDesc($event, item.id)"
                                >
                                    {{ item.description }}
                                </div>
                                <div
                                    v-if="expandedDescId === item.id"
                                    class="game-manage__desc-panel"
                                    @click="collapseDesc"
                                >
                                    {{ item.description }}
                                </div>
                            </template>
                        </td>
                        <!-- 这三列都只占一行、放不下就省略 -->
                        <td class="game-manage__nowrap">{{ typeLabel(item.game_type) }}</td>
                        <td class="game-manage__nowrap">{{ formatSize(item.size) }}</td>
                        <td class="game-manage__nowrap">{{ formatDateTime(item.updated_at) }}</td>
                        <td>
                            <div class="game-manage__row-actions">
                                <app-button @click="openDetail(item.id)">详情</app-button>
                                <app-button @click="openEdit(item.id)">编辑</app-button>
                                <app-button type="danger" @click="onDelete(item)">删除</app-button>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
            <app-empty v-else description="暂无游戏，点击「添加游戏」开始录入。" />
        </div>

        <!-- 添加/编辑游戏：左右两栏——左边元数据、右边两个上传；整窗居中且一页放得下（不滚动） -->
        <app-dialog
            v-model="formVisible"
            :title="formMode === 'create' ? '添加游戏' : '编辑游戏'"
            width="880px"
            align-center
            :confirm-loading="saving"
            confirm-text="保存"
            @confirm="onSave"
        >
            <el-form label-width="88px" class="game-manage__form">
                <div class="game-manage__form-cols">
                    <div class="game-manage__form-col">
                        <!-- 编辑时把卡带ID摆到最上面：它建后不可改、又是磁盘目录名，是这盘卡的身份 -->
                        <el-form-item v-if="formMode === 'edit'" label="卡带 ID">
                            <span class="game-manage__detail-key">{{ editingItem?.cartridge_id }}</span>
                        </el-form-item>
                        <el-form-item label="游戏名称" required>
                            <el-input v-model="form.name" maxlength="255" placeholder="请输入游戏名称" />
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
                                class="game-manage__desc-input"
                                type="textarea"
                                :rows="12"
                                resize="none"
                                maxlength="200"
                                show-word-limit
                                placeholder="简要介绍玩法或来源"
                            />
                        </el-form-item>
                        <el-form-item label="游戏类型">
                            <span class="game-manage__type-value">{{ typeFieldText }}</span>
                        </el-form-item>
                        <!-- 选项由「这次会落成的游戏类型」决定：选了新本体就按新类型给，
                             还没选本体（新建时）只给「默认」。见 cartridgeTypeOptions -->
                        <el-form-item label="卡带类型">
                            <el-radio-group v-model="form.cartridgeType">
                                <!-- 与详情一致：只显示国旗，不显示文字（中文名放 alt） -->
                                <el-radio
                                    v-for="item in cartridgeTypeOptions"
                                    :key="item.value"
                                    :value="item.value"
                                >
                                    <img
                                        class="game-manage__cartridge-flag"
                                        :src="item.flag"
                                        :alt="item.label"
                                    />
                                </el-radio>
                            </el-radio-group>
                        </el-form-item>
                        <el-form-item v-if="formMode === 'edit'" label="CRC32">
                            <span v-if="editingItem?.crc32" class="game-manage__detail-key">
                                {{ editingItem.crc32 }}
                            </span>
                            <span v-else class="game-manage__file-hint muted">
                                尚未锁定（补传本体后写入）
                            </span>
                        </el-form-item>
                    </div>
                    <div class="game-manage__form-col">
                        <el-form-item label="上传本体" :required="formMode === 'create'">
                            <!-- 两个来源做成同款按钮：原生文件选择器藏起来，由「本地上传」代点 -->
                            <div class="game-manage__source">
                                <input
                                    ref="gameFileRef"
                                    class="game-manage__file-input"
                                    type="file"
                                    :accept="gameAccept"
                                    @change="onGameFileChange"
                                />
                                <app-button @click="pickBodyFile">本地上传</app-button>
                                <app-button @click="openRemoteBody">网络上传</app-button>
                            </div>
                            <p v-if="form.gameFile" class="game-manage__file-hint">
                                已选：{{ form.gameFile.name }}（{{ formatSize(form.gameFile.size) }}）
                            </p>
                            <!-- 网络来源与本地文件二选一：选了直链就把本地文件清掉（反之亦然） -->
                            <p v-else-if="form.bodyUrl" class="game-manage__file-hint">
                                待上传：{{ form.bodyUrl }}（{{ typeLabel(form.bodyGameType) }}）
                                <button type="button" class="game-manage__clear" @click="clearRemoteBody">
                                    清除
                                </button>
                            </p>
                            <p v-else-if="formMode === 'edit' && editingItem?.game_path" class="game-manage__file-hint muted">
                                当前：{{ editingItem.game_path }}
                            </p>
                        </el-form-item>
                        <el-form-item label="上传封面">
                            <div class="game-manage__source">
                                <input
                                    ref="coverFileRef"
                                    class="game-manage__file-input"
                                    type="file"
                                    accept="image/*"
                                    @change="onCoverFileChange"
                                />
                                <app-button @click="pickCoverFile">本地上传</app-button>
                                <app-button @click="openRemoteCover">网络上传</app-button>
                            </div>
                            <p v-if="form.coverFile" class="game-manage__file-hint">
                                已选：{{ form.coverFile.name }}
                            </p>
                            <p v-else-if="form.coverUrl" class="game-manage__file-hint">
                                待上传：{{ form.coverUrl }}
                                <button type="button" class="game-manage__clear" @click="form.coverUrl = ''">
                                    清除
                                </button>
                            </p>
                            <p v-else-if="formMode === 'edit' && editingItem?.cover_path" class="game-manage__file-hint muted">
                                当前：{{ editingItem.cover_path }}
                            </p>
                            <!-- 选了新封面就立刻显示新图（提交前先看效果），否则显示当前封面 -->
                            <div v-if="coverPreview" class="game-manage__cover-preview">
                                <img :src="coverPreview.src" :alt="coverPreview.caption" />
                                <span class="game-manage__cover-preview-tip">{{ coverPreview.caption }}</span>
                            </div>
                        </el-form-item>
                        <!-- 图集：只在编辑时出现（新建还没有卡带目录可落，图集又挂在游戏上）。
                             「上传」是快捷入口：选完图直接入库，不必先进管理弹框 -->
                        <el-form-item v-if="formMode === 'edit'" label="图集">
                            <div class="game-manage__source">
                                <image-upload-button
                                    :game-id="editingId"
                                    :upload="uploadGalleryAPI"
                                />
                                <app-button @click="galleryManagerVisible = true">管理</app-button>
                            </div>
                        </el-form-item>
                        <!-- 攻略：只在编辑时出现（新建还没有卡带目录可落）。整目录上传，保存时才发出去 -->
                        <el-form-item v-if="formMode === 'edit'" label="上传攻略">
                            <div class="game-manage__source">
                                <!-- webkitdirectory：整目录选择；只传文件夹内的内容，外层目录名由 guideRelPath 剥掉 -->
                                <input
                                    ref="guideDirRef"
                                    class="game-manage__file-input"
                                    type="file"
                                    webkitdirectory
                                    directory
                                    multiple
                                    @change="onGuideDirChange"
                                />
                                <app-button @click="pickGuideDir">选择文件夹</app-button>
                            </div>
                            <p v-if="guideFiles.length" class="game-manage__file-hint">
                                已选 {{ guideFiles.length }} 个文件
                                <span v-if="!guideHasEntry" class="game-manage__file-warn">
                                    （缺少 index.html，攻略根目录必须包含它）
                                </span>
                                <span v-else-if="guideFiles.length > GUIDE_MAX_FILES" class="game-manage__file-warn">
                                    （超过 {{ GUIDE_MAX_FILES }} 个，无法上传）
                                </span>
                                <button type="button" class="game-manage__clear" @click="clearGuideDir">
                                    清除
                                </button>
                            </p>
                            <p v-else-if="editingItem?.has_guide" class="game-manage__file-hint muted">
                                当前：已有攻略（重新上传会整体替换）
                            </p>
                            <p v-else class="game-manage__file-hint muted">
                                选择一个文件夹整体上传，只传文件夹内的内容，根目录需含 index.html
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
            @confirm="confirmRemoteBody"
        >
            <el-form label-width="88px" class="game-manage__form">
                <el-form-item label="下载地址">
                    <el-input
                        v-model="remoteBody.url"
                        placeholder="https://example.com/roms/game.gba"
                        clearable
                        @blur="syncRemoteType"
                    />
                </el-form-item>
                <el-form-item label="游戏类型">
                    <el-select
                        v-model="remoteBody.gameType"
                        placeholder="请选择游戏类型"
                        class="game-manage__remote-select"
                    >
                        <el-option
                            v-for="type in gameTypes"
                            :key="type"
                            :label="typeLabel(type)"
                            :value="type"
                        />
                    </el-select>
                </el-form-item>
                <p class="game-manage__file-hint muted">
                    地址里能看出类型会先替你选上，之后仍可改；看不出（如网盘直链）就按这里选的类型入库。
                    地址与所选类型不符会当场报错。保存时才真正下载。
                </p>
            </el-form>
        </app-dialog>

        <app-dialog
            v-model="remoteCoverVisible"
            title="网络上传封面"
            width="520px"
            @confirm="confirmRemoteCover"
        >
            <el-form label-width="88px" class="game-manage__form">
                <el-form-item label="图片地址">
                    <el-input
                        v-model="remoteCoverUrl"
                        placeholder="https://example.com/cover.png"
                        clearable
                    />
                </el-form-item>
                <p class="game-manage__file-hint muted">
                    支持 jpg、jpeg、png、gif、webp 图片直链。保存时才真正下载。
                </p>
            </el-form>
        </app-dialog>

        <!-- 详情弹窗：内容与游戏中心右键「详情」共用同一个组件 -->
        <game-detail-dialog v-model="detailVisible" :game-id="detailId" />

        <!-- 图集管理：叠在编辑弹框之上的另一层，所以放在它外面（同为根节点） -->
        <gallery-manager-dialog v-model="galleryManagerVisible" :game-id="editingId" />

        <app-dialog v-model="importVisible" title="搬运游戏" width="560px">
            <div class="game-import">
                <div class="game-import__field">
                    <label class="game-import__label" for="game-import-url">游戏页地址</label>
                    <div class="game-import__form">
                        <el-input
                            id="game-import-url"
                            v-model="importUrl"
                            clearable
                            :disabled="importing"
                            @keyup.enter="onImport"
                        />
                        <app-button type="primary" :loading="importing" @click="onImport">搬运</app-button>
                    </div>
                    <div class="game-import__example">
                        <span class="game-import__example-label">示例</span>
                        <div class="game-import__example-list">
                            <div class="game-import__example-item">
                                <span class="game-import__example-site">7k7k</span>
                                <code>https://www.7k7k.com/flash/205829.htm</code>
                            </div>
                            <div class="game-import__example-item">
                                <span class="game-import__example-site">4399</span>
                                <code>https://www.4399.com/flash/1172_1.htm</code>
                            </div>
                            <div class="game-import__example-item">
                                <span class="game-import__example-site">flash.homes</span>
                                <code>https://flash.homes/flash/F8YX-1DNE-JQG9</code>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="game-import__platforms">
                    <span class="game-import__platforms-label">前往游戏平台查找</span>
                    <div class="game-import__platform-list">
                        <a
                            class="game-import__platform"
                            href="https://www.7k7k.com"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <span class="game-import__platform-badge game-import__platform-badge--7k7k">7k7k</span>
                            <span class="game-import__platform-name">7k7k 小游戏</span>
                        </a>
                        <a
                            class="game-import__platform"
                            href="https://www.4399.com"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <span class="game-import__platform-badge game-import__platform-badge--4399">4399</span>
                            <span class="game-import__platform-name">4399 小游戏</span>
                        </a>
                        <a
                            class="game-import__platform"
                            href="https://flash.homes/flash"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <span class="game-import__platform-badge game-import__platform-badge--flashhomes">
                                flash
                            </span>
                            <span class="game-import__platform-name">flash.homes</span>
                        </a>
                    </div>
                </div>
            </div>
            <template #footer>
                <app-button :disabled="importing" @click="importVisible = false">关闭</app-button>
            </template>
        </app-dialog>
    </div>
</template>

<script setup>
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import AppDialog from "@components/common/AppDialog.vue";
import CopyButton from "@components/common/CopyButton.vue";
import GameDetailDialog from "@components/games/GameDetailDialog.vue";
import GalleryManagerDialog from "@components/games/GalleryManagerDialog.vue";
import ImageUploadButton from "@components/games/ImageUploadButton.vue";
import {
    createManageGameAPI,
    deleteManageGameAPI,
    gamesStatusAPI,
    getManageGameAPI,
    importGameAPI,
    listManageGamesAPI,
    updateManageGameAPI,
    uploadGalleryAPI,
    uploadGameAssetAPI,
    uploadGuideAPI,
} from "@/api/games";
import {
    CARTRIDGE_TYPE_DEFAULT,
    cartridgeTypesFor,
    sortedCartridgeTypes,
} from "@/constants/cartridgeTypes";
import {
    ALL_GAME_EXTENSIONS,
    gameTypeByExtension,
    gameTypeLabel as typeLabel,
} from "@/constants/gameTypes";
import { ensureGameAssetSw, gameCoverUrl } from "@/utils/gameAssetCache";

const loading = ref(false);
const saving = ref(false);
const items = ref([]);
const gameTypes = ref(["flash"]);
const bodyExtensions = ref(ALL_GAME_EXTENSIONS);

const filterType = ref("");
const filterKeyword = ref("");
let keywordTimer = null;

const formVisible = ref(false);
const formMode = ref("create");
const editingId = ref(null);
const editingItem = ref(null);
const gameFileRef = ref(null);
const coverFileRef = ref(null);
const guideDirRef = ref(null);
// 攻略：只在编辑弹框出现；整目录选好后先存着，点「保存」才一次性提交
const guideFiles = ref([]);
const form = reactive({
    name: "",
    cartridgeId: "",
    cartridgeType: CARTRIDGE_TYPE_DEFAULT,
    description: "",
    gameFile: null,
    coverFile: null,
    // 网络上传：与上面的本地文件二选一，真正下载在点「保存」时才发生
    bodyUrl: "",
    bodyGameType: "",
    coverUrl: "",
});

// 图集管理弹框（编辑弹框里的「图集 → 管理」打开；按游戏共享，保存即生效）
const galleryManagerVisible = ref(false);

// 网络上传的两个小弹框：本体要连类型一起选，封面只要地址
const remoteBodyVisible = ref(false);
const remoteBody = reactive({ url: "", gameType: "" });
const remoteCoverVisible = ref(false);
const remoteCoverUrl = ref("");

// 封面允许的图片扩展名（与后端 _COVER_EXTENSIONS 一致）
const COVER_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp"];
// 攻略文件数上限：与后端 _GUIDE_MAX_FILES 及 Starlette 单次表单解析上限一致
const GUIDE_MAX_FILES = 1000;

// 封面预览：刚选的封面用本地 objectURL 即时显示（提交前先看效果），否则显示该游戏当前封面。
// objectURL 要显式回收：换文件、重开弹窗、离开页面时都清掉。
const coverPreviewUrl = ref("");

function releaseCoverPreview() {
    if (coverPreviewUrl.value) {
        URL.revokeObjectURL(coverPreviewUrl.value);
        coverPreviewUrl.value = "";
    }
}

const coverPreview = computed(() => {
    if (coverPreviewUrl.value) {
        return { src: coverPreviewUrl.value, caption: "新封面（保存后生效）" };
    }
    const url = gameCoverUrl(editingItem.value);
    return url ? { src: url, caption: "当前封面" } : null;
});

// 详情弹窗（内容见 components/games/GameDetailDialog.vue，游戏中心右键也用它）
const detailVisible = ref(false);
const detailId = ref(null);

const importVisible = ref(false);
const importUrl = ref("");
const importing = ref(false);

// 本体来源：本地文件优先，其次是网络直链（直链的类型由用户在弹框里选）。
// 本地文件按扩展名识别、直链以所选类型为准，落库类型最终都由后端按扩展名判定。
const bodySourceType = computed(() => {
    if (form.gameFile) {
        return gameTypeByExtension(form.gameFile.name);
    }
    if (form.bodyUrl) {
        return form.bodyGameType || null;
    }
    return null;
});
const hasBodySource = computed(() => Boolean(form.gameFile || form.bodyUrl));
const gameAccept = computed(() => bodyExtensions.value.join(","));

// 卡带类型的候选：按「这次保存后会落成的游戏类型」给——选了新本体就按新类型的扩展名，
// 否则用当前类型（编辑时）；都没有（新建还没选本体）就只剩「默认」。
// 顺序：「默认」固定第一，其余按取值字符串排（见 sortedCartridgeTypes）。
const effectiveGameType = computed(
    () => bodySourceType.value || editingItem.value?.game_type || ""
);
const cartridgeTypeOptions = computed(() =>
    sortedCartridgeTypes(cartridgeTypesFor(effectiveGameType.value))
);

// 类型变了（如编辑时改选成另一机种的本体）后，原来选的日版/美版可能不再合法，回落「默认」
watch(cartridgeTypeOptions, (options) => {
    if (!options.some((item) => item.value === form.cartridgeType)) {
        form.cartridgeType = CARTRIDGE_TYPE_DEFAULT;
    }
});
const typeFieldText = computed(() => {
    if (formMode.value === "create") {
        if (!hasBodySource.value) {
            return "选择本体文件或填写下载地址后确定";
        }
        return bodySourceType.value
            ? typeLabel(bodySourceType.value)
            : "无法识别该格式，请更换本体文件";
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
        : `${currentLabel} → ${typeLabel(bodySourceType.value)}（保存后切换）`;
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

/** 地址能认出的游戏类型；认不出（没扩展名或是没收录的格式）返回 null。 */
function gameTypeOfUrl(url) {
    const name = basenameOfUrl(url);
    return name ? gameTypeByExtension(name) : null;
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

function formatDateTime(value) {
    if (!value) {
        return "—";
    }
    // 后端给的是 ISO（带 +00:00）：空格分隔、去掉时区后缀，并砍掉毫秒——只展示到秒
    return value
        .replace("T", " ")
        .replace(/\.\d+/, "")
        .replace(/\+00:00$/, "");
}

// 列表里展开的那条描述（同时只展开一条）。列表重新加载后行会换掉，顺手收起来。
const expandedDescId = ref(null);

/** 单击描述：被省略（或已展开）才展开/收起；整段都看得见时不响应，免得白点一下。 */
function toggleDesc(event, id) {
    if (expandedDescId.value === id) {
        collapseDesc();
        return;
    }
    const el = event.currentTarget;
    if (el.scrollWidth <= el.clientWidth + 1) {
        return;
    }
    expandedDescId.value = id;
}

function collapseDesc() {
    expandedDescId.value = null;
}

async function reload() {
    loading.value = true;
    // 换了一批行，之前展开的那条描述跟着收起来
    expandedDescId.value = null;
    try {
        const params = {};
        if (filterType.value) {
            params.game_type = filterType.value;
        }
        if (filterKeyword.value.trim()) {
            params.q = filterKeyword.value.trim();
        }
        items.value = await listManageGamesAPI(params);
    } finally {
        loading.value = false;
    }
}

function onKeywordInput() {
    clearTimeout(keywordTimer);
    keywordTimer = setTimeout(() => {
        reload();
    }, 300);
}

function clearGameFile() {
    form.gameFile = null;
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

function resetForm() {
    form.name = "";
    form.cartridgeId = "";
    form.cartridgeType = CARTRIDGE_TYPE_DEFAULT;
    form.description = "";
    clearGameFile();
    clearCoverFile();
    clearGuideDir();
    clearRemoteBody();
    form.coverUrl = "";
    remoteBody.url = "";
    remoteBody.gameType = "";
    remoteCoverUrl.value = "";
    galleryManagerVisible.value = false;
    releaseCoverPreview();
    editingId.value = null;
    editingItem.value = null;
}

function openCreate() {
    resetForm();
    formMode.value = "create";
    formVisible.value = true;
}

async function openEdit(id) {
    resetForm();
    formMode.value = "edit";
    editingId.value = id;
    editingItem.value = await getManageGameAPI(id);
    form.name = editingItem.value.name;
    form.description = editingItem.value.description;
    form.cartridgeType = editingItem.value.cartridge_type || CARTRIDGE_TYPE_DEFAULT;
    formVisible.value = true;
}

function openDetail(id) {
    detailId.value = id;
    detailVisible.value = true;
}

function openImport() {
    importUrl.value = "";
    importVisible.value = true;
}

async function onImport() {
    const url = importUrl.value.trim();
    if (!url) {
        ElMessage.warning("请填写要搬运的游戏地址");
        return;
    }
    importing.value = true;
    try {
        // 服务端要解析页面并下载全部资源，耗时较长，按钮保持 loading 即可
        const item = await importGameAPI(url);
        ElMessage.success(`已搬运「${item.name}」`);
        importVisible.value = false;
        await reload();
    } catch (err) {
        // 拦截器已经弹过提示，只有它没弹（如本地抛错）时才补一次
        if (!err.reported) ElMessage.error(err.message || "搬运失败");
    } finally {
        importing.value = false;
    }
}

// 「本地上传」按钮代点隐藏的原生文件选择器（原生按钮没法套用站内按钮样式）
function pickBodyFile() {
    gameFileRef.value?.click();
}

function pickCoverFile() {
    coverFileRef.value?.click();
}

function onGameFileChange(event) {
    form.gameFile = event.target.files?.[0] || null;
    if (form.gameFile) {
        // 本地文件与网络地址二选一
        clearRemoteBody();
    }
}

function onCoverFileChange(event) {
    form.coverFile = event.target.files?.[0] || null;
    if (form.coverFile) {
        form.coverUrl = "";
    }
    releaseCoverPreview();
    if (form.coverFile) {
        coverPreviewUrl.value = URL.createObjectURL(form.coverFile);
    }
}

function pickGuideDir() {
    guideDirRef.value?.click();
}

/** 剥掉 webkitRelativePath 的首段（选中的文件夹本身），只留文件夹内的相对路径 */
function guideRelPath(file) {
    const parts = (file.webkitRelativePath || "").split("/").filter(Boolean);
    return (parts.length > 1 ? parts.slice(1) : parts).join("/");
}

const guideHasEntry = computed(() =>
    guideFiles.value.some((file) => guideRelPath(file).toLowerCase() === "index.html"),
);

function onGuideDirChange(event) {
    const files = Array.from(event.target.files || []);
    // 拿不到 webkitRelativePath 时拼不出目录结构（子目录会被压平），宁可拒收
    if (files.length && !files.some((file) => file.webkitRelativePath)) {
        ElMessage.warning("无法读取文件夹结构，请用「选择文件夹」重新选择");
        clearGuideDir();
        return;
    }
    guideFiles.value = files;
}

function clearGuideDir() {
    guideFiles.value = [];
    if (guideDirRef.value) {
        guideDirRef.value.value = "";
    }
}

function openRemoteBody() {
    remoteBody.url = form.bodyUrl;
    // 地址能看出类型就先替用户选上，看不出再让他自己挑
    remoteBody.gameType = form.bodyGameType || gameTypeOfUrl(remoteBody.url) || "";
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
        ElMessage.warning("请选择游戏类型");
        return;
    }
    // 地址能认出类型时先在前端拦一道，提示里能带上中文类型名；后端还会再校验一次
    const detected = gameTypeOfUrl(url);
    if (detected && detected !== remoteBody.gameType) {
        ElMessage.warning(
            `该地址是「${typeLabel(detected)}」，与所选类型「${typeLabel(remoteBody.gameType)}」不符`,
        );
        return;
    }
    form.bodyUrl = url;
    form.bodyGameType = remoteBody.gameType;
    clearGameFile();
    remoteBodyVisible.value = false;
}

/** 地址里能看出类型就在还没选时替用户选上；已经选过的不动（改由下面的冲突校验管）。 */
function syncRemoteType() {
    const detected = gameTypeOfUrl(remoteBody.url);
    if (detected && !remoteBody.gameType) {
        remoteBody.gameType = detected;
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
    form.coverUrl = url;
    clearCoverFile();
    remoteCoverVisible.value = false;
}

async function uploadAsset(gameId, kind, { file = null, url = "", gameType = "" }) {
    const data = new FormData();
    data.append("kind", kind);
    if (file) {
        data.append("file", file);
    }
    if (url) {
        data.append("url", url);
        data.append("game_type", gameType);
    }
    await uploadGameAssetAPI(gameId, data);
}

/** 一次性提交整个攻略文件夹：files 与 paths 顺序严格对位（后端按下标配对） */
async function uploadGuide(gameId) {
    const data = new FormData();
    const paths = [];
    for (const file of guideFiles.value) {
        // 必须先 push path 再 append file，两边下标才对得上，顺序不能拆开写
        paths.push(guideRelPath(file));
        data.append("files", file);
    }
    data.append("paths", JSON.stringify(paths));
    await uploadGuideAPI(gameId, data);
}

async function onCreate() {
    // 类型由后端按本体文件名（或直链 + 所选类型）判定，这里只挡住明显无意义的提交
    const data = new FormData();
    data.append("name", form.name);
    data.append("cartridge_id", form.cartridgeId);
    data.append("cartridge_type", form.cartridgeType);
    data.append("description", form.description);
    if (form.gameFile) {
        data.append("file", form.gameFile);
    }
    if (form.bodyUrl) {
        data.append("body_url", form.bodyUrl);
        data.append("body_game_type", form.bodyGameType);
    }
    if (form.coverFile) {
        data.append("cover", form.coverFile);
    }
    if (form.coverUrl) {
        data.append("cover_url", form.coverUrl);
    }
    await createManageGameAPI(data);
}

async function onSave() {
    if (!form.name.trim()) {
        ElMessage.warning("请填写游戏名称");
        return;
    }
    if (formMode.value === "create") {
        if (!form.cartridgeId.trim()) {
            ElMessage.warning("请填写卡带 ID");
            return;
        }
        if (!hasBodySource.value) {
            ElMessage.warning("请选择游戏本体文件，或点「网络上传」填下载地址");
            return;
        }
        if (!bodySourceType.value) {
            ElMessage.warning("无法识别游戏本体格式，请更换文件或检查下载地址");
            return;
        }
    } else if (guideFiles.value.length) {
        if (!guideHasEntry.value) {
            ElMessage.warning("攻略根目录必须包含 index.html");
            return;
        }
        if (guideFiles.value.length > GUIDE_MAX_FILES) {
            ElMessage.warning(`攻略文件不能超过 ${GUIDE_MAX_FILES} 个`);
            return;
        }
    }

    saving.value = true;
    try {
        if (formMode.value === "create") {
            await onCreate();
        } else {
            await updateManageGameAPI(editingId.value, {
                name: form.name,
                description: form.description,
                cartridge_type: form.cartridgeType,
            });
            if (form.gameFile || form.bodyUrl) {
                await uploadAsset(editingId.value, "game", {
                    file: form.gameFile,
                    url: form.bodyUrl,
                    gameType: form.bodyGameType,
                });
            }
            if (form.coverFile || form.coverUrl) {
                await uploadAsset(editingId.value, "cover", {
                    file: form.coverFile,
                    url: form.coverUrl,
                });
            }
            if (guideFiles.value.length) {
                // 排在换本体之后：同一次保存里换了类型的，攻略要落到新类型目录
                await uploadGuide(editingId.value);
            }
        }
        ElMessage.success(formMode.value === "create" ? "游戏已添加" : "游戏已更新");
        formVisible.value = false;
        await reload();
    } catch (err) {
        if (!err.reported) ElMessage.error(err.message || "保存失败");
    } finally {
        saving.value = false;
    }
}

// 删除确认的正文：警示文案下面再单列一行卡带ID（带复制按钮）。要手打的确认串就是它，
// 摆在眼前省得用户先去别处抄一遍。message 传 VNode 渲染，这条弹框挂在 body 下，
// 拿不到组件的 scoped 样式，所以它的样式写在 styles/index.css 里。
function buildDeleteMessage(item) {
    return h("div", null, [
        h(
            "p",
            { class: "game-manage__delete-confirm-text" },
            `确定删除游戏「${item.name}」？此操作会同时删掉该游戏在磁盘上的全部文件，` +
                "以及所有账号在它上面的云端存档，且无法撤销。",
        ),
        h("div", { class: "game-manage__delete-confirm-id" }, [
            h("span", { class: "game-manage__delete-confirm-label" }, "卡带 ID"),
            h("span", { class: "game-manage__delete-confirm-value" }, item.cartridge_id),
            h(CopyButton, { text: item.cartridge_id }),
        ]),
    ]);
}

// 删游戏会连磁盘文件与所有账号在该游戏上的云端存档一起清掉，且不可撤销，
// 所以要求手打一次卡带ID——它建后不可改，是最不会认错游戏的那个标识。
async function onDelete(item) {
    try {
        await ElMessageBox.prompt(buildDeleteMessage(item), "删除确认", {
            type: "warning",
            confirmButtonText: "删除",
            cancelButtonText: "取消",
            confirmButtonClass: "el-button--danger",
            inputPlaceholder: `输入卡带 ID「${item.cartridge_id}」以确认`,
            inputValidator: (value) =>
                String(value || "").trim().toUpperCase() === item.cartridge_id ||
                `请输入卡带 ID「${item.cartridge_id}」以确认`,
        });
    } catch {
        return;
    }
    try {
        await deleteManageGameAPI(item.id);
        ElMessage.success("已删除");
        await reload();
    } catch (err) {
        if (!err.reported) ElMessage.error(err.message || "删除失败");
    }
}

onMounted(async () => {
    loading.value = true;
    try {
        await ensureGameAssetSw();
        const status = await gamesStatusAPI();
        gameTypes.value = status.game_types?.length ? status.game_types : ["flash"];
        bodyExtensions.value = status.body_extensions?.length
            ? status.body_extensions
            : ALL_GAME_EXTENSIONS;
        await reload();
    } finally {
        loading.value = false;
    }
});

onBeforeUnmount(releaseCoverPreview);
</script>

<style scoped>
.game-manage__toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    align-items: center;
}

.game-manage__filter-type {
    /* 足够放下最长的类型名（如 “Sega_Master_System”），避免选中值被截断 */
    width: 240px;
}

.game-manage__filter-keyword {
    width: 240px;
}

.game-manage__actions {
    margin-left: auto;
}

.game-manage__table-wrap {
    min-height: 200px;
}

/* 固定布局 + 百分比列宽：列宽只跟表格宽度走，跟内容长短无关，
   所以再长的名称/描述也只在自己格子里省略，表格永远不会被撑宽（页面不会出水平滚动条）。
   注意别在这里加 overflow: hidden——展开的描述要能盖到表格外面去 */
.game-manage__table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}

/* 没有 overflow 兜底，四角靠表头/末行的圆角自己收（表头有底色，方角会顶出表格圆角） */
.game-manage__table thead th:first-child {
    border-top-left-radius: 11px;
}

.game-manage__table thead th:last-child {
    border-top-right-radius: 11px;
}

.game-manage__table tbody tr:last-child td:first-child {
    border-bottom-left-radius: 11px;
}

.game-manage__table tbody tr:last-child td:last-child {
    border-bottom-right-radius: 11px;
}

/* 百分比之和正好 100%：表格永远等于内容区宽度，不会撑出水平滚动条。
   各列的百分比是按「最窄也要放得下」定的（如更新时间那串固定 19 个字） */
.game-manage__col-cover {
    width: 10%;
}

/* 操作列按三个按钮的实际需要给宽（按钮左对齐，正好从左铺到列尾，右边不留空），
   省下的宽度都给名称列 */
.game-manage__col-name {
    width: 32%;
}

.game-manage__col-type {
    width: 13%;
}

.game-manage__col-size {
    width: 8%;
}

.game-manage__col-time {
    width: 18%;
}

.game-manage__col-actions {
    width: 19%;
}

/* 窗口再窄，19% 就装不下那三个按钮了（会折成两行）：
   这里把操作列加回来一点，名称列让出同样的数 */
@media (max-width: 1240px) {
    .game-manage__col-name {
        width: 29%;
    }

    .game-manage__col-actions {
        width: 22%;
    }
}

.game-manage__table th,
.game-manage__table td {
    padding: 12px 14px;
    border-bottom: 1px solid #f1f5f9;
    text-align: left;
    vertical-align: middle;
}

/* 除名称列外都只占一行，超长（如 Sega_Master_System）就地省略 */
.game-manage__nowrap {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

.game-manage__table th {
    background: #f8fafc;
    font-size: 13px;
    color: #64748b;
    font-weight: 600;
}

/* 封面缩略图：常规宽度下就是 72×48；单元格被挤窄时等比缩小，绝不撑破格子 */
.game-manage__cover {
    width: 100%;
    max-width: 72px;
    aspect-ratio: 3 / 2;
    overflow: hidden;
    background: #f8fafc;
    display: flex;
    align-items: center;
    justify-content: center;
}

.game-manage__cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.game-manage__cover-fallback {
    font-size: 24px;
}

/* 名称列：整格是展开描述的定位基准 */
.game-manage__desc-cell {
    position: relative;
}

.game-manage__name {
    font-weight: 600;
    color: #0f172a;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

/* 字号/行高/颜色要和展开那层完全一致，否则一切换文字会跳一下 */
.game-manage__desc {
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.7;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: pointer;
}

/* 展开的那一层：钉在收起那行的位置上往下铺，白底 + 投影盖住下面的行。
   left/right 取单元格的内边距（14px），文字才和收起的描述对齐 */
.game-manage__desc-panel {
    position: absolute;
    top: 38px;
    left: 14px;
    right: 14px;
    z-index: 3;
    padding-bottom: 10px;
    font-size: 12px;
    line-height: 1.7;
    color: #64748b;
    word-break: break-all;
    background: #fff;
    border-radius: 0 0 8px 8px;
    box-shadow: 0 10px 18px rgba(15, 23, 42, 0.12);
    cursor: pointer;
}

/* 三个操作按钮左对齐（和「操作」表头对齐）；列宽按它们的实际宽度给，
   所以删除右边也不会剩下大片空白 */
.game-manage__row-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.game-manage__form {
    padding-top: 4px;
}

/* 添加/编辑弹窗：左栏放元数据、右栏放两个上传，两栏等宽 */
.game-manage__form-cols {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 0 24px;
}

.game-manage__form-col {
    min-width: 0;
}

.game-manage__file-hint {
    margin: 8px 0 0;
    font-size: 12px;
    color: #64748b;
}

.game-manage__file-hint.muted {
    color: #94a3b8;
}

/* 选了文件但还不合规时的提醒（缺 index.html、超过文件数上限） */
.game-manage__file-warn {
    color: #d97706;
}

/* 本体/封面的来源行：「本地上传」与「网络上传」两个同款按钮并排 */
.game-manage__source {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    width: 100%;
}

/* 原生文件选择器藏起来（样式没法统一），只由「本地上传」按钮代点 */
.game-manage__file-input {
    display: none;
}

/* 描述框：高度交给 rows（不拖拽缩放），底部留出字数统计那一行的位置，免得压住最后一行 */
.game-manage__desc-input :deep(.el-textarea__inner) {
    padding-bottom: 22px;
}

/* 「待上传」那行里的清除：做成行内文字按钮，不抢视线 */
.game-manage__clear {
    margin-left: 6px;
    padding: 0;
    border: 0;
    background: none;
    font-size: 12px;
    color: #2563eb;
    cursor: pointer;
}

.game-manage__clear:hover {
    text-decoration: underline;
}

.game-manage__remote-select {
    width: 100%;
}

/* 卡带类型的单选项里只有国旗（22×16 原尺寸），与单选圆点垂直居中对齐 */
.game-manage__cartridge-flag {
    display: block;
    width: 22px;
    height: 16px;
}

.game-manage__form :deep(.el-radio) {
    margin-right: 20px;
    align-items: center;
}

.game-manage__form :deep(.el-radio__label) {
    display: inline-flex;
    align-items: center;
}

.game-manage__type-value {
    font-size: 13px;
    color: #0f172a;
}

/* 编辑弹窗里的封面预览：整图完整展示（contain 不裁切），便于确认选的图对不对。
   el-form-item__content 是 flex 行，width: 100% 让它独占一行，落在「当前：…」
   那行封面路径的下面，并靠左对齐。 */
.game-manage__cover-preview {
    margin-top: 10px;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
}

.game-manage__cover-preview img {
    width: 168px;
    height: 120px;
    object-fit: contain;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
}

.game-manage__cover-preview-tip {
    font-size: 12px;
    color: #94a3b8;
}

/* 卡带 ID 与 CRC32 的值：窄了就省略 */
.game-manage__detail-key {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* 搬运游戏弹窗 */
.game-import__field {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.game-import__label {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
}

.game-import__form {
    display: flex;
    align-items: center;
    gap: 10px;
}

.game-import__form :deep(.el-input) {
    flex: 1;
    min-width: 0;
}

.game-import__form :deep(.el-input__wrapper) {
    border-radius: 10px;
}

.game-import__example {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.game-import__example-label {
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
}

.game-import__example-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 12px;
    border: 1px solid #eef2f7;
    border-radius: 10px;
    background: #f8fafc;
}

.game-import__example-item {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    font-size: 12px;
}

.game-import__example-site {
    flex-shrink: 0;
    width: 76px;
    font-weight: 600;
    color: #64748b;
}

.game-import__example-item code {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #475569;
    font-family: inherit;
}

@media (max-width: 520px) {
    .game-import__example-item {
        flex-direction: column;
        align-items: flex-start;
        gap: 2px;
    }

    /* 窄屏放不下三个平台块，改为竖排 */
    .game-import__platform-list {
        grid-template-columns: 1fr;
    }

    .game-import__platform {
        justify-content: flex-start;
    }
}

.game-import__platforms {
    margin-top: 22px;
    padding-top: 18px;
    border-top: 1px solid #eef2f7;
}

.game-import__platforms-label {
    display: block;
    margin-bottom: 12px;
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
}

.game-import__platform-list {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
}

.game-import__platform {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-width: 0;
    padding: 10px 12px;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    background: #fff;
    text-decoration: none;
    transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.game-import__platform:hover {
    border-color: #bfdbfe;
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.08);
    transform: translateY(-1px);
}

.game-import__platform-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 9px;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
}

.game-import__platform-badge--7k7k {
    background: linear-gradient(135deg, #fb923c, #ea580c);
}

.game-import__platform-badge--4399 {
    background: linear-gradient(135deg, #60a5fa, #2563eb);
}

/* flash.homes 的徽标字比 7k7k / 4399 长，单独缩一号字 */
.game-import__platform-badge--flashhomes {
    background: linear-gradient(135deg, #2dd4bf, #0f766e);
    font-size: 10px;
    letter-spacing: 0;
}

.game-import__platform-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
    font-weight: 600;
    color: #0f172a;
}
</style>
