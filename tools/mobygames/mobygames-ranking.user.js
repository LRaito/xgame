// ==UserScript==
// @name         MobyGames 机种榜单抓取
// @namespace    https://www.mobygames.com/
// @version      1.1.0
// @description  登录后从 MobyGames 游戏浏览器按机种抓取 Moby Score 排行，每个机种输出一个 CSV；只保留有评分的游戏
// @match        https://www.mobygames.com/*
// @grant        GM_registerMenuCommand
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// @noframes
// ==/UserScript==

/*
 * ============================ 使用方法 ============================
 *
 * 1. 安装
 *    Tampermonkey 控制面板 -> 添加新脚本 -> 清空编辑器 -> 粘贴本文件全部内容 -> 保存。
 *
 * 2. 登录
 *    在浏览器里正常登录 https://www.mobygames.com/ 。脚本不保存账号密码。
 *
 * 3. 打开面板
 *    访问任意 https://www.mobygames.com/ 页面，右上角会出现“MobyGames 榜单抓取”面板。
 *    如果页面仍停在 Cloudflare 验证页，先点 “Verify you are human”，再刷新。
 *
 * 4. 选择要抓的机种
 *    列表里默认全选 34 个机种。可以按住 Ctrl / Shift 多选，或点“全选”“全不选”。
 *
 * 5. 选择保存目录（可选）
 *    点“选择目录”，指定 CSV 保存位置（推荐）。不选时由浏览器逐个下载，
 *    首次可能询问“是否允许下载多个文件”，请选择允许。
 *
 * 6. 开始
 *    点“开始”。脚本按机种逐个请求游戏浏览器接口：
 *      - 每页 50 条；
 *      - 按 Moby Score 降序；
 *      - 遇到第一条无评分的游戏就停止当前 MobyGames 平台页。
 *    每个机种完成后立即写一个 CSV，列固定为：
 *        序号,中文名,英文名,评分,卡带ID
 *    中文名与卡带ID 由建索引前的人工整理流程补充，脚本只写空列。
 *    评分写接口返回的原始 double 值（如 8.345679012345679），不做四舍五入。
 *
 * 7. 合并机种
 *    gb / ngp / ws 在 MobyGames 各有两个平台页。脚本会把两页都拉完，
 *    按评分重新排序并去重后写成一个 CSV。
 *
 * 8. Cloudflare / 网络异常
 *    请求失败会自动重试。如果遇到 Cloudflare 验证，脚本会暂停；
 *    在浏览器里完成验证后点“继续”即可。人机验证不参与自动重试。
 *
 * 9. 断点
 *    每完成一个机种就写文件，重复点“开始”会重抓所选机种。中断后可从列表里
 *    只选尚未完成的机种再跑。
 */

(function () {
  'use strict';

  const SCRIPT_VERSION = '1.1.0';
  const PER_PAGE = 50;
  const SLEEP_MIN = 1200;
  const SLEEP_MAX = 2400;
  const MAX_RETRY = 10;
  const RETRY_WAIT = 5000;

  // 项目机种 -> MobyGames 平台 id。与同目录 README.md 的平台对照表保持一致。
  const PLATFORMS = [
    { id: 'nes', label: '任天堂 FC', moby: [22] },
    { id: 'snes', label: '任天堂 SFC', moby: [15] },
    { id: 'n64', label: '任天堂 N64', moby: [9] },
    { id: 'gb', label: '任天堂 GB/GBC', moby: [10, 11] },
    { id: 'gba', label: '任天堂 GBA', moby: [12] },
    { id: 'nds', label: '任天堂 NDS', moby: [44] },
    { id: 'vb', label: '任天堂 VB', moby: [38] },
    { id: 'segaMD', label: '世嘉 MD', moby: [16] },
    { id: 'segaGG', label: '世嘉 GG', moby: [25] },
    { id: 'segaMS', label: '世嘉 SMS', moby: [26] },
    { id: 'segaCD', label: '世嘉 CD', moby: [20] },
    { id: 'sega32x', label: '世嘉 32X', moby: [21] },
    { id: 'segaSaturn', label: '世嘉 土星', moby: [23] },
    { id: 'psx', label: '索尼 PS1', moby: [6] },
    { id: 'psp', label: '索尼 PSP', moby: [46] },
    { id: 'pce', label: '日电 PCE', moby: [40] },
    { id: 'pcfx', label: '日电 PC-FX', moby: [59] },
    { id: 'ngp', label: 'SNK NGPC', moby: [52, 53] },
    { id: 'ws', label: '万代 WS', moby: [48, 49] },
    { id: 'atari2600', label: '雅达利 2600', moby: [28] },
    { id: 'atari5200', label: '雅达利 5200', moby: [33] },
    { id: 'atari7800', label: '雅达利 7800', moby: [34] },
    { id: 'jaguar', label: '雅达利 Jaguar', moby: [17] },
    { id: 'lynx', label: '雅达利 Lynx', moby: [18] },
    { id: 'coleco', label: 'ColecoVision', moby: [29] },
    { id: '3do', label: '松下 3DO', moby: [35] },
    { id: 'c64', label: '康懋达 64', moby: [27] },
    { id: 'c128', label: '康懋达 128', moby: [61] },
    { id: 'pet', label: '康懋达 PET', moby: [77] },
    { id: 'plus4', label: '康懋达 Plus/4', moby: [115] },
    { id: 'vic20', label: '康懋达 VIC-20', moby: [43] },
    { id: 'amiga', label: 'Amiga', moby: [19] },
    { id: 'dos', label: 'DOS', moby: [2] },
    { id: 'arcade', label: '街机', moby: [143] },
  ];

  const state = {
    running: false,
    paused: false,
    stopped: false,
    dirHandle: null,
    csrf: '',
    requestMode: '',
  };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const randSleep = () => sleep(SLEEP_MIN + Math.random() * (SLEEP_MAX - SLEEP_MIN));

  let panel;
  let logEl;
  let statusEl;
  let platformSelect;
  let startBtn;
  let pauseBtn;
  let stopBtn;

  // ---------------------------------------------------------------- UI

  function log(msg, kind) {
    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const line = document.createElement('div');
    line.textContent = `[${time}] ${msg}`;
    if (kind === 'warn') line.style.color = '#ffd166';
    if (kind === 'error') line.style.color = '#ff6b6b';
    if (kind === 'ok') line.style.color = '#7ee787';
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function setStatus(text, color) {
    statusEl.textContent = text;
    statusEl.style.color = color || '#c9d1d9';
  }

  function buildPanel() {
    panel = document.createElement('div');
    panel.id = 'moby-ranking-panel';
    panel.style.cssText = [
      'position:fixed', 'top:12px', 'right:12px', 'z-index:2147483647',
      'width:360px', 'max-height:calc(100vh - 24px)', 'display:flex',
      'flex-direction:column', 'gap:8px', 'padding:10px', 'border-radius:10px',
      'background:#161b22', 'color:#c9d1d9', 'border:1px solid #30363d',
      'box-shadow:0 8px 24px rgba(0,0,0,.45)', 'font:12px/1.5 system-ui,sans-serif',
    ].join(';');

    const title = document.createElement('div');
    title.textContent = 'MobyGames 榜单抓取';
    title.style.cssText = 'font-size:14px;font-weight:700;color:#e6edf3;cursor:move;user-select:none';
    panel.appendChild(title);

    statusEl = document.createElement('div');
    statusEl.style.cssText = 'font-size:12px;color:#8b949e';
    statusEl.textContent = '等待开始';
    panel.appendChild(statusEl);

    const row1 = document.createElement('div');
    row1.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap';
    const dirBtn = button('选择目录');
    dirBtn.onclick = chooseDir;
    row1.appendChild(dirBtn);
    const allBtn = button('全选');
    allBtn.onclick = () => selectAll(true);
    row1.appendChild(allBtn);
    const noneBtn = button('全不选');
    noneBtn.onclick = () => selectAll(false);
    row1.appendChild(noneBtn);
    const copyBtn = button('复制日志');
    copyBtn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(logEl.innerText);
        log('日志已复制到剪贴板', 'ok');
      } catch (e) {
        log(`复制失败：${e.message}`, 'error');
      }
    };
    row1.appendChild(copyBtn);
    panel.appendChild(row1);

    platformSelect = document.createElement('select');
    platformSelect.multiple = true;
    platformSelect.size = 10;
    platformSelect.style.cssText = [
      'width:100%', 'background:#0d1117', 'color:#c9d1d9',
      'border:1px solid #30363d', 'border-radius:6px', 'padding:4px', 'font:12px monospace',
    ].join(';');
    for (const p of PLATFORMS) {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.id}  ${p.label}`;
      opt.selected = true;
      platformSelect.appendChild(opt);
    }
    panel.appendChild(platformSelect);

    const row2 = document.createElement('div');
    row2.style.cssText = 'display:flex;gap:6px';
    startBtn = button('开始', '#238636');
    startBtn.onclick = run;
    row2.appendChild(startBtn);
    pauseBtn = button('暂停');
    pauseBtn.onclick = togglePause;
    row2.appendChild(pauseBtn);
    const diagBtn = button('诊断');
    diagBtn.onclick = diagnose;
    row2.appendChild(diagBtn);
    stopBtn = button('停止', '#8b2c2c');
    stopBtn.disabled = true;
    stopBtn.onclick = stop;
    row2.appendChild(stopBtn);
    panel.appendChild(row2);

    logEl = document.createElement('div');
    logEl.style.cssText = [
      'height:220px', 'overflow:auto', 'background:#0d1117', 'border:1px solid #30363d',
      'border-radius:6px', 'padding:6px', 'font:11px/1.5 ui-monospace,monospace',
      'white-space:pre-wrap', 'word-break:break-all',
    ].join(';');
    panel.appendChild(logEl);

    document.body.appendChild(panel);

    // 拖动标题
    let drag = null;
    title.addEventListener('mousedown', (e) => {
      drag = { x: e.clientX, y: e.clientY, left: panel.offsetLeft, top: panel.offsetTop };
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!drag) return;
      panel.style.left = `${drag.left + e.clientX - drag.x}px`;
      panel.style.top = `${drag.top + e.clientY - drag.y}px`;
      panel.style.right = 'auto';
    });
    document.addEventListener('mouseup', () => { drag = null; });
  }

  function button(text, bg) {
    const b = document.createElement('button');
    b.textContent = text;
    b.style.cssText = [
      'flex:1', 'padding:6px 8px', 'border-radius:6px', 'cursor:pointer',
      `background:${bg || '#21262d'}`, 'color:#f0f6fc', 'border:1px solid #30363d',
      'font:12px system-ui,sans-serif',
    ].join(';');
    return b;
  }

  function selectAll(on) {
    for (const opt of platformSelect.options) opt.selected = on;
  }

  async function chooseDir() {
    if (!window.showDirectoryPicker) {
      log('当前浏览器不支持目录选择，将改用逐个下载。', 'warn');
      return;
    }
    try {
      state.dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
      log(`保存目录：${state.dirHandle.name}`, 'ok');
    } catch (e) {
      if (e && e.name !== 'AbortError') log(`选择目录失败：${e.message}`, 'error');
    }
  }

  // ------------------------------------------------------- 登录与 CSRF

  function isLoggedIn() {
    return document.querySelector('a[href*="/user/login/"]') === null;
  }

  async function getCsrfToken() {
    const bodyToken = (document.body && document.body.dataset && document.body.dataset.csrfToken) || '';
    if (bodyToken) return bodyToken;

    const el = document.querySelector('game-browser');
    const attrToken = (el && el.getAttribute('csrf-token')) || '';
    if (attrToken) return attrToken;

    const res = await fetch('/game/', { credentials: 'same-origin' });
    const html = await res.text();
    if (/Just a moment|Performing security verification/i.test(html)) {
      throw new Error('拿到的是 Cloudflare 验证页，请先在浏览器里完成验证');
    }
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const docBodyToken = (doc.body && doc.body.dataset && doc.body.dataset.csrfToken) || '';
    if (docBodyToken) return docBodyToken;
    const docEl = doc.querySelector('game-browser');
    const docToken = (docEl && docEl.getAttribute('csrf-token')) || '';
    if (docToken) return docToken;
    throw new Error(`取不到 CSRF token（HTTP ${res.status}）`);
  }

  // ------------------------------------------------------------ 抓取

  async function waitWhilePaused() {
    while (state.paused && !state.stopped) await sleep(1000);
  }

  function snippet(text, n) {
    const s = String(text || '').replace(/\s+/g, ' ').trim();
    return s.length > n ? `${s.slice(0, n)}…` : s;
  }

  function requestBody(mobyId, pageNo) {
    return {
      title: null,
      platform: [mobyId],
      genres: [],
      attributes: [],
      company: [],
      groups: [],
      year: null,
      endyear: null,
      sort: 'moby_score',
      perpage: PER_PAGE,
      page: pageNo,
      // 与站点默认值一致；0 可能被后端拒绝
      min_critic_votes: 5,
      min_user_votes: 25,
      include_dlc: false,
      include_nsfw: false,
      release_status: 'all',
      released_only: false,
      _csrf_token: state.csrf,
    };
  }

  async function requestOnce(mode, mobyId, pageNo) {
    const body = requestBody(mobyId, pageNo);
    let res;
    if (mode === 'json' || mode === 'json-header') {
      const headers = { 'Content-Type': 'application/json' };
      if (mode === 'json-header') headers['X-CSRF-TOKEN'] = state.csrf;
      res = await fetch('/game/?format=json', {
        method: 'POST',
        credentials: 'same-origin',
        headers,
        body: JSON.stringify(body),
      });
    } else if (mode === 'form') {
      const fd = new FormData();
      for (const [key, value] of Object.entries(body)) {
        if (value === null || value === undefined) continue;
        if (Array.isArray(value)) value.forEach((v) => fd.append(key, String(v)));
        else fd.append(key, String(value));
      }
      res = await fetch('/game/?format=json', {
        method: 'POST',
        credentials: 'same-origin',
        body: fd,
      });
    } else {
      const qs = new URLSearchParams();
      qs.set('format', 'json');
      qs.set('platform', String(mobyId));
      qs.set('order_by', 'moby_score');
      qs.set('perpage', String(PER_PAGE));
      qs.set('page', String(pageNo));
      res = await fetch(`/game/?${qs.toString()}`, {
        method: 'GET',
        credentials: 'same-origin',
      });
    }

    const text = await res.text();
    if (res.status === 403 || /Just a moment|Performing security verification/i.test(text)) {
      const e = new Error(`Cloudflare 验证（HTTP ${res.status}）`);
      e.challenge = true;
      throw e;
    }
    if (!res.ok) {
      const e = new Error(`HTTP ${res.status} ${res.statusText} | ${snippet(text, 400)}`);
      e.status = res.status;
      throw e;
    }

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('json') || text.trim().startsWith('{')) {
      let json;
      try {
        json = JSON.parse(text);
      } catch {
        throw new Error(`JSON 解析失败 | ${snippet(text, 400)}`);
      }
      const data = json && json.data ? json.data : json;
      if (!data || !Array.isArray(data.games)) {
        throw new Error(`响应缺少 games | ${snippet(text, 400)}`);
      }
      return data;
    }

    // 回退：GET 返回榜单 HTML 时，从 game-browser 的 initial-values 取数据
    const doc = new DOMParser().parseFromString(text, 'text/html');
    const el = doc.querySelector('game-browser');
    const raw = el && el.getAttribute(':initial-values');
    if (!raw) throw new Error(`响应不是 JSON/榜单 HTML | ${snippet(text, 400)}`);
    const data = JSON.parse(raw);
    if (!data || !Array.isArray(data.games)) throw new Error('initial-values 缺少 games');
    return data;
  }

  async function retryMode(mode, mobyId, pageNo) {
    let lastError = null;
    for (let attempt = 1; attempt <= MAX_RETRY; attempt++) {
      await waitWhilePaused();
      if (state.stopped) throw new Error('已停止');
      try {
        return await requestOnce(mode, mobyId, pageNo);
      } catch (e) {
        lastError = e;
        if (e.challenge) {
          state.paused = true;
          pauseBtn.textContent = '继续';
          log('遇到 Cloudflare 验证。请在浏览器里完成验证，然后点“继续”。', 'warn');
          setStatus('等待人机验证', '#ffd166');
          await waitWhilePaused();
          continue;
        }
        log(`[${mode}] 第 ${attempt}/${MAX_RETRY} 次失败：${e.message}`, 'error');
        if (attempt < MAX_RETRY) {
          log(`等待 ${RETRY_WAIT / 1000} 秒后重试`, 'warn');
          await sleep(RETRY_WAIT);
        }
      }
    }
    throw new Error(`多次重试仍失败：${lastError ? lastError.message : '未知错误'}`);
  }

  async function requestPage(mobyId, pageNo) {
    if (state.requestMode) return retryMode(state.requestMode, mobyId, pageNo);

    // 第一次请求：依次试四种方式，选中能用的那个
    let lastError = null;
    for (const mode of ['json', 'form', 'get', 'json-header']) {
      if (state.stopped) throw new Error('已停止');
      try {
        const data = await requestOnce(mode, mobyId, pageNo);
        state.requestMode = mode;
        log(`接口请求方式：${mode}`, 'ok');
        return data;
      } catch (e) {
        lastError = e;
        if (e.challenge) {
          state.paused = true;
          pauseBtn.textContent = '继续';
          log('遇到 Cloudflare 验证。请在浏览器里完成验证，然后点“继续”。', 'warn');
          setStatus('等待人机验证', '#ffd166');
          await waitWhilePaused();
          continue;
        }
        log(`[${mode}] 失败：${e.message}`, 'error');
      }
    }
    log('提示：点“诊断”可查看四种请求方式的详细返回。', 'warn');
    throw new Error(`四种请求方式都失败：${lastError ? lastError.message : '未知错误'}`);
  }

  async function diagnose() {
    if (state.running) {
      log('抓取进行中，不能诊断。', 'warn');
      return;
    }
    log('===== 诊断开始');
    try {
      state.csrf = await getCsrfToken();
      log(`已登录：${isLoggedIn()}；CSRF：${state.csrf ? `${state.csrf.slice(0, 8)}…` : '空'}`, 'ok');
    } catch (e) {
      log(`诊断失败：${e.message}`, 'error');
      return;
    }
    for (const mode of ['json', 'form', 'get', 'json-header']) {
      try {
        const data = await requestOnce(mode, 22, 1);
        const first = data.games && data.games[0];
        log(
          `[${mode}] 成功：total=${data.total} page=${data.page} perPage=${data.perPage}` +
          ` first=${first ? first.title : '无'}`,
          'ok'
        );
      } catch (e) {
        log(`[${mode}] 失败：${e.message}`, 'error');
      }
    }
    log('===== 诊断结束');
  }

  function platformScore(game, mobyId) {
    const list = game && Array.isArray(game.platforms) ? game.platforms : [];
    const p = list.find((x) => x && x.id === mobyId);
    if (!p) return null;
    const score = p.moby_score;
    return typeof score === 'number' && Number.isFinite(score) ? score : null;
  }

  async function scrapePlatform(item) {
    const collected = new Map();
    for (const mobyId of item.moby) {
      let pageNo = 1;
      let done = false;
      while (!done) {
        if (state.stopped) throw new Error('已停止');
        const data = await requestPage(mobyId, pageNo);
        const games = data.games || [];
        if (games.length === 0) break;

        for (let i = 0; i < games.length; i += 1) {
          const game = games[i];
          const score = platformScore(game, mobyId);
          if (score === null) {
            log(
              `${item.id}/${mobyId} 第 ${pageNo} 页第 ${i + 1} 条遇到无评分游戏，停止该平台页`,
              'warn'
            );
            done = true;
            break;
          }
          const gid = game.game_id;
          if (gid === undefined || gid === null) continue;
          collected.set(gid, {
            game_id: gid,
            title: game.title || '',
            score,
          });
        }

        const total = Number(data.total || 0);
        log(`${item.id}/${mobyId} 第 ${pageNo} 页：${games.length} 条，累计 ${collected.size} 条`);
        if (data.perPage && Number(data.perPage) !== PER_PAGE) {
          log(`注意：服务端每页 ${data.perPage} 条，不是 ${PER_PAGE} 条`, 'warn');
        }
        const first = games[0];
        const last = games[games.length - 1];
        if (first && last) {
          log(
            `  首：${first.title}（${platformScore(first, mobyId)}）` +
            ` / 末：${last.title}（${platformScore(last, mobyId)}）`
          );
        }
        setStatus(`${item.id} 抓取中（${collected.size} 条）`, '#58a6ff');

        if (done) break;
        if (games.length < PER_PAGE) break;
        if (total > 0 && pageNo * PER_PAGE >= total) break;
        pageNo += 1;
        await randSleep();
      }
    }

    const rows = Array.from(collected.values()).sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.title.toLowerCase() < b.title.toLowerCase() ? -1 : a.title.toLowerCase() > b.title.toLowerCase() ? 1 : 0;
    });
    return rows;
  }

  // -------------------------------------------------------------- CSV

  function csvCell(value) {
    const text = String(value);
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function toCsv(rows) {
    const lines = ['序号,中文名,英文名,评分,卡带ID'];
    rows.forEach((r, i) => {
      lines.push([i + 1, '', r.title, r.score, ''].map(csvCell).join(','));
    });
    return `﻿${lines.join('\r\n')}\r\n`;
  }

  async function saveFile(filename, content) {
    if (state.dirHandle) {
      const handle = await state.dirHandle.getFileHandle(filename, { create: true });
      const writable = await handle.createWritable();
      await writable.write(content);
      await writable.close();
      return;
    }
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  // ------------------------------------------------------------ 主流程

  async function run() {
    if (state.running) return;
    if (!isLoggedIn()) {
      log('未登录。请先在浏览器里登录 MobyGames，再点“开始”。', 'error');
      return;
    }
    const selected = Array.from(platformSelect.selectedOptions).map((o) => o.value);
    if (selected.length === 0) {
      log('没有选择机种。', 'warn');
      return;
    }

    state.running = true;
    state.paused = false;
    state.stopped = false;
    startBtn.disabled = true;
    stopBtn.disabled = false;
    pauseBtn.textContent = '暂停';
    setStatus('准备中', '#58a6ff');

    try {
      state.csrf = await getCsrfToken();
      log(`开始，共 ${selected.length} 个机种，每页 ${PER_PAGE} 条`, 'ok');

      let finished = 0;
      for (const id of selected) {
        if (state.stopped) break;
        const item = PLATFORMS.find((p) => p.id === id);
        if (!item) continue;
        log(`===== ${id} ${item.label} 开始`, 'ok');
        setStatus(`${id} 抓取中`, '#58a6ff');
        try {
          const rows = await scrapePlatform(item);
          const csv = toCsv(rows);
          await saveFile(`${id}.csv`, csv);
          finished += 1;
          log(`${id} 完成：${rows.length} 条 -> ${id}.csv`, 'ok');
        } catch (e) {
          if (state.stopped) break;
          log(`${id} 失败：${e.message}`, 'error');
        }
        await sleep(800);
      }

      if (state.stopped) {
        setStatus(`已停止，完成 ${finished} 个`, '#ffd166');
        log(`已停止，完成 ${finished} 个机种。`, 'warn');
      } else {
        setStatus(`全部完成：${finished} 个机种`, '#7ee787');
        log(`全部完成：${finished} 个机种。`, 'ok');
      }
    } catch (e) {
      log(`运行失败：${e.message}`, 'error');
      setStatus('运行失败', '#ff6b6b');
    } finally {
      state.running = false;
      state.paused = false;
      startBtn.disabled = false;
      stopBtn.disabled = true;
      pauseBtn.textContent = '暂停';
    }
  }

  function togglePause() {
    if (!state.running) return;
    state.paused = !state.paused;
    pauseBtn.textContent = state.paused ? '继续' : '暂停';
    if (state.paused) {
      setStatus('已暂停', '#ffd166');
      log('已暂停');
    } else {
      setStatus('继续抓取', '#58a6ff');
      log('继续');
    }
  }

  function stop() {
    state.stopped = true;
    state.paused = false;
    pauseBtn.textContent = '暂停';
    log('收到停止请求，当前请求结束后停止。', 'warn');
  }

  // ------------------------------------------------------------ 启动

  function init() {
    if (document.getElementById('moby-ranking-panel')) return;
    buildPanel();
    log(`脚本 v${SCRIPT_VERSION} 已加载。登录后点“开始”。`);
    if (!isLoggedIn()) log('当前未登录，请先登录。', 'warn');
    if (window.location.pathname.startsWith('/user/login')) {
      log('正在登录页；登录完成后再回来点“开始”。', 'warn');
    }
  }

  if (typeof GM_registerMenuCommand === 'function') {
    GM_registerMenuCommand('打开/关闭 MobyGames 榜单面板', () => {
      const el = document.getElementById('moby-ranking-panel');
      if (el) el.remove();
      else buildPanel();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
