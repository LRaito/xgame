# 机种词表

本文件回答：机种名、扩展名与 BIOS 规格以哪份词表为准。

## 范围与权威

- 权威实现是 `backend/games/platforms.py`，全项目「这是哪台机器」只认这一份。
- 机种 id 就是 EmulatorJS 的 system key；id 集合与 `cores` 逐字取自 EJS 4.2.3。
- 引擎源码在 `frontend/public/emulatorjs/data/emulator.min.js`，升级版本时两处一起对。
- 当前共 **36 个机种**，顺序按厂商分组，即下拉展示顺序。
- `flash` / `h5` 不是机种，是载体类型，不在词表里。
- 游戏管理、游戏检索、游戏榜单三处共用同一套机种名。
- 前端不手写映射：`/api/games/status` 的 `types` / `extension_candidates` 从本表派生，
  前端只在 Pinia store 里缓存。

## 职责

- 作为机种名、显示名、别名、扩展名、后缀候选与 BIOS 规格的唯一权威。
- 把外部名录里的自由文本解析回机种。
- 向 `/api/games/status` 提供前端所需的类型元数据。
- 「机型简史」的介绍文案是前端静态内容，只做展示，不参与词表与可玩判定，
  见 [`../modules/platform-chronicle.md`](../modules/platform-chronicle.md)。

## 关键接口

- 解析：`resolve_platform()`、`platform_label()`、`platform_order()`。
- 可玩机种：`playable_platforms()`、`playable_platforms_for_extension()`、
  `default_playable_platform_for_extension()`。
- 词表定义在 `backend/games/platforms.py`。

## 依赖

- EmulatorJS 的 system key 与 core 列表。
- `backend/search/catalog/` 的文件名映射（`SEARCH_CSV_CONSOLE_NAMES`）与
  `backend/search/rankings/` 的文件名（机种 id）。
- 前端 `constants/gameTypes.js` 只保留图标、描述等纯 UI 元数据。

## 数据与路径

- `Platform` 字段：`id` / `label` / `cores` / `aliases` / `extensions` / `default_extension` /
  `bios` / `bundle_extensions` / `bundle_entries` / `threads`。
- `label` 是统一中文显示名，格式为「厂商 + 空格 + 型号」，如「任天堂 FC」「世嘉 土星」。
- 没有厂商名的机种只写型号，如 `Amiga`、`DOS`。
- 认不出机种的原始名展示时也按同一格式补空格，如 `任天堂3DS` → `任天堂 3DS`。
- `SEARCH_CSV_CONSOLE_NAMES` 把检索名录的文件名 stem 映射回机种原始名；
  未登记文件名由建索引代码回退为 stem 本身。
- `aliases` 收两份 CSV 里的各种写法；匹配走 `normalize_name()`（去所有空白 + casefold）。
- `id` 与 `label` 本身也当别名收，避免认不出的原始名撞上机种键。
- `extensions` 非空才代表本项目已收录、可上传可玩；值就是 `game_type`。
- 同一后缀可以出现在多个机种里；候选顺序就是本表顺序，第 1 个是默认项。
- `default_extension` 在网络直链看不出后缀时补上，只有可玩机种有。
- `bios` 声明该机种需要的用户自备 BIOS 包（`BiosSpec`）；不需要 BIOS 的机种为 `None`。
- 候选查询入口：`playable_platforms_for_extension()` / `default_playable_platform_for_extension()`。
- 别名冲突在导入时抛 `ValueError`，不会静默覆盖。
- 解析入口：`resolve_platform()` / `platform_label()` / `platform_order()` / `playable_platforms()`。
- 未知机种位次是词表长度，即排最后；认不出时调用方回退显示原文。
- 可玩机种在表里的先后 = 管理页下拉与游戏中心分组的先后，刻意保持既有顺序。

## 行为与规则

### 可玩机种（34 个）

| game_type | 显示名 | 扩展名 | 默认后缀 | EmulatorJS core |
|---|---|---|---|---|
| `nes` | 任天堂 FC | `.nes` | `.nes` | `fceumm` / `nestopia` |
| `snes` | 任天堂 SFC | `.sfc` `.smc` | `.sfc` | `snes9x` |
| `n64` | 任天堂 N64 | `.z64` `.n64` `.v64` | `.z64` | `mupen64plus_next` / `parallel_n64` |
| `gb` | 任天堂 GB/GBC | `.gb` `.gbc` | `.gb` | `gambatte` |
| `gba` | 任天堂 GBA | `.gba` | `.gba` | `mgba` |
| `nds` | 任天堂 NDS | `.nds` | `.nds` | `melonds` / `desmume` / `desmume2015` |
| `vb` | 任天堂 VB | `.vb` | `.vb` | `beetle_vb` |
| `segaMD` | 世嘉 MD | `.md` `.gen` | `.md` | `genesis_plus_gx` / `picodrive` |
| `segaGG` | 世嘉 GG | `.gg` | `.gg` | `genesis_plus_gx` |
| `segaMS` | 世嘉 SMS | `.sms` | `.sms` | `smsplus` / `genesis_plus_gx` / `picodrive` |
| `segaCD` | 世嘉 CD | `.chd`（多文件另见下） | `.chd` | `genesis_plus_gx` / `picodrive` |
| `sega32x` | 世嘉 32X | `.32x` | `.32x` | `picodrive` |
| `segaSaturn` | 世嘉 土星 | `.chd` | `.chd` | `yabause` |
| `psx` | 索尼 PS1 | `.chd` `.pbp` `.iso` | `.chd` | `pcsx_rearmed` / `mednafen_psx_hw` |
| `psp` | 索尼 PSP | `.iso` `.cso` | `.iso` | `ppsspp`（线程 + WebGL2） |
| `pce` | 日电 PCE | `.pce` `.sgx` | `.pce` | `mednafen_pce` |
| `pcfx` | 日电 PC-FX | `.chd` | `.chd` | `mednafen_pcfx` |
| `ngp` | SNK NGPC | `.ngc` `.ngp` | `.ngc` | `mednafen_ngp` |
| `ws` | 万代 WS | `.ws` `.wsc` | `.ws` | `mednafen_wswan` |
| `atari2600` | 雅达利 2600 | `.a26` | `.a26` | `stella2014` |
| `atari5200` | 雅达利 5200 | `.a52` | `.a52` | `a5200` |
| `atari7800` | 雅达利 7800 | `.a78` | `.a78` | `prosystem` |
| `jaguar` | 雅达利 Jaguar | `.j64` `.jag` | `.j64` | `virtualjaguar` |
| `lynx` | 雅达利 Lynx | `.lnx` | `.lnx` | `handy` |
| `coleco` | ColecoVision | `.col` | `.col` | `gearcoleco` |
| `3do` | 松下 3DO | `.iso` `.chd` | `.iso` | `opera` |
| `c64` | 康懋达 64 | `.d64` `.tap` `.crt` `.prg` | `.d64` | `vice_x64sc` |
| `c128` | 康懋达 128 | `.d64` `.d71` `.prg` | `.d64` | `vice_x128` |
| `pet` | 康懋达 PET | `.prg` `.d64` | `.prg` | `vice_xpet` |
| `plus4` | 康懋达 Plus/4 | `.prg` `.d64` | `.prg` | `vice_xplus4` |
| `vic20` | 康懋达 VIC-20 | `.prg` `.d64` | `.prg` | `vice_xvic` |
| `amiga` | Amiga | `.adf` `.hdf`（多盘另见下） | `.adf` | `puae` |
| `dos` | DOS | `.jsdos` `.zip` | `.jsdos` | `dosbox_pure`（线程） |
| `arcade` | 街机 | `.zip`（romset，保留集合名） | `.zip` | `fbneo` |

- `cores` 记录引擎支持的全部 core，不代表本项目都打包了资产；NDS 只打包 `melonds`。
  N64 打包 `mupen64plus_next` 与 `parallel_n64`（iOS Safari 会默认选后者）；
  PS1 两个 core 都打包。街机只打包默认 `fbneo`，CPS1/CPS2 切过去会缺资产。
- **扩展名可以跨机种重叠**：Commodore 共用 `.d64` / `.prg`；CD 镜像共用 `.chd`
  （世嘉 CD / 土星 / PS1 / PC-FX / 3DO）与 `.iso`（PS1 / PSP / 3DO）；
  `.zip` 在 H5、DOS 与街机之间共用。
  判定时取「后缀候选集」，候选第 1 个（词表顺序）是默认项；唯一候选自动确定。
  `.zip` 是例外：不传类型时回到历史默认 `h5`，DOS / 街机必须由用户显式选择。
- **线程核**：`threads=True` 的机种（PSP / DOS）只有 `-thread` 变体，宿主页必须
  打开 `EJS_threads`；页面还要带 COOP/COEP 才能拿到 `SharedArrayBuffer`。
  其余机种保持 `EJS_threads=false`，设置菜单里的线程开关统一隐藏。
- **多文件本体**：`bundle_extensions` 是包内允许出现的全部后缀，`bundle_entries`
  是其中可当入口的后缀。当前只有 `segaCD` 与 `amiga` 声明：
  - `segaCD`：`bundle_extensions=(".cue",".bin",".m3u",".chd")`，
    `bundle_entries=(".m3u",".cue",".chd")`；`.bin` 只能作分轨。
  - `amiga`：`bundle_extensions=(".adf",".hdf",".m3u")`，
    `bundle_entries=(".m3u",".adf",".hdf")`。
  `.cue` / `.m3u` / `.bin` 不进单文件 `extensions`，单独上传仍被拒绝；
  多文件以用户选的类型为准，后缀只做合法性校验。
- 多候选后缀的默认项可被 `_EXTENSION_DEFAULT_OVERRIDES` 覆盖：`.chd` 默认 PS1，
  不改变候选列表顺序。`.zip` 的默认 `h5` 在 `service.py` 的
  `_DEFAULT_GAME_TYPES_BY_EXTENSION` 里维护。
- `GAME_TYPES` 派生为 `flash`、`h5` 加 34 个可玩机种 id，顺序与词表一致。
- 后端扩展名白名单、默认后缀表、候选表与 `GAME_TYPE_LABELS` 都从词表派生。
- 前端不保存映射：`GET /api/games/status` 的 `types` / `extension_candidates` /
  `default_game_type_by_extension` 是唯一来源。
- 加机种要同步：本表（词表）、`fetch-emulatorjs.mjs` 的 core 资产、前端
  `constants/emulatorScreens.js` 的帧缓冲尺寸；需要 BIOS 时再补 `BiosSpec` 与
  `emulatorjs/bios/<id>.zip`；核只有线程变体时设 `threads=True`。label 与扩展名不用再抄。
- 不再收 `.bin`：2600/5200/7800 都用它，没法判型，各自用专属后缀。
- 改词表不会挪动任何文件；`id` 同时是磁盘目录名与库里的 `game_type`。
  已有游戏改类型走显式迁移接口（见 `game-storage.md`）。

### 需要 BIOS 的机种

| game_type | BIOS ZIP | 包内必需文件 | 必需性 |
|---|---|---|---|
| `nds` | `nds.zip` | `bios7.bin`、`bios9.bin`、`firmware.bin` | 必需 |
| `atari5200` | `atari5200.zip` | `5200.rom` | 可选（核心内置 AltirraOS） |
| `lynx` | `lynx.zip` | `lynxboot.img` | 必需 |
| `coleco` | `coleco.zip` | `colecovision.rom` | 必需 |
| `segaSaturn` | `segaSaturn.zip` | `saturn_bios.bin` | 必需（核有 HLE 回退，兼容性差） |
| `psx` | `psx.zip` | `scph5500.bin`、`scph5501.bin`、`scph5502.bin` | 必需（按区，建议三个都放） |
| `pcfx` | `pcfx.zip` | `pcfx.rom` | 必需（必须正好 1 MiB） |
| `3do` | `3do.zip` | `panafz1.bin` | 必需（也可用其他 3DO BIOS 文件名） |
| `segaCD` | `segaCD.zip` | `bios_CD_E.bin`、`bios_CD_U.bin`、`bios_CD_J.bin` | 必需（按区，至少放一个） |
| `amiga` | `amiga.zip` | `kick34005.A500`、`kick40068.A1200` | 可选（PUAE 有 AROS 回退） |
| `arcade` | `arcade.zip` | `neogeo.zip`、`pgm.zip` | 可选（ROM 集合也可自带 BIOS） |

- N64、PSP、DOS 不需要 BIOS。
- 街机的 `arcade.zip` 里放的是 BIOS 集合 zip（如 `neogeo.zip`），不是裸文件；
  FBNeo 需要时由引擎解到虚拟文件系统。缺包时只影响需要该 BIOS 的集合。
- 土星也可用 `sega_101.bin` / `mpr-17933.bin`，3DO 也可用 `panafz10.bin` 等；
  文件名必须与 core 查找名完全一致。

- ZIP 放在 `frontend/public/emulatorjs/bios/`，包根目录直接放必需文件，不能套子目录。
- BIOS 是用户自备文件，不随仓库提交；Docker 需重建 web 镜像，Windows 包需重新组装。
- 元数据经 `/status.types[].bios` 与游戏列表条目的 `bios` 下发，播放页不手写映射。

### 检索与榜单

- 检索侧机种来自文件名映射；榜单侧机种就是文件名（机种 id），直接查 `PLATFORM_BY_ID`。
- 检索侧同一个机种的多个原始名在建库时合并成一行 `console`。
- 合并后是 **32 项**：23 个统一机种 + 9 个未收录（原始机种名 36 个）。
- 典型合并：`任天堂GB` / `任天堂GBC` 都落到 `gb`；`任天堂FC磁碟机` 落到 `nes`。
- 榜单目录每个可玩机种一个 CSV，文件名 stem 必须与机种 id 逐字一致。
- 前端榜单下拉的 `label` 与游戏管理页的类型名是同一套名字。

## 边界与错误

- `resolve_platform("")` 返回 `None`，不抛异常。
- 非机种 id 调 `platform_cores()` 返回空元组。
- `platform_label()` 认不出时回退原文，再退到 id。
- 可玩机种必须有扩展名白名单与默认后缀，且默认后缀在白名单内。
- 扩展名重叠本身合法；判型时由候选集消歧，唯一候选自动确定，多候选必须由用户选择。
- 别名冲突会让 `tests/test_platforms.py` 失败。
- 别在别处手写机种名或扩展名对照表；新增写法只补 `aliases` / `extensions`。

## 测试要点

- 机种 id 集合与 EJS `getCores()` 的键集合逐字一致；资产未拉取时跳过。
- 每个机种都声明了 `label` 与非空 `cores`。
- 别名索引无冲突，`id` / `label` 也能反查回同一机种。
- `GAME_TYPES` 顺序正确；前端不再手写 label / 扩展名镜像。
- 同一后缀的候选顺序与默认项正确（`.d64` / `.prg` 的 5 个候选、`.d71` / `.tap` 的唯一候选）。
- 检索名录的每个机种名都能解析，或明确列在「未收录」名单里。
- 榜单目录的每个文件名都是可玩机种 id；检索侧合并后正好 32 项。

## 相关文档

- [游戏存储与入库](../modules/game-storage.md)
- [数据字典](../data_dict.md)
- [架构说明](../architecture.md)
- [编码约定](../../AGENTS.md)
