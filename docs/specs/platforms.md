# 机种词表

## 范围与权威

- 权威实现是 `backend/games/platforms.py`，全项目「这是哪台机器」只认这一份。
- 机种 id 就是 EmulatorJS 的 system key；id 集合与 `cores` 逐字取自 EJS 4.2.3。
- 引擎源码在 `frontend/public/emulatorjs/data/emulator.min.js`，升级版本时两处一起对。
- 当前共 **36 个机种**，顺序按厂商分组，即下拉展示顺序。
- `flash` / `h5` 不是机种，是载体类型，不在词表里。
- 游戏管理、游戏检索、游戏榜单三处共用同一套机种名。
- 前端不手写映射：`/api/games/status` 的 `types` / `extension_candidates` 从本表派生，
  前端只在 Pinia store 里缓存。

## 数据与路径

- `Platform` 字段：`id` / `label` / `cores` / `aliases` / `extensions` / `default_extension`。
- `label` 是统一中文显示名，格式为「厂商 + 空格 + 型号」，如「任天堂 FC」「世嘉 土星」。
- 没有厂商名的机种只写型号，如 `Amiga`、`DOS`。
- 认不出机种的原始名展示时也按同一格式补空格，如 `任天堂3DS` → `任天堂 3DS`。
- `aliases` 收两份 CSV 里的各种写法；匹配走 `normalize_name()`（去所有空白 + casefold）。
- `id` 与 `label` 本身也当别名收，避免认不出的原始名撞上机种键。
- `extensions` 非空才代表本项目已收录、可上传可玩；值就是 `game_type`。
- 同一后缀可以出现在多个机种里；候选顺序就是本表顺序，第 1 个是默认项。
- `default_extension` 在网络直链看不出后缀时补上，只有可玩机种有。
- 候选查询入口：`playable_platforms_for_extension()` / `default_playable_platform_for_extension()`。
- 别名冲突在导入时抛 `ValueError`，不会静默覆盖。
- 解析入口：`resolve_platform()` / `platform_label()` / `platform_order()` / `playable_platforms()`。
- 未知机种位次是词表长度，即排最后；认不出时调用方回退显示原文。
- 可玩机种在表里的先后 = 管理页下拉与游戏中心分组的先后，刻意保持既有顺序。

## 行为与规则

### 可玩机种（21 个）

| game_type | 显示名 | 扩展名 | 默认后缀 | EmulatorJS core |
|---|---|---|---|---|
| `nes` | 任天堂 FC | `.nes` | `.nes` | `fceumm` / `nestopia` |
| `snes` | 任天堂 SFC | `.sfc` `.smc` | `.sfc` | `snes9x` |
| `gb` | 任天堂 GB/GBC | `.gb` `.gbc` | `.gb` | `gambatte` |
| `gba` | 任天堂 GBA | `.gba` | `.gba` | `mgba` |
| `nds` | 任天堂 NDS | `.nds` | `.nds` | `melonds` / `desmume` / `desmume2015` |
| `vb` | 任天堂 Virtual Boy | `.vb` | `.vb` | `beetle_vb` |
| `segaMD` | 世嘉 MD | `.md` `.gen` | `.md` | `genesis_plus_gx` / `picodrive` |
| `segaGG` | 世嘉 GG | `.gg` | `.gg` | `genesis_plus_gx` |
| `segaMS` | 世嘉 SMS | `.sms` | `.sms` | `smsplus` / `genesis_plus_gx` / `picodrive` |
| `sega32x` | 世嘉 32X | `.32x` | `.32x` | `picodrive` |
| `pce` | 日电 PCE | `.pce` `.sgx` | `.pce` | `mednafen_pce` |
| `ngp` | SNK NGPC | `.ngc` `.ngp` | `.ngc` | `mednafen_ngp` |
| `ws` | 万代 WS | `.ws` `.wsc` | `.ws` | `mednafen_wswan` |
| `atari2600` | 雅达利 2600 | `.a26` | `.a26` | `stella2014` |
| `atari7800` | 雅达利 7800 | `.a78` | `.a78` | `prosystem` |
| `jaguar` | 雅达利 Jaguar | `.j64` `.jag` | `.j64` | `virtualjaguar` |
| `c64` | Commodore 64 | `.d64` `.tap` `.crt` `.prg` | `.d64` | `vice_x64sc` |
| `c128` | Commodore 128 | `.d64` `.d71` `.prg` | `.d64` | `vice_x128` |
| `pet` | Commodore PET | `.prg` `.d64` | `.prg` | `vice_xpet` |
| `plus4` | Commodore Plus/4 | `.prg` `.d64` | `.prg` | `vice_xplus4` |
| `vic20` | Commodore VIC-20 | `.prg` `.d64` | `.prg` | `vice_xvic` |

- `cores` 记录引擎支持的全部 core，不代表本项目都打包了资产；NDS 只打包 `melonds`。
- **扩展名可以跨机种重叠**：Commodore 共用 `.d64` / `.prg`。
  判定时取「后缀候选集」，候选第 1 个（词表顺序）是默认项；唯一候选自动确定。
- `GAME_TYPES` 派生为 `flash`、`h5` 加 21 个可玩机种 id，顺序与词表一致。
- 后端扩展名白名单、默认后缀表、候选表与 `GAME_TYPE_LABELS` 都从词表派生。
- 前端不保存映射：`GET /api/games/status` 的 `types` / `extension_candidates` /
  `default_game_type_by_extension` 是唯一来源。
- 加机种要同步：本表（词表）、`fetch-emulatorjs.mjs` 的 core 资产、前端
  `constants/emulatorScreens.js` 的帧缓冲尺寸。label 与扩展名不用再抄。
- 不再收 `.bin`：2600/5200/7800 都用它，没法判型，各自用专属后缀。
- 改词表不会挪动任何文件；`id` 同时是磁盘目录名与库里的 `game_type`。
  已有游戏改类型走显式迁移接口（见 `game-storage.md`）。

### 检索与榜单

- 两份外部 CSV 的机种列都经本词表归一，认不出的保留原文并归为「未收录」。
- 检索侧同一个机种的多个原始名在建库时合并成一行 `console`。
- 合并后是 **32 项**：23 个统一机种 + 9 个未收录（原始机种名 36 个）。
- 典型合并：`任天堂GB` / `任天堂GBC` 都落到 `gb`；`任天堂FC磁碟机` 落到 `nes`。
- 榜单侧 `platform` 用归一后的机种键；认不出时写成 `raw:{归一后的原文}`。
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
- 两份真实 CSV 的每个机种名都能解析，或明确列在「未收录」名单里。
- 检索侧合并后正好 32 项；榜单侧没有两个写法落到同一机种。

## 相关文档

- [游戏存储与入库](./game-storage.md)
- [数据字典](../data_dict.md)
- [架构说明](../architecture.md)
- [编码约定](../../AGENTS.md)
