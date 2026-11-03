# 待接机种清单

## 范围与权威

- 本文是「还要接哪些机种、按什么顺序接」的计划，不定义已有机种的事实。
- 机种词表与可玩机种的权威仍是 [`platforms.md`](platforms.md) 与 `backend/games/platforms.py`。
- 机种名称与先后都取词表顺序，接入后就是游戏类型下拉的展示顺序。
- 下拉顺序 = `/status.game_types` = `flash`、`h5` + 词表里的可玩机种。
- 引擎基线固定 EmulatorJS **4.2.3**，system key 与 core 取自其 `getCores()`。
- 下表只列 EmulatorJS 支持的机种；key / core 与 `getCores()` 一致，由 `tests/test_platforms.py` 钉住。
- 词表当前共 36 个机种，已可玩 29 个，剩余 7 个。
- 剩余 7 个中 `sega` / `mame` 是引擎兜底 key，不单独接，真正可新增 **5 个**。
- 第 1 档 13 个已全部接入，包括 Commodore 五个：
  `c64`、`c128`、`pet`、`plus4`、`vic20`。
- 第 2 档 3 个已全部接入：`atari5200`、`lynx`、`coleco`；BIOS 机制已通用化。
- 第 3 档 5 个已全部接入：`n64`、`segaSaturn`、`psx`、`pcfx`、`3do`；
  单文件镜像按 `.chd` / `.pbp` / `.iso` 收，多文件格式留给第 4 档。
- Commodore 共用 `.d64` / `.prg`，由「后缀候选集 + 用户选择」消歧；
  创建后也能在编辑弹框里改类型。
- 下表仍按词表顺序列出待接机种，不按难度重排；难度用「档」标注。
- 结论：按五档从易到难推进，先做纯配表，最后碰多文件与线程。

## 工作量的五个档位

| 档 | 机种数 | 主要工作 | 相对工作量 |
|---|---|---|---|
| 1 | 0 | 已全部接入 | — |
| 2 | 0 | 已全部接入（BIOS 机制已通用化） | — |
| 3 | 0 | 已全部接入（单文件 CD 镜像） | — |
| 4 | 2 | 多文件上传与播放链路 | 机制 2–3 天，每个 1–2 天 |
| 5 | 3 | 线程、COOP/COEP、数据模型 | 每个 3 天以上，街机以周计 |

## 机种清单（按词表顺序）

已可玩的 29 个不在下表重复列出。下表是剩余 5 个待接机种，按其在词表中的先后排列，
接入后在下拉里的相对位置与此一致。

| 机种 | key / core | 扩展名 | 档 | 说明 |
|---|---|---|---|---|
| 世嘉 CD | `segaCD` / `genesis_plus_gx` | cue+bin / `.chd` | 4 | BIOS `bios_CD_E/U/J.bin` |
| 索尼 PSP | `psp` / `ppsspp` | `.iso` `.cso` | 5 | 强制线程 + WebGL2 |
| Amiga | `amiga` / `puae` | adf/hdf 多盘或 zip | 4 | Kickstart 必需 |
| DOS | `dos` / `dosbox_pure` | jsdos zip | 5 | 强制线程；键鼠 |
| 街机 | `arcade` / `fbneo` | romset zip | 5 | `mame` 是独立兜底 key，不单独接；数据治理最重 |

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
- 512MB 上传上限不变；超大的 ISO 建议先转 CHD 或 PBP。

### 第 4 档：多文件 / 多碟

对应：`segaCD`、`amiga`。

当前上传只收单文件，播放只服务 `game.{后缀}` 一个文件。

机制工作：

- 支持 ZIP 或 cue+bin 组合上传。
- 播放接口把多文件清单交给 EJS。
- 扩展名判型要区分「用户选的类型」与「后缀推断」。

- `pce` 的 CD 游戏与本档同源：加 `syscard3.pce` 与多文件。
- PS1、土星、3DO 若收 cue+bin 原盘格式，也落在本档。
- 同一游戏多盘的切换交互要单独定义，不能只解压了事。

### 第 5 档：需要改运行环境或数据模型

对应：`psp`、`dos`、`arcade`。

- 宿主页现在固定 `EJS_threads=false`。
- PSP 与 DOS 要开线程，同时补齐 COOP/COEP，`SharedArrayBuffer` 才可用。
- 需要改的位置：Docker 的 nginx、Windows 静态站、vite dev server。
- PSP 核只有线程变体，约 4.5 MB；ISO/CSO 容易撞 512 MB 上传上限。
- DOS 核也只有线程变体，游戏要打成 jsdos ZIP。
- 街机不需要线程，但 romset 与 FBNeo/MAME 版本绑定，数据治理最重。
- 街机核体积：FBNeo 约 8.3 MB，MAME 2003 Plus 约 5.4 MB。

## 共性注意事项

- **`.bin` 不能直接开放**：Atari 2600/5200/7800 常用 `.bin`，会与多机种歧义。
- 这些机种用 `.a26` / `.a52` / `.a78` 等专属后缀。
- 新增机种的显示名统一为「公司名 + 空格 + 型号」，由 `tests/test_platforms.py` 钉住。
- **`.zip` 已被 H5 占用**：不能把 `.zip` 直接加给街机、DOS、Sega CD、Amiga。
- 多文件类型必须改成「用户选类型优先」，后缀只做提示。
- 线程开关现在是全局的；按机种开线程要避免影响现有 29 个机种。
- EJS 文档里的 3DS 属于 4.3-pre；本仓库钉死 4.2.3，不接。
- 不新增 `sega` / `mame` 两个兜底 key 的入口。

## 建议推进顺序

1. ~~先做 `vb`、`ngp`、`ws`、`pce`、`atari2600`，验证「加机种」链路。~~ 已接入。
2. ~~再做 BIOS 通用化，接 `atari5200`、`lynx`、`coleco`。~~ 已完成。
3. ~~第 1 档 13 个全部接入，含 Commodore 与类型选择/修改机制。~~ 已完成。
4. ~~接 `n64`，跑通第一个重核机种。~~ 第 3 档 5 个已全部接入。
5. 最后才做多文件、PSP、DOS、街机。

## 测试要点

- 第 1 档：上传、播放、云存档、截图、列表分组各跑一遍。
- BIOS 档：BIOS 缺失时有中文提示，补齐后可正常启动。
- 重核档：确认帧率与截图比例，低配设备要有可接受的降级表现。
- 多文件档：多盘切换、存档、删除时不残留临时文件。
- 线程档：确认响应头带 COOP/COEP，且现有 29 个机种不受影响。
- 每档都要更新 `tests/test_platforms.py` 的词表不变量（显示名格式、扩展名、BIOS 规格）
  与 EJS `getCores()` 一致性断言。
- 待接清单本身也由测试校验：只允许列 EJS 支持的 key / core，且覆盖全部剩余机种。

## 相关文档

- [`platforms.md`](platforms.md)：机种词表与扩展名的权威说明。
- [`game-center-playback.md`](game-center-playback.md)：播放页、宿主页与核心资产。
- [`game-storage.md`](game-storage.md)：本体上传、磁盘路径与卡带 ID。
- [`delivery-docker.md`](delivery-docker.md)：nginx 与响应头。
- [`delivery-windows.md`](delivery-windows.md)：Windows 静态站与响应头。
