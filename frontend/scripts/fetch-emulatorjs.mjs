/**
 * 抓取 EmulatorJS 引擎资产到 public/emulatorjs/，供 dev（vite serve public）与
 * Docker 构建（npm run build）共用；运行时不再访问任何外网。
 *
 * 与 scripts/copy-ruffle.mjs 的分工一致，但 EmulatorJS 没有官方 npm 包、官方 release
 * 是 303MB 的全量 .7z，因此这里只从官方 CDN（与 release 同源同版本）按需拉取最小集：
 *  loader + 引擎（emulator.min.js/.css）+ 本项目 34 个唯一 core（覆盖 34 个可玩机种，wasm.data + report）。
 *
 * core 文件命名规则（EmulatorJS 4.2.3 引擎逻辑）：
 *   cores/<core>[-thread][-legacy]-wasm.data
 * 引擎默认（core report 未声明 options.defaultWebGL2 时）会请求 <core>-legacy-wasm.data；
 * 只有在引擎设置里打开 WebGL2 后才改用无后缀的 <core>-wasm.data。为离线兜底两种都打包。
 * 本播放页只对 PSP / DOS 打开 EJS_threads，因此只打包这两个核的 -thread 变体。
 * reports/<core>.json 提供 buildStart，让 EJS 能把 core 缓存进 IndexedDB，二次游玩免下载。
 * 本地化：引擎会按浏览器语言自动请求 data/localization/<locale>.json（本次 404 即 zh-CN）。
 * 官方 zh-CN 翻译不全，直接加载会让引擎对缺词条逐个打 “Translation not found”。因此构建时
 * 下载官方 en-US + zh-CN 合并成“完整中文包”（en-US 兜底 + zh-CN 覆盖 + 引擎实际查询而两者都缺
 * 的词条补英文原文占位），只发布 localization/zh-CN.json；播放页固定 EJS_language=zh-CN。
 *
 * 版本固定：EJS_VERSION 即钉死的引擎版本（当前为默认版本），下载 URL 一律按它取，
 * 绝不跟随 CDN 的 “latest” 自动升级。升级 = 手动改下面这一个版本号 + 删除
 * public/emulatorjs/ 后重跑（本地）或 make all（镜像构建，详见幂等段）。
 *
 * 幂等：先走“版本标记一致且文件齐全”的离线快路径（完全不碰网络）；否则按文件增量——
 * 本地已有且非空的文件直接复用，只补缺失项，整套就绪后再统一刷新 .emulatorjs.done。
 * 下载中断也只停在缺的文件上，重跑即续传，不会从头全量重下。整包重下仅在两种场景触发：
 * 本地没有对应文件，或 .emulatorjs.done 记录的是别的版本（改了 EJS_VERSION 却没删目录）。
 * 下载时在终端（TTY）里显示“当前文件 + 总进度”两段进度条；Docker 构建日志等非 TTY
 * 环境不画动态条，保持原有的逐文件结果输出。
 * Docker 镜像构建（make all / docker compose build web）通过构建上下文复用宿主机这份
 * public/emulatorjs（frontend/.dockerignore 不再排除它），宿主机资产齐全时镜像构建零下载。
 */
import { createHash } from "node:crypto";
import { fail, info, ok, warn } from "./console.mjs";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// 引擎版本（固定默认，勿随 CDN 变化自动跟新）：升级 = 改这里 + 删除 public/emulatorjs/ 后重跑
const EJS_VERSION = "4.2.3";
const BASE = `https://cdn.emulatorjs.org/${EJS_VERSION}/data/`;
const DONE_MARKER = ".emulatorjs.done";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const destRoot = join(root, "public/emulatorjs", "data");

// data/ 目录下相对路径清单（顶层引擎文件 + 34 个唯一 core，覆盖 34 个可玩机种）
const FILES = [
    "loader.js",
    "emulator.min.js",
    "emulator.min.css",
    "version.json",
    // 解压模块：EmulatorJS 解包 core 归档 / 压缩 ROM 时按需加载
    "compression/extract7z.js",
    "compression/extractzip.js",
    "compression/libunrar.js",
    "compression/libunrar.wasm",
    "compression/README.md",
    // cores：NES(fceumm) SNES(snes9x) GB/GBC(gambatte) GBA(mgba) NDS(melonds)
    //        MD/GG(genesis_plus_gx) SMS(smsplus)
    // 每个平台同时打 -wasm.data（WebGL2 开关打开时用）与 -legacy-wasm.data（引擎默认用）
    "cores/fceumm-wasm.data",
    "cores/fceumm-legacy-wasm.data",
    "cores/reports/fceumm.json",
    "cores/snes9x-wasm.data",
    "cores/snes9x-legacy-wasm.data",
    "cores/reports/snes9x.json",
    "cores/gambatte-wasm.data",
    "cores/gambatte-legacy-wasm.data",
    "cores/reports/gambatte.json",
    "cores/mgba-wasm.data",
    "cores/mgba-legacy-wasm.data",
    "cores/reports/mgba.json",
    "cores/genesis_plus_gx-wasm.data",
    "cores/genesis_plus_gx-legacy-wasm.data",
    "cores/reports/genesis_plus_gx.json",
    "cores/smsplus-wasm.data",
    "cores/smsplus-legacy-wasm.data",
    "cores/reports/smsplus.json",
    // NDS(melonds)：EJS 的 nds 默认核；desmume / desmume2015 刻意不打包
    "cores/melonds-wasm.data",
    "cores/melonds-legacy-wasm.data",
    "cores/reports/melonds.json",
    // 其余家用机：Virtual Boy / 32X / PCE / NGPC / WS / Atari 2600 / 7800 / Jaguar
    // 32X 用的就是 picodrive；PCE / NGPC / WS 是 Mednafen 系核
    "cores/beetle_vb-wasm.data",
    "cores/beetle_vb-legacy-wasm.data",
    "cores/reports/beetle_vb.json",
    "cores/picodrive-wasm.data",
    "cores/picodrive-legacy-wasm.data",
    "cores/reports/picodrive.json",
    "cores/mednafen_pce-wasm.data",
    "cores/mednafen_pce-legacy-wasm.data",
    "cores/reports/mednafen_pce.json",
    "cores/mednafen_ngp-wasm.data",
    "cores/mednafen_ngp-legacy-wasm.data",
    "cores/reports/mednafen_ngp.json",
    "cores/mednafen_wswan-wasm.data",
    "cores/mednafen_wswan-legacy-wasm.data",
    "cores/reports/mednafen_wswan.json",
    "cores/stella2014-wasm.data",
    "cores/stella2014-legacy-wasm.data",
    "cores/reports/stella2014.json",
    "cores/prosystem-wasm.data",
    "cores/prosystem-legacy-wasm.data",
    "cores/reports/prosystem.json",
    "cores/virtualjaguar-wasm.data",
    "cores/virtualjaguar-legacy-wasm.data",
    "cores/reports/virtualjaguar.json",
    // Atari 5200 / Lynx / ColecoVision
    "cores/a5200-wasm.data",
    "cores/a5200-legacy-wasm.data",
    "cores/reports/a5200.json",
    "cores/handy-wasm.data",
    "cores/handy-legacy-wasm.data",
    "cores/reports/handy.json",
    "cores/gearcoleco-wasm.data",
    "cores/gearcoleco-legacy-wasm.data",
    "cores/reports/gearcoleco.json",
    // N64 / 土星 / PS1 / PC-FX / 3DO
    // N64 打包两个核：iOS Safari 会反转列表后默认选 parallel_n64。
    "cores/mupen64plus_next-wasm.data",
    "cores/mupen64plus_next-legacy-wasm.data",
    "cores/reports/mupen64plus_next.json",
    "cores/parallel_n64-wasm.data",
    "cores/parallel_n64-legacy-wasm.data",
    "cores/reports/parallel_n64.json",
    "cores/yabause-wasm.data",
    "cores/yabause-legacy-wasm.data",
    "cores/reports/yabause.json",
    // PS1 两个核都打包，设置菜单里切换时不会 404
    "cores/pcsx_rearmed-wasm.data",
    "cores/pcsx_rearmed-legacy-wasm.data",
    "cores/reports/pcsx_rearmed.json",
    "cores/mednafen_psx_hw-wasm.data",
    "cores/mednafen_psx_hw-legacy-wasm.data",
    "cores/reports/mednafen_psx_hw.json",
    "cores/mednafen_pcfx-wasm.data",
    "cores/mednafen_pcfx-legacy-wasm.data",
    "cores/reports/mednafen_pcfx.json",
    "cores/opera-wasm.data",
    "cores/opera-legacy-wasm.data",
    "cores/reports/opera.json",
    // Commodore 五个：VICE 各机种核（c64/c128/pet/plus4/vic20）
    "cores/vice_x64sc-wasm.data",
    "cores/vice_x64sc-legacy-wasm.data",
    "cores/reports/vice_x64sc.json",
    "cores/vice_x128-wasm.data",
    "cores/vice_x128-legacy-wasm.data",
    "cores/reports/vice_x128.json",
    "cores/vice_xpet-wasm.data",
    "cores/vice_xpet-legacy-wasm.data",
    "cores/reports/vice_xpet.json",
    "cores/vice_xplus4-wasm.data",
    "cores/vice_xplus4-legacy-wasm.data",
    "cores/reports/vice_xplus4.json",
    "cores/vice_xvic-wasm.data",
    "cores/vice_xvic-legacy-wasm.data",
    "cores/reports/vice_xvic.json",
    // Amiga（puae）；世嘉 CD 复用 genesis_plus_gx / picodrive
    "cores/puae-wasm.data",
    "cores/puae-legacy-wasm.data",
    "cores/reports/puae.json",
    // PSP（ppsspp）只有 -thread 变体，且强制 WebGL2；
    // EJS 启动时还会额外拉 cores/ppsspp-assets.zip，必须一起打包。
    "cores/ppsspp-thread-wasm.data",
    "cores/reports/ppsspp.json",
    "cores/ppsspp-assets.zip",
    // DOS（dosbox_pure）同样只有 -thread 变体；WebGL2 开关决定取不取 legacy
    "cores/dosbox_pure-thread-wasm.data",
    "cores/dosbox_pure-thread-legacy-wasm.data",
    "cores/reports/dosbox_pure.json",
    // 街机只打包默认 FBNeo；CPS1/CPS2 仍保留在词表里，切过去会缺资产（与 NDS 现状一致）
    "cores/fbneo-wasm.data",
    "cores/fbneo-legacy-wasm.data",
    "cores/reports/fbneo.json",
];

// 本地化合并的输入（官方语言包，仅构建期下载、不入 data/）与合并产物输出（相对 data/）
const LOCALES = ["localization/en-US.json", "localization/zh-CN.json"];
const LOCALE_OUT = "localization/zh-CN.json";

/** 标记文件里记录的已完成版本；不存在或读失败返回 null。 */
function diskVersion() {
    const marker = join(destRoot, DONE_MARKER);
    if (!existsSync(marker)) {
        return null;
    }
    try {
        return readFileSync(marker, "utf-8").trim();
    } catch {
        return null;
    }
}

/** 相对 data/ 的路径是否已在本地存在且非空（存在即视为本版本可用，避免整包重下）。 */
function presentOnDisk(path) {
    try {
        return statSync(join(destRoot, path)).size > 0;
    } catch {
        return false;
    }
}

const IS_TTY = Boolean(process.stdout.isTTY);
const BAR_WIDTH = 20;
const UNITS = ["B", "KB", "MB", "GB"];

/** 1024 进制、一位小数；进度行里不显示 0 字节之外的精度。 */
function formatSize(bytes) {
    let value = Number(bytes) || 0;
    let unit = 0;
    while (value >= 1024 && unit < UNITS.length - 1) {
        value /= 1024;
        unit += 1;
    }
    return `${unit === 0 ? value : value.toFixed(1)} ${UNITS[unit]}`;
}

function progressBar(ratio) {
    const safe = Number.isFinite(ratio) ? Math.min(1, Math.max(0, ratio)) : 0;
    const filled = Math.round(safe * BAR_WIDTH);
    return `[${"█".repeat(filled)}${"░".repeat(BAR_WIDTH - filled)}]`;
}

/**
 * 单行进度：总进度按“已完成文件数”计，当前文件另有自己的百分比/字节数。
 * 只在 TTY 下原地刷新；非 TTY（Docker 构建日志、重定向）不输出动态内容。
 * 同一文件内最多每 100ms 刷新一次，避免小分片把终端刷得太碎。
 */
let lastProgressKey = "";
let lastProgressAt = 0;
function renderProgress({ index, total, path, loaded, bytes }) {
    if (!IS_TTY) {
        return;
    }
    const key = `${index}|${path}`;
    const now = Date.now();
    if (key === lastProgressKey && now - lastProgressAt < 100) {
        return;
    }
    lastProgressKey = key;
    lastProgressAt = now;
    const done = index - 1;
    const overall = total > 0 ? done / total : 0;
    const current = bytes > 0
        ? `${progressBar(loaded / bytes)} ${Math.min(100, Math.floor((loaded / bytes) * 100))}%` +
          ` ${formatSize(loaded)}/${formatSize(bytes)}`
        : formatSize(loaded);
    process.stdout.write(
        `\r\x1b[2K\x1b[36m[INFO]\x1b[0m 总进度 ${progressBar(overall)} ${done}/${total}  ${path} ${current}`
    );
}

/** 结束动态进度行；没画过就什么也不做。 */
function endProgressLine() {
    if (IS_TTY) {
        process.stdout.write("\n");
    }
}

/** 流式读响应体：边读边回报进度，最后拼成 Buffer（单个 core 最大几十 MB）。 */
async function readBody(response, onProgress) {
    const total = Number(response.headers.get("content-length")) || 0;
    if (!response.body) {
        const buffer = Buffer.from(await response.arrayBuffer());
        onProgress?.({ loaded: buffer.length, total: total || buffer.length });
        return buffer;
    }
    const reader = response.body.getReader();
    const chunks = [];
    let loaded = 0;
    for (;;) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        chunks.push(Buffer.from(value));
        loaded += value.length;
        onProgress?.({ loaded, total });
    }
    return Buffer.concat(chunks);
}

/** 合成“完整中文语言包”并写入 data/localization/zh-CN.json（见文件头注释）。 */
async function installLocalization(onProgress) {
    // 两个语言包并发下载，进度按两者合计回报，避免进度条在两个小文件之间来回跳。
    const loaded = new Map();
    const totals = new Map();
    const report = (path) => ({ loaded: current, total }) => {
        loaded.set(path, current);
        if (total > 0) {
            totals.set(path, total);
        }
        onProgress?.({
            loaded: [...loaded.values()].reduce((sum, value) => sum + value, 0),
            total: [...totals.values()].reduce((sum, value) => sum + value, 0),
        });
    };
    const fetchJson = async (path) => {
        const url = BASE + path;
        const response = await fetch(url, { redirect: "follow" });
        if (!response.ok) {
            throw new Error(`下载失败 ${response.status}: ${url}`);
        }
        const text = (await readBody(response, report(path))).toString("utf-8");
        const parsed = JSON.parse(text);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            throw new Error(`语言包格式异常: ${url}`);
        }
        return parsed;
    };
    const [en, zh] = await Promise.all(LOCALES.map(fetchJson));

    // en-US 兜底 → zh-CN 覆盖为中文；空串视为该键未翻译，交给后表或英文占位兜底
    const merged = {};
    for (const table of [en, zh]) {
        for (const [key, value] of Object.entries(table)) {
            if (typeof value === "string" && value.trim() !== "") {
                merged[key] = value;
            }
        }
    }
    // 引擎会以 this.localization(...) / EJS.localization(...) / this._(...) 查询界面词条，
    // 官方 en/zh 都未收录的用英文原文补齐，这样加载语言包时引擎不会因缺词条而逐条打
    // “Translation not found”。
    const engineSource = readFileSync(join(destRoot, "emulator.min.js"), "utf-8");
    const QUERY = /\.localization\("([^"]+)"|this\._\("([^"]+)"/g;
    for (const match of engineSource.matchAll(QUERY)) {
        const token = match[1] || match[2];
        if (token && !(token in merged)) {
            merged[token] = token;
        }
    }

    const content = JSON.stringify(merged, null, 2) + "\n";
    const target = join(destRoot, LOCALE_OUT);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, content, "utf-8");
    return {
        bytes: Buffer.byteLength(content, "utf-8"),
        sha256: createHash("sha256").update(content).digest("hex"),
    };
}

async function downloadOne(path, onProgress) {
    const url = BASE + path;
    const response = await fetch(url, { redirect: "follow" });
    if (!response.ok) {
        throw new Error(`下载失败 ${response.status}: ${url}`);
    }
    const buffer = await readBody(response, onProgress);
    if (!buffer.length) {
        throw new Error(`下载为空: ${url}`);
    }
    const target = join(destRoot, path);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, buffer);
    return { path, bytes: buffer.length, sha256: createHash("sha256").update(buffer).digest("hex") };
}

const REQUIRED = [...FILES, LOCALE_OUT];
const localVersion = diskVersion();

// 快路径：版本标记一致且文件齐全 → 完全离线，直接跳过
if (localVersion === EJS_VERSION && REQUIRED.every(presentOnDisk)) {
    info(`EmulatorJS v${EJS_VERSION} 资产已就绪于 public/emulatorjs/，跳过下载。`);
    process.exit(0);
}

// 标记存在但版本不同（改了 EJS_VERSION 却没删目录）：本地文件属旧版本，不可复用，须整包重下。
// 其余情况（无标记 / 标记同版本但文件缺失）：复用本地已有文件，只补缺失项。
const forceRefresh = localVersion !== null && localVersion !== EJS_VERSION;

// 先算出本次要下载的清单：总进度按“文件数”计，本地合成的语言包也算一项。
let reused = 0;
const queue = [];
for (const file of FILES) {
    if (!forceRefresh && presentOnDisk(file)) {
        reused += 1;
    } else {
        queue.push({ path: file, localization: false });
    }
}
if (forceRefresh || !presentOnDisk(LOCALE_OUT)) {
    queue.push({ path: LOCALE_OUT, localization: true });
} else {
    reused += 1;
}

if (forceRefresh) {
    warn(
        `本地 .emulatorjs.done 记录的是 ${localVersion}，与目标 ${EJS_VERSION} 不符，` +
            `将从 ${BASE} 整包重下…（常规升级请先删除 public/emulatorjs/）`
    );
} else if (queue.length) {
    info(
        `复用本地 ${reused} 个文件，从 ${BASE} 补齐缺失的 ${queue.length} 个 ` +
            `EmulatorJS v${EJS_VERSION} 文件…`
    );
}

let totalBytes = 0;
let downloaded = 0;
const results = [];
try {
    for (const [offset, item] of queue.entries()) {
        const index = offset + 1;
        if (item.localization) {
            const localization = await installLocalization(({ loaded, total }) =>
                renderProgress({
                    index,
                    total: queue.length,
                    path: `${LOCALE_OUT}（合成）`,
                    loaded,
                    bytes: total,
                })
            );
            results.push({ path: item.path, sha256: localization.sha256 });
            totalBytes += localization.bytes;
        } else {
            const result = await downloadOne(item.path, ({ loaded, total }) =>
                renderProgress({
                    index,
                    total: queue.length,
                    path: item.path,
                    loaded,
                    bytes: total,
                })
            );
            results.push(result);
            totalBytes += result.bytes;
        }
        downloaded += 1;
    }
    endProgressLine();
    // 整套资产就绪后再统一刷新标记：中途失败则旧标记保留，重跑只续缺失项
    mkdirSync(destRoot, { recursive: true });
    writeFileSync(join(destRoot, DONE_MARKER), `${EJS_VERSION}\n`, "utf-8");
} catch (error) {
    endProgressLine();
    fail(`EmulatorJS 资产下载失败：${error.message}`);
    fail("已下载的文件会被保留，修正后重跑本脚本即可续传剩余文件，无需从头再来。");
    process.exit(1);
}

if (downloaded > 0) {
    for (const { path, sha256 } of results) {
        info(`  ✔ ${path}  (${sha256.slice(0, 12)}…)`);
    }
    ok(`本次补齐 ${downloaded} 个文件（${(totalBytes / 1024 / 1024).toFixed(2)} MB），本地复用 ${reused} 个。`);
} else {
    info(`EmulatorJS v${EJS_VERSION} 资产已齐全（复用本地 ${reused} 个），仅刷新版本标记，无需下载。`);
}
