// ==UserScript==
// @name         Vimm's Lair 按名称抓取卡带图
// @namespace    https://vimm.net/
// @version      1.0.0
// @description  从本地 CSV 读取游戏英文名（第二列），按机种搜索 Vimm's Lair，只下载完全同名且区域为 USA / Japan 的卡带图片；成功与失败分别记录到 list.csv、error.csv，支持断点续跑
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
 *    访问任意 https://vimm.net/ 页面，右上角会出现“Vimm's Lair 按名称抓图”面板；
 *    点标题栏的“—”可收起/展开。
 *
 * 3. 准备名称文件
 *    - 点“选择名称文件”，选择本地 CSV，例如 backend/search/rankings/nes.csv。
 *    - 默认取每行第二列（英文名）；没有第二列时取第一列。
 *    - 首行若是“英文名 / English Name / Name / Title”等表头会自动跳过。
 *    - 也支持纯文本文件：一行一个名称（名称里不要带英文逗号）。
 *
 * 4. 选择输出目录
 *    - 点“选择输出目录”，封面、list.csv、error.csv 都会写入该目录。
 *    - 目录选择会记住；浏览器重启后首次点“开始”时需重新授权写入。
 *    - 目录功能依赖 File System Access API，请使用 Chrome / Edge 等浏览器。
 *    - 不要把本脚本和旧的“排行榜抓取”脚本指向同一个目录：
 *      两个脚本的 list.csv / error.csv 列结构不同，本脚本会拒绝覆盖。
 *    - list.csv 不记录机种，请为不同机种选择不同输出目录。
 *
 * 5. 开始抓取
 *    - 选择机种，点“开始”。脚本对每个名称执行：
 *      搜索 -> 在结果中筛出完全同名且区域为 USA / Japan 的条目
 *      -> 进入详情页读取卡带 ID -> 下载卡带图片。
 *    - 完全同名指忽略大小写与多余空格后一致。
 *    - 每个区域最多取一条：优先没有 VC / Prototype / Demo 等角标的普通条目；
 *      没有普通条目时才退回使用角标条目；同区域有多条普通条目时取第一条。
 *    - 只认 USA 和 Japan。若某个标题没有 USA 条目但有 World 条目，
 *      则把 World 当作美版使用（例如 NES 的 Super Mario Bros.）；
 *      Europe / Asia 等其它区域不会下载。
 *    - 每成功一条输出一行日志，之后随机等待 1000~2000 毫秒再处理下一条。
 *
 * 6. 文件命名
 *    - 详情页能读到卡带 ID 时：<卡带ID>.<后缀>，如 NES-SM-USA.jpg、HVC-SM.png。
 *    - 读不到卡带 ID 时：<游戏名称>.<区域>.<后缀>，如 Super Mario Bros..USA.jpg。
 *    - 同一轮里文件名冲突时，后一条会追加“-<条目ID>”，避免互相覆盖。
 *
 * 7. 记录与去重
 *    - list.csv 列：query,name,region,id,cart,status
 *        query  = 输入文件里的英文名
 *        name   = Vimm 上的完全同名标题
 *        region = USA / Japan
 *        id     = Vimm 条目 ID（如 834）
 *        cart   = 已下载的封面文件名
 *        status = ok 表示已下载；pending 表示已匹配但尚未成功下载
 *    - error.csv 列：query,name,region,id,reason
 *        id 为空表示搜索阶段的失败（搜索报错或没有匹配条目）；
 *        id 不为空表示该条目下载失败。
 *    - 开始时会先读 list.csv 与 error.csv：
 *        list.csv 中 status=ok 的条目直接跳过；
 *        搜索匹配过的名称会复用 list.csv 的条目，不重复搜索；
 *        error.csv 中记录的条目直接跳过，不再自动重试。
 *    - 如需重试失败条目：清空 error.csv（菜单命令），再点“开始”。
 *      list.csv 里保留的 pending 行会重新下载，无需重新搜索。
 *    - 每次抓取结束后，list.csv 与 error.csv 会按名称、条目 ID 排序并去重重写。
 *
 * 8. 暂停 / 继续 / 人机验证
 *    - “暂停”在当前请求结束后生效；“继续”从暂停处恢复。
 *    - 遇到人机验证时脚本立即暂停，并在新标签页打开搜索页或详情页。
 *    - 在新标签页完成验证；详情页会缓存卡带 ID。
 *    - 回到原标签页点“继续”，脚本优先使用刚缓存的卡带 ID。
 *    - 人机验证不参与自动重试，必须手动点“继续”。
 *
 * 9. 可修改的配置
 *    - SLEEP_MIN / SLEEP_MAX：每条游戏处理完后的随机等待范围（毫秒）。
 *    - MAX_RETRIES / RETRY_BASE_MS / RETRY_MAX_MS：网络错误重试次数与退避。
 *    - 网站明确拒绝（HTTP 错误）、封面校验失败、人机验证都不自动重试。
 *
 * 10. 菜单命令
 *    - “清空已抓记录 (list.csv)”：清空已下载记录与搜索缓存。
 *    - “清空失败记录 (error.csv)”：清空失败记录，之后会重试这些条目。
 * ==================================================================
 */

(function () {
  'use strict';

  /* ================= 配置 ================= */
  const SYSTEMS = [
    'Atari2600', 'Atari5200', 'NES', 'SMS', 'Atari7800', 'TG16', 'Genesis', 'TGCD',
    'SNES', 'CDi', 'SegaCD', 'Jaguar', '32X', 'Saturn', 'PS1', 'JaguarCD', 'N64',
    'Dreamcast', 'PS2', 'GameCube', 'Xbox', 'Xbox360', 'X360-D', 'PS3', 'Wii',
    'WiiWare', 'WiiU', 'GB', 'Lynx', 'GG', 'VB', 'GBC', 'GBA', 'DS', 'PSP', '3DS',
  ];
  const DEFAULT_SYSTEM = 'NES';
  const SYSTEM_KEY = 'vimm_cart_system_v1';
  const NAMES_KEY = 'vimm_cart_names_v1';
  const LIST_CSV_NAME = 'list.csv';
  const ERROR_CSV_NAME = 'error.csv';
  const LIST_CSV_HEADER = 'query,name,region,id,cart,status';
  const ERROR_CSV_HEADER = 'query,name,region,id,reason';
  const DIR_DB = 'vimm_cart_grab_db';
  const DIR_STORE = 'handles';
  const DIR_KEY = 'target_dir';
  const SERIAL_KEY_PREFIX = 'vimm_cart_serial_';
  const SLEEP_MIN = 1000;          // 每条游戏处理完后的最短等待（毫秒）
  const SLEEP_MAX = 2000;          // 每条游戏处理完后的最长等待（毫秒）
  const MAX_RETRIES = 10;          // 单个请求最多重试次数
  const RETRY_BASE_MS = 1000;      // 首次重试等待（毫秒）
  const RETRY_MAX_MS = 5000;       // 单次重试等待上限（毫秒）

  /* ================= 工具 ================= */
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const randSleep = () => sleep(SLEEP_MIN + Math.random() * (SLEEP_MAX - SLEEP_MIN));

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

  const CART_ID_RE = /\b([A-Z][A-Z0-9]{0,5}-[A-Z0-9]{1,12}(?:-[A-Z0-9]{1,12}){0,4})\b/g;
  const IMAGE_EXT = {
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/pjpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
  };

  function normalizeName(value) {
    return String(value == null ? '' : value)
      .normalize('NFC')
      .replace(/\s+/g, ' ')
      .trim();
  }

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

  // 从详情页 HTML 中读取卡带 ID。
  // 优先看 “Cart ID / Cartridge ID / Serial / Product ID” 标签后的内容；
  // 再退回到页面中第一个像卡带编号的字符串。
  function extractCartId(html) {
    const labelRe = /cart\s*id|cartridge\s*id|serial|product\s*id|game\s*id/gi;
    let match;
    while ((match = labelRe.exec(html)) !== null) {
      const start = match.index + match[0].length;
      const windowHtml = html.slice(start, start + 1200);

      // 优先匹配带横杠的编号（NES-SM-USA、HVC-SM、T-1207 等）
      const hyphenated = [...windowHtml.matchAll(CART_ID_RE)].map((item) => item[1]);
      if (hyphenated.length) return hyphenated[0];

      // 再兼容 CX2613、7006 这类没有横杠的编号：取标签后第一个含数字的词
      const text = windowHtml.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/gi, ' ');
      const loose = [...text.matchAll(/\b([A-Z0-9][A-Z0-9-]{1,29})\b/g)]
        .map((item) => item[1])
        .filter((value) => /\d/.test(value));
      const withLetter = loose.find((value) => /[A-Z]/.test(value));
      if (withLetter) return withLetter;
      if (loose.length) return loose[0];
    }

    const all = [...html.matchAll(CART_ID_RE)].map((item) => item[1]);
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

  // Windows / macOS 都不允许的字符替换为下划线；保留名称中的点号。
  function safePart(value) {
    const text = String(value == null ? '' : value)
      .replace(/[\\/:*?"<>|\x00-\x1f]/g, '_')
      .replace(/\s+/g, ' ')
      .trim();
    return text || 'unknown';
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

  /* ================= CSV ================= */
  function csvEscape(value) {
    const text = String(value == null ? '' : value);
    return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
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

  function parseCsvTable(text) {
    const raw = String(text || '').replace(/^﻿/, '');
    return parseCsv(raw).filter((row) => row.some((cell) => cell.trim()));
  }

  function buildListCsv(rows) {
    const lines = [LIST_CSV_HEADER];
    for (const row of rows) {
      lines.push([row.query, row.name, row.region, row.id, row.cart, row.status].map(csvEscape).join(','));
    }
    return lines.join('\r\n') + '\r\n';
  }

  function buildErrorCsv(rows) {
    const lines = [ERROR_CSV_HEADER];
    for (const row of rows) {
      lines.push([row.query, row.name, row.region, row.id, row.reason].map(csvEscape).join(','));
    }
    return lines.join('\r\n') + '\r\n';
  }

  function listRowsFromCsv(text) {
    const table = parseCsvTable(text);
    if (!table.length) return { rows: [], total: 0 };
    const header = table[0].map((cell) => cell.trim().toLowerCase());
    const idx = (name) => header.indexOf(name);
    if (idx('query') < 0 || idx('name') < 0 || idx('id') < 0) return null;
    const rows = table.slice(1).map((row) => {
      const cart = idx('cart') >= 0 ? (row[idx('cart')] || '').trim() : '';
      const statusText = idx('status') >= 0 ? (row[idx('status')] || '').trim().toLowerCase() : '';
      return {
        query: (row[idx('query')] || '').trim(),
        name: (row[idx('name')] || '').trim(),
        region: idx('region') >= 0 ? (row[idx('region')] || '').trim() : '',
        id: (row[idx('id')] || '').trim(),
        cart,
        status: statusText || (cart ? 'ok' : 'pending'),
      };
    }).filter((row) => row.query && row.id);
    return { rows, total: rows.length };
  }

  function errorRowsFromCsv(text) {
    const table = parseCsvTable(text);
    if (!table.length) return { rows: [], total: 0 };
    const header = table[0].map((cell) => cell.trim().toLowerCase());
    const idx = (name) => header.indexOf(name);
    if (idx('query') < 0 || idx('reason') < 0) return null;
    const rows = table.slice(1).map((row) => ({
      query: (row[idx('query')] || '').trim(),
      name: idx('name') >= 0 ? (row[idx('name')] || '').trim() : '',
      region: idx('region') >= 0 ? (row[idx('region')] || '').trim() : '',
      id: idx('id') >= 0 ? (row[idx('id')] || '').trim() : '',
      reason: (row[idx('reason')] || '').trim(),
    })).filter((row) => row.query || row.id);
    return { rows, total: rows.length };
  }

  // 输入文件：优先第二列；只有一列时用第一列。
  function namesFromCsv(text) {
    const table = parseCsvTable(text);
    if (!table.length) return [];
    const multiColumnRows = table.filter((row) => row.length > 1).length;
    const column = multiColumnRows >= table.length / 2 ? 1 : 0;
    const names = [];
    const seen = new Set();

    table.forEach((row, index) => {
      const value = normalizeName(row[column] || '');
      if (!value) return;
      if (index === 0 && /^(英文名(?:称)?|english\s*name|name|title|名称|游戏名)$/i.test(value)) return;
      const key = value.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      names.push(value);
    });

    return names;
  }

  /* ================= 本地存储 ================= */
  function loadSavedNames() {
    try {
      const raw = GM_getValue(NAMES_KEY, '');
      if (!raw) return null;
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
      if (!data || !Array.isArray(data.names)) return null;
      return {
        fileName: String(data.fileName || ''),
        names: data.names.map((name) => normalizeName(name)).filter(Boolean),
      };
    } catch (e) {
      return null;
    }
  }

  function saveInputNames() {
    try {
      GM_setValue(NAMES_KEY, JSON.stringify({ fileName: inputFileName, names: inputNames }));
    } catch (e) {
      // 忽略存储失败
    }
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

  async function writeListCsvToDir(rows) {
    await writeFileToDir(LIST_CSV_NAME, buildListCsv(rows));
  }

  async function writeErrorCsvToDir(rows) {
    await writeFileToDir(ERROR_CSV_NAME, buildErrorCsv(rows));
  }

  async function readTextFromDir(name) {
    if (!dirHandle) throw new Error('未选择目标目录');
    const handle = await dirHandle.getFileHandle(name);
    const file = await handle.getFile();
    return file.text();
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

  /* ================= 界面 ================= */
  const host = document.createElement('div');
  host.id = 'vimm-cart-grab-host';
  host.style.cssText = 'position:fixed;top:12px;right:12px;z-index:2147483647;';
  document.documentElement.appendChild(host);

  const shadow = host.attachShadow({ mode: 'open' });
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      #panel {
        width: 400px;
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
      select {
        background: #11111a;
        border: 1px solid #3a3a55;
        color: #fff;
        border-radius: 6px;
        padding: 3px 6px;
        font: inherit;
      }
      #fileName, #dirName {
        color: #b9b9cc;
        word-break: break-all;
      }
      #hint { color: #8f8fa8; margin-bottom: 8px; }
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
        max-height: 260px;
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
        <span>Vimm's Lair 按名称抓图</span>
        <button id="collapse" title="收起 / 展开">—</button>
      </div>
      <div id="body">
        <div class="row">
          <label>机种 <select id="system"></select></label>
        </div>
        <div class="row">
          <button id="pickFile">选择名称文件</button>
          <span id="fileName">未选择</span>
        </div>
        <div class="row">
          <button id="pickDir">选择输出目录</button>
          <button id="clearDir" disabled>取消目录</button>
          <span id="dirName">未选择</span>
        </div>
        <div class="row">
          <button id="run">开始</button>
          <button id="pause" disabled>暂停</button>
          <button id="resume" disabled>继续</button>
        </div>
        <div id="hint">名称取 CSV 第二列；只抓完全同名且区域为 USA / Japan 的条目。</div>
        <input id="fileInput" type="file" accept=".csv,.txt,text/csv,text/plain" style="display:none">
        <div id="progress-wrap"><div id="progress"></div></div>
        <div id="status">空闲</div>
        <div id="log"></div>
      </div>
    </div>
  `;

  const $ = (selector) => shadow.querySelector(selector);
  const bodyEl = $('#body');
  const systemSelect = $('#system');
  const pickFileBtn = $('#pickFile');
  const fileInput = $('#fileInput');
  const fileNameEl = $('#fileName');
  const pickDirBtn = $('#pickDir');
  const clearDirBtn = $('#clearDir');
  const dirNameEl = $('#dirName');
  const runBtn = $('#run');
  const pauseBtn = $('#pause');
  const resumeBtn = $('#resume');
  const collapseBtn = $('#collapse');
  const progressEl = $('#progress');
  const statusEl = $('#status');
  const logEl = $('#log');

  for (const code of SYSTEMS) {
    const option = document.createElement('option');
    option.value = code;
    option.textContent = code;
    systemSelect.appendChild(option);
  }
  const savedSystem = GM_getValue(SYSTEM_KEY, DEFAULT_SYSTEM);
  systemSelect.value = SYSTEMS.includes(savedSystem) ? savedSystem : DEFAULT_SYSTEM;
  systemSelect.addEventListener('change', () => GM_setValue(SYSTEM_KEY, systemSelect.value));

  function currentSystem() {
    return SYSTEMS.includes(systemSelect.value) ? systemSelect.value : DEFAULT_SYSTEM;
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

  function updateFileLabel() {
    if (inputFileName) {
      fileNameEl.textContent = `${inputFileName}（${inputNames.length} 个名称）`;
      fileNameEl.title = inputFileName;
    } else {
      fileNameEl.textContent = '未选择';
      fileNameEl.title = '';
    }
  }

  function updateDirLabel() {
    if (dirHandle) {
      dirNameEl.textContent = `目录：${dirHandle.name}`;
      dirNameEl.title = '封面、list.csv 与 error.csv 会保存到此目录';
    } else {
      dirNameEl.textContent = '未选择';
      dirNameEl.title = '';
    }
    clearDirBtn.disabled = !dirHandle;
  }

  function updateButtons() {
    runBtn.disabled = state.running || !inputNames.length || !dirHandle;
    systemSelect.disabled = state.running;
    pickFileBtn.disabled = state.running;
    pickDirBtn.disabled = state.running || !directoryPicker();
    clearDirBtn.disabled = state.running || !dirHandle;
    pauseBtn.disabled = !state.running || state.paused;
    resumeBtn.disabled = !state.running || !state.paused;
  }

  const state = { running: false, paused: false, total: 0, completed: 0 };
  let resumeResolvers = [];
  let inputNames = [];
  let inputFileName = '';

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

  /* ================= 记录 ================= */
  let listRows = [];
  let errorRows = [];
  let okIds = new Set();
  let errorIds = new Set();
  let knownQueries = new Set();
  const usedFilenames = new Map();

  function listKey(row) {
    return row.id || `query:${row.query}\u0000region:${row.region}\u0000name:${row.name}`;
  }

  function errorKey(row) {
    if (row.id) return `id:${row.id}`;
    if (row.query) return `query:${row.query}`;
    return `name:${row.name}\u0000region:${row.region}`;
  }

  function dedupeListRows(rows) {
    const map = new Map();
    for (const row of rows) map.set(listKey(row), row);
    return [...map.values()];
  }

  function dedupeErrorRows(rows) {
    const map = new Map();
    for (const row of rows) map.set(errorKey(row), row);
    return [...map.values()];
  }

  function rebuildSets() {
    okIds = new Set();
    for (const row of listRows) {
      if (row.status === 'ok' && row.id) okIds.add(row.id);
    }

    errorIds = new Set();
    for (const row of errorRows) {
      if (row.id) errorIds.add(row.id);
    }

    // 只有 list.csv 记录过，或 error.csv 中有“搜索阶段失败”（id 为空）的名称，
    // 才免去再次搜索。条目级失败不会阻止重新搜索，便于清空 list.csv 后重来。
    knownQueries = new Set();
    for (const row of listRows) {
      if (row.query) knownQueries.add(row.query);
    }
    for (const row of errorRows) {
      if (!row.id && row.query) knownQueries.add(row.query);
    }
  }

  function pendingEntries(query) {
    return listRows.filter((row) => row.query === query
      && row.id
      && row.status !== 'ok'
      && !errorIds.has(row.id));
  }

  function listStats() {
    let okCount = 0;
    let pendingCount = 0;
    let failedPendingCount = 0;
    for (const row of listRows) {
      if (row.status === 'ok') {
        okCount += 1;
      } else if (errorIds.has(row.id)) {
        failedPendingCount += 1;
      } else {
        pendingCount += 1;
      }
    }
    return { okCount, pendingCount, failedPendingCount };
  }

  function compareRows(a, b) {
    const q = String(a.query || '').localeCompare(String(b.query || ''));
    if (q) return q;
    const na = Number(a.id);
    const nb = Number(b.id);
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
    return String(a.id || '').localeCompare(String(b.id || ''));
  }

  async function appendListEntries(rows) {
    if (!rows.length) return;
    for (const row of rows) {
      const index = listRows.findIndex((item) => item.id === row.id);
      if (index >= 0) listRows[index] = row;
      else listRows.push(row);
    }
    rebuildSets();
    if (!dirHandle) return;
    try {
      await appendCsvRowsToDir(
        LIST_CSV_NAME,
        LIST_CSV_HEADER,
        rows.map((row) => [row.query, row.name, row.region, row.id, row.cart, row.status]),
      );
    } catch (e) {
      log(`追加 ${LIST_CSV_NAME} 失败：${e.message}`, 'warn');
    }
  }

  async function appendErrorEntry(row) {
    const key = errorKey(row);
    if (errorRows.some((item) => errorKey(item) === key)) return;
    errorRows.push(row);
    rebuildSets();
    if (!dirHandle) return;
    try {
      await appendCsvRowsToDir(
        ERROR_CSV_NAME,
        ERROR_CSV_HEADER,
        [[row.query, row.name, row.region, row.id, row.reason]],
      );
    } catch (e) {
      log(`追加 ${ERROR_CSV_NAME} 失败：${e.message}`, 'warn');
    }
  }

  async function recordQueryError(query, reason) {
    await appendErrorEntry({
      query,
      name: '',
      region: '',
      id: '',
      reason: reason || '未知错误',
    });
  }

  async function recordEntryError(entry, reason) {
    // 保证 list.csv 中有待下载行：清空 error.csv 后可以凭它重试，无需重新搜索。
    if (!listRows.some((row) => row.id === entry.id)) {
      await appendListEntries([{
        query: entry.query,
        name: entry.name,
        region: entry.region,
        id: entry.id,
        cart: '',
        status: 'pending',
      }]);
    }
    await appendErrorEntry({
      query: entry.query,
      name: entry.name,
      region: entry.region,
      id: entry.id,
      reason: reason || '未知错误',
    });
  }

  async function recordSuccess(entry, filename) {
    const row = {
      query: entry.query,
      name: entry.name,
      region: entry.region,
      id: entry.id,
      cart: filename,
      status: 'ok',
    };
    const index = listRows.findIndex((item) => item.id === entry.id);
    if (index >= 0) listRows[index] = row;
    else listRows.push(row);
    rebuildSets();
    if (!dirHandle) return;
    try {
      await appendCsvRowsToDir(
        LIST_CSV_NAME,
        LIST_CSV_HEADER,
        [[row.query, row.name, row.region, row.id, row.cart, row.status]],
      );
    } catch (e) {
      log(`追加 ${LIST_CSV_NAME} 失败：${e.message}`, 'warn');
    }
  }

  async function refreshRecordsFromDirectory() {
    let parsedList = { rows: [], total: 0 };
    try {
      const parsed = listRowsFromCsv(await readTextFromDir(LIST_CSV_NAME));
      if (parsed === null) {
        log(`${LIST_CSV_NAME} 缺少 query/name/id 列，不是本脚本的格式；请换目录或先备份该文件`, 'fail');
        return false;
      }
      parsedList = parsed;
    } catch (e) {
      if (e && e.name === 'NotFoundError') {
        log(`目标目录中没有 ${LIST_CSV_NAME}，将新建`, 'info');
      } else {
        log(`读取 ${LIST_CSV_NAME} 失败：${e.message}`, 'fail');
        return false;
      }
    }

    let parsedError = { rows: [], total: 0 };
    try {
      const parsed = errorRowsFromCsv(await readTextFromDir(ERROR_CSV_NAME));
      if (parsed === null) {
        log(`${ERROR_CSV_NAME} 缺少 query/reason 列，不是本脚本的格式；请换目录或先备份该文件`, 'fail');
        return false;
      }
      parsedError = parsed;
    } catch (e) {
      if (e && e.name === 'NotFoundError') {
        log(`目标目录中没有 ${ERROR_CSV_NAME}，将新建`, 'info');
      } else {
        log(`读取 ${ERROR_CSV_NAME} 失败：${e.message}`, 'fail');
        return false;
      }
    }

    listRows = dedupeListRows(parsedList.rows);
    errorRows = dedupeErrorRows(parsedError.rows);
    rebuildSets();

    const stats = listStats();
    log(`已读取 ${LIST_CSV_NAME}：成功 ${stats.okCount} 条，待下载 ${stats.pendingCount} 条，失败待重试 ${stats.failedPendingCount} 条；${ERROR_CSV_NAME}：失败 ${errorRows.length} 条`, 'info');
    if (parsedList.total !== listRows.length) {
      log(`${LIST_CSV_NAME} 中有重复条目，结束时按条目 ID 去重`, 'info');
    }
    if (parsedError.total !== errorRows.length) {
      log(`${ERROR_CSV_NAME} 中有重复条目，结束时去重`, 'info');
    }
    return true;
  }

  async function cleanupRecords() {
    if (!dirHandle) return;

    listRows = dedupeListRows(listRows).sort(compareRows);
    errorRows = dedupeErrorRows(errorRows).sort(compareRows);
    rebuildSets();

    const stats = listStats();
    try {
      await writeListCsvToDir(listRows);
      log(`${LIST_CSV_NAME} 已整理：成功 ${stats.okCount} 条，待下载 ${stats.pendingCount} 条，失败待重试 ${stats.failedPendingCount} 条`, 'info');
    } catch (e) {
      log(`重写 ${LIST_CSV_NAME} 失败：${e.message}`, 'warn');
    }
    try {
      await writeErrorCsvToDir(errorRows);
      log(`${ERROR_CSV_NAME} 已整理：${errorRows.length} 条`, 'info');
    } catch (e) {
      log(`重写 ${ERROR_CSV_NAME} 失败：${e.message}`, 'warn');
    }
  }

  /* ================= 搜索与下载 ================= */
  function searchUrl(query, systemCode) {
    const params = new URLSearchParams({
      mode: 'adv',
      p: 'list',
      system: systemCode,
      q: query,
      players: '>=',
      playersValue: '1',
      simultaneous: '',
      publisher: '',
      year: '=',
      yearValue: '',
      rating: '>=',
      ratingValue: '',
      region: '',
      sort: 'Title',
      sortOrder: 'ASC',
    });
    return `/vault/?${params.toString()}`;
  }

  function pickRegion(row) {
    const titles = [...row.querySelectorAll('img.flag')]
      .map((img) => normalizeName(img.getAttribute('title') || ''));
    if (titles.includes('USA')) return 'USA';
    if (titles.includes('Japan')) return 'Japan';
    // World 只在没有 USA 条目时作为美版回退，见 parseSearchResults。
    if (titles.includes('World')) return 'World';
    return null;
  }

  function chooseCandidate(list, region, viaWorld) {
    if (!list || !list.length) return null;
    const normal = list.filter((item) => !item.variant);
    return {
      ...(normal[0] || list[0]),
      region,
      viaWorld: !!viaWorld,
    };
  }

  // 从搜索结果页中筛出完全同名、且区域为 USA / Japan 的条目。
  // 每个区域优先取没有 VC / Prototype / Demo 等角标的普通条目。
  function parseSearchResults(html, query) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    let rows = [...doc.querySelectorAll('table.hovertable tr')];
    if (!rows.length) rows = [...doc.querySelectorAll('tr')];

    const target = normalizeName(query).toLowerCase();
    const candidates = [];

    for (const tr of rows) {
      const cells = tr.querySelectorAll('td');
      if (cells.length < 2) continue;

      const titleAnchor = [...cells[0].querySelectorAll('a[href]')]
        .find((anchor) => /^\/vault\/\d+\/?$/.test(anchor.getAttribute('href') || '')
          && normalizeName(anchor.textContent));
      if (!titleAnchor) continue;

      const name = normalizeName(titleAnchor.textContent);
      if (!name || name.toLowerCase() !== target) continue;

      const region = pickRegion(tr);
      if (!region) continue;

      const id = (titleAnchor.getAttribute('href') || '').match(/(\d+)/);
      if (!id) continue;

      candidates.push({
        id: id[1],
        name,
        region,
        variant: !!cells[0].querySelector('b.redBorder'),
      });
    }

    const byRegion = new Map();
    for (const item of candidates) {
      if (!byRegion.has(item.region)) byRegion.set(item.region, []);
      byRegion.get(item.region).push(item);
    }

    const usa = chooseCandidate(byRegion.get('USA'), 'USA', false)
      || chooseCandidate(byRegion.get('World'), 'USA', true);
    const japan = chooseCandidate(byRegion.get('Japan'), 'Japan', false);

    const seen = new Set();
    return [usa, japan].filter((item) => {
      if (!item || seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }

  async function searchEntries(query, systemCode) {
    const url = searchUrl(query, systemCode);
    const text = await retryRequest(`搜索「${query}」`, async () => {
      const res = await fetchNetwork(url, { credentials: 'same-origin' });
      const body = await readTextNetwork(res);
      if (looksBlocked(body)) {
        const error = new Error('搜索需要人机验证');
        error.blocked = true;
        throw error;
      }
      if (!res.ok) throw new Error(`搜索 HTTP ${res.status}`);
      return body;
    });
    return parseSearchResults(text, query);
  }

  async function fetchCartId(entry) {
    const cacheKey = SERIAL_KEY_PREFIX + entry.id;
    const cached = GM_getValue(cacheKey, '');
    if (cached) return String(cached);

    const text = await retryRequest(`条目 ${entry.id} 详情页`, async () => {
      const res = await fetchNetwork(`/vault/${entry.id}`, { credentials: 'same-origin' });
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

    const serial = extractCartId(text);
    if (serial) GM_setValue(cacheKey, serial);
    return serial;
  }

  function uniqueFilename(base, extension, id) {
    let filename = `${base}${extension}`;
    let key = filename.toLowerCase();
    if (usedFilenames.has(key) && usedFilenames.get(key) !== id) {
      filename = `${base}-${id}${extension}`;
      key = filename.toLowerCase();
    }
    usedFilenames.set(key, id);
    return filename;
  }

  async function fetchCover(entry, serial) {
    const url = `/image.php?type=cart&id=${encodeURIComponent(entry.id)}&page=1`;
    const { data, contentType, extension } = await retryRequest(`条目 ${entry.id} 封面`, async () => {
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

    const base = serial
      ? safePart(serial)
      : `${safePart(entry.name)}.${safePart(entry.region)}`;
    const filename = uniqueFilename(base, extension, entry.id);
    const mime = contentType.split(';')[0].trim() || `image/${extension.slice(1)}`;
    const blob = new Blob([data], { type: mime });

    if (dirHandle) {
      await writeFileToDir(filename, blob);
    } else {
      // 本脚本要求先选目录；保留该分支以便将来放宽限制。
      downloadBlob(blob, filename);
    }

    return { filename, bytes: data.byteLength };
  }

  /* ================= 人机验证辅助 ================= */
  function openTab(url) {
    try {
      GM_openInTab(url, { active: true, insert: true, setParent: true });
    } catch (e) {
      window.open(url, '_blank');
    }
  }

  function openVerifyTabUrl(path) {
    openTab(new URL(path, location.origin).href);
  }

  function openVerifyTab(vaultId) {
    openTab(`https://vimm.net/vault/${vaultId}`);
  }

  async function cacheSerialFromVaultPage() {
    const match = location.pathname.match(/^\/vault\/(\d+)\/?$/);
    if (!match) return;
    const vaultId = match[1];
    if (GM_getValue(SERIAL_KEY_PREFIX + vaultId, '')) return;

    for (let attempt = 0; attempt < 3; attempt += 1) {
      const html = document.documentElement.innerHTML;
      if (!looksBlocked(html)) {
        const serial = extractCartId(html);
        if (serial) {
          GM_setValue(SERIAL_KEY_PREFIX + vaultId, serial);
          log(`已记录条目 ${vaultId} 的卡带 ID：${serial}。回到抓取标签点“继续”。`, 'info');
          return;
        }
      }
      await sleep(2000);
    }
  }

  /* ================= 主流程 ================= */
  async function processEntries(entries) {
    let ok = 0;
    let fail = 0;
    let skip = 0;

    for (const entry of entries) {
      await waitIfPaused();

      if (okIds.has(entry.id)) {
        skip += 1;
        log(`[跳过] ${entry.name} [${entry.region}]（已抓过）`, 'skip');
        continue;
      }
      if (errorIds.has(entry.id)) {
        skip += 1;
        log(`[跳过] ${entry.name} [${entry.region}]（error.csv 已记录）`, 'skip');
        continue;
      }

      const label = `${entry.name} [${entry.region}] | 条目 ${entry.id}`;
      let serial = null;
      let detailFailed = false;

      while (true) {
        await waitIfPaused();
        try {
          serial = await fetchCartId(entry);
          break;
        } catch (e) {
          if (e && e.blocked) {
            // 不自动重试：打开详情页让用户手动验证，然后暂停等待用户点“继续”
            log(`[验证] ${label} 需要人机验证，已打开详情页；完成后点“继续”`, 'warn');
            openVerifyTab(entry.id);
            setPaused(true);
            setStatus('等待人机验证，完成后点“继续”');
            continue;
          }
          detailFailed = true;
          fail += 1;
          log(`[失败] ${label} | ${e.message}`, 'fail');
          await recordEntryError(entry, e.message);
          break;
        }
      }

      if (detailFailed) {
        await randSleep();
        continue;
      }

      try {
        setStatus(`下载中：${label}`);
        const cover = await fetchCover(entry, serial);
        await recordSuccess(entry, cover.filename);
        ok += 1;
        log(`[成功] ${label} | 卡带ID ${serial || '无'} | ${cover.filename} (${cover.bytes} 字节)`, 'ok');
      } catch (e) {
        fail += 1;
        log(`[失败] ${label} | ${e.message}`, 'fail');
        await recordEntryError(entry, e.message);
      }

      // 每处理一条随机等待 1~2 秒，降低对方压力
      await randSleep();
    }

    return { ok, fail, skip };
  }

  async function handleQuery(query) {
    await waitIfPaused();

    let entries = null;

    if (knownQueries.has(query)) {
      const pending = pendingEntries(query);
      if (!pending.length) {
        log(`[跳过] ${query}（已完成或已记录失败）`, 'skip');
        return { ok: 0, fail: 0, skip: 1 };
      }
      log(`[续跑] ${query}：还有 ${pending.length} 条待下载`, 'info');
      entries = pending;
    } else {
      let results = null;
      while (results === null) {
        await waitIfPaused();
        try {
          results = await searchEntries(query, currentSystem());
        } catch (e) {
          if (e && e.blocked) {
            log(`[验证] 搜索「${query}」需要人机验证，已打开搜索页；完成后点“继续”`, 'warn');
            openVerifyTabUrl(searchUrl(query, currentSystem()));
            setPaused(true);
            setStatus('等待人机验证，完成后点“继续”');
            continue;
          }
          log(`[失败] 搜索「${query}」| ${e.message}`, 'fail');
          await recordQueryError(query, e.message);
          await randSleep();
          return { ok: 0, fail: 1, skip: 0 };
        }
      }

      if (!results.length) {
        const reason = '未找到完全同名且区域为 USA / Japan 的条目';
        log(`[失败] 搜索「${query}」| ${reason}`, 'fail');
        await recordQueryError(query, reason);
        await randSleep();
        return { ok: 0, fail: 1, skip: 0 };
      }

      const newRows = [];
      for (const item of results) {
        if (listRows.some((row) => row.id === item.id)) continue;
        if (okIds.has(item.id) || errorIds.has(item.id)) continue;
        newRows.push({
          query,
          name: item.name,
          region: item.region,
          id: item.id,
          cart: '',
          status: 'pending',
        });
      }
      if (newRows.length) await appendListEntries(newRows);

      knownQueries.add(query);
      const worldCount = results.filter((item) => item.viaWorld).length;
      const worldNote = worldCount ? `，其中 ${worldCount} 条 World 按美版使用` : '';
      log(`[搜索] ${query}：匹配 ${results.length} 条（${results.map((item) => item.region).join(' / ')}${worldNote}）`, 'info');

      entries = results.map((item) => {
        const row = listRows.find((saved) => saved.id === item.id);
        return row || {
          query,
          name: item.name,
          region: item.region,
          id: item.id,
          cart: '',
          status: 'pending',
        };
      }).filter((row) => row.status !== 'ok' && !errorIds.has(row.id));
    }

    return processEntries(entries);
  }

  async function runAll() {
    state.running = true;
    state.completed = 0;
    state.total = inputNames.length;
    setPaused(false);
    setProgress(0);
    updateButtons();
    setStatus('读取记录...');
    usedFilenames.clear();

    log(`开始：${currentSystem()} 共 ${inputNames.length} 个名称`, 'info');
    log('只抓完全同名且区域为 USA / Japan 的条目；命名优先用详情页卡带 ID。', 'info');

    if (!await refreshRecordsFromDirectory()) {
      log('记录文件格式不兼容，已停止。请换一个输出目录，或先备份同名 CSV。', 'fail');
      state.running = false;
      setStatus('已停止');
      updateButtons();
      return;
    }

    let ok = 0;
    let fail = 0;
    let skip = 0;

    try {
      for (let i = 0; i < inputNames.length; i += 1) {
        const query = inputNames[i];
        setStatus(`处理中 ${i + 1}/${inputNames.length}：${query}`);
        let result;
        try {
          result = await handleQuery(query);
        } catch (e) {
          result = { ok: 0, fail: 1, skip: 0 };
          log(`[失败] ${query} | ${e && e.message ? e.message : e}`, 'fail');
        }
        ok += result.ok;
        fail += result.fail;
        skip += result.skip;
        bumpProgress();
      }
    } catch (e) {
      log(`运行中断：${e && e.message ? e.message : e}`, 'fail');
    } finally {
      state.running = false;
      setPaused(false);
      await cleanupRecords();
      updateButtons();
      setProgress(state.total ? state.completed / state.total : 0);
      setStatus('完成');
      log(`结束：成功 ${ok} 条，失败 ${fail} 条，跳过 ${skip} 条`, 'info');
    }
  }

  /* ================= 事件绑定 ================= */
  runBtn.addEventListener('click', async () => {
    if (state.running) return;
    if (!inputNames.length) {
      log('请先选择名称文件', 'warn');
      return;
    }
    if (!dirHandle) {
      log('请先选择输出目录', 'warn');
      return;
    }
    if (!(await ensureDirectoryPermission())) {
      updateButtons();
      return;
    }
    logEl.textContent = '';
    runBtn.disabled = true;
    void runAll().catch((e) => {
      log(`运行失败：${e && e.message ? e.message : e}`, 'fail');
      state.running = false;
      setPaused(false);
      updateButtons();
      setStatus('已停止');
    });
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

  pickFileBtn.addEventListener('click', () => {
    if (state.running) return;
    fileInput.click();
  });

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      inputNames = namesFromCsv(text);
      inputFileName = file.name;
      saveInputNames();
      updateFileLabel();
      updateButtons();
      log(`已读取 ${file.name}：${inputNames.length} 个名称`, 'info');
      if (!inputNames.length) {
        log('文件中没有可用的名称（默认取第二列）', 'warn');
      }
    } catch (e) {
      log(`读取文件失败：${e.message}`, 'fail');
    } finally {
      fileInput.value = '';
    }
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
      log(`已选择输出目录：${handle.name}`, 'info');
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
    log('已取消输出目录', 'info');
  });

  collapseBtn.addEventListener('click', () => {
    bodyEl.classList.toggle('collapsed');
    collapseBtn.textContent = bodyEl.classList.contains('collapsed') ? '+' : '—';
  });

  if (typeof GM_registerMenuCommand === 'function') {
    GM_registerMenuCommand('清空已抓记录 (list.csv)', async () => {
      if (state.running) {
        log('抓取进行中，请等结束后再清空记录', 'warn');
        return;
      }
      if (!dirHandle) {
        log('请先选择输出目录', 'warn');
        return;
      }
      if (!window.confirm('确定清空 list.csv？已下载记录与搜索缓存都会清除。')) return;
      if (!await ensureDirectoryPermission()) return;
      listRows = [];
      rebuildSets();
      try {
        await writeListCsvToDir([]);
        log('已清空 list.csv', 'info');
      } catch (e) {
        log(`清空 ${LIST_CSV_NAME} 失败：${e.message}`, 'fail');
      }
    });

    GM_registerMenuCommand('清空失败记录 (error.csv)', async () => {
      if (state.running) {
        log('抓取进行中，请等结束后再清空记录', 'warn');
        return;
      }
      if (!dirHandle) {
        log('请先选择输出目录', 'warn');
        return;
      }
      if (!window.confirm('确定清空 error.csv？清空后再次开始会重试已记录的失败条目。')) return;
      if (!await ensureDirectoryPermission()) return;
      errorRows = [];
      rebuildSets();
      try {
        await writeErrorCsvToDir([]);
        log('已清空 error.csv，再次开始会重试失败条目', 'info');
      } catch (e) {
        log(`清空 ${ERROR_CSV_NAME} 失败：${e.message}`, 'fail');
      }
    });
  }

  /* ================= 启动 ================= */
  const savedNames = loadSavedNames();
  if (savedNames) {
    inputNames = savedNames.names;
    inputFileName = savedNames.fileName;
  }

  updateFileLabel();
  updateDirLabel();
  updateButtons();
  setStatus('空闲');
  log('准备就绪：选择名称文件与输出目录后点“开始”。', 'info');
  log('名称取 CSV 第二列；只抓完全同名且区域为 USA / Japan 的条目。', 'info');
  if (inputNames.length) {
    log(`已恢复名称文件：${inputFileName || '（未知文件名）'}（${inputNames.length} 个名称）`, 'info');
  }

  if (directoryPicker()) {
    dirDbGet(DIR_KEY)
      .then((handle) => {
        if (!handle) return;
        dirHandle = handle;
        updateDirLabel();
        updateButtons();
        log(`已恢复输出目录：${handle.name}（点“开始”时会请求写入权限）`, 'info');
      })
      .catch(() => {
        log('读取已保存的输出目录失败，请重新选择目录', 'warn');
      });
  } else {
    pickDirBtn.disabled = true;
    dirNameEl.textContent = '当前浏览器不支持选择目录';
  }

  cacheSerialFromVaultPage();
})();
