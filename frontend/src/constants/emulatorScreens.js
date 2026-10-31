/**
 * 各主机平台的原始帧缓冲分辨率（像素）与截图比例。
 *
 * 窗口倍率按帧缓冲高度换算，窗口选择器以它为基准；截图框也按它决定竖版/横版。
 * 帧缓冲比例 ≠ 显示比例——内核会按像素宽高比（PAR）校正，舞台长宽比最终以引擎上报的
 * aspect 为准（见 emulator-player.vue 的 stageAspect）。
 *
 * NES 是 256 × 224：fceumm 默认裁掉上下各 8 行过扫描（Crop Vertical Top/Bottom Overscan = 8，
 * 内核选项 fceumm_overscan_v_top/_bottom），宿主页默认把显示比例设成像素完美（见
 * emulator-host.html），于是 1× 就是 256 × 224 个方像素。FC 还可以切到 4:3 那一列，
 * 那用的是另一套帧缓冲（完整 240 行），见 emulator-player.vue 的 WIDE_MODE。
 *
 * NDS 默认是 256 × 438：上下两屏各 192 行，中间 54px 间隙（melonds_screen_gap），
 * 192 + 54 + 192 = 438。54 由真实机壳的屏幕洞几何反推（外接矩形 840×1437，
 * 256×1437/840 − 384 ≈ 53.94），与外接矩形比例 256:438 对齐。洞已修成精确 4:3
 * （840×630），每块 256×192 屏幕都能完整铺满洞。间隙是否计入帧缓冲
 * **仍待实机确认**：若引擎上报 256×384，以截图 PNG 为准同时改这里与 SHELLS.nds，不能只改一处。
 */
export const EMU_NATIVE = {
    nes: { width: 256, height: 224 },
    snes: { width: 256, height: 224 },
    gb: { width: 160, height: 144 },
    gba: { width: 240, height: 160 },
    nds: { width: 256, height: 438 },
    segaMD: { width: 320, height: 224 },
    segaGG: { width: 160, height: 144 },
    segaMS: { width: 256, height: 192 },
};

/**
 * NDS 三种屏幕布局的帧缓冲尺寸（- / = 循环切换，见播放页与 emulator-host.html）。
 *
 * - dual：`Top/Bottom` + gap 54，256×(192+54+192)；
 * - top：`Top Only`，只显示上屏，256×192；
 * - side：对外几何是 (256+51+256)×192 = 563×192。
 *   注意 melonDS 内核的 `Left/Right` 布局**不吃 `melonds_screen_gap`**，帧缓冲固定
 *   512×192（两屏紧贴）；51px 间隙由宿主页把两屏拆开后合成（emulator-host.html 的
 *   `setupNdsSideScreen`），再按 563×192 上报给播放页，舞台与机壳才按两块分开的屏算。
 *   51 由左右机壳素材 nds-side-shell.png 的洞口反推：两洞各 460 图像 px 宽、间距 92，
 *   92×256/460 ≈ 51.2，取 51。机壳洞各 460×345 = 精确 4:3，与 256×192 一一对应。
 *
 * 宿主页 emulator-host.html 里有一份对应的 layout/gap 表，改这里必须同步改那边；
 * 切换成功与否以引擎上报的 `videoInfo` 为准（见播放页 switchNdsScreenMode）。
 */
export const NDS_NATIVE = {
    dual: { width: 256, height: 438 },
    top: { width: 256, height: 192 },
    side: { width: 563, height: 192 },
};

/** - / = 循环顺序。 */
export const NDS_SCREEN_MODES = ["dual", "top", "side"];

/**
 * 该游戏类型截图的宽高比（宽 / 高）；未知类型按 1:1。
 *
 * 详情图片栏与截图管理只用它决定**截图**格子的形状；封面与图集仍保持 1:1，
 * 所以加竖屏机种（NDS）不会改变现有 7 个机种的观感。
 * NDS 固定按 dual 的 256:438 展示：在 top / side 模式截的图尺寸不同，会在框内
 * 以 object-fit: contain 居中显示（不变形、留黑边），这是已知限制。
 */
export function screenshotAspect(gameType) {
    const size = EMU_NATIVE[gameType];
    return size ? size.width / size.height : 1;
}
