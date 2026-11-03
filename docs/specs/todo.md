# 待接机种清单

## 范围与权威

- 本文是「还要接哪些机种、按什么顺序接」的计划，不定义已有机种的事实。
- 机种词表与可玩机种的权威仍是 [`platforms.md`](platforms.md) 与 `backend/games/platforms.py`。
- 机种名称与先后都取词表顺序，接入后就是游戏类型下拉的展示顺序。
- 下拉顺序 = `/status.game_types` = `flash`、`h5` + 词表里的可玩机种。
- 引擎基线固定 EmulatorJS **4.2.3**，system key 与 core 取自其 `getCores()`。
- 下表只列 EmulatorJS 支持的机种；key / core 与 `getCores()` 一致，由 `tests/test_platforms.py` 钉住。
- 词表当前共 36 个机种，已可玩 34 个，剩余 2 个。
- 剩余 2 个 `sega` / `mame` 是引擎兜底 key，不单独接，因此没有待新增机种。
- 第 1 档 13 个已全部接入，包括 Commodore 五个：
  `c64`、`c128`、`pet`、`plus4`、`vic20`。
- 第 2 档 3 个已全部接入：`atari5200`、`lynx`、`coleco`；BIOS 机制已通用化。
- 第 3 档 5 个已全部接入：`n64`、`segaSaturn`、`psx`、`pcfx`、`3do`；
  单文件镜像按 `.chd` / `.pbp` / `.iso` 收，多文件格式留给第 4 档。
- 第 4 档 2 个已全部接入：`segaCD`、`amiga`；多文件本体走 `body/` 目录 +
  `EJS_externalFiles`，多碟用 m3u。
- Commodore 共用 `.d64` / `.prg`，由「后缀候选集 + 用户选择」消歧；
  创建后也能在编辑弹框里改类型。
- 第 5 档 3 个已全部接入：`psp`、`dos`、`arcade`；线程按机种开启，
  `.zip` 三义（HTML5 / DOS / 街机）由用户显式选择，街机保留 romset 名。
- 机种清单当前为空；以后新增待接机种时再按词表顺序补表。
- 结论：第 1–5 档已完成，词表 36 个机种中 34 个可玩，剩下 `sega` / `mame` 两个兜底 key。

## 工作量的五个档位

| 档 | 机种数 | 主要工作 | 相对工作量 |
|---|---|---|---|
| 1 | 0 | 已全部接入 | — |
| 2 | 0 | 已全部接入（BIOS 机制已通用化） | — |
| 3 | 0 | 已全部接入（单文件 CD 镜像） | — |
| 4 | 0 | 已全部接入（多文件本体 + m3u 多碟） | — |
| 5 | 0 | 已全部接入（线程 + COOP/COEP + ZIP 三义） | — |

## 机种清单（按词表顺序）

已可玩的 34 个不在下表重复列出。当前没有待接机种；`sega` / `mame` 是引擎兜底 key，
不单独接入。新增机种时再在这里补表。

## 各档说明

### 第 1 档：纯配表（已全部接入）

13 个均已接入：`vb`、`sega32x`、`pce`、`ngp`、`ws`、`atari2600`、`atari7800`、
`jaguar`、`c64`、`c128`、`pet`、`plus4`、`vic20`。

单文件 ROM、无必须 BIOS、非线程核。加机种要同步：

- `platforms.py` 的 `extensions` 与 `default_extension`（唯一权威）。
- `fetch-emulatorjs.mjs` 的 core 文件：`-wasm.data`、`-legacy-wasm.data`、report。
- `emulatorScreens.js` 的 `EMU_NATIVE` 画幅。
- 前端 `gameTypes.js` 只是适配器，label / 扩展名从 `/status` 读取，不用再抄。

- 云端模拟器设置的类型集合从词表派生，不用手改 `settings_service.py`。
- Commodore 五个共用 `.d64` / `.prg`：创建时按后缀候选集弹下拉，编辑时可改类型。
- Commodore 系列是计算机，键鼠输入、磁盘镜像启动与多盘操作仍需实机回归。
- `pce` 的 CD 游戏不在本档，见第 4 档。

### 第 2 档：需要 BIOS 机制（已全部接入）

`atari5200`、`lynx`、`coleco`，均已接入。

仍是单文件 ROM，但核启动缺 BIOS 会黑屏。已完成一次通用化：

- BIOS 规格写进 `platforms.py` 的 `BiosSpec`，经 `/status.types[].bios` 与游戏列表条目的
  `bios` 下发；宿主页按播放页传来的文件名校验并拼 `/emulatorjs/bios/<file>`。
- BIOS 仍打包成 ZIP，沿用 `nds.zip` 的 `EJS_biosUrl` 模式。
- 必需包缺失时给中文提示，不静默黑屏；可选包缺失时跳过并继续启动。

- Lynx 文档正文写「无 BIOS」，但表格把 `lynxboot.img` 标为 Required，按表格准备（必需）。
- 5200 文档未列 BIOS；`a5200` 核内置 AltirraOS，`5200.rom` 按可选处理，缺包回退。

### 第 3 档：单文件但重（已全部接入）

`n64`、`segaSaturn`、`psx`、`pcfx`、`3do`，均已接入。

只收单文件镜像，cue+bin 归到第 4 档：

- N64 无 BIOS，后缀 `.z64` `.n64` `.v64`。
- 土星只收 `.chd`；PS1 收 `.chd` `.pbp` `.iso`；PC-FX 只收 `.chd`；
  3DO 收 `.iso` `.chd`。`.bin` / `.cue` 继续不收。
- `.chd` 在四台机种间共用，候选顺序按词表；默认项由覆盖表指定为更常见的 PS1。
- PS1 / 土星核有 HLE BIOS 回退，但兼容性差，按必需处理；PC-FX 的 `pcfx.rom`
  必须正好 1 MiB；3DO 按 EJS 文档也按必需。
- 播放 URL 末段必须带真实落盘名（`game.<ext>`），EmulatorJS 才能识别 `.pbp` 等格式。
- 土星的 wasm 性能最差，仍需实机确认可玩阈值。
- 本地上传超过 30MB 已改走 16MB 分片，单盘总大小只受磁盘限制；网络直链仍限 512MB。

### 第 4 档：多文件 / 多碟（已全部接入）

对应：`segaCD`、`amiga`，均已接入。

落地方案：

- 单文件仍走 `game.{ext}`：世嘉 CD 收 `.chd`，Amiga 收 `.adf` / `.hdf`。
- 多文件本体存 `game/{type}/{卡带ID}/body/`，带 `manifest.json`；
  `games.game_path` 指向入口（统一改名 `game.{cue|m3u|chd|adf|hdf}`）。
- 每个物理文件各开一个现有分片会话，创建/换本体时一次提交多个 `upload_ids`；
  不新增打包会话，分片、重试、TTL 与清理全部复用。
- 播放接口新增 `/play/manifest` 与 `/play/files/{name}`；宿主页用
  `EJS_externalFiles` 把其余文件写进 MEMFS，多碟用 m3u + EJS 内置 Disk 菜单。
- `.cue` / `.m3u` / `.bin` 只进 `bundle_extensions`，不进单文件 `extensions`，
  因此 `.cue` 单文件仍被拒绝，错误文案提示改用多文件上传。
- `.chd` 是世嘉 CD 推荐格式：cue/bin 会整份进浏览器内存，体积大时可能 OOM。

后续单独做：

- `pce` 的 CD 游戏与本档同源：要加 `syscard3.pce` 且 BIOS 必须按游戏而非按类型下发，
  本次不动 HuCard。
- PS1、土星、3DO 若收 cue+bin 原盘格式，可直接复用本档的 bundle 机制。
- 同一游戏多盘的自研换盘 UI 暂不做，先用 EJS Disk 菜单；实机不支持时再补。

### 第 5 档：线程与 ZIP 三义（已全部接入）

对应：`psp`、`dos`、`arcade`，均已接入。

- 宿主页不再固定 `EJS_threads=false`：`Platform.threads` 为真的机种（PSP / DOS）
  由播放页传 `threads=1`，其余机种保持关闭。
- HTML 文档（SPA 入口与 `emulator-host.html`）在 Docker nginx、Windows 静态站与
  Vite dev server 三处都带 `Cross-Origin-Opener-Policy: same-origin` 与
  `Cross-Origin-Embedder-Policy: require-corp`，让 `SharedArrayBuffer` 可用。
- H5 资源响应显式 `Cross-Origin-Embedder-Policy: unsafe-none` 与
  `Cross-Origin-Resource-Policy: cross-origin`，沙箱页里的外链资源不被隔离策略拦掉。
- PSP 收 `.iso` / `.cso`，核 `ppsspp` 只有线程变体并强制 WebGL2；
  除核心外还要打包 `cores/ppsspp-assets.zip`。
- DOS 收 `.jsdos` 与 `.zip`，核 `dosbox_pure` 只有线程变体；`.zip` 与 H5 / 街机共用后缀，
  创建时三选一，默认仍是 HTML5。
- 街机收 romset `.zip`，落盘名保持集合名（如 `mslug.zip`），否则 FBNeo 找不到集合；
  只打包默认 `fbneo`，BIOS 用可选 `arcade.zip`（`neogeo.zip`、`pgm.zip`）。
- 街机只接受本地上传；网络直链的临时名 `remote.zip` 无法满足集合名要求。

## 共性注意事项

- **`.bin` 不能直接开放**：Atari 2600/5200/7800 常用 `.bin`，会与多机种歧义。
- 这些机种用 `.a26` / `.a52` / `.a78` 等专属后缀。
- 新增机种的显示名统一为「公司名 + 空格 + 型号」，由 `tests/test_platforms.py` 钉住。
- **`.zip` 已被 H5 占用**：不能把 `.zip` 直接加给街机、DOS、Sega CD、Amiga。
- 多文件类型必须改成「用户选类型优先」，后缀只做提示。
- 线程开关现在是按机种的；PSP / DOS 之外保持关闭，避免影响其余 32 个机种。
- EJS 文档里的 3DS 属于 4.3-pre；本仓库钉死 4.2.3，不接。
- 不新增 `sega` / `mame` 两个兜底 key 的入口。

## 建议推进顺序

1. ~~先做 `vb`、`ngp`、`ws`、`pce`、`atari2600`，验证「加机种」链路。~~ 已接入。
2. ~~再做 BIOS 通用化，接 `atari5200`、`lynx`、`coleco`。~~ 已完成。
3. ~~第 1 档 13 个全部接入，含 Commodore 与类型选择/修改机制。~~ 已完成。
4. ~~接 `n64`，跑通第一个重核机种。~~ 第 3 档 5 个已全部接入。
5. ~~第 4 档 `segaCD`、`amiga` 与多文件本体。~~ 已完成。
6. ~~最后做第 5 档：PSP、DOS、街机。~~ 已完成；后续只剩 PCE CD 与街机数据治理增强。

## 测试要点

- 第 1 档：上传、播放、云存档、截图、列表分组各跑一遍。
- BIOS 档：BIOS 缺失时有中文提示，补齐后可正常启动。
- 重核档：确认帧率与截图比例，低配设备要有可接受的降级表现。
- 多文件档：多盘切换、存档、删除时不残留临时文件。
- 线程档：确认响应头带 COOP/COEP，且 PSP / DOS 之外的机种不受影响。
- 每档都要更新 `tests/test_platforms.py` 的词表不变量（显示名格式、扩展名、BIOS 规格）
  与 EJS `getCores()` 一致性断言。
- 待接清单本身也由测试校验：只允许列 EJS 支持的 key / core，且覆盖全部剩余机种。

## 相关文档

- [`platforms.md`](platforms.md)：机种词表与扩展名的权威说明。
- [`game-center-playback.md`](game-center-playback.md)：播放页、宿主页与核心资产。
- [`game-storage.md`](game-storage.md)：本体上传、磁盘路径与卡带 ID。
- [`delivery-docker.md`](delivery-docker.md)：nginx 与响应头。
- [`delivery-windows.md`](delivery-windows.md)：Windows 静态站与响应头。
