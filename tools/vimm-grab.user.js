// ==UserScript==
// @name         Vimm's Lair 排行榜抓取
// @namespace    https://vimm.net/
// @version      1.3.3
// @description  按机种与名次区间抓取 Vimm's Lair 游戏的条目 ID、卡带 ID 和封面，可指定保存目录；排行榜缓存到 list.csv，失败项记录到 error.csv，仅网络错误自动重试
// @match        https://vimm.net/*
// @grant        GM_openInTab
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @run-at       document-idle
// @noframes
// ==/UserScript==

/*
 * ============================ 使用方法 ============================
 *
 * 1. 安装
 *    Tampermonkey 控制面板 -> 添加新脚本 -> 清空编辑器 -> 粘贴本文件全部内容 -> 保存。
 *
 * 2. 打开面板
 *    访问任意 https://vimm.net/ 页面，右上角会出现“Vimm's Lair 抓取”面板；
 *    点标题栏的“—”可收起/展开。
 *
 * 3. 开始抓取
 *    - 先在“机种”下拉框选择类型（默认 NES）。
 *    - 可选：点“选择目录”，指定封面、meta.csv、error.csv 与 list.csv 的保存目录。
 *    - 设置“开始”“结束”名次（按排行榜名次，从 1 开始）。
 *    - 点“开始”。脚本会读取该机种的排行榜，逐条抓取：
 *      条目 ID（如 834）-> 卡带 ID（如 NES-SM-USA）-> 下载封面（如 NES-SM-USA.jpg）。
 *    - 排行榜每页只有 10 条；每次翻页前随机等待 1~2 秒，并打印一条取页信息。
 *    - 每处理完一个游戏会随机等待 1~5 秒，降低对方压力。
 *    - 只有网络错误会自动重试，最多 10 次，退避 1s -> 2s -> 4s -> 5s -> 5s ...；
 *      网站明确拒绝（HTTP 错误）或封面校验不通过时直接判为失败。
 *
 * 4. 遇到人机验证
 *    - 脚本会立即暂停，并自动在新标签页打开该游戏的详情页。
 *    - 在新标签页完成“Verify you are human”验证；该页也会运行本脚本，
 *      若日志出现“已记录条目 xxx 的卡带 ID”，说明已取到卡带 ID。
 *    - 回到原来的标签页，点“继续”。脚本会优先使用刚缓存的卡带 ID。
 *    - 人机验证不参与自动重试；必须手动点“继续”才会再尝试一次。
 *
 * 5. 暂停 / 继续
 *    - “暂停”在当前请求结束后生效，之后不再发起新请求。
 *    - “继续”从暂停处恢复，已完成/已跳过的游戏不会重复抓取。
 *
 * 6. 记录与去重
 *    - 每成功一个游戏立即写入 Tampermonkey 存储（相当于逐行落盘）。
 *    - 指定目录后，每成功一个游戏还会立即向该目录的 meta.csv 追加一行，
 *      不再重写整个文件；首次写入时自动补表头。
 *    - 每次点“开始”都会重新读取目标目录的 meta.csv，刷新已抓记录；
 *      可手动编辑该 CSV 来增删去重项；CSV 不存在时按空记录处理。
 *    - meta.csv、error.csv、list.csv 都按游戏项 ID（Vimm 条目 ID）去重；
 *      该 ID 在全平台唯一，名次变化不会导致重复。
 *    - meta.csv 列为 number,id,name,cart：
 *        number = Vimm 条目 ID（如 834）
 *        id     = 卡带 ID（如 NES-SM-USA）
 *        name   = 游戏名
 *        cart   = 封面文件名（如 NES-SM-USA.jpg）
 *    - 失败的游戏写入同目录的 error.csv（首列同样是 Vimm 条目 ID）：
 *        number,id,name,cart,reason
 *        id / name / cart 取不到时允许空串；reason 为失败原因。
 *    - error.csv 按 number 去重；开始抓取时会直接跳过其中记录的条目，
 *      如需重试，先从 error.csv 手动删除对应行。
 *    - 排行榜结果会追加写入同目录的 list.csv，列为 rank,id,name：
 *        rank = 名次；id = Vimm 条目 ID；name = 游戏名。
 *      开始抓取时先读该文件；缓存已覆盖的名次页不再列举
 *      （例如第 1~10 名都有，就不请求第 1 页），只补缺失的页。
 *      list.csv 不记录机种，请按机种分目录使用。
 *    - 每次抓取结束后，meta.csv 与 error.csv 会按游戏项 ID 升序重写。
 *    - 菜单命令“清空已抓取记录”可重置 meta 去重数据。
 *
 * 7. 封面保存
 *    - 未指定目录时：封面通过 https://vimm.net/image.php 以 blob 方式下载到
 *      浏览器默认下载目录；首次批量下载时可能询问“是否允许下载多个文件”，请选择允许。
 *    - 指定目录时：封面直接写入该目录，不再弹出下载询问。
 *    - 目录功能依赖 File System Access API，请使用 Chrome / Edge 等浏览器。
 *
 * 8. 可修改的配置
 *    - 文件下方“配置”区域：SYSTEMS（机种代号与卡带 ID 前缀）、
 *      SLEEP_MIN / SLEEP_MAX（每个游戏的随机等待范围，单位毫秒）、
 *      PAGE_SLEEP_MIN / PAGE_SLEEP_MAX（排行榜翻页等待范围，单位毫秒）、
 *      MAX_RETRIES / RETRY_BASE_MS / RETRY_MAX_MS（重试次数与退避）。
 *    - code 直接用于排行榜接口；prefixes 用于从详情页识别卡带 ID。
 *      prefixes 为空数组时，接受“Cart ID / Serial”标签后的任意编号。
 *    - 若某个机种抓不到卡带 ID，按实际页面补上该机种的 prefixes 即可。
 *    - 目标目录选择会记住；浏览器重启后首次点“开始”时需重新授权写入。
 *
 * 9. 该网站支持类型
 *    - Atari2600,Atari5200,NES,SMS,Atari7800,TG16,Genesis,TGCD,SNES,CDi,SegaCD,
 *    - Jaguar,32X,Saturn,PS1,JaguarCD,N64,Dreamcast,PS2,GameCube,Xbox,Xbox360,
 *    - X360-D,PS3,Wii,WiiWare,WiiU,GB,Lynx,GG,VB,GBC,GBA,DS,PSP,3DS
 * 
 * 注意：排行榜名次会变化，所以 --start/--end 只是本次拉取范围；
 *       已抓过的游戏以条目 ID 判断，不受名次变化影响。
 * ==================================================================
 */

(function () {
  'use strict';

  /* ================= 配置 ================= */
  // 机种代号用于排行榜接口，prefixes 用于从详情页识别卡带 ID。
  // prefixes 为空数组时，接受详情页标签后的任意编号。
  const SYSTEMS = [
    { code: 'Atari2600', prefixes: ['CX'] },
    { code: 'Atari5200', prefixes: ['CX'] },
    { code: 'NES', prefixes: ['NES'] },
    { code: 'SMS', prefixes: [] },
    { code: 'Atari7800', prefixes: ['CX'] },
    { code: 'TG16', prefixes: ['TGX'] },
    { code: 'Genesis', prefixes: ['MK', 'GM'] },
    { code: 'TGCD', prefixes: [] },
    { code: 'SNES', prefixes: ['SNS'] },
    { code: 'CDi', prefixes: [] },
    { code: 'SegaCD', prefixes: ['T'] },
    { code: 'Jaguar', prefixes: ['J'] },
    { code: '32X', prefixes: ['MK'] },
    { code: 'Saturn', prefixes: ['T'] },
    { code: 'PS1', prefixes: ['SL', 'SC'] },
    { code: 'JaguarCD', prefixes: [] },
    { code: 'N64', prefixes: ['NUS'] },
    { code: 'Dreamcast', prefixes: ['T'] },
    { code: 'PS2', prefixes: ['SL', 'SC'] },
    { code: 'GameCube', prefixes: ['DOL'] },
    { code: 'Xbox', prefixes: [] },
    { code: 'Xbox360', prefixes: [] },
    { code: 'X360-D', prefixes: [] },
    { code: 'PS3', prefixes: ['BL', 'BC'] },
    { code: 'Wii', prefixes: ['RVL'] },
    { code: 'WiiWare', prefixes: [] },
    { code: 'WiiU', prefixes: ['WUP'] },
    { code: 'GB', prefixes: ['DMG'] },
    { code: 'Lynx', prefixes: ['PA', 'LX'] },
    { code: 'GG', prefixes: [] },
    { code: 'VB', prefixes: ['VUE'] },
    { code: 'GBC', prefixes: ['CGB'] },
    { code: 'GBA', prefixes: ['AGB'] },
    { code: 'DS', prefixes: ['NTR'] },
    { code: 'PSP', prefixes: ['UL', 'UC', 'NP'] },
    { code: '3DS', prefixes: ['CTR'] },
  ];
  const DEFAULT_SYSTEM = 'NES';
  const SYSTEM_KEY = 'vimm_grab_system_v1';
  const CSV_NAME = 'meta.csv';
  const ERROR_CSV_NAME = 'error.csv';
  const LIST_CSV_NAME = 'list.csv';
  const CSV_HEADER = 'number,id,name,cart';
  const ERROR_CSV_HEADER = 'number,id,name,cart,reason';
  const LIST_CSV_HEADER = 'rank,id,name';
  const DIR_DB = 'vimm_grab_db';
  const DIR_STORE = 'handles';
  const DIR_KEY = 'target_dir';
  const STORE_KEY = 'vimm_grab_results_v1';
  const ERROR_STORE_KEY = 'vimm_grab_errors_v1';
  const SERIAL_KEY_PREFIX = 'vimm_grab_serial_';
  const SLEEP_MIN = 1000;          // 每个游戏处理完后的最短等待（毫秒）
  const SLEEP_MAX = 5000;          // 每个游戏处理完后的最长等待（毫秒）
  const PAGE_SLEEP_MIN = 1000;     // 排行榜两次翻页之间的最短等待（毫秒）
  const PAGE_SLEEP_MAX = 2000;     // 排行榜两次翻页之间的最长等待（毫秒）
  const MAX_RETRIES = 10;          // 单个请求最多重试次数
  const RETRY_BASE_MS = 1000;      // 首次重试等待（毫秒）
  const RETRY_MAX_MS = 5000;       // 单次重试等待上限（毫秒）

  /* ================= 工具 ================= */
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const randSleep = () => sleep(SLEEP_MIN + Math.random() * (SLEEP_MAX - SLEEP_MIN));
  const randPageSleep = () => sleep(PAGE_SLEEP_MIN + Math.random() * (PAGE_SLEEP_MAX - PAGE_SLEEP_MIN));

  // 统一重试：只重试网络层错误。
  // HTTP 错误、内容校验失败与人机验证都直接抛出，交给上层处理。
  async function retryRequest(label, task) {
    let lastError = null;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
      if (attempt > 0) {
        const wait = Math.min(RETRY_BASE_MS * 2 ** (attempt - 1), RETRY_MAX_MS);
        log(`[重试] ${label} 第 ${attempt}/${MAX_RETRIES} 次，${wait}ms 后重试（${lastError ? lastError.message : '未知错误'}）`, 'warn');
        await sleep(wait);
      }
      try {
        return await task();
      } catch (e) {
        if (!e || !e.retryable) throw e;
        lastError = e;
      }
    }
    throw new Error(`${lastError ? lastError.message : '请求失败'}（已重试 ${MAX_RETRIES} 次）`);
  }

  // 仅把 fetch 与读取响应体时的异常标记为可重试的网络错误。
  function networkError(action, e) {
    const error = new Error(`${action}：${e && e.message ? e.message : e}`);
    error.retryable = true;
    return error;
  }

  async function fetchNetwork(url, options) {
    try {
      return await fetch(url, options);
    } catch (e) {
      throw networkError('网络错误', e);
    }
  }

  async function readTextNetwork(res) {
    try {
      return await res.text();
    } catch (e) {
      throw networkError('读取响应失败', e);
    }
  }

  async function readBufferNetwork(res) {
    try {
      return await res.arrayBuffer();
    } catch (e) {
      throw networkError('读取封面数据失败', e);
    }
  }

  const SERIAL_RE = /\b([A-Z]{2,6}-[A-Z0-9]{1,10}(?:-[A-Z0-9]{1,10}){0,4})\b/g;
  const IMAGE_EXT = {
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/pjpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
  };

  function looksBlocked(text) {
    const low = String(text).toLowerCase();
    return [
      'turnstile',
      'checking if you are human',
      'verify you are human',
      'challenge-platform',
      'cf-chl',
      'just a moment',
      'attention required',
    ].some((marker) => low.includes(marker));
  }

  function extractSerial(html, prefixes) {
    const list = (prefixes || []).map((prefix) => prefix.toUpperCase());
    const matchPrefix = (value) =>
      !list.length || list.some((prefix) => value.toUpperCase().startsWith(prefix));

    const labelRe = /cart\s*id|cartridge\s*id|serial|product\s*id/gi;
    let match;
    while ((match = labelRe.exec(html)) !== null) {
      const start = match.index + match[0].length;
      const windowHtml = html.slice(start, start + 800);

      // 优先匹配带横杠的编号（如 NES-SM-USA、SLUS-00594）
      const found = [...windowHtml.matchAll(SERIAL_RE)]
        .map((item) => item[1])
        .filter(matchPrefix);
      if (found.length) return found[0];

      // 再兼容 CX2613、7006 这类没有横杠的编号：取标签后第一个含数字的词
      const text = windowHtml.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/gi, ' ');
      const loose = [...text.matchAll(/\b([A-Z0-9][A-Z0-9-]{1,29})\b/g)]
        .map((item) => item[1])
        .filter((value) => /\d/.test(value) && matchPrefix(value));
      if (loose.length) return loose[0];
    }

    const all = [...html.matchAll(SERIAL_RE)]
      .map((item) => item[1])
      .filter(matchPrefix);
    return all[0] || null;
  }

  function sniffExt(buf, contentType) {
    const b = new Uint8Array(buf);
    const ascii = (start, len) => {
      let text = '';
      for (let i = start; i < start + len && i < b.length; i += 1) {
        text += String.fromCharCode(b[i]);
      }
      return text;
    };
    if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return '.jpg';
    if (b[0] === 0x89 && ascii(1, 3) === 'PNG') return '.png';
    if (ascii(0, 6) === 'GIF87a' || ascii(0, 6) === 'GIF89a') return '.gif';
    if (ascii(0, 4) === 'RIFF' && ascii(8, 4) === 'WEBP') return '.webp';
    if (ascii(0, 2) === 'BM') return '.bmp';
    const key = String(contentType || '').split(';')[0].trim().toLowerCase();
    return IMAGE_EXT[key] || null;
  }

  function imageSize(buf) {
    const b = new Uint8Array(buf);
    const dv = new DataView(buf);
    if (b.length >= 24 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) {
      return [dv.getUint32(16), dv.getUint32(20)];
    }
    if (b.length >= 10 && b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46) {
      return [dv.getUint16(6, true), dv.getUint16(8, true)];
    }
    if (b.length >= 4 && b[0] === 0xff && b[1] === 0xd8) {
      let i = 2;
      while (i + 9 < b.length) {
        if (b[i] !== 0xff) {
          i += 1;
          continue;
        }
        const marker = b[i + 1];
        if (marker === 0xff) {
          i += 1;
          continue;
        }
        if (marker === 0xd8 || marker === 0xd9 || (marker >= 0xd0 && marker <= 0xd7) || marker === 0x01) {
          i += 2;
          continue;
        }
        const segLen = dv.getUint16(i + 2);
        if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(marker)) {
          return [dv.getUint16(i + 7), dv.getUint16(i + 5)];
        }
        i += 2 + segLen;
      }
    }
    return null;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  /* ================= 本地存储 ================= */
  function loadRows() {
    try {
      const raw = GM_getValue(STORE_KEY, '[]');
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw;
      return Array.isArray(rows) ? rows : [];
    } catch (e) {
      return [];
    }
  }

  function saveRows(rows) {
    GM_setValue(STORE_KEY, JSON.stringify(rows));
  }

  function loadErrorRows() {
    try {
      const raw = GM_getValue(ERROR_STORE_KEY, '[]');
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw;
      return Array.isArray(rows) ? rows : [];
    } catch (e) {
      return [];
    }
  }

  function saveErrorRows(rows) {
    try {
      GM_setValue(ERROR_STORE_KEY, JSON.stringify(rows));
    } catch (e) {
      // 本地存储失败不影响抓取，文件仍会写入
    }
  }

  let errorRows = loadErrorRows();
  const errorSet = new Set(
    errorRows.map((row) => String(row.number)).filter(Boolean),
  );

  // list.csv 的排行榜缓存，启动抓取时从目标目录读取。
  let listRows = [];

  /* ================= CSV ================= */
  function csvEscape(value) {
    const text = String(value == null ? '' : value);
    return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function buildCsv(rows) {
    const lines = [CSV_HEADER];
    for (const row of rows) {
      lines.push([row.number, row.id, row.name, row.cart].map(csvEscape).join(','));
    }
    return lines.join('\r\n') + '\r\n';
  }

  function buildErrorCsv(rows) {
    const lines = [ERROR_CSV_HEADER];
    for (const row of rows) {
      lines.push([row.number, row.id, row.name, row.cart, row.reason].map(csvEscape).join(','));
    }
    return lines.join('\r\n') + '\r\n';
  }

  function buildListCsv(rows) {
    const lines = [LIST_CSV_HEADER];
    for (const row of rows) {
      lines.push([row.rank, row.id, row.name].map(csvEscape).join(','));
    }
    return lines.join('\r\n') + '\r\n';
  }

  function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = '';
    let quoted = false;
    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"') {
          if (text[i + 1] === '"') {
            field += '"';
            i += 1;
          } else {
            quoted = false;
          }
        } else {
          field += ch;
        }
      } else if (ch === '"') {
        quoted = true;
      } else if (ch === ',') {
        row.push(field);
        field = '';
      } else if (ch === '\r') {
        // 忽略，统一按 \n 换行
      } else if (ch === '\n') {
        row.push(field);
        field = '';
        rows.push(row);
        row = [];
      } else {
        field += ch;
      }
    }
    if (field.length || row.length) {
      row.push(field);
      rows.push(row);
    }
    return rows;
  }

  function rowsFromCsv(text) {
    const raw = String(text || '').replace(/^\uFEFF/, '');
    const table = parseCsv(raw).filter((row) => row.some((cell) => cell.trim()));
    if (!table.length) return [];
    const header = table[0].map((cell) => cell.trim().toLowerCase());
    const numberIndex = header.indexOf('number');
    if (numberIndex < 0) return null;
    const idIndex = header.indexOf('id');
    const nameIndex = header.indexOf('name');
    const cartIndex = header.indexOf('cart');
    const reasonIndex = header.indexOf('reason');
    return table
      .slice(1)
      .map((row) => ({
        number: (row[numberIndex] || '').trim(),
        id: idIndex >= 0 ? (row[idIndex] || '').trim() : '',
        name: nameIndex >= 0 ? (row[nameIndex] || '').trim() : '',
        cart: cartIndex >= 0 ? (row[cartIndex] || '').trim() : '',
        reason: reasonIndex >= 0 ? (row[reasonIndex] || '').trim() : '',
      }))
      .filter((row) => row.number);
  }

  function listRowsFromCsv(text) {
    const raw = String(text || '').replace(/^\uFEFF/, '');
    const table = parseCsv(raw).filter((row) => row.some((cell) => cell.trim()));
    if (!table.length) return { rows: [], total: 0 };
    const header = table[0].map((cell) => cell.trim().toLowerCase());
    const rankIndex = header.indexOf('rank');
    const idIndex = header.indexOf('id');
    if (rankIndex < 0 || idIndex < 0) return null;
    const nameIndex = header.indexOf('name');
    const rows = table
      .slice(1)
      .map((row) => ({
        rank: (row[rankIndex] || '').trim(),
        id: (row[idIndex] || '').trim(),
        name: nameIndex >= 0 ? (row[nameIndex] || '').trim() : '',
      }))
      .filter((row) => /^\d+$/.test(row.rank) && row.id);
    // 游戏项 ID 唯一：同一 ID 只保留最后一条。
    const deduped = new Map();
    for (const row of rows) deduped.set(row.id, row);
    return { rows: [...deduped.values()], total: rows.length };
  }

  /* ================= 目标目录 ================= */
  let dirHandle = null;

  function openDirDb() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        reject(new Error('浏览器不支持 IndexedDB'));
        return;
      }
      const request = window.indexedDB.open(DIR_DB, 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(DIR_STORE)) {
          request.result.createObjectStore(DIR_STORE);
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB 打开失败'));
    });
  }

  async function dirDbGet(key) {
    const db = await openDirDb();
    return new Promise((resolve, reject) => {
      const request = db.transaction(DIR_STORE, 'readonly').objectStore(DIR_STORE).get(key);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function dirDbSet(key, value) {
    const db = await openDirDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(DIR_STORE, 'readwrite');
      tx.objectStore(DIR_STORE).put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function dirDbDelete(key) {
    const db = await openDirDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(DIR_STORE, 'readwrite');
      tx.objectStore(DIR_STORE).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function writeFileToDir(name, data) {
    if (!dirHandle) throw new Error('未选择目标目录');
    const handle = await dirHandle.getFileHandle(name, { create: true });
    const writable = await handle.createWritable();
    await writable.write(data);
    await writable.close();
  }

  async function writeCsvToDir(rows) {
    await writeFileToDir(CSV_NAME, buildCsv(rows));
  }

  async function writeErrorCsvToDir(rows) {
    await writeFileToDir(ERROR_CSV_NAME, buildErrorCsv(rows));
  }

  async function writeListCsvToDir(rows) {
    await writeFileToDir(LIST_CSV_NAME, buildListCsv(rows));
  }

  async function readTextFromDir(name) {
    if (!dirHandle) throw new Error('未选择目标目录');
    const handle = await dirHandle.getFileHandle(name);
    const file = await handle.getFile();
    return file.text();
  }

  async function readCsvFromDir(name = CSV_NAME) {
    return rowsFromCsv(await readTextFromDir(name));
  }

  // 向目录里的 CSV 尾部追加若干行；文件为空时先写表头。
  async function appendCsvRowsToDir(name, header, rows) {
    if (!dirHandle || !rows.length) return;
    const handle = await dirHandle.getFileHandle(name, { create: true });
    const file = await handle.getFile();
    let prefix = header + '\r\n';
    if (file.size > 0) {
      const tail = await file.slice(file.size - 1).text();
      prefix = tail === '\n' ? '' : '\r\n';
    }
    const body = rows.map((values) => values.map(csvEscape).join(',')).join('\r\n');
    const writable = await handle.createWritable({ keepExistingData: true });
    await writable.seek(file.size);
    await writable.write(prefix + body + '\r\n');
    await writable.close();
  }

  async function appendCsvRowToDir(name, header, values) {
    await appendCsvRowsToDir(name, header, [values]);
  }

  /* ================= 界面 ================= */
  const host = document.createElement('div');
  host.id = 'vimm-grab-host';
  host.style.cssText = 'position:fixed;top:12px;right:12px;z-index:2147483647;';
  document.documentElement.appendChild(host);

  const shadow = host.attachShadow({ mode: 'open' });
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      #panel {
        width: 380px;
        max-width: calc(100vw - 24px);
        background: #1b1b26;
        color: #e8e8f0;
        border: 1px solid #3a3a55;
        border-radius: 10px;
        box-shadow: 0 8px 30px rgba(0,0,0,.45);
        font: 12px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
        overflow: hidden;
      }
      #head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 10px;
        background: #222235;
        font-weight: 600;
      }
      #collapse {
        background: none;
        border: 0;
        color: #9aa0ff;
        font-size: 14px;
        cursor: pointer;
        padding: 0 4px;
      }
      #body { padding: 10px; }
      #body.collapsed { display: none; }
      .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
      label { color: #b9b9cc; display: flex; align-items: center; gap: 4px; }
      input[type=number] {
        width: 70px;
        background: #11111a;
        border: 1px solid #3a3a55;
        color: #fff;
        border-radius: 6px;
        padding: 3px 6px;
      }
      select {
        background: #11111a;
        border: 1px solid #3a3a55;
        color: #fff;
        border-radius: 6px;
        padding: 3px 6px;
        font: inherit;
      }
      #dirName {
        color: #b9b9cc;
        word-break: break-all;
      }
      button {
        background: #2f2f4a;
        color: #e8e8f0;
        border: 1px solid #4a4a70;
        border-radius: 6px;
        padding: 4px 10px;
        cursor: pointer;
        font: inherit;
      }
      button:hover:not(:disabled) { background: #3c3c60; }
      button:disabled { opacity: .4; cursor: not-allowed; }
      #progress-wrap {
        height: 8px;
        background: #11111a;
        border-radius: 4px;
        overflow: hidden;
        margin: 6px 0;
      }
      #progress {
        height: 100%;
        width: 0;
        background: linear-gradient(90deg, #6c7bff, #9d6cff);
        transition: width .2s;
      }
      #status { color: #b9b9cc; margin-bottom: 6px; min-height: 16px; }
      #log {
        max-height: 220px;
        overflow: auto;
        background: #11111a;
        border: 1px solid #2c2c40;
        border-radius: 6px;
        padding: 6px;
        font: 11px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        white-space: pre-wrap;
        word-break: break-all;
      }
      #log .ok { color: #7ee2a8; }
      #log .fail { color: #ff8f8f; }
      #log .skip { color: #c9c9a0; }
      #log .info { color: #9aa0ff; }
      #log .warn { color: #ffd479; }
    </style>
    <div id="panel">
      <div id="head">
        <span>Vimm's Lair 抓取</span>
        <button id="collapse" title="收起 / 展开">—</button>
      </div>
      <div id="body">
        <div class="row">
          <label>机种 <select id="system"></select></label>
        </div>
        <div class="row">
          <button id="pickDir">选择目录</button>
          <button id="clearDir" disabled>取消目录</button>
          <span id="dirName">未选择（封面走浏览器下载）</span>
        </div>
        <div class="row">
          <label>开始 <input id="start" type="number" min="1" step="1" value="1"></label>
          <label>结束 <input id="end" type="number" min="1" step="1" value="10"></label>
        </div>
        <div class="row">
          <button id="run">开始</button>
          <button id="pause" disabled>暂停</button>
          <button id="resume" disabled>继续</button>
        </div>
        <div id="progress-wrap"><div id="progress"></div></div>
        <div id="status">空闲</div>
        <div id="log"></div>
      </div>
    </div>
  `;

  const $ = (selector) => shadow.querySelector(selector);
  const bodyEl = $('#body');
  const systemSelect = $('#system');
  const pickDirBtn = $('#pickDir');
  const clearDirBtn = $('#clearDir');
  const dirNameEl = $('#dirName');
  const startInput = $('#start');
  const endInput = $('#end');
  const runBtn = $('#run');
  const pauseBtn = $('#pause');
  const resumeBtn = $('#resume');
  const collapseBtn = $('#collapse');
  const progressEl = $('#progress');
  const statusEl = $('#status');
  const logEl = $('#log');

  for (const system of SYSTEMS) {
    const option = document.createElement('option');
    option.value = system.code;
    option.textContent = system.code;
    systemSelect.appendChild(option);
  }
  const savedSystem = GM_getValue(SYSTEM_KEY, DEFAULT_SYSTEM);
  systemSelect.value = SYSTEMS.some((system) => system.code === savedSystem)
    ? savedSystem
    : DEFAULT_SYSTEM;
  systemSelect.addEventListener('change', () => GM_setValue(SYSTEM_KEY, systemSelect.value));

  function currentSystem() {
    return SYSTEMS.find((system) => system.code === systemSelect.value)
      || SYSTEMS.find((system) => system.code === DEFAULT_SYSTEM);
  }

  function directoryPicker() {
    if (typeof window.showDirectoryPicker === 'function') {
      return window.showDirectoryPicker.bind(window);
    }
    if (typeof unsafeWindow !== 'undefined'
      && typeof unsafeWindow.showDirectoryPicker === 'function') {
      return unsafeWindow.showDirectoryPicker.bind(unsafeWindow);
    }
    return null;
  }

  function updateDirLabel() {
    if (dirHandle) {
      dirNameEl.textContent = `目录：${dirHandle.name}`;
      dirNameEl.title = '封面、meta.csv、error.csv 与 list.csv 会保存到此目录';
    } else {
      dirNameEl.textContent = '未选择（封面走浏览器下载）';
      dirNameEl.title = '';
    }
    clearDirBtn.disabled = !dirHandle;
  }

  async function ensureDirectoryPermission() {
    if (!dirHandle) return true;
    try {
      const status = await dirHandle.requestPermission({ mode: 'readwrite' });
      if (status !== 'granted') {
        log('没有目标目录的写入权限，请重新选择目录', 'fail');
        return false;
      }
      return true;
    } catch (e) {
      log(`目录权限请求失败：${e.message}`, 'fail');
      return false;
    }
  }

  async function refreshDoneFromDirectory() {
    if (!dirHandle) return;
    try {
      const rows = await readCsvFromDir();
      if (rows === null) {
        log(`${CSV_NAME} 缺少 number 列，沿用现有记录`, 'warn');
      } else {
        const seenNumbers = new Set();
        const deduped = rows.filter((row) => {
          const key = String(row.number);
          if (seenNumbers.has(key)) return false;
          seenNumbers.add(key);
          return true;
        });
        saveRows(deduped);
        log(`已从 ${dirHandle.name}/${CSV_NAME} 刷新 ${deduped.length} 条已抓记录`, 'info');
        if (deduped.length !== rows.length) {
          try {
            await writeCsvToDir(deduped);
            log(`${CSV_NAME} 中有重复游戏项，已按 ID 去重`, 'info');
          } catch (e) {
            log(`清理 ${CSV_NAME} 重复项失败：${e.message}`, 'warn');
          }
        }
      }
    } catch (e) {
      if (e && e.name === 'NotFoundError') {
        saveRows([]);
        log(`目标目录中没有 ${CSV_NAME}，已抓记录按空处理`, 'info');
      } else {
        log(`读取 ${CSV_NAME} 失败：${e.message}`, 'fail');
      }
    }

    try {
      const errorList = await readCsvFromDir(ERROR_CSV_NAME);
      if (errorList === null) {
        log(`${ERROR_CSV_NAME} 缺少 number 列，沿用现有记录`, 'warn');
      } else {
        const seenNumbers = new Set();
        errorRows = errorList.filter((row) => {
          const key = String(row.number);
          if (seenNumbers.has(key)) return false;
          seenNumbers.add(key);
          return true;
        });
        errorSet.clear();
        for (const row of errorRows) errorSet.add(String(row.number));
        saveErrorRows(errorRows);
        log(`已从 ${dirHandle.name}/${ERROR_CSV_NAME} 刷新 ${errorRows.length} 条失败记录`, 'info');
        if (errorRows.length !== errorList.length) {
          try {
            await writeErrorCsvToDir(errorRows);
            log(`${ERROR_CSV_NAME} 中有重复条目，已按首列去重`, 'info');
          } catch (e) {
            log(`清理 ${ERROR_CSV_NAME} 重复项失败：${e.message}`, 'warn');
          }
        }
      }
    } catch (e) {
      if (e && e.name === 'NotFoundError') {
        errorRows = [];
        errorSet.clear();
        saveErrorRows(errorRows);
        log(`目标目录中没有 ${ERROR_CSV_NAME}，失败记录按空处理`, 'info');
      } else {
        log(`读取 ${ERROR_CSV_NAME} 失败：${e.message}`, 'fail');
      }
    }

    try {
      const parsed = listRowsFromCsv(await readTextFromDir(LIST_CSV_NAME));
      if (parsed === null) {
        listRows = [];
        log(`${LIST_CSV_NAME} 缺少 rank/id 列，本次会请求排行榜`, 'warn');
      } else {
        listRows = parsed.rows;
        log(`已从 ${dirHandle.name}/${LIST_CSV_NAME} 读取 ${listRows.length} 条排行榜缓存`, 'info');
        if (listRows.length !== parsed.total) {
          try {
            await writeListCsvToDir(listRows);
            log(`${LIST_CSV_NAME} 中有重复游戏项，已按 ID 去重`, 'info');
          } catch (e) {
            log(`清理 ${LIST_CSV_NAME} 重复项失败：${e.message}`, 'warn');
          }
        }
      }
    } catch (e) {
      if (e && e.name === 'NotFoundError') {
        listRows = [];
        log(`目标目录中没有 ${LIST_CSV_NAME}，本次会请求排行榜`, 'info');
      } else {
        listRows = [];
        log(`读取 ${LIST_CSV_NAME} 失败：${e.message}`, 'fail');
      }
    }
  }

  const state = { running: false, paused: false, total: 0, completed: 0 };
  let resumeResolvers = [];

  function log(message, cls) {
    const line = document.createElement('div');
    if (cls) line.className = cls;
    line.textContent = message;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function setProgress(ratio) {
    const clamped = Math.max(0, Math.min(1, ratio));
    progressEl.style.width = (clamped * 100).toFixed(1) + '%';
  }

  function updateButtons() {
    runBtn.disabled = state.running;
    systemSelect.disabled = state.running;
    pickDirBtn.disabled = state.running || !directoryPicker();
    clearDirBtn.disabled = state.running || !dirHandle;
    pauseBtn.disabled = !state.running || state.paused;
    resumeBtn.disabled = !state.running || !state.paused;
  }

  function setPaused(paused) {
    state.paused = paused;
    if (!paused) {
      const waiters = resumeResolvers;
      resumeResolvers = [];
      waiters.forEach((resolve) => resolve());
    }
    updateButtons();
  }

  function waitIfPaused() {
    return new Promise((resolve) => {
      if (!state.paused) {
        resolve();
        return;
      }
      resumeResolvers.push(resolve);
    });
  }

  function bumpProgress() {
    state.completed += 1;
    setProgress(state.total ? state.completed / state.total : 0);
    setStatus(`进度 ${state.completed}/${state.total}`);
  }

  /* ================= 数据抓取 ================= */
  async function appendListingToDir(rows) {
    if (!rows.length) return;
    // 同步内存缓存，同一页面里再次抓取时也能直接复用。
    listRows = listRows.concat(rows);
    if (!dirHandle) return;
    try {
      await appendCsvRowsToDir(
        LIST_CSV_NAME,
        LIST_CSV_HEADER,
        rows.map((row) => [row.rank, row.id, row.name]),
      );
      log(`[排行榜] 已向 ${dirHandle.name}/${LIST_CSV_NAME} 追加 ${rows.length} 条`, 'info');
    } catch (e) {
      log(`追加 ${LIST_CSV_NAME} 失败：${e.message}`, 'warn');
    }
  }

  async function loadRanking(count, systemCode) {
    // list.csv 按游戏项 ID 去重，后写入的记录覆盖先前的。
    const merged = new Map();
    for (const row of listRows) merged.set(row.id, row);
    const cachedRanks = new Set();
    for (const row of merged.values()) cachedRanks.add(Number(row.rank));

    // 只列举缓存没有覆盖的页；例如 1~10 名都已缓存，就不请求第 1 页。
    const pageCount = Math.min(Math.ceil(count / 10), 100);
    const pagesToFetch = [];
    for (let page = 1; page <= pageCount; page += 1) {
      const firstRank = (page - 1) * 10 + 1;
      const lastRank = Math.min(page * 10, count);
      let covered = true;
      for (let rank = firstRank; rank <= lastRank; rank += 1) {
        if (!cachedRanks.has(rank)) {
          covered = false;
          break;
        }
      }
      if (covered) {
        log(`[排行榜] 第 ${page} 页已有缓存，跳过列举`, 'info');
      } else {
        pagesToFetch.push(page);
      }
    }

    const toGames = () => [...merged.values()]
      .sort((a, b) => Number(a.rank) - Number(b.rank))
      .slice(0, count)
      .map((row) => ({ id: row.id, name: row.name }));

    if (!pagesToFetch.length) {
      log(`[排行榜] ${LIST_CSV_NAME} 已覆盖 1~${count} 名，跳过列举请求`, 'info');
      return toGames();
    }

    const newRows = [];
    let requests = 0;
    for (const page of pagesToFetch) {
      if (requests > 0) await randPageSleep();
      requests += 1;
      const url = `/vault/ajax/loadTopTen.php?system=${encodeURIComponent(systemCode)}&page=${page}`;
      const text = await retryRequest(`排行榜第 ${page} 页`, async () => {
        const res = await fetchNetwork(url, { credentials: 'same-origin' });
        if (!res.ok) throw new Error(`排行榜 HTTP ${res.status}`);
        const body = await readTextNetwork(res);
        if (looksBlocked(body)) {
          const error = new Error('排行榜接口需要人机验证');
          error.blocked = true;
          throw error;
        }
        return body;
      });
      const doc = new DOMParser().parseFromString(text, 'text/html');
      const rows = [...doc.querySelectorAll('a[href]')]
        .filter((anchor) => /^\d+$/.test(anchor.getAttribute('href')))
        .map((anchor) => ({
          id: anchor.getAttribute('href'),
          name: anchor.textContent.replace(/\s+/g, ' ').trim(),
        }));
      if (!rows.length) {
        log(`[排行榜] 第 ${page} 页没有数据，停止翻页`, 'info');
        break;
      }
      let added = 0;
      rows.forEach((game, index) => {
        const rank = (page - 1) * 10 + index + 1;
        if (cachedRanks.has(rank)) return;
        if (merged.has(game.id)) return;
        const row = { rank: String(rank), id: game.id, name: game.name };
        merged.set(game.id, row);
        cachedRanks.add(rank);
        newRows.push(row);
        added += 1;
      });
      const coveredCount = [...merged.values()]
        .filter((row) => Number(row.rank) <= count).length;
      log(`[排行榜] 第 ${page} 页成功：${rows.length} 条，新增 ${added} 条，累计 ${coveredCount}/${count}`, 'info');
    }

    if (newRows.length) await appendListingToDir(newRows);
    return toGames();
  }

  async function fetchSerial(game, prefixes) {
    const cached = GM_getValue(SERIAL_KEY_PREFIX + game.id, '');
    if (cached) return String(cached);

    const text = await retryRequest(`条目 ${game.id} 详情页`, async () => {
      const res = await fetchNetwork(`/vault/${game.id}`, { credentials: 'same-origin' });
      const body = await readTextNetwork(res);
      if (looksBlocked(body)) {
        const error = new Error('需要人机验证');
        error.blocked = true;
        throw error;
      }
      if (!res.ok && res.status !== 404) {
        throw new Error(`详情页 HTTP ${res.status}`);
      }
      return body;
    });

    const serial = extractSerial(text, prefixes);
    if (!serial) throw new Error('详情页中未找到卡带 ID');
    GM_setValue(SERIAL_KEY_PREFIX + game.id, serial);
    return serial;
  }

  async function fetchCover(game, serial) {
    const url = `/image.php?type=cart&id=${encodeURIComponent(game.id)}&page=1`;
    const { data, contentType, extension } = await retryRequest(`条目 ${game.id} 封面`, async () => {
      const res = await fetchNetwork(url, {
        credentials: 'same-origin',
        referrer: 'https://vimm.net/',
      });
      if (!res.ok) throw new Error(`封面 HTTP ${res.status}`);

      const body = await readBufferNetwork(res);
      if (body.byteLength < 1024) throw new Error(`封面文件过小 (${body.byteLength} 字节)`);
      const dims = imageSize(body);
      if (dims && dims[0] === 400 && dims[1] === 100) {
        throw new Error('拿到的是防盗链占位图 (400x100)');
      }

      const type = res.headers.get('Content-Type') || '';
      const ext = sniffExt(body, type);
      if (!ext) throw new Error(`未知图片格式 (${type || '无 Content-Type'})`);
      return { data: body, contentType: type, extension: ext };
    });

    const filename = serial + extension;
    const mime = contentType.split(';')[0].trim() || 'image/' + extension.slice(1);
    const blob = new Blob([data], { type: mime });
    if (dirHandle) {
      await writeFileToDir(filename, blob);
    } else {
      downloadBlob(blob, filename);
    }
    return { filename, bytes: data.byteLength };
  }

  function openVerifyTab(vaultId) {
    const url = `https://vimm.net/vault/${vaultId}`;
    try {
      GM_openInTab(url, { active: true, insert: true, setParent: true });
    } catch (e) {
      window.open(url, '_blank');
    }
  }

  async function recordError(game, serial, reason) {
    const number = String(game.id);
    if (errorSet.has(number)) return;
    const row = {
      number,
      id: serial || '',
      name: game.name || '',
      cart: '',
      reason: reason || '未知错误',
    };
    errorRows.push(row);
    errorSet.add(number);
    saveErrorRows(errorRows);
    if (!dirHandle) return;
    try {
      await appendCsvRowToDir(
        ERROR_CSV_NAME,
        ERROR_CSV_HEADER,
        [row.number, row.id, row.name, row.cart, row.reason],
      );
    } catch (e) {
      log(`追加 ${ERROR_CSV_NAME} 失败：${e.message}`, 'warn');
    }
  }

  function compareByNumber(a, b) {
    const na = Number(a.number);
    const nb = Number(b.number);
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
    return String(a.number).localeCompare(String(b.number));
  }

  // 抓取结束后把 meta.csv 与 error.csv 按游戏项 ID 升序重写。
  async function sortCsvFiles() {
    if (!dirHandle) return;

    try {
      const rows = await readCsvFromDir();
      if (rows !== null) {
        const sorted = rows.slice().sort(compareByNumber);
        saveRows(sorted);
        await writeCsvToDir(sorted);
        log(`${CSV_NAME} 已按游戏项 ID 升序重排（${sorted.length} 条）`, 'info');
      }
    } catch (e) {
      if (!e || e.name !== 'NotFoundError') {
        log(`重排 ${CSV_NAME} 失败：${e.message}`, 'warn');
      }
    }

    try {
      const rows = await readCsvFromDir(ERROR_CSV_NAME);
      if (rows !== null) {
        errorRows = rows.slice().sort(compareByNumber);
        saveErrorRows(errorRows);
        await writeErrorCsvToDir(errorRows);
        log(`${ERROR_CSV_NAME} 已按游戏项 ID 升序重排（${errorRows.length} 条）`, 'info');
      }
    } catch (e) {
      if (!e || e.name !== 'NotFoundError') {
        log(`重排 ${ERROR_CSV_NAME} 失败：${e.message}`, 'warn');
      }
    }
  }

  /* ================= 主流程 ================= */
  async function runRange(start, end, system) {
    state.running = true;
    state.completed = 0;
    state.total = Math.max(0, end - start + 1);
    setPaused(false);
    setProgress(0);
    updateButtons();
    setStatus('读取排行榜...');
    log(`开始：${system.code} 第 ${start}~${end} 名`, 'info');
    log('提示：浏览器若询问是否允许下载多个文件，请选择允许。', 'info');

    const rows = loadRows();
    const done = new Set(rows.map((row) => String(row.number)));
    log(`已有记录 ${done.size} 条（按第一列的条目 ID 去重）`, 'info');

    let games;
    try {
      games = await loadRanking(end, system.code);
    } catch (e) {
      log(`读取排行榜失败：${e.message}`, 'fail');
      state.running = false;
      setStatus('已停止');
      await sortCsvFiles();
      updateButtons();
      return;
    }

    if (!games.length) {
      log('排行榜为空', 'fail');
      state.running = false;
      setStatus('已停止');
      await sortCsvFiles();
      updateButtons();
      return;
    }
    if (games.length < end) {
      log(`注意：排行榜只返回 ${games.length} 条`, 'warn');
    }

    const selected = games.slice(start - 1, end);
    state.total = selected.length;
    setProgress(0);

    let ok = 0;
    let fail = 0;
    let skip = 0;

    for (let i = 0; i < selected.length; i += 1) {
      await waitIfPaused();

      const game = selected[i];
      const rank = start + i;
      const label = `第${rank}名 | 条目ID ${game.id} | ${game.name}`;

      if (done.has(String(game.id))) {
        skip += 1;
        log(`[跳过] ${label}（已抓过）`, 'skip');
        bumpProgress();
        continue;
      }

      if (errorSet.has(String(game.id))) {
        skip += 1;
        log(`[跳过] ${label}（error.csv 已记录）`, 'skip');
        bumpProgress();
        continue;
      }

      let serial = null;
      let failed = false;

      while (serial === null) {
        await waitIfPaused();
        setStatus(`抓取中：${label}`);
        try {
          serial = await fetchSerial(game, system.prefixes);
        } catch (e) {
          if (e && e.blocked) {
            // 不自动重试：打开页面让用户手动验证，然后暂停等待用户点“继续”
            log(`[验证] ${label} 需要人机验证，已打开页面；验证完成后点“继续”`, 'warn');
            openVerifyTab(game.id);
            setPaused(true);
            setStatus('等待人机验证，完成后点“继续”');
            continue;
          }
          failed = true;
          fail += 1;
          log(`[失败] ${label} | ${e.message}`, 'fail');
          await recordError(game, null, e.message);
          break;
        }
      }

      if (failed) {
        bumpProgress();
        await randSleep();
        continue;
      }

      try {
        await waitIfPaused();
        const { filename, bytes } = await fetchCover(game, serial);
        const row = {
          number: String(game.id),
          id: serial,
          name: game.name,
          cart: filename,
        };
        rows.push(row);
        saveRows(rows);
        done.add(String(game.id));
        if (dirHandle) {
          try {
            await appendCsvRowToDir(CSV_NAME, CSV_HEADER, [row.number, row.id, row.name, row.cart]);
          } catch (e) {
            log(`追加 ${CSV_NAME} 失败：${e.message}`, 'warn');
          }
        }
        ok += 1;
        log(`[成功] ${label} | 卡带ID ${serial} | ${filename} (${bytes} 字节${dirHandle ? '，已追加到目录' : ''})`, 'ok');
      } catch (e) {
        fail += 1;
        log(`[失败] ${label} | ${e.message}`, 'fail');
        await recordError(game, serial, e.message);
      }

      bumpProgress();
      // 每处理一个游戏随机等待 1~5 秒，降低对方压力
      await randSleep();
    }

    state.running = false;
    setPaused(false);
    await sortCsvFiles();
    updateButtons();
    setProgress(1);
    setStatus('完成');
    log(`结束：成功 ${ok} 个，失败 ${fail} 个，跳过 ${skip} 个`, 'info');
  }

  /* ================= 在详情页缓存卡带 ID ================= */
  async function cacheSerialFromVaultPage() {
    const match = location.pathname.match(/^\/vault\/(\d+)\/?$/);
    if (!match) return;
    const vaultId = match[1];
    if (GM_getValue(SERIAL_KEY_PREFIX + vaultId, '')) return;

    const prefixes = currentSystem().prefixes;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const html = document.documentElement.innerHTML;
      if (!looksBlocked(html)) {
        const serial = extractSerial(html, prefixes);
        if (serial) {
          GM_setValue(SERIAL_KEY_PREFIX + vaultId, serial);
          log(`已记录条目 ${vaultId} 的卡带 ID：${serial}。回到抓取标签点“继续”。`, 'info');
          return;
        }
      }
      await sleep(2000);
    }
  }

  /* ================= 事件绑定 ================= */
  runBtn.addEventListener('click', async () => {
    const start = parseInt(startInput.value, 10);
    const end = parseInt(endInput.value, 10);
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start) {
      log('名次区间无效：开始必须 >= 1，结束必须 >= 开始', 'warn');
      return;
    }
    if (state.running) return;
    runBtn.disabled = true;
    logEl.textContent = '';
    if (!(await ensureDirectoryPermission())) {
      updateButtons();
      return;
    }
    await refreshDoneFromDirectory();
    runRange(start, end, currentSystem());
  });

  pauseBtn.addEventListener('click', () => {
    if (!state.running) return;
    setPaused(true);
    setStatus('已暂停');
    log('已暂停', 'info');
  });

  resumeBtn.addEventListener('click', () => {
    if (!state.running) return;
    setPaused(false);
    setStatus('继续中...');
    log('继续', 'info');
  });

  pickDirBtn.addEventListener('click', async () => {
    const picker = directoryPicker();
    if (!picker) {
      log('当前浏览器不支持选择目录，请使用 Chrome / Edge', 'warn');
      return;
    }
    try {
      const handle = await picker({ mode: 'readwrite' });
      dirHandle = handle;
      updateDirLabel();
      updateButtons();
      log(`已选择目标目录：${handle.name}`, 'info');
      try {
        await dirDbSet(DIR_KEY, handle);
      } catch (e) {
        log('目录已选中，但浏览器无法记住该选择；刷新页面后需重新选择', 'warn');
      }
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      log(`选择目录失败：${e.message}`, 'fail');
    }
  });

  clearDirBtn.addEventListener('click', async () => {
    dirHandle = null;
    updateDirLabel();
    updateButtons();
    try {
      await dirDbDelete(DIR_KEY);
    } catch (e) {
      // 忽略清理失败
    }
    log('已取消目标目录，封面改回浏览器下载', 'info');
  });

  collapseBtn.addEventListener('click', () => {
    bodyEl.classList.toggle('collapsed');
    collapseBtn.textContent = bodyEl.classList.contains('collapsed') ? '+' : '—';
  });

  if (typeof GM_registerMenuCommand === 'function') {
    GM_registerMenuCommand('清空已抓取记录', async () => {
      const extra = dirHandle ? '目标目录中的 meta.csv 也会被清空。' : '';
      if (window.confirm(`确定清空已抓取记录？此操作不可恢复。${extra}`)) {
        saveRows([]);
        if (!dirHandle) {
          log('已清空已抓取记录', 'info');
          return;
        }
        if (!await ensureDirectoryPermission()) {
          log('已清空内存记录，但目标目录的 meta.csv 未清空', 'warn');
          return;
        }
        try {
          await writeCsvToDir([]);
          log('已清空已抓取记录（含 meta.csv）', 'info');
        } catch (e) {
          log(`清空 ${CSV_NAME} 失败：${e.message}`, 'fail');
        }
      }
    });
  }

  /* ================= 启动 ================= */
  updateDirLabel();
  updateButtons();
  setStatus('空闲');
  log('准备就绪：设置名次区间后点“开始”。', 'info');
  log('去重依据为 CSV 第一列（Vimm 条目 ID，如 834）。', 'info');

  if (directoryPicker()) {
    dirDbGet(DIR_KEY)
      .then((handle) => {
        if (!handle) return;
        dirHandle = handle;
        updateDirLabel();
        updateButtons();
        log(`已恢复目标目录：${handle.name}（点“开始”时会请求写入权限）`, 'info');
      })
      .catch(() => {
        log('读取已保存的目标目录失败，请重新选择目录', 'warn');
      });
  } else {
    pickDirBtn.disabled = true;
    dirNameEl.textContent = '当前浏览器不支持选择目录';
  }

  cacheSerialFromVaultPage();
})();
