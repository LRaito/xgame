# 待接机种清单

## 范围与权威

- 本文是「还要接哪些机种、按什么顺序接」的计划，不定义已有机种的事实。
- 机种词表与可玩机种的权威仍是 [`platforms.md`](platforms.md) 与 `backend/games/platforms.py`。
- 引擎基线固定 EmulatorJS **4.2.3**，system key 与 core 取自其 `getCores()`。
- 词表当前共 36 个机种，已可玩 8 个，剩余 28 个。
- 剩余 28 个中 `sega` / `mame` 是引擎兜底 key，不单独接，真正可新增 **26 个**。
- 结论：按五档从易到难推进，先做纯配表，最后碰多文件与线程。

## 工作量的五个档位

| 档 | 机种数 | 主要工作 | 相对工作量 |
|---|---|---|---|
| 1 | 13 | 配表 + core 资产 | 每个约 0.5–1 小时 |
| 2 | 3 | BIOS 机制 + 配表 | 机制约半天，之后每个约 1 小时 |
| 3 | 5 | BIOS / 性能 / 画幅 QA | 每个约 0.5–1 天 |
| 4 | 2 | 多文件上传与播放链路 | 机制 2–3 天，每个 1–2 天 |
| 5 | 3 | 线程、COOP/COEP、数据模型 | 每个 3 天以上，街机以周计 |

## 第 1 档：纯配表

单文件 ROM、无必须 BIOS、非线程核。

只改四处：

- `platforms.py` 的 `extensions` 与 `default_extension`。
- `fetch-emulatorjs.mjs` 的 core 文件：`-wasm.data`、`-legacy-wasm.data`、report。
- `gameTypes.js` 的展示项与 system key。
- `emulatorScreens.js` 的 `EMU_NATIVE` 画幅。

| # | 机种 | key / core | 常用扩展名 | 说明 |
|---|---|---|---|---|
| 1 | 雅达利 2600 | `atari2600` / `stella2014` | `.a26` | 无 BIOS，核约 1 MB |
| 2 | 雅达利 7800 | `atari7800` / `prosystem` | `.a78` | BIOS 可选 |
| 3 | Virtual Boy | `vb` / `beetle_vb` | `.vb` | 无 BIOS |
| 4 | SNK NGPC | `ngp` / `mednafen_ngp` | `.ngc` | 无 BIOS |
| 5 | 万代 WonderSwan | `ws` / `mednafen_wswan` | `.ws` `.wsc` | 无 BIOS |
| 6 | 日电 PCE | `pce` / `mednafen_pce` | `.pce` `.sgx` | 先只开 HuCard |
| 7 | 世嘉 32X | `sega32x` / `picodrive` | `.32x` | 文档未列 BIOS，需实测 |
| 8 | Commodore 64 | `c64` / `vice_x64sc` | `.d64` `.tap` `.crt` `.prg` | 核自带 ROM |
| 9 | Commodore 128 | `c128` / `vice_x128` | `.d64` `.d71` `.prg` | 核自带 ROM |
| 10 | Commodore Plus/4 | `plus4` / `vice_xplus4` | `.prg` `.d64` | 核自带 ROM |
| 11 | Commodore VIC-20 | `vic20` / `vice_xvic` | `.prg` `.d64` | 核自带 ROM |
| 12 | Commodore PET | `pet` / `vice_xpet` | `.prg` `.d64` | 核自带 ROM |
| 13 | 雅达利 Jaguar | `jaguar` / `virtualjaguar` | `.j64` `.jag` | 接入易，兼容性差 |

- 第 13 项排最后，因为核兼容性差，回归成本高于前 12 项。
- Commodore 系列是计算机，键鼠输入与多盘操作要单独做回归。
- `pce` 的 CD 游戏不在本档，见第 4 档。

## 第 2 档：需要 BIOS 机制

仍是单文件 ROM，但核启动缺 BIOS 会黑屏。

先做一次通用化：

- 把宿主页里 NDS 专用的 `NDS_BIOS_URL` 与 HEAD 预检改成按机种查表。
- BIOS 仍打包成 ZIP，沿用 `nds.zip` 的 `EJS_biosUrl` 模式。
- 缺失时给中文提示，不静默黑屏。

| # | 机种 | key / core | 常用扩展名 | BIOS |
|---|---|---|---|---|
| 14 | 雅达利 Lynx | `lynx` / `handy` | `.lnx` | `lynxboot.img` 必需 |
| 15 | ColecoVision | `coleco` / `gearcoleco` | `.col` | `colecovision.rom` 必需 |
| 16 | 雅达利 5200 | `atari5200` / `a5200` | `.a52` | `5200.rom` 通常必需，需实测 |

- Lynx 文档正文写「无 BIOS」，但表格把 `lynxboot.img` 标为 Required，按表格准备。
- 5200 文档未列 BIOS，`a5200` 核通常需要 `5200.rom`，落地前先实测。

## 第 3 档：单文件但重

建议只收单文件镜像，cue+bin 归到第 4 档。

| # | 机种 | key / core | 单文件扩展名 | 主要成本 |
|---|---|---|---|---|
| 17 | 任天堂 N64 | `n64` / `mupen64plus_next` | `.z64` `.n64` `.v64` | 无 BIOS；核 1.45 MB；性能与画幅 |
| 18 | 索尼 PS1 | `psx` / `pcsx_rearmed` | `.chd` `.pbp` `.iso` | BIOS 按区必需 |
| 19 | 松下 3DO | `3do` / `opera` | `.iso` `.chd` | BIOS `panafz1.bin` 等必需 |
| 20 | 日电 PC-FX | `pcfx` / `mednafen_pcfx` | `.chd` | BIOS `pcfx.rom` 必需 |
| 21 | 世嘉土星 | `segaSaturn` / `yabause` | `.chd` | BIOS `saturn_bios.bin`；性能最差 |

- N64 排最前，因为没有 BIOS，配置层面与第 1 档相同。
- PS1、土星、3DO、PC-FX 都需要按区或按型号准备 BIOS。
- 土星的 wasm 性能最差，需先确认可玩阈值再决定是否开放。

## 第 4 档：多文件 / 多碟

当前上传只收单文件，播放只服务 `game.{后缀}` 一个文件。

机制工作：

- 支持 ZIP 或 cue+bin 组合上传。
- 播放接口把多文件清单交给 EJS。
- 扩展名判型要区分「用户选的类型」与「后缀推断」。

| # | 机种 | key / core | 形式 | 主要成本 |
|---|---|---|---|---|
| 22 | 世嘉 CD | `segaCD` / `genesis_plus_gx` | cue+bin / chd | BIOS `bios_CD_E/U/J.bin` 必需 |
| 23 | Amiga | `amiga` / `puae` | adf/hdf 多盘或 zip | Kickstart 必需；多盘与键鼠；核 4.1 MB |

- `pce` 的 CD 游戏与本档同源：加 `syscard3.pce` 与多文件。
- PS1、土星、3DO 若收 cue+bin 原盘格式，也落在本档。
- 同一游戏多盘的切换交互要单独定义，不能只解压了事。

## 第 5 档：需要改运行环境或数据模型

| # | 机种 | key / core | 为什么最麻烦 |
|---|---|---|---|
| 24 | 索尼 PSP | `psp` / `ppsspp` | 强制 `EJS_threads=true` + WebGL2 |
| 25 | DOS | `dos` / `dosbox_pure` | 强制线程；jsdos ZIP 配置包；键鼠 |
| 26 | 街机 | `arcade` / `fbneo`、`mame` | romset 版本绑定、parent/BIOS、去重 |

- 宿主页现在固定 `EJS_threads=false`。
- PSP 与 DOS 要开线程，同时补齐 COOP/COEP，`SharedArrayBuffer` 才可用。
- 需要改的位置：Docker 的 nginx、Windows 静态站、vite dev server。
- PSP 核只有线程变体，约 4.5 MB；ISO/CSO 容易撞 512 MB 上传上限。
- DOS 核也只有线程变体，游戏要打成 jsdos ZIP。
- 街机不需要线程，但 romset 与 FBNeo/MAME 版本绑定，数据治理最重。
- 街机核体积：FBNeo 约 8.3 MB，MAME 2003 约 5.4 MB。

## 共性注意事项

- **`.bin` 不能直接开放**：Atari 2600/5200/7800 常用 `.bin`，会与多机种歧义。
- 这些机种用 `.a26` / `.a52` / `.a78` 等专属后缀。
- **`.zip` 已被 H5 占用**：不能把 `.zip` 直接加给街机、DOS、Sega CD、Amiga。
- 多文件类型必须改成「用户选类型优先」，后缀只做提示。
- 线程开关现在是全局的；按机种开线程要避免影响现有 8 个机种。
- EJS 文档里的 3DS 属于 4.3-pre；本仓库钉死 4.2.3，不接。
- 不新增 `sega` / `mame` 两个兜底 key 的入口。

## 建议推进顺序

1. 先做 `atari2600`、`vb`、`ngp`、`ws`、`pce`，验证「加机种」链路。
2. 再做 BIOS 通用化，接 `lynx`、`coleco`、`atari5200`。
3. 接 `n64`，跑通第一个重核机种。
4. 补齐其余第 1 档机种，按实际 ROM 库存取舍。
5. 最后才做多文件、PSP、DOS、街机。

## 测试要点

- 第 1 档：上传、播放、云存档、截图、列表分组各跑一遍。
- BIOS 档：BIOS 缺失时有中文提示，补齐后可正常启动。
- 重核档：确认帧率与截图比例，低配设备要有可接受的降级表现。
- 多文件档：多盘切换、存档、删除时不残留临时文件。
- 线程档：确认响应头带 COOP/COEP，且现有 8 个机种不受影响。
- 每档都要更新 `tests/test_platforms.py` 的显示名镜像断言。

## 相关文档

- [`platforms.md`](platforms.md)：机种词表与扩展名的权威说明。
- [`game-center-playback.md`](game-center-playback.md)：播放页、宿主页与核心资产。
- [`game-storage.md`](game-storage.md)：本体上传、磁盘路径与卡带 ID。
- [`delivery-docker.md`](delivery-docker.md)：nginx 与响应头。
- [`delivery-windows.md`](delivery-windows.md)：Windows 静态站与响应头。
