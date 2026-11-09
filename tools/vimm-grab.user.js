// ==UserScript==
// @name         Vimm's Lair 排行榜抓取
// @namespace    https://vimm.net/
// @version      1.0.0
// @description  按名次区间抓取 Vimm's Lair 游戏的条目 ID、卡带 ID 和封面；检测到人机验证时暂停并打开页面
// @match        https://vimm.net/*
// @grant        GM_openInTab
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
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
 *    - 设置“开始”“结束”名次（按排行榜名次，从 1 开始）。
 *    - 点“开始”。脚本会读取排行榜，逐条抓取：
 *      条目 ID（如 834）-> 卡带 ID（如 NES-SM-USA）-> 下载封面（如 NES-SM-USA.jpg）。
 *    - 每处理完一个游戏会随机等待 1~5 秒，降低对方压力。
 *
 * 4. 遇到人机验证
 *    - 脚本会立即暂停，并自动在新标签页打开该游戏的详情页。
 *    - 在新标签页完成“Verify you are human”验证；该页也会运行本脚本，
 *      若日志出现“已记录条目 xxx 的卡带 ID”，说明已取到卡带 ID。
 *    - 回到原来的标签页，点“继续”。脚本会优先使用刚缓存的卡带 ID。
 *    - 脚本不会自动重试；必须手动点“继续”才会再尝试一次。
 *
 * 5. 暂停 / 继续
 *    - “暂停”在当前请求结束后生效，之后不再发起新请求。
 *    - “继续”从暂停处恢复，已完成/已跳过的游戏不会重复抓取。
 *
 * 6. 记录与去重
 *    - 每成功一个游戏立即写入 Tampermonkey 存储（相当于逐行落盘）。
 *    - 去重依据是 CSV 第一列（Vimm 条目 ID，如 834），名次变化不会导致重复。
 *    - 点“导出CSV”下载 meta.csv，列为 number,id,name,cart：
 *        number = Vimm 条目 ID（如 834）
 *        id     = 卡带 ID（如 NES-SM-USA）
 *        name   = 游戏名
 *        cart   = 封面文件名（如 NES-SM-USA.jpg）
 *    - 菜单命令“清空已抓取记录”可重置去重数据。
 *
 * 7. 封面下载
 *    - 封面通过 https://vimm.net/image.php 以 blob 方式下载，保存到浏览器默认下载目录。
 *    - 首次批量下载时浏览器可能询问“是否允许下载多个文件”，请选择允许。
 *
 * 8. 可修改的配置
 *    - 文件下方“配置”区域：SYSTEM（系统代号）、SERIAL_PREFIX（卡带 ID 前缀）、
 *      SLEEP_MIN / SLEEP_MAX（随机等待范围，单位毫秒）。
 *    - 目前默认适配 NES；换其他系统时请同时调整 SYSTEM 和 SERIAL_PREFIX。
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
  const SYSTEM = 'NES';            // 排行榜系统代号
  const SERIAL_PREFIX = 'NES';     // 卡带 ID 前缀
  const STORE_KEY = 'vimm_grab_results_v1';
  const SERIAL_KEY_PREFIX = 'vimm_grab_serial_';
  const SLEEP_MIN = 1000;          // 每个游戏处理完后的最短等待（毫秒）
  const SLEEP_MAX = 5000;          // 最长等待（毫秒）

  /* ================= 工具 ================= */
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const randSleep = () => sleep(SLEEP_MIN + Math.random() * (SLEEP_MAX - SLEEP_MIN));

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

  function extractSerial(html, prefix) {
    const labelRe = /cart\s*id|cartridge\s*id|serial|product\s*id/gi;
    let match;
    while ((match = labelRe.exec(html)) !== null) {
      const start = match.index + match[0].length;
      const windowText = html.slice(start, start + 800);
      const found = [...windowText.matchAll(SERIAL_RE)]
        .map((item) => item[1])
        .filter((serial) => serial.startsWith(prefix + '-'));
      if (found.length) return found[0];
    }
    const all = [...html.matchAll(SERIAL_RE)]
      .map((item) => item[1])
      .filter((serial) => serial.startsWith(prefix + '-'));
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
          <label>开始 <input id="start" type="number" min="1" step="1" value="1"></label>
          <label>结束 <input id="end" type="number" min="1" step="1" value="10"></label>
        </div>
        <div class="row">
          <button id="run">开始</button>
          <button id="pause" disabled>暂停</button>
          <button id="resume" disabled>继续</button>
          <button id="export">导出CSV</button>
        </div>
        <div id="progress-wrap"><div id="progress"></div></div>
        <div id="status">空闲</div>
        <div id="log"></div>
      </div>
    </div>
  `;

  const $ = (selector) => shadow.querySelector(selector);
  const bodyEl = $('#body');
  const startInput = $('#start');
  const endInput = $('#end');
  const runBtn = $('#run');
  const pauseBtn = $('#pause');
  const resumeBtn = $('#resume');
  const exportBtn = $('#export');
  const collapseBtn = $('#collapse');
  const progressEl = $('#progress');
  const statusEl = $('#status');
  const logEl = $('#log');

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
  async function loadRanking(count) {
    const games = [];
    const seen = new Set();
    for (let page = 1; games.length < count && page <= 100; page += 1) {
      const url = `/vault/ajax/loadTopTen.php?system=${encodeURIComponent(SYSTEM)}&page=${page}`;
      const res = await fetch(url, { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`排行榜 HTTP ${res.status}`);
      const text = await res.text();
      if (looksBlocked(text)) throw new Error('排行榜接口需要人机验证');
      const doc = new DOMParser().parseFromString(text, 'text/html');
      const rows = [...doc.querySelectorAll('a[href]')]
        .filter((anchor) => /^\d+$/.test(anchor.getAttribute('href')))
        .map((anchor) => ({
          id: anchor.getAttribute('href'),
          name: anchor.textContent.replace(/\s+/g, ' ').trim(),
        }));
      if (!rows.length) break;
      let added = 0;
      for (const game of rows) {
        if (seen.has(game.id)) continue;
        seen.add(game.id);
        games.push(game);
        added += 1;
      }
      if (!added) break;
    }
    return games.slice(0, count);
  }

  async function fetchSerial(game) {
    const cached = GM_getValue(SERIAL_KEY_PREFIX + game.id, '');
    if (cached) return String(cached);

    const res = await fetch(`/vault/${game.id}`, { credentials: 'same-origin' });
    const text = await res.text();
    if (looksBlocked(text)) {
      const error = new Error('需要人机验证');
      error.blocked = true;
      throw error;
    }
    if (!res.ok && res.status !== 404) {
      throw new Error(`详情页 HTTP ${res.status}`);
    }
    const serial = extractSerial(text, SERIAL_PREFIX);
    if (!serial) throw new Error('详情页中未找到卡带 ID');
    GM_setValue(SERIAL_KEY_PREFIX + game.id, serial);
    return serial;
  }

  async function fetchCover(game, serial) {
    const url = `/image.php?type=cart&id=${encodeURIComponent(game.id)}&page=1`;
    const res = await fetch(url, {
      credentials: 'same-origin',
      referrer: 'https://vimm.net/',
    });
    if (!res.ok) throw new Error(`封面 HTTP ${res.status}`);

    const buf = await res.arrayBuffer();
    if (buf.byteLength < 1024) throw new Error(`封面文件过小 (${buf.byteLength} 字节)`);
    const dims = imageSize(buf);
    if (dims && dims[0] === 400 && dims[1] === 100) {
      throw new Error('拿到的是防盗链占位图 (400x100)');
    }

    const contentType = res.headers.get('Content-Type') || '';
    const ext = sniffExt(buf, contentType);
    if (!ext) throw new Error(`未知图片格式 (${contentType || '无 Content-Type'})`);

    const filename = serial + ext;
    const mime = contentType.split(';')[0].trim() || 'image/' + ext.slice(1);
    downloadBlob(new Blob([buf], { type: mime }), filename);
    return { filename, bytes: buf.byteLength };
  }

  function openVerifyTab(vaultId) {
    const url = `https://vimm.net/vault/${vaultId}`;
    try {
      GM_openInTab(url, { active: true, insert: true, setParent: true });
    } catch (e) {
      window.open(url, '_blank');
    }
  }

  function exportCsv() {
    const rows = loadRows();
    const escape = (value) => {
      const text = String(value == null ? '' : value);
      return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
    };
    const lines = ['number,id,name,cart'];
    for (const row of rows) {
      lines.push([row.number, row.id, row.name, row.cart].map(escape).join(','));
    }
    downloadBlob(
      new Blob([lines.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' }),
      'meta.csv'
    );
    log(`已导出 meta.csv（${rows.length} 条）`, 'info');
  }

  /* ================= 主流程 ================= */
  async function runRange(start, end) {
    state.running = true;
    state.completed = 0;
    state.total = Math.max(0, end - start + 1);
    setPaused(false);
    setProgress(0);
    updateButtons();
    logEl.textContent = '';
    setStatus('读取排行榜...');
    log(`开始：${SYSTEM} 第 ${start}~${end} 名`, 'info');
    log('提示：浏览器若询问是否允许下载多个文件，请选择允许。', 'info');

    const rows = loadRows();
    const done = new Set(rows.map((row) => String(row.number)));
    log(`已有记录 ${done.size} 条（按第一列的条目 ID 去重）`, 'info');

    let games;
    try {
      games = await loadRanking(end);
    } catch (e) {
      log(`读取排行榜失败：${e.message}`, 'fail');
      state.running = false;
      setStatus('已停止');
      updateButtons();
      return;
    }

    if (!games.length) {
      log('排行榜为空', 'fail');
      state.running = false;
      setStatus('已停止');
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

      let serial = null;
      let failed = false;

      while (serial === null) {
        await waitIfPaused();
        setStatus(`抓取中：${label}`);
        try {
          serial = await fetchSerial(game);
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
        rows.push({
          number: String(game.id),
          id: serial,
          name: game.name,
          cart: filename,
        });
        saveRows(rows);
        done.add(String(game.id));
        ok += 1;
        log(`[成功] ${label} | 卡带ID ${serial} | ${filename} (${bytes} 字节)`, 'ok');
      } catch (e) {
        fail += 1;
        log(`[失败] ${label} | ${e.message}`, 'fail');
      }

      bumpProgress();
      // 每处理一个游戏随机等待 1~5 秒，降低对方压力
      await randSleep();
    }

    state.running = false;
    setPaused(false);
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

    for (let attempt = 0; attempt < 3; attempt += 1) {
      const html = document.documentElement.innerHTML;
      if (!looksBlocked(html)) {
        const serial = extractSerial(html, SERIAL_PREFIX);
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
  runBtn.addEventListener('click', () => {
    const start = parseInt(startInput.value, 10);
    const end = parseInt(endInput.value, 10);
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start) {
      log('名次区间无效：开始必须 >= 1，结束必须 >= 开始', 'warn');
      return;
    }
    runRange(start, end);
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

  exportBtn.addEventListener('click', exportCsv);

  collapseBtn.addEventListener('click', () => {
    bodyEl.classList.toggle('collapsed');
    collapseBtn.textContent = bodyEl.classList.contains('collapsed') ? '+' : '—';
  });

  if (typeof GM_registerMenuCommand === 'function') {
    GM_registerMenuCommand('清空已抓取记录', () => {
      if (window.confirm('确定清空已抓取记录？此操作不可恢复。')) {
        saveRows([]);
        log('已清空已抓取记录', 'info');
      }
    });
  }

  /* ================= 启动 ================= */
  updateButtons();
  setStatus('空闲');
  log('准备就绪：设置名次区间后点“开始”。', 'info');
  log('去重依据为 CSV 第一列（Vimm 条目 ID，如 834）。', 'info');
  cacheSerialFromVaultPage();
})();
