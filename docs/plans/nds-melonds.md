# NDS（melonDS）接入方案

## Context

平台目前有 7 个可玩主机机种（`nes/snes/gb/gba/segaMD/segaGG/segaMS`），统一走 EmulatorJS 4.2.3。NDS 的机种词条早已存在（`backend/games/platforms.py:95`），但 `extensions` 为空，所以只能用于「游戏发现」的机种归一，不能上传、不能玩。

本次把 NDS 做成第 8 个可玩机种，目标是与现有主机一致的完整体验：**melonDS 核、固定竖排双屏、BIOS、机壳、美化封面、双屏截图、云存档、Docker/Windows 打包、文档与测试**。

### 已确定的决策

| 项 | 决策 |
|---|---|
| 内核 | 只用 `melonds`（EJS 的 `nds` 默认核） |
| 屏幕布局 | 固定 `Top/Bottom`，不提供用户切换 |
| 屏幕间隙 | `melonds_screen_gap = 24`（实现时按实际帧缓冲标定） |
| BIOS | **前端静态文件**：`frontend/public/emulatorjs/bios/nds.zip`，用户自备、不进 git |
| 上传上限 | nginx `client_max_body_size` 128m → **512m** |
| 机壳 | **多洞结构 + 屏幕间隙**，铰链落在两屏之间的黑边上 |
| 截图 | **整屏双屏截图**（如 256×408），三处预览改为竖版/按比例适配 |
| 素材 | 先用 Pillow 生成占位框图提交，几何写死并在注释里说明，后续替换真实素材 |

### 不做

- 不接 `desmume` / `desmume2015`，不做运行时切换内核。
- 不做屏幕布局切换 UI（`Left/Right`、单屏等）。
- 不做 BIOS 上传界面；BIOS 只认静态文件。
- 不新增截图表字段/接口，不改 NDS 存档格式。
- 不画真实机壳/卡带美术，只提交占位图。

---

## 实施步骤

### 阶段 1：机种接入、melonDS 资产、存档上限

**后端**

- `backend/games/platforms.py:95-99`：`nds` 词条补
  `extensions=(".nds",)`、`default_extension=".nds"`。
  同步更新模块 docstring（`:20-21` 里「本项目还没打包 core 的 n64/psx/nds 等」）。
- `backend/games/settings_service.py:14`：`_EMULATOR_TYPES` 加 `"nds"`，否则「保存配置」400。
- `backend/games/save_service.py:16`：`_SAVE_MAX_FILE_SIZE` 从 8MB 改为 **64MB**。
  理由：melonDS 即时存档约 19–32MB；注释改成这个事实。

`GAME_TYPES`、扩展名白名单、`detect_game_type()`、CRC、播放路由都从 `playable_platforms()` 派生，不需要手改。

**前端**

- `frontend/src/constants/gameTypes.js`：在 `gba` 之后加 NDS 条目：

  ```js
  {
      slug: "nds",
      label: "任天堂 NDS",       // 必须与 platforms.py 逐字一致
      kind: "emulator",
      core: "nds",               // 系统 key；不要写 "melonds"
      extensions: [".nds"],
      icon: "🎮",
      description: "通过 EmulatorJS（melonDS）在浏览器内运行；支持账号云存档。",
  }
  ```

- `frontend/src/views/games/emulator-player.vue:192-200`：`EMU_NATIVE` 加
  `nds: { width: 256, height: 408 }`（408 = 192 + 24 gap + 192，标定后校正）。
- `frontend/scripts/fetch-emulatorjs.mjs:45-76`：`FILES` 加

  ```js
  "cores/melonds-wasm.data",
  "cores/melonds-legacy-wasm.data",
  "cores/reports/melonds.json",
  ```

  文件头与清单注释里的「6 个平台」改成「7 个平台/机种」；`EJS_VERSION` 保持 `4.2.3`。
  CDN 4.2.3 上这三个文件已确认存在，两个 wasm.data 各约 1.19MB。

**测试**

- `tests/test_games.py:122-139` 加 `.nds → nds`；`:527-540` 参数化加 `("nds", ".nds")`。
- `tests/test_platforms.py` 自动覆盖，不需要改。

**验收**：`pytest tests/test_platforms.py tests/test_games.py -q`；`npm run fetch:emulatorjs` 后三个文件非空。

---

### 阶段 2：BIOS 静态包

**文件**

- `frontend/public/emulatorjs/bios/nds.zip`，zip 根目录放 `bios7.bin`、`bios9.bin`、`firmware.bin`。
- 根 `.gitignore:13` 已整体忽略 `frontend/public/emulatorjs/`，不需要新增规则；**不要提交 zip**。

**宿主页 `frontend/public/emulator-host.html`**

- 常量：
  ```js
  const NDS_BIOS_URL = "/emulatorjs/bios/nds.zip";
  const NDS_LAYOUT = { layout: "Top/Bottom", gap: "24" };
  ```
- `start()`（`:570`）里在 `EJS_defaultOptions` 初始化后加：
  ```js
  if (core === "nds") {
      window.EJS_biosUrl = NDS_BIOS_URL;
      window.EJS_defaultOptions.melonds_screen_layout = NDS_LAYOUT.layout;
      window.EJS_defaultOptions.melonds_screen_gap = NDS_LAYOUT.gap;
  }
  ```
- `EJS_onGameStart`（`:601`）里对 nds 再强制一次：
  ```js
  const manager = window.EJS_emulator?.gameManager;
  manager?.setVariable?.("melonds_screen_layout", NDS_LAYOUT.layout);
  manager?.setVariable?.("melonds_screen_gap", NDS_LAYOUT.gap);
  ```
  若实测 `setVariable` 需要重启才生效，以「启动前剔除保存设置」为主（见「关键设计」），这里只作兜底。
- 启动前预检：现有 loader HEAD 检查扩展成「loader + （nds 时）BIOS」两项。BIOS 缺失时中文提示：
  > NDS BIOS 缺失：请把 bios7.bin、bios9.bin、firmware.bin 打包成 nds.zip，放到 `frontend/public/emulatorjs/bios/`（Docker 需重建 web 镜像；Windows 包放到 `web/emulatorjs/bios/`）后重试。

**缓存（关键）**

`/emulatorjs/` 现在是 immutable 一年，BIOS 会顶住旧文件。两处都要加更具体的 no-cache 规则：

- `frontend/nginx.conf.template`：在 `location ^~ /emulatorjs/` 之前加
  ```nginx
  location ^~ /emulatorjs/bios/ {
      try_files $uri =404;
      add_header Cache-Control "no-cache";
      default_type application/zip;
  }
  ```
  更长的 `^~` 前缀优先命中，不继承父级 immutable。
- `backend/static_site.py`：
  - 新增 `_NO_CACHE_PREFIXES = ("emulatorjs/bios/",)`；
  - `_file_response()`（`:123`）先判 no-cache 前缀，再判 immutable；
  - `_MIME_TYPES` 加 `".zip": "application/zip"`；
  - `serve_frontend()` 的 404 分支不变（`emulatorjs/bios/` 仍属于 `emulatorjs/`，缺文件直接 404，不回落 SPA）。

**Windows 打包**

`packaging/windows/build-win-dist.sh` 在 `cp -a "$REPO/frontend/dist/." "$PKG/web/"`（`:95-96`）之后加：

```bash
if [ -d "$REPO/frontend/public/emulatorjs/bios" ]; then
    mkdir -p "$PKG/web/emulatorjs/bios"
    cp -a "$REPO/frontend/public/emulatorjs/bios/." "$PKG/web/emulatorjs/bios/"
else
    say "提示：宿主机没有 NDS BIOS 包，Windows 包的 NDS 会提示缺少 BIOS。"
fi
```

`Dockerfile.build` 不需要改；Docker 路线靠 `frontend/Dockerfile` 的 `COPY . .` 自动带上 `public/emulatorjs/bios`。

**测试**

- `tests/test_static_site.py` fixture 增加 `emulatorjs/bios/nds.zip`；
  断言 BIOS 的 `Cache-Control: no-cache`、缺文件 404、`melonds-wasm.data` 仍是 immutable + octet-stream。

---

### 阶段 3：实机标定（手工门禁）

用一盘 `.nds`（带 BIOS）跑通后，在播放页 devtools 记录：

| 项 | 方法 | 用途 |
|---|---|---|
| 帧缓冲尺寸 | `iframe.contentWindow.__ejsRpc.videoInfo()` 的 width/height/aspect | 确认 gap 是否计入、实际高度 |
| 截图尺寸 | `__ejsRpc.screenshot()` 的 PNG 宽高 | 双屏是否都截到 |
| 存档大小 | `await __ejsRpc.capture()` 的 `size` | 64MB 是否够 |
| BIOS 是否必需 | 临时移走 `nds.zip` 启动 | 预检是硬拦截还是警告 |
| 实际内核 | Network 过滤 `melonds` | 确认不是 desmume |

**假设值**：`256×408`、`aspect = 256/408 ≈ 0.62745`。若实测不是（例如 gap 不计入、高度 384），以截图 PNG 为准同时改 `EMU_NATIVE.nds`、`SHELLS.nds.holes` 和生成脚本，**不能只改一边**。

---

### 阶段 4：机壳多洞结构

**素材**

- `frontend/src/assets/shells/nds-shell.png`（Pillow 生成占位图）。
- 初始几何（与 256×408 对应，整体 2.5 倍）：

  | 项 | 值 |
  |---|---|
  | 整图 | `800 × 1220` |
  | 上洞 | `(80, 100) 640 × 480` |
  | 下洞 | `(80, 640) 640 × 480` |
  | 铰链带 | `y = 580..640`，高 60 |
  | bounds | `(80, 100) 640 × 1020` |
  | 比例 | `640/1020 = 256/408`；`60/2.5 = 24` |

  洞必须**全透明**；机身不透明；铰链画在两洞之间。

**`emulator-player.vue`**

- import `ndsShellUrl`。
- `SHELLS`（`:218-249`）统一改成 `holes` 数组，**现有 5 个条目也改成单元素数组**，只保留一套结构：

  ```js
  { url, image: { width, height }, holes: [{ x, y, width, height }, ...] }
  ```

- 新增纯函数 `shellBounds(spec)`：取所有洞的 `x/y` 最小值和右/下边界，返回外接矩形。
- `shellStyle`（`:439`）：
  ```js
  const bounds = shellBounds(spec);
  const scale = stage.width / bounds.width;
  left = rect.left - bounds.x * scale;
  top  = rect.top  - bounds.y * scale;
  width  = spec.image.width * scale;
  height = spec.image.height * scale;
  ```
- `fitInArea`（`:562`）开机壳时用 `bounds` 代替 `spec.hole`，先按整图比例塞进可用区域，再乘 `bounds`。
- 更新 `:202-217` 的几何注释：多洞、bounds、NDS 的 gap 假设、换素材必须同步改整图尺寸与洞坐标。
- 单洞条目的 `bounds === hole`，现有 GBA/GBC/FC 行为逐像素不变。

**验收**：开关机壳、1×/1.5×/2×/3×/适应窗口/全屏，铰链必须正好压在 gap 上。

---

### 阶段 5：美化封面 NDS 卡带

**后端 `backend/games/models.py`**

- `COVER_TYPES_BY_GAME_TYPE`（`:35`）加 `"nds": ("nds",)`。
- `COVER_TYPE_LABELS`（`:42`）加 `"nds": "NDS"`。
- 两处必须同时加，否则 `validate_cover_type()` 会 `KeyError`。

**前端 `frontend/src/constants/coverStyles.js`**

- import `ndsCartUrl from "@/assets/carts/nds-cart.png"`。
- `CART_STYLES`（`:98`）加：

  ```js
  nds: {
      label: "NDS",
      url: ndsCartUrl,
      image: { width: 640, height: 480 },
      hole: { x: 70, y: 80, width: 500, height: 357 },
      radius: 10,
  },
  ```

- `STYLE_BY_GAME_TYPE`（`:139`）加 `nds: ["nds"]`。
- `STYLE_META`（`:153`）加 NDS 条目（`output` 展开 `CART_STYLES.nds.image`；`hint` 写「建议 500 : 357（约 1.40:1）」）。
- 文件头几何表补一行：`nds-cart.png 640×480 洞口 (70,80) 500×357 圆角 10`。

**素材**：`frontend/src/assets/carts/nds-cart.png`，640×480 RGBA；洞口区域**填机身色、不透明**（与机壳洞相反），轮廓外透明。

`coverCompose.js`、`CoverBeautifyDialog.vue`、管理页都按表通用，不需要改。

---

### 阶段 6：双屏截图与三处预览

**共享尺寸常量**

新增 `frontend/src/constants/emulatorScreens.js`，把 `emulator-player.vue` 的 `EMU_NATIVE` 移进去，并导出：

```js
export const EMU_NATIVE = { ..., nds: { width: 256, height: 408 } };
export function screenshotAspect(gameType) {
    const size = EMU_NATIVE[gameType];
    return size ? size.width / size.height : 1;
}
```

`emulator-player.vue` 改为 `import { EMU_NATIVE } from "@/constants/emulatorScreens"`，其余用法不变。

**适配规则**

- 只对**截图**用竖版框；封面、图集仍保持 1:1，避免改变现有 7 个机种的观感。
- 框宽不变（180），高度 = `180 / aspect`；NDS 约 `180 × 287`。
- 图片仍 `object-fit: contain`，不裁切、不拉伸。

**确认框 `ScreenshotConfirmDialog.vue`**

- props 加 `previewWidth` / `previewHeight`。
- `shot-confirm__frame` 从固定 180×180 改为 `width:180px` + 内联 `aspect-ratio: min(1, w/h)`（无尺寸时 1/1）。
- `emulator-player.vue:757-779` 记录 `result.width/height`，在 `releaseShot` 里清空，传给确认框。

**详情图片栏 `GameScreenshotGallery.vue`**

- props 加 `screenshotAspect`（默认 1）。
- `slots` 里给每项加 `kind`（`cover` / `gallery` / `screenshot`）。
- 只有 `kind === "screenshot"` 的 frame 用 `aspect-ratio: screenshotAspect`；其余保持 1/1。
- `.gallery__track` 加 `align-items: flex-end`；`.gallery__nav` 的 `top: 90px` 改为 `calc(var(--frame-h) / 2)`，`--frame-h` 取 `max(180, 180 / screenshotAspect)`。
- `PAGE_SIZE`、`CELL_SIZE`、`CELL_GAP`、`PAGE_OFFSET` 不变，横向翻页不受高度影响。
- `GameDetailDialog.vue` 传入 `:screenshot-aspect="screenshotAspect(detail.game_type)"`。

**截图管理 `ScreenshotManagerDialog.vue` / `ImageAlbumDialog.vue`**

- `ScreenshotManagerDialog` 新增 `frameAspect` prop（默认 1），透传给 `ImageAlbumDialog`。
- `GameDetailDialog` 打开管理弹框时传同样的 `screenshotAspect(detail.game_type)`；图集管理走默认 1。
- `ImageAlbumDialog` 的 `.album__frame` 保留默认 `aspect-ratio: 1/1`，有 `frameAspect` 时内联覆盖；`.album__grid` 加 `align-items: end`。
- 网格列宽仍 `minmax(150px, 1fr)`，不新增分页概念。

**后端**：`backend/games/images.py` 的 magic/16MB 校验、路径 `image/{用户名}/{game_type}/{卡带ID}/` 都不需要改。

---

### 阶段 7：上传上限与打包

- `frontend/nginx.conf.template:10`：`client_max_body_size 128m;` → `512m;`，注释补「NDS 本体可达数百 MB」。
- 应用层上限保持不变：`archive.py` 的 ZIP 128MB、攻略 PDF 128MB、图片 16MB；只放宽网关。
- 同步「nginx 128m」相关注释：`backend/games/images.py:12`、`backend/games/archive.py:42`、`backend/games/service.py:107`、`backend/request_limit.py:1,3,17`、`backend/__init__.py:72`、`packaging/windows/README.md`。
- Docker：改完 `public/emulatorjs`（core + BIOS）后 `docker compose build web && docker compose up -d web`。
- Windows：`build-win-dist.sh` 的 BIOS 拷贝见阶段 2；新增 core 后 `build-in-docker.sh` 的构建镜像哈希会变，`make win` 会自动重建构建镜像（需联网一次）。
- 出包后检查：`web/emulatorjs/data/cores/melonds-wasm.data`、`melonds-legacy-wasm.data`、`reports/melonds.json`，以及（用户自备时）`web/emulatorjs/bios/nds.zip`。

---

### 阶段 8：占位素材生成、文档、测试

**占位素材**

- 新增 `scripts/make_nds_placeholders.py`（Pillow 12 可用），提交脚本与两张 PNG：
  - `frontend/src/assets/shells/nds-shell.png`：800×1220，圆角机身、两个 640×480 全透明洞、60px 铰链带，可加简单按钮/扬声器装饰。
  - `frontend/src/assets/carts/nds-cart.png`：640×480，洞口 (70,80) 500×357 填机身色、轮廓外透明，可加顶部缺口。
- 脚本顶部写死几何常量，并断言 `640/1020 == 256/408`、`60/2.5 == 24`、`500/357 ≈ 1.4`。
- docstring 写明：**替换真实素材后不要再跑脚本**，否则会覆盖。

**文档同步**

- `CLAUDE.md` 第 7、79-80 行一带：机种列表、封面类型、播放页/机壳说明。
- `AGENTS.md` 第 9、44、193-194、232、425、541-542 行一带。
- `docs/architecture.md` 30-31、51、82-85、146-147、191-192、323-326、408-412、474-493、535-545、555-562。
- `docs/data_dict.md` 38、75、153、226-227。
- `README.md` 平台列表、机壳、封面类型、上传限制。
- `packaging/windows/README.md`：BIOS 放置位置与 512m 网关。
- `frontend/scripts/fetch-emulatorjs.mjs` 文件头/清单注释。
- `platforms.py` docstring 里「nds 未开放」的说明。

**测试**

- `tests/test_game_emulator_settings.py`：补 nds 的 GET/PUT 往返；`flash` 仍 400。
- `tests/test_static_site.py`：`emulatorjs/bios/` no-cache、缺文件 404、melonds MIME。
- `tests/test_games.py`：`.nds` 判定与上传参数化。
- `tests/test_platforms.py` 自动通过（前端 label、GAME_TYPES 顺序、扩展名不重叠）。
- 前端没有测试框架，机壳几何与截图预览靠手测。

---

## 关键设计

### 双屏机壳的定位

- 机壳只认 `holes` 的外接矩形 `bounds`，不关心洞内部。
- `scale = stage.width / bounds.width`，整图按同一 scale 放大，再用 `bounds.x/y` 把洞对齐到舞台左上角。
- `fitInArea` 开机壳时先按整张图比例塞进可用区域，再用同一 scale 乘 `bounds` 得到舞台尺寸。
- 因此 `stageAspect` 必须等于 `bounds.width / bounds.height`；NDS 标定后若 `aspect` 不符，改 `EMU_NATIVE` 与机壳几何两边。

### 布局与云端设置的冲突

引擎只在启动前读一次设置块 `{controlSettings, settings, cheats}`；云端设置会覆盖 `EJS_defaultOptions`。因此：

1. **主措施**：`launchEngine` 写云端设置前，对 `nds` 剔除 `settings.melonds_screen_layout` 与 `settings.melonds_screen_gap`；同时把本机已存的设置块也剔除这两个键后再写回。这样宿主页的 `EJS_defaultOptions` 一定生效。
2. **兜底**：`EJS_onGameStart` 里再 `setVariable` 一次，防止引擎自己写回了旧值。
3. 不新增 UI，不删除引擎设置菜单项；`melonds_screen_gap` 若标注「需要重启」，以第 1 条为准。

建议在 `frontend/src/utils/emulatorSettings.js` 加一个纯函数：

```js
export function stripNdsDisplayOptions(value) { ... }  // 返回新对象，不改入参
```

`applyCloudSettings()` 与 `launchEngine` 里对 nds 调用它。

### BIOS 缓存

- 文件名固定、用户随时可能替换，所以用 **no-cache**，不用 `?v=`。
- nginx 与 `static_site.py` 两处必须一致（项目规则：静态行为规范以 nginx 为准）。
- EJS 自己会按 HEAD 的 `Content-Length` 判断是否复用已解压的 BIOS；若遇到「同字节长度替换」仍复用旧文件，再考虑给 URL 加 `/version.txt` 的版本参数。

### 截图比例

- 不存宽高、不改表；前端按游戏类型的帧缓冲比例决定截图框。
- 封面/图集保持 1:1，只有截图框在 NDS 下变高，现有 7 个机种观感不变。
- 确认框用实际截图宽高，能承受未来其它竖屏机种。

### 占位素材替换约定

| 素材 | 整图 | 洞 | 备注 |
|---|---|---|---|
| `nds-shell.png` | 800×1220 | 上 `(80,100) 640×480`；下 `(80,640) 640×480` | 洞全透明；铰链带 60px；换图必须同步 `SHELLS.nds` 与 `EMU_NATIVE.nds` |
| `nds-cart.png` | 640×480 | `(70,80) 500×357`，圆角 10 | 洞口填机身色、不透明；换图必须同步 `CART_STYLES.nds` |

---

## 风险与验证

| 风险 | 验证方法 | 不通过时 |
|---|---|---|
| gap 不计入帧缓冲 | `videoInfo.height` + 截图 PNG 高度 | 高度按 384 修正；机壳洞改为无 gap，或降低 gap，铰链绝不能压画面 |
| `aspect` 与 `width/height` 不一致 | 比较两者，误差 < 0.001 | 以 `aspect` 和截图真实尺寸为准重定 `EMU_NATIVE` 与机壳 |
| BIOS 实际非必需 | 移走 `nds.zip` 启动 | 预检从硬拦截改为警告 |
| BIOS zip 结构不对 | 引擎 Network/Console 看解压结果 | zip 根目录必须是三个 bin |
| 存档超过 64MB | `capture().size` | 调高 `_SAVE_MAX_FILE_SIZE`（96MB），确认 512m 网关余量 |
| base64 捕捉/上传卡顿 | `performance.now()` 包住 capture/转换/上传 | 若 >2s，追加返回 ArrayBuffer/Blob 的 RPC，本次先实测 |
| 截图只截到上屏 | `__ejsRpc.screenshot()` 的宽高 | 改用 canvas 路径，必要时在宿主页组合画布 |
| 机壳铰链遮画面 | 各倍率/全屏逐项看 | 调整 gap、`EMU_NATIVE`、洞坐标，实机标定后再定稿 |
| WebGL2 不可用 | Network 看请求 legacy 还是非 legacy | 两个文件都已打包；老浏览器仍可能起不来 |
| BIOS 旧缓存 | `curl -I .../emulatorjs/bios/nds.zip` | 检查 nginx location 与 `static_site.py` 前缀顺序 |
| Windows 包缺 core/BIOS | 解包检查 `web/emulatorjs/` | 检查 `make win` 是否重建构建镜像、BIOS 拷贝分支 |

---

## 验证清单

**后端**

- [ ] `pytest tests/test_platforms.py tests/test_games.py tests/test_game_emulator_settings.py tests/test_static_site.py -q`
- [ ] 全量 `pytest -q`

**前端**

- [ ] `cd frontend && npm run lint`
- [ ] `npm run fetch:emulatorjs` 后 `public/emulatorjs/data/cores/melonds-*` 存在
- [ ] `npm run build` 后 `dist/emulatorjs/data/cores/melonds-*` 存在

**手动主路径**

- [ ] 上传 `.nds`，管理页显示「任天堂 NDS」，类型自动判定
- [ ] 播放页加载 `melonds`（不是 desmume），双屏竖排、24px gap
- [ ] 开「显示机壳」，铰链落在 gap 上；各倍率/全屏不错位
- [ ] 截图确认框为竖版；详情图片栏与截图管理按竖版显示；其它机种仍 180 方框
- [ ] 云存档：捕捉、下载、同步、还原；19–32MB 存档不被拦
- [ ] 美化封面：选「NDS」，输出 640×480；游戏中心分组正常
- [ ] BIOS 缺失时中文提示；放回 zip 后正常启动
- [ ] 512m 网关下上传一个 >128MB 的 NDS 本体成功

**打包**

- [ ] `docker compose build web && docker compose up -d web`
- [ ] `curl -I https://<host>/emulatorjs/bios/nds.zip` 返回 `Cache-Control: no-cache`
- [ ] `make win` 成功；包内 core 与 BIOS 齐全；启动器能玩 NDS

---

## 关键文件

- `backend/games/platforms.py`
- `backend/games/settings_service.py`
- `backend/games/save_service.py`
- `backend/games/models.py`
- `backend/static_site.py`
- `frontend/src/constants/gameTypes.js`
- `frontend/src/constants/coverStyles.js`
- `frontend/src/constants/emulatorScreens.js`（新增）
- `frontend/src/utils/emulatorSettings.js`
- `frontend/src/views/games/emulator-player.vue`
- `frontend/src/components/games/ScreenshotConfirmDialog.vue`
- `frontend/src/components/games/GameScreenshotGallery.vue`
- `frontend/src/components/games/ScreenshotManagerDialog.vue`
- `frontend/src/components/games/ImageAlbumDialog.vue`
- `frontend/src/components/games/GameDetailDialog.vue`
- `frontend/public/emulator-host.html`
- `frontend/scripts/fetch-emulatorjs.mjs`
- `frontend/nginx.conf.template`
- `packaging/windows/build-win-dist.sh`
- `scripts/make_nds_placeholders.py`（新增）
- 测试：`tests/test_games.py`、`tests/test_game_emulator_settings.py`、`tests/test_static_site.py`

---

## 待确认问题（实机标定前）

以下事项无法只靠仓库静态确认，实施时按顺序记录结论；有结论后回填本文件并修正相关常量。

1. **gap 是否计入帧缓冲**：`melonds_screen_gap = 24` 后，`__ejsRpc.videoInfo()` 的高度是 408 还是 384；截图 PNG 的真实宽高是多少。以实测为准同时改 `EMU_NATIVE.nds`、`SHELLS.nds.holes` 与生成脚本。
2. **核心选项键名与取值**：EJS 4.2.3 里 `melonds_screen_layout` / `melonds_screen_gap` 是否就是设置块里的键名，`Top/Bottom` 与 `24` 是否被接受；`setVariable` 修改后是否需要重启内核才生效。
3. **BIOS 是否真的必需**：移走 `nds.zip` 后 melonDS 是否回退 FreeBIOS。若可回退，把启动预检从硬拦截改为警告。
4. **BIOS zip 结构**：三个文件必须在 zip 根目录；EJS 的 `downloadBios()` 解压后写入虚拟 FS 根目录。若引擎报找不到，检查压缩包层级与文件名。
5. **即时存档大小**：`capture().size` 实测是否落在 19–32MB；64MB 上限是否足够。若超过，调高 `_SAVE_MAX_FILE_SIZE` 并确认 512m 网关余量。
6. **双屏截图范围**：`__ejsRpc.screenshot()` 是否同时截到上下两屏，还是只截上屏；若只截上屏，改用 canvas 路径并在宿主页组合画布。
7. **设置块结构**：云端/本机设置里的核心选项是否确实位于 `settings` 对象下（`{controlSettings, settings, cheats}`）。`stripNdsDisplayOptions()` 按此实现；若层级不同，先改实现再联调。
8. **512m 上传**：nginx 会把大请求体缓冲到临时文件，需实测磁盘空间与上传耗时；Windows 包的 `request_limit.py` 默认已是 512MB，不需要改。
9. **真实素材替换**：替换 `nds-shell.png` / `nds-cart.png` 后，必须同步 `SHELLS.nds`、`EMU_NATIVE.nds`、`CART_STYLES.nds` 与 `scripts/make_nds_placeholders.py` 的几何；替换后不要再运行生成脚本，否则会覆盖。
