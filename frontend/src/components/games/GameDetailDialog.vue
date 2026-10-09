<template>
    <app-dialog
        :model-value="modelValue"
        title="游戏详情"
        width="min(810px, 96vw)"
        align-center
        confirm-text="关闭"
        @update:model-value="emit('update:modelValue', $event)"
        @confirm="emit('update:modelValue', false)"
    >
        <div v-if="detail" class="game-detail">
            <!-- 图片栏：封面（共享）恒占第一格，其后是图集与本人的截图，可左右翻页 -->
            <game-screenshot-gallery
                :cover-url="gameCoverUrl(detail)"
                :cover-alt="detail.name"
                :gallery="galleryImages"
                :screenshots="screenshots"
            />
            <dl>
                <div><dt>名称</dt><dd>{{ detail.name }}</dd></div>
                <div>
                    <dt>卡带 ID</dt>
                    <dd>
                        <span class="game-detail__key">{{ detail.cartridge_id }}</span>
                    </dd>
                </div>
                <div><dt>类型</dt><dd>{{ typeLabel(detail.game_type) }}</dd></div>
                <div>
                    <dt>卡带类型</dt>
                    <!-- 只给国旗，不叠文字：alt 里带中文名，读屏与图挂掉时仍有意义 -->
                    <dd>
                        <img
                            class="game-detail__flag"
                            :src="cartridgeTypeFlag(detail.cartridge_type)"
                            :alt="cartridgeTypeLabel(detail.cartridge_type)"
                        />
                    </dd>
                </div>
                <div><dt>大小</dt><dd>{{ formatSize(detail.size) }}</dd></div>
                <div>
                    <dt>CRC32</dt>
                    <dd>
                        <span v-if="detail.crc32" class="game-detail__key">{{ detail.crc32 }}</span>
                        <span v-else>—</span>
                    </dd>
                </div>
                <!-- 截图这一行让右栏也填满 6 行（原 11 条里右下角空着一格）；
                     「上传」是快捷入口：选完图直接入库，不必先进管理弹框 -->
                <div>
                    <dt>截图</dt>
                    <dd class="game-detail__actions">
                        <image-upload-button
                            :game-id="props.gameId"
                            :upload="uploadScreenshotAPI"
                            @uploaded="reloadScreenshots"
                        />
                        <app-button @click="screenshotManagerVisible = true">管理</app-button>
                    </dd>
                </div>
                <div>
                    <dt>描述</dt>
                    <!-- 收起的这一行照旧留在流里撑住行高；展开的整段是绝对定位的另一层，
                         盖在它上面往下铺，所以不会把下面的条目顶走。
                         展开/折叠都由单击描述本身触发，点别处不动。
                         展开层放在 dd 里面（dd 自己不裁切，裁切的是里面那行文字），
                         这样它永远钉在文字起点的同一位置，行高怎么变都对齐 -->
                    <dd class="game-detail__desc-cell">
                        <span
                            class="game-detail__desc"
                            :class="{ 'is-clickable': detail.description }"
                            @click="toggleDesc($event)"
                        >
                            {{ detail.description || "—" }}
                        </span>
                        <div
                            v-if="descExpanded"
                            class="game-detail__desc-panel"
                            @click="descExpanded = false"
                        >
                            {{ detail.description }}
                        </div>
                    </dd>
                </div>
                <!-- 这两条只给下载入口，不摆磁盘路径（路径是内部实现细节） -->
                <div>
                    <dt>本体</dt>
                    <dd>
                        <app-button v-if="detail.game_path" @click="downloadGame">
                            下载
                        </app-button>
                        <span v-else>—</span>
                    </dd>
                </div>
                <div>
                    <dt>封面</dt>
                    <dd>
                        <app-button v-if="detail.cover_path" @click="downloadCover">
                            下载
                        </app-button>
                        <span v-else>—</span>
                    </dd>
                </div>
                <div><dt>创建时间</dt><dd>{{ formatDateTime(detail.created_at) }}</dd></div>
                <div><dt>更新时间</dt><dd>{{ formatDateTime(detail.updated_at) }}</dd></div>
            </dl>
        </div>
    </app-dialog>

    <!-- 截图管理是叠在详情之上的另一层弹框，所以放在详情弹框外面（同为根节点） -->
    <screenshot-manager-dialog
        v-model="screenshotManagerVisible"
        :game-id="props.gameId"
        @changed="reloadScreenshots"
    />
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
    coverDownloadPath,
    gameDownloadPath,
    getManageGameAPI,
    listGalleryAPI,
    listScreenshotsAPI,
    uploadScreenshotAPI,
} from "@/api/games";
import { cartridgeTypeFlag, cartridgeTypeLabel } from "@/constants/cartridgeTypes";
import { gameTypeLabel as typeLabel } from "@/constants/gameTypes";
import AppDialog from "@components/common/AppDialog.vue";
import GameScreenshotGallery from "@components/games/GameScreenshotGallery.vue";
import ImageUploadButton from "@components/games/ImageUploadButton.vue";
import ScreenshotManagerDialog from "@components/games/ScreenshotManagerDialog.vue";
import { gameCoverUrl } from "@/utils/gameAssetCache";
import { downloadViaPath } from "@/utils/download";

// 游戏详情弹窗：游戏中心（右键「详情」）与游戏管理（列表「详情」按钮）共用同一份内容。
// 字段比中心列表多，所以打开时按 id 现取一次 /api/games/manage/{id}。
const props = defineProps({
    modelValue: { type: Boolean, default: false },
    gameId: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue"]);

const detail = ref(null);

// 本人该游戏的截图与共享图集（图片栏用；封面是共享的，走 gameCoverUrl）
const screenshots = ref([]);
const galleryImages = ref([]);
const screenshotManagerVisible = ref(false);

// 描述是否展开：每次打开都从收起开始；只由「单击描述」切换，点别处不折叠
const descExpanded = ref(false);

watch(
    () => props.modelValue,
    async (visible) => {
        if (!visible) {
            return;
        }
        descExpanded.value = false;
        detail.value = null;
        screenshots.value = [];
        galleryImages.value = [];
        screenshotManagerVisible.value = false;
        if (!props.gameId) {
            return;
        }
        // 详情、截图、图集并行取；后两者失败只丢图片栏，不挡住详情展示
        const detailTask = getManageGameAPI(props.gameId).then(
            (value) => {
                detail.value = value;
            },
            (err) => {
                // 拦截器已经弹过中文提示了，这里只兜一层没报过的
                if (!err?.reported) {
                    ElMessage.error("游戏详情加载失败，请稍后重试。");
                }
            }
        );
        await Promise.all([detailTask, reloadScreenshots(), reloadGallery()]);
    },
    { immediate: true }
);

/** 拉取共享图集（只读展示；管理入口在游戏管理页的编辑弹框里）。 */
async function reloadGallery() {
    if (!props.gameId) {
        galleryImages.value = [];
        return;
    }
    try {
        galleryImages.value = (await listGalleryAPI(props.gameId)) || [];
    } catch {
        // 错误提示已由请求层 toast
        galleryImages.value = [];
    }
}

/** 重新拉取本人该游戏的截图（管理弹框里改过之后由 @changed 触发）。 */
async function reloadScreenshots() {
    if (!props.gameId) {
        screenshots.value = [];
        return;
    }
    try {
        screenshots.value = (await listScreenshotsAPI(props.gameId)) || [];
    } catch {
        // 错误提示已由请求层 toast
        screenshots.value = [];
    }
}

/** 单击描述：被截断（或已展开）才展开/收起；一行就放得下时点了不动，免得白点一下。 */
function toggleDesc(event) {
    if (descExpanded.value) {
        descExpanded.value = false;
        return;
    }
    const el = event.currentTarget;
    const clamped = el.scrollWidth > el.clientWidth + 1;
    if (!clamped) {
        return;
    }
    descExpanded.value = true;
}

function downloadGame() {
    downloadViaPath(gameDownloadPath(detail.value.id, detail.value.updated_at));
}

function downloadCover() {
    downloadViaPath(coverDownloadPath(detail.value.id, detail.value.updated_at));
}

/** 与游戏管理页同一套显示格式（那边列表也在用，所以各自留一份） */
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
</script>

<style scoped>
/* 条目区：固定 6 行、按列填充，12 条正好分成左右两栏各 6 行（第 1–6 条走左栏、
   第 7–12 条走右栏），不裁不滚；两栏行高成对对齐。
   两处都得是 minmax(0, 1fr)：默认的 1fr 最小是「内容最小宽度」，
   描述那行是 nowrap 的（最小宽度 = 整段文字），不加 0 会把右栏顶得比左栏宽 */
.game-detail dl {
    margin: 0;
    display: grid;
    grid-auto-flow: column;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-rows: repeat(6, auto);
    column-gap: 24px;
}

/* 每行等高：按下载按钮那行的高度定（按钮 32px + 上下内边距 7px），
   行内内容垂直居中，所以十行看起来是整齐的一格一格 */
.game-detail dl > div {
    min-width: 0;
    min-height: 46px;
    display: grid;
    align-items: center;
    grid-template-columns: 88px minmax(0, 1fr);
    gap: 8px;
    padding: 7px 0;
    border-bottom: 1px solid #f1f5f9;
}

/* 描述最长 200 字：收起时只占一行、放不下就截断，单击描述本身整段展开。
   展开的文本绝对定位、脱离排版，所以是「盖住」下面几行，既不撑高弹窗也不挤动别的条目；
   白底 + 投影让它压在下面内容之上看得出是浮起来的一层。
   （定位基准是这一格 dd，见下面的 panel） */
.game-detail__desc-cell {
    position: relative;
}

/* 有描述才给手型，空着的「—」不提示可点 */
.game-detail__desc.is-clickable {
    cursor: pointer;
}

/* 收起的那行与展开的整段必须是同一套字（字号/行高/颜色），否则一切换文字会跳 */
.game-detail__desc,
.game-detail__desc-panel {
    font-size: 13px;
    line-height: 1.6;
    color: #0f172a;
    word-break: break-all;
}

/* 就一行，放不下末尾省略：裁切放在这层，dd 自己不裁——
   否则绝对定位的展开层会被一起裁掉。判据是 scrollWidth 超出 clientWidth */
.game-detail__desc {
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* 钉在 dd 的左上角（= 收起那行文字的起点），行多高都对齐 */
.game-detail__desc-panel {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 2;
    padding-bottom: 8px;
    border-radius: 0 0 6px 6px;
    background: var(--el-dialog-bg-color, #fff);
    box-shadow: 0 10px 18px rgba(15, 23, 42, 0.12);
    cursor: pointer;
}

.game-detail dt {
    margin: 0;
    color: #64748b;
    font-size: 13px;
}

.game-detail dd {
    margin: 0;
    min-width: 0;
    color: #0f172a;
    font-size: 13px;
    word-break: break-all;
}

/* 一行里并排几个按钮（如「上传 + 管理」）：留出间距，垂直居中对齐 */
.game-detail__actions {
    display: flex;
    align-items: center;
    gap: 8px;
}

/* 卡带类型：原尺寸（22×16）显示国旗，不放大也不裁切 */
.game-detail__flag {
    display: block;
    width: 22px;
    height: 16px;
}

/* 卡带 ID 与 CRC32 的值：窄了就省略 */
.game-detail__key {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>
