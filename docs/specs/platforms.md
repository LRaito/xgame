# 机种词表

## 范围与权威

- 权威实现是 `backend/games/platforms.py`，全项目「这是哪台机器」只认这一份。
- 机种 id 就是 EmulatorJS 的 system key；id 集合与 `cores` 逐字取自 EJS 4.2.3。
- 引擎源码在 `frontend/public/emulatorjs/data/emulator.min.js`，升级版本时两处一起对。
- 当前共 **36 个机种**，顺序按厂商分组，即下拉展示顺序。
- `flash` / `h5` 不是机种，是载体类型，不在词表里。
- 游戏管理、游戏检索、游戏榜单三处共用同一套机种名。
- 前端镜像是 `frontend/src/constants/gameTypes.js`，一致性由 `tests/test_platforms.py` 钉住。

## 数据与路径

- `Platform` 字段：`id` / `label` / `cores` / `aliases` / `extensions` / `default_extension`。
- `label` 是统一中文显示名，格式为「厂商 + 型号」，如「任天堂 FC」「世嘉 MD」。
- `aliases` 收两份 CSV 里的各种写法；匹配走 `normalize_name()`（去所有空白 + casefold）。
- `id` 与 `label` 本身也当别名收，避免认不出的原始名撞上机种键。
- `extensions` 非空才代表本项目已收录、可上传可玩；值就是 `game_type`。
- `default_extension` 只在网络直链看不出后缀时补上，只有可玩机种有。
- 别名冲突在导入时抛 `ValueError`，不会静默覆盖。
- 解析入口：`resolve_platform()` / `platform_label()` / `platform_order()` / `playable_platforms()`。
- 未知机种位次是词表长度，即排最后；认不出时调用方回退显示原文。
- 可玩机种在表里的先后 = 管理页下拉与游戏中心分组的先后，刻意保持既有顺序。

## 行为与规则

### 可玩机种（8 个）

| game_type | 显示名 | 扩展名 | 默认后缀 | EmulatorJS core |
|---|---|---|---|---|
| `nes` | 任天堂 FC | `.nes` | `.nes` | `fceumm` / `nestopia` |
| `snes` | 任天堂 SFC | `.sfc` `.smc` | `.sfc` | `snes9x` |
| `gb` | 任天堂 GB/GBC | `.gb` `.gbc` | `.gb` | `gambatte` |
| `gba` | 任天堂 GBA | `.gba` | `.gba` | `mgba` |
| `nds` | 任天堂 NDS | `.nds` | `.nds` | `melonds` / `desmume` / `desmume2015` |
| `segaMD` | 世嘉 MD | `.md` `.gen` | `.md` | `genesis_plus_gx` / `picodrive` |
| `segaGG` | 世嘉 GG | `.gg` | `.gg` | `genesis_plus_gx` |
| `segaMS` | 世嘉 SMS | `.sms` | `.sms` | `smsplus` / `genesis_plus_gx` / `picodrive` |

- `cores` 记录引擎支持的全部 core，不代表本项目都打包了资产；NDS 只打包 `melonds`。
- 扩展名在各可玩机种之间互不重叠，本体类型判定没有歧义。
- `GAME_TYPES` 派生为 `flash`、`h5` 加 8 个可玩机种 id，顺序与词表一致。
- 后端扩展名白名单、默认后缀表与 `GAME_TYPE_LABELS` 都从词表派生。
- 加机种只改这一张表：id 用 EJS system key、cores 照抄 EJS、别名覆盖两份 CSV。
- 改词表不会挪动任何文件；`id` 同时是磁盘目录名与库里的 `game_type`。

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
- 扩展名一旦重叠、或别名冲突，`tests/test_platforms.py` 会失败。
- 别在别处手写机种名对照表；新增写法只补 `aliases`。

## 测试要点

- 机种 id 集合与 EJS `getCores()` 的键集合逐字一致；资产未拉取时跳过。
- 每个机种都声明了 `label` 与非空 `cores`。
- 别名索引无冲突，`id` / `label` 也能反查回同一机种。
- `GAME_TYPES` 顺序正确；前端 label 与后端 `GAME_TYPE_LABELS` 逐字一致。
- 两份真实 CSV 的每个机种名都能解析，或明确列在「未收录」名单里。
- 检索侧合并后正好 32 项；榜单侧没有两个写法落到同一机种。

## 相关文档

- [游戏存储与入库](./game-storage.md)
- [数据字典](../data_dict.md)
- [架构说明](../architecture.md)
- [编码约定](../../AGENTS.md)
