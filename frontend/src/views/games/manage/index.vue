<template>
    <div class="game-manage">
        <!-- 页头顶部标签：结构与游戏发现一致，同款 AppSegmented；现在只有一个标签，
             以后新列表就从这里加。标签状态由 URL ?tab 驱动（同游戏发现） -->
        <app-segmented
            v-model="activeTab"
            class="game-manage__tabs"
            :options="TABS"
            size="lg"
            aria-label="游戏管理"
        />

        <!-- 游戏管理 -->
        <section class="game-manage__panel">
            <div class="game-manage__toolbar">
                <app-type-select
                    v-model="filterType"
                    placeholder="游戏类型"
                    clearable
                    class="game-manage__filter-type"
                    :options="typeFilterOptions"
                    @change="applyFilter"
                />
                <el-input
                    v-model="filterKeyword"
                    placeholder="搜索名称或描述"
                    clearable
                    class="game-manage__filter-keyword"
                    @input="onKeywordInput"
                    @clear="onKeywordClear"
                />
                <div class="game-manage__actions">
                    <app-button variant="secondary" @click="openBatchImport">批量导入</app-button>
                    <app-button variant="secondary" @click="openImport">搬运游戏</app-button>
                    <app-button variant="secondary" @click="openCreate">添加游戏</app-button>
                </div>
            </div>

            <div
                ref="tableWrapEl"
                v-loading="loading"
                class="game-manage__table-wrap"
                :style="{ height: tableWrapHeight }"
            >
                <table v-if="items.length" class="game-manage__table">
                    <!-- 列宽走百分比/定宽（见样式里的 table-layout: fixed）：内容再长也只在
                         格子里省略，表格永远不超出内容区，页面不会出现水平滚动条 -->
                    <thead>
                        <tr>
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
                                <app-truncatable-name>
                                    {{ item.name }}
                                    <!-- 名称被截断时展开层顺带给出描述：行高保持单行
                                         （40px 系），描述不再占列表行 -->
                                    <template #panel-extra>
                                        <div class="game-manage__panel-desc">
                                            {{ item.description }}
                                        </div>
                                    </template>
                                </app-truncatable-name>
                            </td>
                            <td class="game-manage__nowrap">{{ typeLabel(item.game_type) }}</td>
                            <td class="game-manage__nowrap">{{ formatSize(item.size) }}</td>
                            <td class="game-manage__nowrap">{{ formatDateTime(item.updated_at) }}</td>
                            <td>
                                <div class="game-manage__row-actions">
                                    <app-button
                                        variant="secondary"
                                        size="sm"
                                        @click="openDetail(item.id)"
                                    >
                                        详情
                                    </app-button>
                                    <app-button
                                        variant="secondary"
                                        size="sm"
                                        @click="openEdit(item.id)"
                                    >
                                        编辑
                                    </app-button>
                                    <app-button variant="danger" size="sm" @click="onDelete(item)">
                                        删除
                                    </app-button>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <app-empty v-else description="暂无游戏，点击「添加游戏」开始录入。" />
            </div>

            <!-- 翻页放在表格下面；只有一页时整块不渲染（AppPagination 自己判，左右键翻页也在它里面） -->
            <app-pagination
                v-model:page="page"
                :total="total"
                :page-size="pageSize"
                previous-shortcut="manage.page.prev"
                next-shortcut="manage.page.next"
                @change="reload"
            />
        </section>

        <!-- 添加/编辑游戏：左右两栏——左边元数据、右边两个上传；整窗居中且一页放得下（不滚动）。
             新建要等全部填完才建条目，底部保留「取消 / 保存」；
             编辑时每个字段改完即存、文件选完即传，没有保存按钮，只留右上角关闭。 -->
        <app-dialog
            v-model="formVisible"
            :title="formMode === 'create' ? '添加游戏' : '编辑游戏'"
            width="880px"
            align-center
            :footer-mode="formMode === 'create' ? 'default' : 'none'"
            :confirm-loading="saving"
            confirm-text="保存"
            @confirm="onSave"
        >
            <el-form label-width="88px" class="game-manage__form">
                <div class="game-manage__form-cols">
                    <div class="game-manage__form-col">
                        <!-- 编辑时把卡带ID摆到最上面：它既是磁盘目录名、又是这盘卡的身份。
                             值旁边给一个「修改 ID」：改它会连磁盘目录与各账号的存档/截图一起搬，
                             所以单独一次请求、保存即生效 -->
                        <el-form-item v-if="formMode === 'edit'" label="卡带 ID">
                            <div class="game-manage__cartridge">
                                <template v-if="!cartridgeEditing">
                                    <span class="game-manage__detail-key">
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
                                        class="game-manage__cartridge-input"
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
                                class="game-manage__desc-input"
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
                                class="game-manage__type-select"
                                :options="hasBodySource ? bodyTypeOptions : allTypeOptions"
                            />
                            <!-- 编辑：只有当前本体后缀有多个候选时才允许改类型 -->
                            <app-type-select
                                v-else-if="formMode === 'edit' && editingTypeCandidates.length > 1"
                                v-model="form.gameType"
                                :disabled="typeSaving"
                                class="game-manage__type-select"
                                :options="editingTypeOptions"
                                @change="onChangeGameType"
                            />
                            <span v-else class="game-manage__type-value">{{ typeFieldText }}</span>
                        </el-form-item>
                        <p v-if="bodyTypeHint" class="game-manage__file-hint muted">
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
                            <span v-if="editingItem?.crc32" class="game-manage__detail-key">
                                {{ editingItem.crc32 }}
                            </span>
                            <span v-else class="game-manage__file-hint muted">
                                尚未计算（上传或更换本体后写入）
                            </span>
                        </el-form-item>
                    </div>
                    <div class="game-manage__form-col">
                        <el-form-item label="游戏本体">
                            <!-- 两个来源做成同款按钮：原生文件选择器藏起来，由「本地上传」代点 -->
                            <div class="game-manage__source">
                                <input
                                    ref="gameFileRef"
                                    class="game-manage__file-input"
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
                                <p v-if="form.gameFiles.length" class="game-manage__file-hint">
                                    {{ bodyUploading || formMode === "edit" ? "正在上传：" : "已选：" }}{{ form.gameFiles.length }} 个文件，共 {{ formatSize(bodyFilesTotalSize) }}<template v-if="bodyUploading"> · {{ bodyProgress }}%</template>
                                </p>
                                <p v-else class="game-manage__file-hint">
                                    {{ bodyUploading || formMode === "edit" ? "正在上传：" : "已选：" }}{{ form.gameFile.name }}（{{ formatSize(form.gameFile.size) }}<template v-if="bodyUploading"> · {{ bodyProgress }}%</template>）
                                </p>
                                <p
                                    v-if="form.gameFiles.length"
                                    class="game-manage__file-hint muted"
                                >
                                    {{ form.gameFiles.map((file) => file.name).join("、") }}
                                </p>
                                <p
                                    v-if="form.gameFiles.length && bodyFilesTotalSize > 1024 * 1024 * 1024"
                                    class="game-manage__file-hint muted"
                                >
                                    多文件本体超过 1GB 时浏览器内存压力较大，世嘉 CD 建议优先用单个 .chd。
                                </p>
                                <el-progress
                                    v-if="bodyUploading"
                                    class="game-manage__upload-progress"
                                    :percentage="bodyProgress"
                                    :show-text="false"
                                    :stroke-width="4"
                                />
                            </template>
                            <!-- 网络来源与本地文件二选一：选了直链就把本地文件清掉（反之亦然） -->
                            <p v-else-if="form.bodyUrl" class="game-manage__file-hint">
                                待上传：{{ form.bodyUrl }}（{{ typeLabel(form.bodyGameType) }}）
                                <app-button text size="sm" @click="clearRemoteBody">
                                    清除
                                </app-button>
                            </p>
                            <p v-else-if="formMode === 'edit' && editingItem?.game_path" class="game-manage__file-hint muted">
                                当前：{{ editingItem.game_path }}
                            </p>
                            <p v-if="formMode === 'create' && !hasBodySource" class="game-manage__file-hint muted">
                                可稍后上传；未上传本体的游戏不会进入游玩页。
                            </p>
                        </el-form-item>
                        <el-form-item label="游戏封面">
                            <div class="game-manage__source">
                                <input
                                    ref="coverFileRef"
                                    class="game-manage__file-input"
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
                            <p v-if="form.coverFile" class="game-manage__file-hint">
                                {{ formMode === "edit" ? "正在上传：" : "已选：" }}{{ form.coverFile.name }}
                            </p>
                            <p v-else-if="form.coverUrl" class="game-manage__file-hint">
                                待上传：{{ form.coverUrl }}
                                <app-button text size="sm" @click="form.coverUrl = ''">
                                    清除
                                </app-button>
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
                                <app-button variant="secondary" @click="galleryManagerVisible = true">
                                    管理
                                </app-button>
                            </div>
                        </el-form-item>
                        <!-- 攻略：只在编辑时出现（新建还没有卡带目录可落）。上传 ZIP 或 PDF，选完立即上传 -->
                        <el-form-item v-if="formMode === 'edit'" label="游戏攻略">
                            <div class="game-manage__source">
                                <input
                                    ref="guideFileRef"
                                    class="game-manage__file-input"
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
                            <p v-if="guideUploading" class="game-manage__file-hint">
                                正在上传攻略…
                            </p>
                            <p v-else-if="editingItem?.has_guide" class="game-manage__file-hint muted">
                                当前：已有攻略（{{ editingItem.guide_kind === "pdf" ? "PDF" : "ZIP" }}，重新上传会整体替换）
                            </p>
                            <p v-else class="game-manage__file-hint muted">
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
                    <app-type-select
                        v-model="remoteBody.gameType"
                        placeholder="请选择游戏类型"
                        class="game-manage__remote-select"
                        :disabled="formMode === 'edit'"
                        :options="remoteTypeSelectOptions"
                    />
                </el-form-item>
                <p v-if="formMode === 'edit'" class="game-manage__file-hint muted">
                    编辑时只能更换同一游戏类型的本体（同类型后缀可互换：.gb ↔ .gbc、.sfc ↔ .smc、.md ↔ .gen）；
                    地址后缀属于其他类型会被拒绝。
                </p>
                <p v-else class="game-manage__file-hint muted">
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
            <el-form label-width="88px" class="game-manage__form">
                <el-form-item label="图片地址">
                    <el-input
                        v-model="remoteCoverUrl"
                        placeholder="https://example.com/cover.png"
                        clearable
                    />
                </el-form-item>
                <p class="game-manage__file-hint muted">
                    支持 jpg、jpeg、png、gif、webp 图片直链。{{ formMode === "edit" ? "确定后立即下载。" : "保存时才真正下载。" }}
                </p>
            </el-form>
        </app-dialog>

        <!-- 详情弹窗：内容与游戏中心右键「详情」共用同一个组件 -->
        <game-detail-dialog v-model="detailVisible" :game-id="detailId" />

        <!-- 图集管理：叠在编辑弹框之上的另一层，所以放在它外面（同为根节点） -->
        <gallery-manager-dialog v-model="galleryManagerVisible" :game-id="editingId" />

        <!-- 美化封面：同样叠在编辑弹框之上，确认后直接把合成图存成该游戏的新封面 -->
        <cover-beautify-dialog
            v-model="beautifyVisible"
            :game="editingItem"
            :confirm-loading="beautifySaving"
            @confirm="onBeautifyConfirm"
        />

        <app-dialog
            v-model="importVisible"
            title="搬运游戏"
            width="560px"
            footer-mode="none"
        >
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
                        <app-button variant="secondary" :loading="importing" @click="onImport">
                            搬运
                        </app-button>
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
        </app-dialog>

        <!-- 批量导入：目录根下的 meta.csv → 卡带ID / 名称 / 封面，逐条建无本体条目 -->
        <app-dialog
            v-model="batchImportVisible"
            title="批量导入"
            width="620px"
            footer-mode="none"
            :close-disabled="batchImporting"
        >
            <div class="game-batch">
                <p class="game-batch__tip">
                    选择游戏所在目录，读取目录根下的 meta.csv：第 2 列卡带 ID、第 3 列名称、第 4 列封面文件名。封面图片需与 meta.csv 在同一目录。
                </p>

                <div class="game-batch__field">
                    <span class="game-batch__label">游戏类型</span>
                    <app-type-select
                        v-model="batchImportType"
                        placeholder="请选择游戏类型"
                        class="game-batch__type"
                        :options="allTypeOptions"
                        :disabled="batchImporting"
                    />
                </div>

                <div class="game-batch__field">
                    <span class="game-batch__label">游戏目录</span>
                    <div class="game-batch__dir">
                        <input
                            ref="batchImportDirRef"
                            class="game-manage__file-input"
                            type="file"
                            webkitdirectory
                            directory
                            multiple
                            @change="onBatchDirChange"
                        />
                        <app-button
                            variant="secondary"
                            :disabled="batchImporting"
                            @click="pickBatchDir"
                        >
                            选择目录
                        </app-button>
                        <span
                            class="game-batch__dir-name"
                            :class="{ 'is-empty': !batchImportDirName }"
                        >
                            {{ batchImportDirText }}
                        </span>
                    </div>
                </div>

                <p v-if="batchImportError" class="game-batch__error">
                    {{ batchImportError }}
                </p>

                <el-progress
                    v-if="(batchImporting && batchImportTotal) || batchImportFinished"
                    class="game-batch__progress"
                    :percentage="batchImportPercent"
                    :show-text="false"
                    :stroke-width="4"
                />
                <p v-if="batchImporting" class="game-batch__status">
                    <template v-if="batchImportTotal">
                        已处理 {{ batchImportDone }} / {{ batchImportTotal }}
                    </template>
                    <template v-else>正在读取 meta.csv…</template>
                </p>

                <div v-if="batchImportFinished" class="game-batch__stats">
                    <span class="game-batch__stat game-batch__stat--ok">
                        成功 {{ batchImportStats.success }}
                    </span>
                    <span class="game-batch__stat">失败 {{ batchImportStats.failed }}</span>
                    <span class="game-batch__stat">跳过 {{ batchImportStats.skipped }}</span>
                    <span v-if="batchImportStats.unprocessed" class="game-batch__stat">
                        未处理 {{ batchImportStats.unprocessed }}
                    </span>
                </div>

                <ul v-if="batchImportFailures.length" class="game-batch__failures">
                    <li v-for="item in batchImportFailures" :key="`${item.line}-${item.reason}`">
                        第 {{ item.line }} 行{{ item.name ? `「${item.name}」` : "" }}：{{ item.reason }}
                    </li>
                </ul>

                <div class="game-batch__actions">
                    <app-button
                        variant="secondary"
                        :disabled="batchImporting"
                        @click="batchImportVisible = false"
                    >
                        关闭
                    </app-button>
                    <app-button
                        :loading="batchImporting"
                        :disabled="!batchImportCanStart"
                        @click="startBatchImport"
                    >
                        开始导入
                    </app-button>
                </div>
            </div>
        </app-dialog>
    </div>
</template>

<script setup>
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { dangerConfirm, dangerPrompt } from "@/utils/confirm";
import AppDialog from "@components/common/AppDialog.vue";
import CopyButton from "@components/common/CopyButton.vue";
import CoverBeautifyDialog from "@components/games/CoverBeautifyDialog.vue";
import GameDetailDialog from "@components/games/GameDetailDialog.vue";
import GalleryManagerDialog from "@components/games/GalleryManagerDialog.vue";
import ImageUploadButton from "@components/games/ImageUploadButton.vue";
import {
    createManageGameAPI,
    deleteGuideAPI,
    deleteManageGameAPI,
    getManageGameAPI,
    importGameAPI,
    listManageGamesAPI,
    prepareManageImportAPI,
    renameCartridgeIdAPI,
    updateManageGameAPI,
    updateManageGameTypeAPI,
    uploadGalleryAPI,
    uploadGameAssetAPI,
    uploadGuideAPI,
    abortGameUploadAPI,
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
    uploadFileInChunks,
    uploadFilesInChunks,
    shouldUseChunkedUpload,
} from "@/utils/chunkUpload";
import { formatDateTimeSeconds as formatDateTime } from "@/utils/fileDisplay";
import { useAdaptiveRows } from "@/utils/adaptiveRows";
import { useRoute, useRouter } from "vue-router";

// 行高固定、行数自适应（见 utils/adaptiveRows.js）：行高 40px 与游戏发现一致，
// 后端 backend/games/service.py 的 MANAGE_PAGE_SIZE_MAX = 100 是上限。
// 行内容是 28px 的按钮 + 上下各 6px 内边距 = 40；表头 44 + 分隔线合计 12 算在
// TABLE_EXTRA 里；底部开销 = 分页条（上边距 20 + 高 32）+ 内容区下边距 28 = 80。
// 行高全屏/非全屏一致，只有行数不同；排不满整行的余量留在最后一行与分页条之间。
const ROW_HEIGHT = 40;
const TABLE_EXTRA = 56;
const PAGE_SIZE_MAX = 100;

// 顶部标签：现在只有「游戏管理」一个，值与 URL ?tab 对齐（与游戏发现同一套写法），
// 以后加标签在这里追加即可
const TABS = [{ label: "游戏管理", value: "manage" }];

const route = useRoute();
const router = useRouter();

const activeTab = computed({
    get: () =>
        TABS.some((tab) => tab.value === route.query.tab)
            ? route.query.tab
            : TABS[0].value,
    set: (value) => {
        const query = { ...route.query };
        if (value === TABS[0].value) {
            delete query.tab;
        } else {
            query.tab = value;
        }
        router.replace({ path: "/games/manage", query });
    },
});

const { rows: pageSize, measure: measureRows } = useAdaptiveRows(
    {
        rowHeight: ROW_HEIGHT,
        extraHeight: TABLE_EXTRA,
        reservePx: 80,
        maxRows: PAGE_SIZE_MAX,
        // 量到之前按旧条数占位，高度别闪跳
        initialRows: 5,
    },
    () => reload()
);

// 列表容器永远按「一页满行」定高：最后一页数据不满时高度也不缩，分页条位置固定不动；
// 行高全屏/非全屏一致，排不满整行的余量落在表格下方
const tableWrapEl = ref(null);
const tableWrapHeight = computed(
    () => `${TABLE_EXTRA + pageSize.value * ROW_HEIGHT}px`
);


const loading = ref(false);
const saving = ref(false);
const items = ref([]);
const page = ref(1);
const total = ref(0);
// 类型与可上传后缀都来自 /status（后端词表派生），这里只读缓存
const gameTypesStore = useGameTypesStore();
const gameTypes = computed(() => gameTypesStore.gameTypes);
// 类型筛选下拉：「全部」+ 当前类型；输入过滤交给 AppTypeSelect
const typeFilterOptions = computed(() => [
    { value: "", label: "全部游戏类型" },
    ...gameTypes.value.map((type) => ({ value: type, label: typeLabel(type) })),
]);

const filterType = ref("");
const filterKeyword = ref("");
let keywordTimer = null;
// Element Plus 点 X 会先 emit clear、再 emit input：clear 已立即查询，跳过随后那次防抖
let skipKeywordInput = false;
// 请求序号：防抖 + 快速翻页时，慢的旧响应不能覆盖新结果（同检索页）
let requestSeq = 0;

const formVisible = ref(false);
const formMode = ref("create");
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

// 详情弹窗（内容见 components/games/GameDetailDialog.vue，游戏中心右键也用它）
const detailVisible = ref(false);
const detailId = ref(null);

const importVisible = ref(false);
const importUrl = ref("");
const importing = ref(false);

// 批量导入：选本地目录 → 上传 meta.csv 让后端解析/查重 → 逐行创建（无本体，只带封面）
const BATCH_COVER_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp"]);
const batchImportVisible = ref(false);
const batchImportType = ref("");
const batchImportDirRef = ref(null);
const batchImportDirName = ref("");
const batchImportMetaFile = ref(null);
const batchImportCoverFiles = ref(new Map());
const batchImportRootFileCount = ref(0);
const batchImportError = ref("");
const batchImporting = ref(false);
const batchImportFinished = ref(false);
const batchImportDone = ref(0);
const batchImportTotal = ref(0);
const batchImportStats = ref({ success: 0, failed: 0, skipped: 0, unprocessed: 0 });
const batchImportFailures = ref([]);

const batchImportPercent = computed(() =>
    batchImportTotal.value
        ? Math.min(100, Math.round((batchImportDone.value / batchImportTotal.value) * 100))
        : 0,
);
const batchImportCanStart = computed(
    () =>
        !batchImporting.value &&
        Boolean(batchImportMetaFile.value && batchImportType.value),
);
const batchImportDirText = computed(() => {
    if (!batchImportDirName.value) {
        return "尚未选择目录";
    }
    return `${batchImportDirName.value}（${batchImportRootFileCount.value} 个文件）`;
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


function listParams() {
    const params = { page: page.value, page_size: pageSize.value };
    if (filterType.value) {
        params.game_type = filterType.value;
    }
    if (filterKeyword.value.trim()) {
        params.q = filterKeyword.value.trim();
    }
    return params;
}

/** 取当前页。**保持页码**——保存、删除、搬运之后都调它，别把用户从第 3 页踢回第 1 页。 */
async function reload() {
    const seq = ++requestSeq;
    loading.value = true;
    try {
        const data = await listManageGamesAPI(listParams());
        if (seq !== requestSeq) {
            return;
        }
        // 删掉本页最后一条后页码会越界：收敛到最后一页再取一次。
        // （服务端不收敛页码、只返回空 items + 真 total，与检索页同一口径，收敛放前端）
        const pageCount = Math.max(
            1,
            Math.ceil((data.total || 0) / (data.page_size || pageSize.value))
        );
        if (page.value > pageCount) {
            page.value = pageCount;
            // 内层会 ++requestSeq，外层 finally 的 seq 判断自然跳过、不覆盖 loading
            await reload();
            return;
        }
        items.value = data.items || [];
        total.value = data.total || 0;
        page.value = data.page || 1;
    } finally {
        if (seq === requestSeq) {
            loading.value = false;
        }
    }
}

/** 改筛选条件要回到第 1 页，否则会停在一个新结果里不存在的页码上。 */
function applyFilter() {
    page.value = 1;
    reload();
}

function onKeywordInput() {
    if (skipKeywordInput) {
        skipKeywordInput = false;
        return;
    }
    clearTimeout(keywordTimer);
    keywordTimer = setTimeout(applyFilter, 300);
}

/** 点 X 清空：立即查询；紧随其后的 input 已由 skipKeywordInput 跳过。 */
function onKeywordClear() {
    skipKeywordInput = true;
    clearTimeout(keywordTimer);
    applyFilter();
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

// 关掉弹框就停掉在途分片，避免 5 路请求在后台继续跑
watch(formVisible, (open) => {
    if (!open) {
        cancelBodyUpload();
    }
});

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
        await reload();
    } catch (err) {
        // 失败留在编辑态，改完再试；错误提示已由请求层 toast
        if (!err.reported) ElMessage.error(err.message || "修改失败");
    } finally {
        cartridgeSaving.value = false;
    }
}

function openCreate() {
    resetForm();
    formMode.value = "create";
    formVisible.value = true;
}

async function openEdit(id) {
    // 上一只游戏关弹框时排队的元数据保存先落地，避免它的响应晚到覆盖这一只的编辑态
    await metaSaveChain.catch(() => {});
    resetForm();
    formMode.value = "edit";
    editingId.value = id;
    editingItem.value = await getManageGameAPI(id);
    form.name = editingItem.value.name;
    form.description = editingItem.value.description;
    form.gameType = editingItem.value.game_type;
    form.coverType = editingItem.value.cover_type || "";
    formVisible.value = true;
}

function openDetail(id) {
    detailId.value = id;
    detailVisible.value = true;
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
        await reload();
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

// 右上角关闭时输入框可能还没触发 change：补一次落库（空名称不提交，避免把游戏改成无名）
watch(formVisible, (visible) => {
    if (!visible && formMode.value === "edit" && form.name.trim()) {
        queueMetaSave();
    }
});

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

function resetBatchImportState() {
    batchImportDirName.value = "";
    batchImportMetaFile.value = null;
    batchImportCoverFiles.value = new Map();
    batchImportRootFileCount.value = 0;
    batchImportError.value = "";
    batchImportFinished.value = false;
    batchImportDone.value = 0;
    batchImportTotal.value = 0;
    batchImportStats.value = { success: 0, failed: 0, skipped: 0, unprocessed: 0 };
    batchImportFailures.value = [];
}

function openBatchImport() {
    batchImportType.value = "";
    resetBatchImportState();
    batchImportVisible.value = true;
}

// 「选择目录」代点隐藏的 webkitdirectory 文件选择器；先清空 value 才能重选同一目录
function pickBatchDir() {
    if (batchImporting.value || !batchImportDirRef.value) {
        return;
    }
    batchImportDirRef.value.value = "";
    batchImportDirRef.value.click();
}

function onBatchDirChange(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    resetBatchImportState();
    if (!files.length) {
        return;
    }
    // 只认所选目录根下的文件：webkitRelativePath 形如「目录名/meta.csv」
    const depthOf = (file) => (file.webkitRelativePath || file.name).split("/").length;
    const rootFiles = files.filter((file) => depthOf(file) <= 2);
    const meta = rootFiles.find((file) => file.name.toLowerCase() === "meta.csv");
    if (!meta) {
        const nested = files.some(
            (file) => file.name.toLowerCase() === "meta.csv" && depthOf(file) > 2,
        );
        batchImportError.value = nested
            ? "请选择直接包含 meta.csv 的目录，而不是它的上级目录。"
            : "所选目录根下没有 meta.csv。";
        return;
    }
    const covers = new Map();
    for (const file of rootFiles) {
        if (file === meta) {
            continue;
        }
        const key = file.name.toLowerCase();
        if (!covers.has(key)) {
            covers.set(key, file);
        }
    }
    batchImportDirName.value =
        (meta.webkitRelativePath || "").split("/")[0] || "所选目录";
    batchImportMetaFile.value = meta;
    batchImportCoverFiles.value = covers;
    batchImportRootFileCount.value = rootFiles.length;
}

function extensionOfCover(name) {
    const value = String(name || "");
    const index = value.lastIndexOf(".");
    return index < 0 ? "" : value.slice(index).toLowerCase();
}

function recordBatchFailure(row, reason) {
    batchImportStats.value.failed += 1;
    batchImportFailures.value.push({
        line: row.line,
        name: row.name,
        reason,
    });
}

/** 预检之后库又变了（例如另一个标签页）：创建接口的重复错误按跳过处理。 */
function isDuplicateCreateError(message) {
    return /已经被占用|已经有叫/.test(String(message || ""));
}

/** 网络错误 / 401 / 5xx 时整批停下；单行 400 只算这一行失败。 */
function isFatalImportError(err) {
    return !err?.status || err.status === 401 || err.status >= 500;
}

async function importBatchRow(row) {
    if (row.error) {
        recordBatchFailure(row, row.error);
        return;
    }
    if (row.skip) {
        batchImportStats.value.skipped += 1;
        return;
    }
    const cover = batchImportCoverFiles.value.get(
        String(row.cover || "").toLowerCase(),
    );
    if (!cover) {
        recordBatchFailure(row, `封面文件不存在：${row.cover || "（空）"}`);
        return;
    }
    if (!BATCH_COVER_EXTENSIONS.has(extensionOfCover(cover.name))) {
        recordBatchFailure(row, "封面仅支持 jpg、png、gif、webp 图片。");
        return;
    }
    const data = new FormData();
    data.append("name", row.name);
    data.append("cartridge_id", row.cartridge_id);
    data.append("description", "");
    data.append("body_game_type", batchImportType.value);
    data.append("cover", cover);
    if (row.cover_type) {
        data.append("cover_type", row.cover_type);
    }
    try {
        await createManageGameAPI(data, { silent: true });
        batchImportStats.value.success += 1;
    } catch (err) {
        if (isDuplicateCreateError(err?.message)) {
            batchImportStats.value.skipped += 1;
            return;
        }
        if (isFatalImportError(err)) {
            throw err;
        }
        recordBatchFailure(row, err?.message || "创建失败");
    }
}

async function startBatchImport() {
    if (!batchImportCanStart.value) {
        return;
    }
    batchImporting.value = true;
    batchImportFinished.value = false;
    batchImportError.value = "";
    batchImportDone.value = 0;
    batchImportTotal.value = 0;
    batchImportStats.value = { success: 0, failed: 0, skipped: 0, unprocessed: 0 };
    batchImportFailures.value = [];
    try {
        const payload = new FormData();
        payload.append("game_type", batchImportType.value);
        payload.append("meta", batchImportMetaFile.value);
        const result = await prepareManageImportAPI(payload);
        const rows = result?.rows || [];
        batchImportTotal.value = rows.length;
        if (!rows.length) {
            batchImportError.value = "meta.csv 没有可导入的数据行。";
            return;
        }
        for (const row of rows) {
            try {
                await importBatchRow(row);
            } catch (err) {
                recordBatchFailure(row, err?.message || "导入已停止。");
                batchImportDone.value += 1;
                batchImportStats.value.unprocessed =
                    batchImportTotal.value - batchImportDone.value;
                batchImportError.value =
                    err?.message || "导入已停止，请检查网络后重试。";
                break;
            }
            batchImportDone.value += 1;
        }
        batchImportFinished.value = true;
    } catch (err) {
        batchImportError.value = err?.message || "导入失败，请稍后重试。";
    } finally {
        batchImporting.value = false;
        if (batchImportStats.value.success > 0) {
            await reload();
        }
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
        await reload();
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
        await reload();
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
        await reload();
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
        await reload();
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
        await reload();
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
        await reload();
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
        await createManageGameAPI(data);
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
        await onCreate();
        ElMessage.success("游戏已添加");
        formVisible.value = false;
        await reload();
    } catch (err) {
        if (!err.aborted && !err.reported) {
            ElMessage.error(err.message || "保存失败");
        }
    } finally {
        saving.value = false;
        bodyProgress.value = 0;
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
    const confirmed = await dangerPrompt(buildDeleteMessage(item), {
        title: "删除确认",
        inputPlaceholder: `输入卡带 ID「${item.cartridge_id}」以确认`,
        inputValidator: (value) =>
            String(value || "").trim().toUpperCase() === item.cartridge_id ||
            `请输入卡带 ID「${item.cartridge_id}」以确认`,
    });
    if (!confirmed) {
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
    // 先量视口算出每页行数，首屏请求才知道带多大 page_size
    measureRows(tableWrapEl.value);
    loading.value = true;
    try {
        // 类型与后缀来自 /status；失败时页面仍能列出游戏，只是下拉候选为空
        await gameTypesStore.ensureLoaded();
        await reload();
    } finally {
        loading.value = false;
    }
});

onBeforeUnmount(() => {
    // 挂起的防抖别再触发一次请求（序号防竞态兜得住，但清掉更干净）
    clearTimeout(keywordTimer);
    cancelBodyUpload();
    releaseCoverPreview();
});
</script>

<style scoped>
/* 页面纵向铺满：内容区上下各 28px 内边距，页面根按 100vh−56 占满后再不滚动；
   面板（tab 栏 + 工具条 + 列表 + 分页）填满剩余高度，行数自适应的空间吃满 */
.game-manage {
    display: flex;
    flex-direction: column;
    min-height: calc(100vh - 56px);
}

.game-manage__panel {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
}

/* 页头标签共用 AppSegmented 的尺寸与选中态，这里只留与下方工具条的间距 */
.game-manage__tabs {
    margin-bottom: 20px;
}

.game-manage__toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    align-items: center;
}

.game-manage__filter-type {
    /* 足够放下最长的类型名（如 “任天堂 GB/GBC”），避免选中值被截断 */
    width: 240px;
}

.game-manage__filter-keyword {
    width: 240px;
}

.game-manage__actions {
    margin-left: auto;
}

/* 列表高度直接占量出的可用高度（模板 :style 绑定 available，覆盖下面的 min-height）：
   行数按视口高度自适应（utils/adaptiveRows.js），取整后不足一行的余量由表格行均摊消化 */
.game-manage__table-wrap {
    min-height: 200px;
}

/* 固定布局 + 定宽/百分比列宽：列宽只跟表格宽度走，跟内容长短无关，
   所以再长的名称也只在自己格子里省略，表格永远不会被撑宽（页面不会出水平滚动条）。
   注意别在这里加 overflow: hidden——展开的名称浮层要能盖到表格外面去 */
.game-manage__table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
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

/* 名称列不给定宽：吃掉其余定宽列剩下的全部宽度（table-layout: fixed 语义）。
   定宽列按内容最宽需要给（如更新时间那串 19 个字、三个操作按钮并排） */
.game-manage__col-type {
    width: 180px;
}

.game-manage__col-size {
    width: 96px;
}

.game-manage__col-time {
    width: 180px;
}

/* 操作列：三个 sm 按钮（高 28、左右内边距各 10、短字约 26）= 每个约 46px，
   加两个 8px 间距再算上单元格左右各 16 的内边距 ≈ 186，给 200 留余量——
   少了按钮会顶出格子 */
.game-manage__col-actions {
    width: 200px;
}

/* 与游戏发现同款：行高固定 40px（28px 按钮 + 上下各 6px 内边距），
   全屏与非全屏行高一致，只有行数不同。
   line-height 显式写死，两张表不会因为字体默认值不同而差几个像素 */
.game-manage__table th,
.game-manage__table td {
    border-bottom: 1px solid var(--border);
    text-align: left;
    vertical-align: middle;
}

.game-manage__table td {
    padding: 6px 16px;
    font-size: 14px;
    line-height: 20px;
}

/* 表头没有内容撑着，上下留 12px 就够——别白占一屏的竖向预算。
   行高显式写死 20px，表格定高（见 __table-wrap）才能算准 */
.game-manage__table th {
    padding: 12px 16px;
    line-height: 20px;
}

/* 除名称列外都只占一行，超长（如 任天堂 GB/GBC）就地省略 */
.game-manage__nowrap {
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.game-manage__table th {
    background: #f8fafc;
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 600;
}

/* 名称被截断时展开层里的描述段落：小一号的灰字，跟浮层自身的白底配 */
.game-manage__panel-desc {
    margin-top: 6px;
    font-size: 12px;
    line-height: 1.7;
    color: #64748b;
    white-space: normal;
}

/* 三个操作按钮左对齐（和「操作」表头对齐）；列宽按它们的实际宽度给，
   所以删除右边也不会剩下大片空白。
   Element Plus 默认给相邻按钮加 12px 左边距，这里间距统一由 flex gap 管，
   去掉它，否则三个按钮会把内容顶出格子右边 */
.game-manage__row-actions {
    display: flex;
    gap: 8px;
}

.game-manage__row-actions :deep(.el-button + .el-button) {
    margin-left: 0;
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

/* 大本体分片上传的细进度条：只占一行，不挤动表单布局 */
.game-manage__upload-progress {
    margin-top: 6px;
    max-width: 320px;
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

/* 卡带 ID 那一行：值占满左侧、按钮贴到左栏右边缘（改名时把值换成输入框，排版不跳） */
.game-manage__cartridge {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
}

.game-manage__cartridge .game-manage__detail-key,
.game-manage__cartridge-input {
    flex: 1 1 auto;
    min-width: 0;
}

/* 描述框：高度交给 rows（不拖拽缩放），底部留出字数统计那一行的位置，免得压住最后一行 */
.game-manage__desc-input :deep(.el-textarea__inner) {
    padding-bottom: 22px;
}

/* 「待上传」那行里的清除：做成行内文字按钮，不抢视线 */
.game-manage__remote-select,
.game-manage__type-select {
    width: 100%;
}

/* 封面类型的单选项是纯文字（样式名），与单选圆点垂直居中对齐 */
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

/* 批量导入弹窗 */
.game-batch {
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.game-batch__tip {
    margin: 0;
    font-size: 13px;
    line-height: 1.6;
    color: #64748b;
}

.game-batch__field {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.game-batch__label {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
}

.game-batch__type {
    width: 100%;
}

.game-batch__dir {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
}

.game-batch__dir-name {
    min-width: 0;
    overflow: hidden;
    font-size: 13px;
    color: #334155;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.game-batch__dir-name.is-empty {
    color: #94a3b8;
}

.game-batch__error {
    margin: 0;
    font-size: 13px;
    color: #dc2626;
}

.game-batch__progress {
    margin-top: 2px;
}

.game-batch__status {
    margin: 0;
    font-size: 12px;
    color: #64748b;
}

.game-batch__stats {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    font-size: 13px;
    color: #475569;
}

.game-batch__stat--ok {
    color: #16a34a;
    font-weight: 600;
}

.game-batch__failures {
    max-height: 120px;
    margin: 0;
    padding: 10px 12px;
    overflow: auto;
    list-style: none;
    background: #f8fafc;
    border-radius: 8px;
    font-size: 12px;
    line-height: 1.6;
    color: #64748b;
}

.game-batch__actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 4px;
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
    background: linear-gradient(135deg, #60a5fa, #0098ee);
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
