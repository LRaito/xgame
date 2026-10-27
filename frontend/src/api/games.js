import request from "@/utils/request";
import { blobToBase64 } from "@/utils/gameSaves";

export function listGamesAPI() {
    return request({ url: "/api/games", method: "get" });
}

/** 取单个可游玩的游戏（中心列表数据）。找不到返回 null。 */
export async function getPlayableGameAPI(id) {
    const games = await listGamesAPI();
    return (games || []).find((item) => Number(item.id) === Number(id)) || null;
}

export function gamesStatusAPI() {
    return request({ url: "/api/games/status", method: "get" });
}

/** 当前账号最近玩过的游戏（按最近一次开玩倒序；limit 由后端收敛到 1..50）。 */
export function listRecentGamesAPI(limit = 20) {
    return request({ url: "/api/games/recent", method: "get", params: { limit } });
}

/**
 * 上报一次开玩。播放页 best-effort 调用：失败不弹全局提示、401 也不跳登录页
 * （游玩中不打断；游戏本身加载不出来自会有别的报错路径）。
 */
export function markGamePlayedAPI(gameId) {
    return request({
        url: "/api/games/recent",
        method: "post",
        data: { game_id: gameId },
        notShowError: true,
        skipAuthRedirect: true,
    });
}

/**
 * 累加一段游玩时长。播放页计时器 best-effort 调用（同 markGamePlayedAPI）：
 * 失败不弹全局提示、401 也不跳登录页，丢掉的只是一小段时长。
 */
export function addGamePlaytimeAPI(gameId, seconds) {
    return request({
        url: "/api/games/stats/playtime",
        method: "post",
        data: { game_id: gameId, seconds },
        notShowError: true,
        skipAuthRedirect: true,
    });
}

/** 手动把总时长改写成指定小时数（游戏中心右键菜单）。 */
export function setGamePlaytimeAPI(gameId, hours) {
    return request({
        url: `/api/games/stats/${gameId}/playtime`,
        method: "put",
        data: { hours },
    });
}

/** 手动设置游戏进度：未开始 / 进行中 / 已通关。 */
export function setGameProgressAPI(gameId, progress) {
    return request({
        url: `/api/games/stats/${gameId}/progress`,
        method: "put",
        data: { progress },
    });
}

export function listManageGamesAPI(params = {}) {
    return request({ url: "/api/games/manage", method: "get", params });
}
export function getManageGameAPI(id) {
    return request({ url: `/api/games/manage/${id}`, method: "get" });
}

/** 新建游戏：一次性提交名称/描述/本体（可选封面），类型由后端按本体文件名判定。 */
export function createManageGameAPI(formData) {
    return request({
        url: "/api/games/manage",
        method: "post",
        data: formData,
        timeout: 0,
    });
}

export function updateManageGameAPI(id, data) {
    return request({ url: `/api/games/manage/${id}`, method: "put", data });
}

/** 改卡带 ID：后端会把磁盘目录（含各账号的存档与截图）一起改名并改写库里的路径列。

    独立接口——普通编辑（updateManageGameAPI）不接受这个字段。 */
export function renameCartridgeIdAPI(id, cartridgeId) {
    return request({
        url: `/api/games/manage/${id}/cartridge-id`,
        method: "put",
        data: { cartridge_id: cartridgeId },
    });
}

/** 从 7k7k / 4399 / flash.homes 游戏页地址搬运游戏（服务端解析、下载并入库，耗时较长）。

    卡带ID 由服务端按本体 CRC32 自动生成（F-{CRC32}），不用前端传。 */
export function importGameAPI(url) {
    return request({
        url: "/api/games/manage/import",
        method: "post",
        data: { url },
        timeout: 0,
    });
}

export function deleteManageGameAPI(id) {
    return request({ url: `/api/games/manage/${id}`, method: "delete" });
}

/** 一步上传游戏本体(kind=game)或封面(kind=cover)，经后端写入存储目录并更新游戏行。 */
export function uploadGameAssetAPI(id, formData) {
    return request({
        url: `/api/games/manage/${id}/assets`,
        method: "post",
        data: formData,
        timeout: 0,
    });
}

/** 上传攻略：multipart 里只有一个 file 字段（ZIP 解压后根目录需含 index.html，或单个 PDF）。 */
export function uploadGuideAPI(id, formData) {
    return request({
        url: `/api/games/manage/${id}/guide`,
        method: "post",
        data: formData,
        timeout: 0,
    });
}

/** 删除攻略（ZIP/PDF 都删），返回更新后的管理条目。 */
export function deleteGuideAPI(id) {
    return request({ url: `/api/games/manage/${id}/guide`, method: "delete" });
}

/**
 * 取当前登录用户某平台（gba/nes/…）的模拟器设置；还没存过时 settings 为 null。
 * 自动同步用：失败不弹全局提示、401 也不跳登录页（游玩中不打断）。
 */
export function getEmulatorSettingsAPI(gameType) {
    return request({
        url: "/api/games/emulator-settings",
        method: "get",
        params: { game_type: gameType },
        notShowError: true,
        skipAuthRedirect: true,
    });
}

/** 整块覆盖保存当前登录用户某平台的模拟器设置。 */
export function saveEmulatorSettingsAPI(gameType, settings) {
    return request({
        url: "/api/games/emulator-settings",
        method: "put",
        data: { game_type: gameType, settings },
        notShowError: true,
        skipAuthRedirect: true,
    });
}

/** 游戏封面的同源流式地址（供 <img> 预览，必要时加 ?v=updated_at 破缓存）。 */
export function gameCoverPath(id, updatedAt = "") {
    const query = updatedAt ? `?v=${encodeURIComponent(updatedAt)}` : "";
    return `/api/games/${id}/cover${query}`;
}

/** 游戏本体的下载地址（Content-Disposition 附件，文件名 game.<后缀>；SWF/ROM/ZIP 通用）。
 *  v=updated_at 破缓存：游戏 id 会被复用，换本体后文件名也常常不变。 */
export function gameDownloadPath(id, updatedAt = "") {
    const query = updatedAt ? `?v=${encodeURIComponent(updatedAt)}` : "";
    return `/api/games/${id}/play${query}`;
}

/** H5 入口页地址（沙箱 iframe 的 src）；带 v=updated_at 破缓存，重传后立即生效。 */
export function h5EntryPath(id, updatedAt = "") {
    const query = updatedAt ? `?v=${encodeURIComponent(updatedAt)}` : "";
    return `/api/games/${id}/h5/index.html${query}`;
}

/** 攻略入口页地址（新标签页顶层打开，同源请求会带上登录 cookie，所以接口要登录）。 */
export function guideEntryPath(id) {
    return `/api/games/${id}/guide/index.html`;
}

/** 攻略 PDF 地址（数据根直读，新标签页内联展示；接口同样需登录）。 */
export function guidePdfPath(id) {
    return `/api/games/${id}/guide.pdf`;
}

/** 游戏封面的下载地址（download=1 时附件下载，文件名 cover.{后缀}）；
 *  v=updated_at 破缓存，理由同 gameDownloadPath。 */
export function coverDownloadPath(id, updatedAt = "") {
    const suffix = updatedAt ? `&v=${encodeURIComponent(updatedAt)}` : "";
    return `/api/games/${id}/cover?download=1${suffix}`;
}

/** 某游戏的云端存档（整体快照）列表。 */
export function listCloudSavesAPI(gameId) {
    return request({ url: "/api/games/saves", method: "get", params: { game_id: gameId } });
}

/** 云端存档详情（文件清单，含还原用的 local_key）。 */
export function cloudSaveDetailAPI(id) {
    return request({ url: `/api/games/saves/${id}`, method: "get" });
}

/** “同步至云端”：把当前游戏全部本地 .sol 打包上传成一个云端快照。 */
export function uploadCloudSaveAPI(formData) {
    return request({
        url: "/api/games/saves",
        method: "post",
        data: formData,
        timeout: 0,
    });
}

/** 删除某个云端存档。 */
export function deleteCloudSaveAPI(id) {
    return request({ url: `/api/games/saves/${id}`, method: "delete" });
}

/** 修改云端存档的描述（备注）。 */
export function updateCloudSaveAPI(id, remark, config = {}) {
    return request({
        url: `/api/games/saves/${id}`,
        method: "put",
        data: { remark },
        ...config,
    });
}

/** 设置/清除云端存档的父级（parentId=null 表示设为顶层）。 */
export function setCloudSaveParentAPI(id, parentId, config = {}) {
    return request({
        url: `/api/games/saves/${id}/parent`,
        method: "put",
        data: { parent_id: parentId },
        ...config,
    });
}

/** 调整云端存档在同级兄弟中的位置（toIndex 从 0 起）；返回整份有序列表。 */
export function moveCloudSaveAPI(id, toIndex, config = {}) {
    return request({
        url: `/api/games/saves/${id}/move`,
        method: "post",
        data: { to_index: toIndex },
        ...config,
    });
}

/** 云端存档单个文件的同源流式地址（octet-stream）。 */
export function cloudSaveFileDownloadPath(id, fileId) {
    return `/api/games/saves/${id}/files/${fileId}/download`;
}

/** 本人某游戏的截图列表（按展示顺序升序；只含本人的截图）。 */
export function listScreenshotsAPI(gameId) {
    return request({
        url: "/api/games/screenshots",
        method: "get",
        params: { game_id: gameId },
    });
}

/** 上传一张截图（FormData：game_id / description / file），描述可空。 */
export function uploadScreenshotAPI(formData) {
    return request({
        url: "/api/games/screenshots",
        method: "post",
        data: formData,
        timeout: 0,
    });
}

/** 修改截图描述（上限 15 字）。 */
export function updateScreenshotAPI(id, description) {
    return request({
        url: `/api/games/screenshots/${id}`,
        method: "put",
        data: { description },
    });
}

/** 拖到指定位置（下标 0 起），返回整份有序列表（顺序以后端为准）。 */
export function moveScreenshotAPI(id, toIndex) {
    return request({
        url: `/api/games/screenshots/${id}/move`,
        method: "post",
        data: { to_index: toIndex },
    });
}

/** 删除一张截图（行与磁盘文件一起清掉）。 */
export function deleteScreenshotAPI(id) {
    return request({ url: `/api/games/screenshots/${id}`, method: "delete" });
}

/**
 * 截图本体的同源 inline 地址。
 *
 * **必须带版本参数**：SQLite 的主键会被复用（字段声明是普通 `INTEGER PRIMARY KEY`，
 * 没有 AUTOINCREMENT——删掉最大 id 的那行之后再插入，新行会拿回同一个 id），
 * 于是同一个 URL 会先后对应两张不同的图。不带版本号时，浏览器缓存与 Vue 的节点
 * 复用都会把新图渲染成旧图（表现为「选了新图片，上传后却是之前那张」）。
 * created_at 是微秒级且每行独立，足够当内容版本号。
 */
export function screenshotImagePath(item) {
    return `/api/games/screenshots/${item.id}/image?v=${encodeURIComponent(
        item.created_at || ""
    )}`;
}

/** 某游戏的图集列表（按展示顺序升序；图集按游戏共享，谁都能看）。 */
export function listGalleryAPI(gameId) {
    return request({
        url: "/api/games/gallery",
        method: "get",
        params: { game_id: gameId },
    });
}

/** 上传一张图集图片（FormData：game_id / description / file），描述可空。 */
export function uploadGalleryAPI(formData) {
    return request({
        url: "/api/games/gallery",
        method: "post",
        data: formData,
        timeout: 0,
    });
}

/** 修改图集图片描述（上限 15 字）。 */
export function updateGalleryAPI(id, description) {
    return request({
        url: `/api/games/gallery/${id}`,
        method: "put",
        data: { description },
    });
}

/** 拖到指定位置（下标 0 起），返回整份有序列表（顺序以后端为准）。 */
export function moveGalleryAPI(id, toIndex) {
    return request({
        url: `/api/games/gallery/${id}/move`,
        method: "post",
        data: { to_index: toIndex },
    });
}

/** 删除一张图集图片（行与磁盘文件一起清掉）。 */
export function deleteGalleryAPI(id) {
    return request({ url: `/api/games/gallery/${id}`, method: "delete" });
}

/** 图集图片本体的同源 inline 地址（版本参数的由来见 screenshotImagePath）。 */
export function galleryImagePath(item) {
    return `/api/games/gallery/${item.id}/image?v=${encodeURIComponent(
        item.created_at || ""
    )}`;
}

/** 拉取云端快照里某个文件的内容并转成 base64，供“同步至本地”写回 localStorage。 */
export async function fetchCloudSaveFileBase64(id, fileId) {
    const blob = await request({
        url: cloudSaveFileDownloadPath(id, fileId),
        method: "get",
        responseType: "blob",
        notShowError: true,
        skipAuthRedirect: true,
    });
    return blobToBase64(blob);
}

/**
 * 游戏检索：在外部中英文名录索引里搜一页（服务端分页 + 机种过滤）。
 * 数据来自独立只读库，由项目根目录的 `make index` 构建。
 * 请求带 notShowError：检索是高频操作，失败由页面内联提示，不弹全局 Message。
 */
export function searchGamesAPI(params) {
    return request({
        url: "/api/games/search",
        method: "get",
        params,
        notShowError: true,
    });
}

/** 游戏检索的机种下拉候选项（按源文件顺序）。 */
export function listSearchConsolesAPI() {
    return request({ url: "/api/games/search/consoles", method: "get" });
}

/**
 * 游戏榜单的机种下拉候选项（只列榜单里出现过的机种）与默认机种。
 * 数据与检索同一个只读库，见后端 ranking_router.py。
 */
export function listRankingConsolesAPI() {
    return request({
        url: "/api/games/search/ranking/consoles",
        method: "get",
        notShowError: true,
    });
}

/** 游戏榜单：取某个机种的整份榜单（不分页）。失败由页面内联提示，不弹全局 Message。 */
export function getGameRankingAPI(params) {
    return request({
        url: "/api/games/search/ranking",
        method: "get",
        params,
        notShowError: true,
    });
}
