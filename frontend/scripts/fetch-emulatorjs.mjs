/**
 * 抓取 EmulatorJS 引擎资产到 public/emulatorjs/，供 dev（vite serve public）与
 * Docker 构建（npm run build）共用；运行时不再访问任何外网。
 *
 * 与 scripts/copy-ruffle.mjs 的分工一致，但 EmulatorJS 没有官方 npm 包、官方 release
 * 是 303MB 的全量 .7z，因此这里只从官方 CDN（与 release 同源同版本）按需拉取最小集：
 *  loader + 引擎（emulator.min.js/.css）+ 本项目 6 个平台 core（wasm.data + report）。
 *
 * core 文件命名规则（EmulatorJS 4.2.3 引擎逻辑）：
 *   cores/<core>[-thread][-legacy]-wasm.data
 * 引擎默认（core report 未声明 options.defaultWebGL2 时）会请求 <core>-legacy-wasm.data；
 * 只有在引擎设置里打开 WebGL2 后才改用无后缀的 <core>-wasm.data。为离线兜底两种都打包。
 * 本播放页固定 EJS_threads=false，不需要 -thread 变体。
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
 * Docker 镜像构建（make all / docker compose build web）通过构建上下文复用宿主机这份
 * public/emulatorjs（frontend/.dockerignore 不再排除它），宿主机资产齐全时镜像构建零下载。
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// 引擎版本（固定默认，勿随 CDN 变化自动跟新）：升级 = 改这里 + 删除 public/emulatorjs/ 后重跑
const EJS_VERSION = "4.2.3";
const BASE = `https://cdn.emulatorjs.org/${EJS_VERSION}/data/`;
const DONE_MARKER = ".emulatorjs.done";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const destRoot = join(root, "public/emulatorjs", "data");

// data/ 目录下相对路径清单（顶层引擎文件 + 6 平台 core）
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
    // cores：NES(fceumm) SNES(snes9x) GB/GBC(gambatte) GBA(mgba) MD/GG(genesis_plus_gx) SMS(smsplus)
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

/** 合成“完整中文语言包”并写入 data/localization/zh-CN.json（见文件头注释）。 */
async function installLocalization() {
    const fetchJson = async (path) => {
        const url = BASE + path;
        const response = await fetch(url, { redirect: "follow" });
        if (!response.ok) {
            throw new Error(`下载失败 ${response.status}: ${url}`);
        }
        const parsed = await response.json();
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

async function downloadOne(path) {
    const url = BASE + path;
    const response = await fetch(url, { redirect: "follow" });
    if (!response.ok) {
        throw new Error(`下载失败 ${response.status}: ${url}`);
    }
    const buffer = Buffer.from(await response.arrayBuffer());
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
    console.log(`EmulatorJS v${EJS_VERSION} 资产已就绪于 public/emulatorjs/，跳过下载。`);
    process.exit(0);
}

// 标记存在但版本不同（改了 EJS_VERSION 却没删目录）：本地文件属旧版本，不可复用，须整包重下。
// 其余情况（无标记 / 标记同版本但文件缺失）：复用本地已有文件，只补缺失项。
const forceRefresh = localVersion !== null && localVersion !== EJS_VERSION;
console.log(
    forceRefresh
        ? `本地 .emulatorjs.done 记录的是 ${localVersion}，与目标 ${EJS_VERSION} 不符，将从 ${BASE} 整包重下…（常规升级请先删除 public/emulatorjs/）`
        : `复用本地已有资产，从 ${BASE} 补齐缺失的 EmulatorJS v${EJS_VERSION} 文件…`
);

let totalBytes = 0;
let downloaded = 0;
let reused = 0;
const results = [];
try {
    for (const file of FILES) {
        if (!forceRefresh && presentOnDisk(file)) {
            reused += 1;
            continue;
        }
        const result = await downloadOne(file);
        results.push(result);
        downloaded += 1;
        totalBytes += result.bytes;
    }
    // 中文语言包本地合成（依赖上面的 emulator.min.js 扫描引擎词条）；已存在则复用
    if (forceRefresh || !presentOnDisk(LOCALE_OUT)) {
        const localization = await installLocalization();
        results.push({ path: LOCALE_OUT, sha256: localization.sha256 });
        downloaded += 1;
        totalBytes += localization.bytes;
    } else {
        reused += 1;
    }
    // 整套资产就绪后再统一刷新标记：中途失败则旧标记保留，重跑只续缺失项
    mkdirSync(destRoot, { recursive: true });
    writeFileSync(join(destRoot, DONE_MARKER), `${EJS_VERSION}\n`, "utf-8");
} catch (error) {
    console.error(`EmulatorJS 资产下载失败：${error.message}`);
    console.error("已下载的文件会被保留，修正后重跑本脚本即可续传剩余文件，无需从头再来。");
    process.exit(1);
}

if (downloaded > 0) {
    for (const { path, sha256 } of results) {
        console.log(`  ✔ ${path}  (${sha256.slice(0, 12)}…)`);
    }
    console.log(`本次补齐 ${downloaded} 个文件（${(totalBytes / 1024 / 1024).toFixed(2)} MB），本地复用 ${reused} 个。`);
} else {
    console.log(`EmulatorJS v${EJS_VERSION} 资产已齐全（复用本地 ${reused} 个），仅刷新版本标记，无需下载。`);
}
