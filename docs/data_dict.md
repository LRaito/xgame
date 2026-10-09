# 数据字典

本项目所有结构化数据的权威清单：**SQLite 关系结构** 与 **文件存储结构**。

**准确性约定：** 以代码为准，本文件只是索引。SQLite 结构源头是各模块的 `backend/*/models.py`（SQLModel `table=True`）；文件路径规则的源头是 `backend/games/paths.py`。改模型或路径规则时请同步更新本文。最后核对时间：2026-10-04。

## 存储总览

| 存储 | 位置 | 用途 |
|--------|------|------|
| SQLite 单文件 | `<数据根>/db/app.db`（Docker 里是宿主 `${STORAGE_HOST_DIR}/db/app.db` → 容器 `/data/db/app.db`） | 全部业务元数据 |
| SQLite 月度备份 | 与库同目录的 `<数据根>/db/<YYYY-MM>.db` | 服务启动时按当月补一份，一个自然月一份；不做还原，回滚就手工换回 `app.db` |
| 数据根目录 | `STORAGE_ROOT`（本机默认 `<仓库>/data/storage`；容器内固定 `/data`，宿主目录由 `STORAGE_HOST_DIR` 挂进去） | 游戏本体/封面/H5 资源/攻略/图集、云端存档、游戏截图，以及 `db/` 下的 SQLite 库与月度备份 |

分工原则：**所有元数据在 SQLite，SQLite 里存的是相对于文件根目录的路径**；文件本身是磁盘上的普通文件，用户可以直接从宿主目录拷走、备份、浏览。相对路径统一用 `/` 作分隔符，读取时由 `LocalStorage` 拼上根路径。

SQLModel 到 SQLite 的类型映射：`str(max_length=n)` → `VARCHAR(n)`；`str`（无长度）→ `TEXT`；`int` → `INTEGER`；`datetime` → `DATETIME`。整型主键即 SQLite 自增 `INTEGER PRIMARY KEY`。

## SQLite 结构

库路径在代码里写死为 `<STORAGE_ROOT>/db/app.db`（`backend/config.py` 的 `DB_SUBDIR` / `DB_FILENAME`，不可另配），`create_app()` 启动时 `init_db()` 建全部表。**没有迁移框架**：`create_all` 只建缺失的表、不给已存在的表补列，所以后来新增的列靠 `backend/database.py` 的 `_ADDED_COLUMNS` / `_ensure_columns()` 在启动时 `ALTER TABLE … ADD COLUMN` 补上（只加列，不改不删）。

### 表索引

| # | 表 | 定义文件 | 一句话用途 |
|---|-----|----------|-------------|
| 1 | `users` | `backend/auth/models.py` | 平台账号（werkzeug 哈希），同时决定存档目录名 |
| 2 | `login_attempts` | 同上 | 登录失败计数与锁定，按 username 一行 |
| 3 | `games` | `backend/games/models.py` | 游戏条目（卡带ID、本体/封面相对路径） |
| 4 | `game_h5_files` | 同上 | H5 游戏 ZIP 解包后的单文件清单（包内相对路径 → 磁盘相对路径） |
| 5 | `game_cloud_snapshots` | 同上 | 某(用户,游戏)的一次云端存档快照 |
| 6 | `game_cloud_snapshot_files` | 同上 | 快照里的单个存档文件（.sol / .state）及还原元信息 |
| 7 | `game_screenshots` | 同上 | 按(用户,游戏)的游玩截图（相对路径 + 描述 + 展示顺序） |
| 8 | `game_emulator_settings` | 同上 | 按(用户,平台)一份的模拟器设置（键位/选项/金手指，JSON 文本） |
| 9 | `game_recent_plays` | 同上 | 按(用户,游戏)一行的最近游玩时间（游戏中心 rail 用） |
| 10 | `game_user_stats` | 同上 | 按(用户,游戏)一行的游玩时长（秒）与进度 |
| 11 | `game_gallery_images` | 同上 | 游戏图集：一个游戏一套的**共享**展示图（宣传图、说明书扫描件之类） |

### auth — 账号

**`users`**（平台账号：只用于隔离各人的模拟器配置与存档，不做邮箱/找回密码等安全机制）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| username | VARCHAR(32) | NOT NULL, UNIQUE, 索引 | 登录名。规则见 `backend/auth/models.py`：2–32 字符，只允许数字、字母、中划线、下划线（`^[0-9A-Za-z_-]+$`），大小写敏感。字符集收窄是因为它会被直接当成存档目录名 |
| password_hash | VARCHAR(255) | NOT NULL | werkzeug `generate_password_hash` 结果，单向哈希，永不明文 |
| created_at | DATETIME | NOT NULL | UTC 创建时间 |

**`login_attempts`**（按 `username` 一行；登录成功后该行被删）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| username | VARCHAR(32) | PK | 锁定对象即用户名 |
| failed_count | INTEGER | NOT NULL | 累计失败次数（阈值见 `backend/auth/login_lockout.py`：≥3 短锁 5 分钟，≥6 锁到当天 UTC 结束） |
| locked_until | DATETIME | NULL | 为 NULL 表示未锁定；锁定时为解锁时刻 |

### games — 游戏中心

**`games`**（一个游戏条目；本体/封面各在磁盘上一个文件。联合唯一索引 `uq_games_game_type_name` 保证**同类型下游戏名唯一**（不同类型可重名），唯一索引 `uq_games_cartridge_id` 保证**卡带ID 全局唯一**）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | 接口路由里的 `{game_id}`，与磁盘目录**无关** |
| name | VARCHAR(255) | NOT NULL, 索引，联合唯一 `(game_type, name)` | 游戏名。校验为合法的 Windows 与百度网盘文件名（`validate_game_name()`）：不含 `\ / : * ? " < > |` 与控制字符、不以点结尾、非保留设备名、≤255 字符 |
| cartridge_id | VARCHAR(64) | NOT NULL, 唯一索引 `uq_games_cartridge_id` | 卡带ID：创建时必填、**建后不可改**（只能删掉重建），同时是磁盘上的目录名与「同一盘卡带」的身份标识。规则见 `validate_cartridge_id()`：只允许数字、字母、中划线、下划线，落库前统一转**大写** |
| cartridge_type | VARCHAR(20) | NOT NULL, 默认 `'default'` | 卡带类型（卡带版本）：`default` 默认 / `jp` 日版 / `us` 美版。**始终有值**（不是可空字段）；只有 FC NES（`nes`）允许 `jp`/`us`，其余游戏类型只允许 `default`。可选集合见 `backend/games/models.py` 的 `CARTRIDGE_TYPES_BY_GAME_TYPE` / `cartridge_types_for()`，校验入口 `service.py::validate_cartridge_type()`。换本体导致游戏类型变化时，新类型不认的值回落 `default`。游戏中心「全部游戏」在游戏类型分组内再按它分行。界面只显示国旗（`frontend/public/flags/` 下 22×16 静态图片，文件名是国家/地区英文全称，如 `Japan.png`/`USA.png`；`default` 用空白图 `Default.png`），中文名只作 `<img alt>`；改它只有管理页的添加/编辑弹框（单选） |
| description | VARCHAR(200) | NOT NULL, 默认 `''` | 描述。上限 200 字（`validate_description()`）：新建/编辑超长直接 400，搬运抓来的站点简介按上限截断入库 |
| game_type | VARCHAR(50) | NOT NULL, 索引 | 类型值：`flash`（Ruffle 播放 SWF）、`h5`（上传 ZIP，后端解包为多文件，沙箱 iframe 播放）或主机平台 `nes`/`snes`/`gb`/`gba`/`segaMD`/`segaGG`/`segaMS`（EmulatorJS 播放，值与 EJS system key 一致）。**由本体文件扩展名自动判定**（不手动指定），判定入口与白名单在 `backend/games/service.py` 的 `GAME_TYPES`/`_GAME_TYPE_EXTENSIONS`/`detect_game_type()`。中心列表按 `game_path != ''` 过滤 |
| size | INTEGER | NOT NULL, 默认 0 | 本体字节数（h5 为 ZIP 压缩包大小） |
| crc32 | VARCHAR(8) | NOT NULL, 默认 `''` | 本体内容的 CRC32，8 位大写十六进制（如 `D445F698`）。上传本体时算好落库，**用作换本体的锁定凭据**：非空时只接受 CRC32 相同的文件；空（如文件已丢、尚未补传）表示未锁定 |
| game_path | VARCHAR(500) | NOT NULL, 默认 `''` | 本体相对路径（`game/{game_type}/{卡带ID}/game.{后缀}`）；空串 = 尚未上传。h5 为原始 ZIP，解包资源另见 `game_h5_files` |
| cover_path | VARCHAR(500) | NULL | 封面相对路径（`game/{game_type}/{卡带ID}/cover.{后缀}`）；NULL = 无封面 |
| created_at | DATETIME | NOT NULL | |
| updated_at | DATETIME | NOT NULL | 上传资源 / 改信息时更新 |

> **攻略不落列也不建表**：有没有攻略由 `guide/index.html` 是否存在现算（`GameService._has_guide`），所以这里没有 `has_guide` 字段；接口载荷里的 `has_guide` 是每次按磁盘 stat 出来的。文件本身见下文「路径规则」的攻略一条。

**`game_h5_files`**（H5 游戏一个 ZIP 解包后的资源清单；重传整包替换）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| game_id | INTEGER | NOT NULL, 索引，联合唯一 `(game_id, path)` | 所属游戏（仅索引，**无 FK**） |
| path | VARCHAR(512) | NOT NULL | 归一化后的**包内**相对路径；入口固定为 `index.html` |
| file_path | VARCHAR(700) | NOT NULL | 磁盘**相对路径**（`game/{game_type}/{卡带ID}/h5/{包内相对路径}`） |
| size | INTEGER | NOT NULL, 默认 0 | 解压后字节数 |
| mime | VARCHAR(200) | NULL | 按后缀显式映射（`guess_asset_mime`），未知后缀为 `application/octet-stream` |
| created_at | DATETIME | NOT NULL | |

> 重传 ZIP 时先完整校验清单，再整包解到同层的暂存目录 `game/{类型}/{卡带ID}/.h5-{随机}`，成功后用目录改名整体替换 `h5/`（先把旧目录改名挪开、再把暂存目录改名就位，中途失败旧目录还在），最后单事务替换清单行。删除游戏或把类型改离 `h5` 时连同整个游戏目录一起清掉。

**`game_cloud_snapshots`**（一个云端存档 = 某(用户,游戏)此刻全部本地存档文件的整体快照：Flash 为多条 `.sol`，模拟器恒为 1 条 `.state`（该游戏本地只有一份档，固定名 `save.state`））

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 存档归属用户 |
| game_id | INTEGER | NOT NULL, 索引 | 所属游戏（仅索引，**无 FK** 到 `games`） |
| remark | VARCHAR(100) | NOT NULL, 默认 `''` | 备注，上限 100 字（service 层校验，超长直接报错） |
| created_at | DATETIME | NOT NULL | 列表按此倒序 |

> 快照随游戏一起消失：`GameService.delete` 会把该游戏所有账号的快照行、存档文件以及 `save/{用户名}/{类型}/{卡带ID}/` 目录一并清掉（游戏一删，快照就再也没有入口能列出来）。

**`game_cloud_snapshot_files`**（快照内的单个存档文件；字节透传，扩展名不限定）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| snapshot_id | INTEGER | NOT NULL, FK → `game_cloud_snapshots.id`, 索引 | 所属快照 |
| sort_order | INTEGER | NOT NULL, 默认 0 | 快照内顺序，从 0 起（列表按此排序） |
| local_key | VARCHAR(500) | NOT NULL | 还原时写回浏览器本地存储的键：Flash 为 localStorage 的 Ruffle 键；模拟器固定为 `x_emusave:{gameId}:state1`（内容经 IndexedDB 保存） |
| name | VARCHAR(255) | NOT NULL, 默认 `''` | 展示名；下载名按此——name 含扩展名时原样（模拟器固定 `save.state`），否则补 `.sol`（Flash 历史名） |
| size | INTEGER | NOT NULL, 默认 0 | 字节数（快照列表的 total_size 由此聚合） |
| mime | VARCHAR(200) | NULL | 默认回退 `application/octet-stream` |
| file_path | VARCHAR(500) | NOT NULL, 默认 `''` | 磁盘相对路径，见「云端存档」路径规则 |
| created_at | DATETIME | NOT NULL | |

**`game_screenshots`**（游戏截图：主机播放页截下的画面，**按 (用户, 游戏) 隔离**——只本人可见可改；封面不在这张表里，封面是全站共享的一份）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 截图归属用户 |
| game_id | INTEGER | NOT NULL, 索引 | 所属游戏（仅索引，**无 FK** 到 `games`） |
| sort_order | REAL | NOT NULL, 默认 0 | **展示分数**（越小越靠前）：新截图取「最大分 + 步长」，拖动重排只改这一行的分数（取相邻两分数的中值），相邻间隔小到阈值以下才由 service 把整份重新铺开 |
| description | VARCHAR(15) | NOT NULL, 默认 `''` | 描述，上限 15 字（`SCREENSHOT_DESCRIPTION_MAX_LENGTH`，service 层校验，超长 400）；展示在缩略图下方 |
| file_path | VARCHAR(500) | NOT NULL, 默认 `''` | 磁盘相对路径，见「游戏截图」路径规则；**不下发给前端**（内部实现细节） |
| size | INTEGER | NOT NULL, 默认 0 | 字节数 |
| mime | VARCHAR(200) | NULL | 按内容 magic 定下的类型（`image/png` / `image/jpeg` / `image/webp` / `image/gif`），读图时显式当 content-type 下发 |
| created_at | DATETIME | NOT NULL | |

另有复合索引 `ix_game_screenshots_user_game_order(user_id, game_id, sort_order)`（列表恒按 (用户, 游戏) 过滤 + 排序）。**刻意不加** `(user_id, game_id, sort_order)` 唯一约束：分数排序靠中值插入，唯一约束只会碍事。

**上传两张来源**：主机播放页标题栏「截图」按钮或快捷键 Ctrl+Shift+S（截下 PNG → 确认框预览并填描述 → 点「确认」入库），以及详情弹框「截图 [管理]」里的「上传截图」按钮（本地图片）。**格式按内容 magic 判定**（PNG / JPG / WebP / GIF，不看文件名与 content-type），后缀也由内容定；单张上限 16MB。删除游戏时由 `GameService.delete` 连同该游戏所有账号的截图行、文件与目录一起清掉（目录按 `file_path` 反推，见路径规则）。

**`game_gallery_images`**（游戏图集：一个游戏一套的展示图——宣传图、说明书扫描件之类）

与截图**正好相反**：图集**按游戏共享**，不记上传者，任何登录用户都能看、能传、能改描述、能删、能排序（接口只要求登录，不做归属校验）。校验、分数排序、上传/删除流程与截图同一套实现。

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| game_id | INTEGER | NOT NULL, 索引 | 所属游戏（仅索引，**无 FK** 到 `games`） |
| sort_order | REAL | NOT NULL, 默认 0 | **展示分数**（越小越靠前），机制与 `game_screenshots.sort_order` 完全一致 |
| description | VARCHAR(15) | NOT NULL, 默认 `''` | 描述，上限 15 字（`GALLERY_DESCRIPTION_MAX_LENGTH`，service 层校验，超长 400）；展示在缩略图下方 |
| file_path | VARCHAR(500) | NOT NULL, 默认 `''` | 磁盘相对路径，见「游戏图集」路径规则；**不下发给前端**（内部实现细节） |
| size | INTEGER | NOT NULL, 默认 0 | 字节数 |
| mime | VARCHAR(200) | NULL | 按内容 magic 定下的类型（`image/png` / `image/jpeg` / `image/webp` / `image/gif`），读图时显式当 content-type 下发 |
| created_at | DATETIME | NOT NULL | |

另有复合索引 `ix_game_gallery_images_game_order(game_id, sort_order)`；与截图一样**刻意不加**唯一约束。上传校验同上（非空、单张 ≤16MB、按内容 magic 认格式、描述 ≤15 字、游戏不存在 404）。**图集落在游戏目录内**，所以换游戏类型时随目录一起搬、行里的 `file_path` 同步改成新类型前缀（截图不迁移，这点两者不同）；删游戏时行与文件一并清掉。

**`game_emulator_settings`**（模拟器（EmulatorJS）设置：登录用户按平台一套，进游戏时自动加载、由播放页「保存配置」按钮手动整体覆盖保存）

只覆盖 7 个主机模拟器平台（`nes/snes/gb/gba/segaMD/segaGG/segaMS`），不含 flash/h5；内容小（几 KB），**只存 SQLite，不落文件**。

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 设置归属用户 |
| game_type | VARCHAR(50) | NOT NULL, 唯一约束 `(user_id, game_type)` | 平台，取值见上；无 FK 到 `games` |
| payload | TEXT | NOT NULL, 默认 `''` | 引擎 localStorage 那块的 JSON 文本：`{controlSettings, settings, cheats}`，service 层校验结构与 ≤64KB |
| updated_at | DATETIME | NOT NULL | 整块覆盖时刷新 |

**`game_recent_plays`**（最近游玩：游戏中心列表页顶部 rail 的数据源，按账号跨设备同步）

每个(用户, 游戏)只留一行，只记最后一次开玩时间；唯一约束保证重玩只刷新时间，行数天然不超过游戏总数，因此**不需要裁剪或分页**。删游戏时由 `GameService.delete` 连同这些行一起清理（无 FK/级联，与其它表一致）。

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | 同 `played_at` 时作排序兜底 |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 记录归属用户 |
| game_id | INTEGER | NOT NULL, 索引，唯一约束 `(user_id, game_id)` | 所属游戏（仅索引，**无 FK** 到 `games`） |
| played_at | DATETIME | NOT NULL | 最近一次开玩时间（UTC），重玩刷新；列表按它倒序 |

**`game_user_stats`**（游玩统计：游戏中心卡片上的总时长与游戏进度，按账号跨设备同步）

每个(用户, 游戏)只留一行。**与游戏类型无关**：Flash、H5、主机 ROM 三类播放都往同一张表累加。删游戏时由 `GameService.delete` 连同这些行一起清理（无 FK/级联，与其它表一致）。

`play_seconds` 由播放页的计时器每 30 秒心跳累加（`POST /api/games/stats/playtime`，单次上报在 service 里收敛到 0..300 秒防时钟跳变），也可由游戏中心右键菜单直接改写为指定小时数（`PUT …/playtime`，**覆盖**而非累加，之后再玩仍从该值往上加）。`progress` **只由用户手动设置**（`PUT …/progress`），不会因游玩自动变更，所以会出现「时长 > 0 但进度仍是未开始」的组合。

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 统计归属用户 |
| game_id | INTEGER | NOT NULL, 索引，唯一约束 `(user_id, game_id)` | 所属游戏（仅索引，**无 FK** 到 `games`） |
| play_seconds | INTEGER | NOT NULL, 默认 `0` | 累计游玩秒数；前端按小时展示（<10 小时保留 1 位小数，≥10 小时取整），0 时卡片上不显示任何内容 |
| progress | VARCHAR(20) | NOT NULL, 默认 `'not_started'` | 取值 `not_started` 未开始 / `in_progress` 进行中 / `completed` 已通关，service 层校验 |
| updated_at | DATETIME | NOT NULL | 任一字段变更时刷新 |

## 文件存储结构

根目录由 `backend/config.py` 的 `STORAGE_ROOT` 决定（本机默认 `<仓库>/data/storage`，容器内为 `/data/storage`），`LocalStorage` 构造时自动建出来。**SQLite 里存的都是相对这个根目录的路径**，读取时 `LocalStorage._resolve()` 拼上根路径并挡掉越界（绝对路径、`..` 一律拒绝）。浏览器从不直连磁盘，所有上传/下载都由 API 经 `StorageBackend` 分块流式代理。

目录名一律用「游戏类型键 + 卡带ID」，**不随游戏名变化**——卡带ID 建后不可改，所以改游戏名不会挪动任何文件。

### 路径规则

| 内容 | 相对路径 | 例子 | 生成处 |
|--------|----------|------|--------|
| 游戏本体 | `game/{game_type}/{卡带ID}/game.{后缀}` | `game/nes/AB-12/game.nes`、`game/h5/AB-12/game.zip` | `backend/games/paths.py::body_path` |
| 游戏封面 | `game/{game_type}/{卡带ID}/cover.{后缀}` | `game/nes/AB-12/cover.png` | `paths.py::cover_path` |
| 游戏图集 | `game/{game_type}/{卡带ID}/image/{uuid}.{后缀}` | `game/nes/AB-12/image/3f2a….png` | `paths.py::gallery_file_path` |
| H5 解包资源 | `game/{game_type}/{卡带ID}/h5/{包内相对路径}` | `game/h5/AB-12/h5/assets/app.js` | `paths.py::h5_asset_path` |
| H5 解包暂存 | `game/{game_type}/{卡带ID}/.h5-{随机}` | — | `paths.py::h5_temp_dir`（替换完即消失） |
| 攻略资源 | `game/{game_type}/{卡带ID}/guide/{文件夹内相对路径}` | `game/nes/AB-12/guide/pages/mc/1.html` | `paths.py::guide_asset_path`（入口 `guide_entry_path`） |
| 攻略上传暂存 | `game/{game_type}/{卡带ID}/.guide-{随机}` | — | `paths.py::guide_temp_dir`（替换完即消失） |
| 云端存档文件 | `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state` | `save/alice/nes/AB-12/3f2a….state` | `paths.py::save_file_path` |
| 游戏截图 | `image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}` | `image/alice/nes/AB-12/3f2a….png` | `paths.py::screenshot_file_path` |

细节说明：

- **类型目录名**：用 `game_type` 的键值（`flash` / `h5` / `nes` / `snes` / `gb` / `gba` / `segaMD` / `segaGG` / `segaMS`），与 SQLite 字段一致，纯标识符、无空格，后端不需要知道中文展示名。
- **游戏本体 / 封面**：路径随 `game_type` 与卡带ID 固定、不随上传文件名变，**同名重复上传会覆盖同一个文件**（先写同目录临时文件再改名）。本体后缀决定 `game_type`（扩展名与类型一一对应）：`.swf`→`flash`；`.zip`→`h5`；`.nes`→`nes`；`.sfc/.smc`→`snes`；`.gb/.gbc`→`gb`；`.gba`→`gba`；`.md/.gen`→`segaMD`；`.gg`→`segaGG`；`.sms`→`segaMS`；封面 `.jpg/.jpeg/.png/.gif/.webp`。换本体导致类型切换时，封面会跟着从旧类型目录挪到新类型目录（`LocalStorage.move`），随后**整个旧类型目录被递归删掉**；换封面后缀（如 `cover.png` → `cover.jpg`）在新文件写成功后删旧文件。
- **H5 解包资源**：上传的 ZIP 本体存 `game/{类型}/{卡带ID}/game.zip`；解包出的每个文件按包内相对路径落盘到 `h5/` 下，`game_h5_files` 记录「包内路径 → 磁盘相对路径」。入口固定为根目录 `index.html`（大小写不敏感识别、落库统一小写）；整包套在单一顶层目录时会剥掉该前缀。**磁盘上没有代际前缀**：重传是整包替换，靠目录改名完成（旧 `h5/` 改名挪开 → 暂存目录改名就位 → 删掉挪开的旧目录），中途失败旧目录都还在；删除游戏或换本体离开 `h5` 时连同 ZIP 与整个解包目录一起清。
- **攻略**：一份攻略就是 `guide/` 下的一个静态目录树，**没有清单表、也没有库里的标记**——「这个游戏有没有攻略」由 `guide/index.html` 是否存在（一次 `stat`）现算，所以从宿主目录手动拷走或删掉攻略，界面立刻跟着变。上传是**前端整目录选、后端一次 multipart 全收**：前端用 `webkitdirectory` 选文件夹、剥掉最外层目录名，把「文件夹内相对路径」按顺序放进 `paths`（JSON 数组，与 `files` 按下标一一对位），后端逐个过路径归一化（与 H5 包内路径同一套规则）、大小写不敏感查重、大小写不敏感识别入口并统一落成小写 `index.html`，根目录没有它就 400。落盘同样**没有代际前缀**：先写同层暂存目录 `.guide-{随机}`，全部就位后一次目录改名整体替换 `guide/`，失败清掉暂存目录、旧攻略还在；单次文件数上限 1000（Starlette 表单解析的硬上限）。读取走 `GET|HEAD /api/games/<id>/guide/<资源路径>`（**需登录**，与 H5 解包资源的免登录不同），路径归一化后直接拼磁盘路径，文件不存在即 404。删除游戏、或换本体把类型改走时，攻略随整个旧游戏目录一起清掉（不参与跨类型迁移）。
- **游戏截图**：与云端存档同构——目录按 `用户名/游戏类型/卡带ID` 分，一个截图一个 `{uuid}.{后缀}`（uuid 不可猜、不重名），原始文件名与游戏名都不进路径。后缀由**内容的 magic** 定（播放页截的是 `.png`，图库里手动上传的还可能是 `.jpg`/`.webp`/`.gif`），单张上限 16MB。**目录里的 `game_type` 是上传当时的类型**：截图不参与「换游戏类型」的迁移，所以读取、单张删除、删游戏清理一律用行里的 `file_path`，绝不用游戏当前类型拼目录（换过类型时，同一游戏的截图可能分散在两个类型目录里，功能不受影响）。
- **游戏图集**：与截图相反，它在**游戏目录内**（`game/{类型}/{卡带ID}/image/{uuid}.{后缀}`），一个游戏一套、按游戏共享、不记上传者（目录名 `image` 与顶层按账号隔离的截图目录同名，但一个挂在游戏目录下、一个挂在用户名下，是两回事）。**目录里的 `game_type` 跟游戏当前类型走**：换本体换了游戏类型时整个 `image/` 目录随游戏目录一起搬到新类型目录，行里的 `file_path` 同步换成新前缀；读取、单张删除、删游戏清理同样按行里的 `file_path`。
- **云端存档**：目录按 `用户名/游戏类型/卡带ID` 分，一个快照的每个文件各一个 `{uuid}.state`，文件名不体现原文件名（原名只用于下载时的 `Content-Disposition`，见 `game_cloud_snapshot_files.name`）。用户名进路径是安全的——用户名规则本身就限定在数字/字母/中划线/下划线。下载/删除快照按 `file_path` 定位文件；快照删除时逐文件删；上传中途失败回滚已写的文件（避免孤儿文件）。**删除游戏时连同它的全部存档快照与 `save/{用户名}/{类型}/{卡带ID}/` 目录一起清掉**（目录名带的是快照当时的游戏类型，所以按文件路径反推目录，而不是用游戏当前类型拼）。
