# 数据字典

本项目所有结构化数据的权威清单：**SQLite 关系结构** 与 **文件存储结构**。

**准确性约定：** 以代码为准，本文件只是索引。SQLite 结构源头是各模块的 `backend/*/models.py`（SQLModel `table=True`）；文件路径规则的源头是 `backend/games/paths.py`。改模型或路径规则时请同步更新本文。最后核对时间：2026-10-12。

## 存储总览

| 存储 | 位置 | 用途 |
|--------|------|------|
| SQLite 单文件 | `<运行时根>/db/app.db`（Docker 里是宿主 `${RUNTIME_HOST_DIR}/db/app.db` → 容器 `/runtime/db/app.db`） | 全部业务元数据 |
| SQLite 备份 | `<数据根>/db/<YYYY-MM>.db` | 启动时备一次、之后每小时一次，**当月只此一份、每次整份重写**（快照最多落后一小时）；不做还原，回滚就手工换回 `app.db` |
| SQLite 发现索引 | `<数据根>/db/game.db` | 游戏发现的**派生只读库**（外部中英文名录的全文索引 + 按机种的游戏榜单），服务启动时不存在会自动补建、榜单 CSV 变化时会就地补载，也可用 `make index` 重建；**不备份**，可从 CSV 重建，见文末「游戏发现索引」 |
| 数据根目录 | `STORAGE_ROOT`（本机默认 `<仓库>/data/storage`；容器内固定 `/data`，宿主目录由 `STORAGE_HOST_DIR` 挂进去） | 游戏本体/封面/攻略（ZIP 或 PDF）与 H5 的 **zip**/图集、云端存档、游戏截图，以及 `db/` 下的备份与检索索引。**只放原始素材**，会被整体拷走备份 |
| 运行时根目录 | `RUNTIME_ROOT`（不配 = 与数据根相同；容器内固定 `/runtime`，宿主目录由 `RUNTIME_HOST_DIR` 挂进去） | SQLite 库 + H5/攻略的**解包产物**（派生物，删掉会在下次访问时自动重建）。库单独放是为了让数据根整个可以交给网盘之类的客户端备份——它拷不动一个一直被写着的库文件 |
| 哨兵文件 | 每个根目录下的 `.mounted` | **人工创建**的空文件；该根的宿主路径在 Windows 盘挂载路径前缀下时启动会检查，缺了服务拒绝启动（见 `backend/mount_guard.py`）。两个根相同时只有一个 |

分工原则：**所有元数据在 SQLite，SQLite 里存的是相对于文件根目录的路径**（两个根下逐字一致）；文件本身是磁盘上的普通文件，用户可以直接从宿主目录拷走、备份、浏览。相对路径统一用 `/` 作分隔符，读取时由 `LocalStorage` 拼上根路径。

SQLModel 到 SQLite 的类型映射：`str(max_length=n)` → `VARCHAR(n)`；`str`（无长度）→ `TEXT`；`int` → `INTEGER`；`datetime` → `DATETIME`。整型主键即 SQLite 自增 `INTEGER PRIMARY KEY`。

## SQLite 结构

库路径在代码里写死为 `<运行时根>/db/app.db`（`backend/config.py` 的 `DB_SUBDIR` / `DB_FILENAME`，不可另配；运行时根不配就是数据根），`create_app()` 启动时 `init_db()` 建全部表。**没有迁移框架**：`create_all` 只建缺失的表、不给已存在的表补列，所以后来新增的列靠 `backend/database.py` 的 `_ADDED_COLUMNS` / `_ensure_columns()` 在启动时 `ALTER TABLE … ADD COLUMN` 补上（只加列，不改不删）；已经整张删掉的表靠 `_DROPPED_TABLES` / `_drop_tables()` 在启动时 `DROP TABLE`（目前只有 `game_h5_files`）。

数据根的 `db/` 下还有第二个库 `game.db`（游戏发现的检索索引与游戏榜单），它是**派生、只读**的，结构与本节无关，见文末「游戏发现索引」。

### 表索引

| # | 表 | 定义文件 | 一句话用途 |
|---|-----|----------|-------------|
| 1 | `users` | `backend/auth/models.py` | 平台账号（werkzeug 哈希），同时决定存档目录名 |
| 2 | `login_attempts` | 同上 | 登录失败计数与锁定，按 username 一行 |
| 3 | `games` | `backend/games/models.py` | 游戏条目（卡带ID、本体/封面相对路径） |
| 4 | `game_cloud_snapshots` | 同上 | 某(用户,游戏)的一次云端存档快照 |
| 5 | `game_cloud_snapshot_files` | 同上 | 快照里的单个存档文件（.sol / .state）及还原元信息 |
| 6 | `game_screenshots` | 同上 | 按(用户,游戏)的游玩截图（相对路径 + 描述 + 展示顺序） |
| 7 | `game_emulator_settings` | 同上 | 按(用户,平台)一份的模拟器设置（键位/选项/金手指，JSON 文本） |
| 8 | `game_recent_plays` | 同上 | 按(用户,游戏)一行的最近游玩时间（游戏中心 rail 用） |
| 9 | `game_user_stats` | 同上 | 按(用户,游戏)一行的游玩时长（秒）与进度 |
| 10 | `game_gallery_images` | 同上 | 游戏图集：一个游戏一套的**共享**展示图（宣传图、说明书扫描件之类） |

> `game_h5_files` 已删除（H5 改成「zip 存在数据根、按需解到运行时根」，不再有清单表）；老库里的空表由启动时的 `_drop_tables()` 清掉。

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
| cartridge_id | VARCHAR(64) | NOT NULL, 唯一索引 `uq_games_cartridge_id` | 卡带ID：创建时必填，同时是磁盘上的目录名与「同一盘卡带」的身份标识。规则见 `validate_cartridge_id()`：只允许数字、字母、中划线、下划线，落库前统一转**大写**。**普通编辑（`PUT /manage/{id}`）改不动它**，要换走显式改名接口 `PUT /manage/{id}/cartridge-id`（`GameService.rename_cartridge_id()`）——一次迁移会搬三类目录并改写下面五处路径列（见「文件存储结构」）。游戏榜单页在**请求期**拿它把榜单行关联到库存（`GameService.map_for_cartridge_ids`，比对前经 `normalize_cartridge_id()` 归一；只读、不落库），所以改名后关联**立刻**跟着新 ID 走、不需要重建索引 |
| cover_type | VARCHAR(20) | NULL | 封面类型：这盘封面被「美化」成了哪种外观，值就是封面样式 id（`flash` DISK / `gb` GB / `gbc` GBC / `gba` GBA / `fc` FC / `nes` NES）。**可空**，空 = 没有封面类型：新建（手动上传 / 网络上传 / 搬运）一律留空，只有管理页**编辑弹框手动选**（`PUT /manage/{id}`）与**「美化封面」**（`POST /manage/{id}/assets` 的 `cover_type` 表单字段，与封面文件同一次提交）两条写入路径。可选集合按游戏类型给，见 `backend/games/models.py` 的 `COVER_TYPES_BY_GAME_TYPE` / `cover_types_for()`——不支持美化封面的 `h5`/`snes`/`sega*` 返回空元组、永远为空；校验入口 `service.py::validate_cover_type()`。游戏类型创建后不可变，换本体不会改动它。游戏中心「全部游戏」在游戏类型分组内再按它分行，空的自成一组排在最后。前端展示层镜像是 `frontend/src/constants/coverStyles.js` 的 `STYLE_BY_GAME_TYPE`（两边 id 集合与顺序必须一致） |
| description | VARCHAR(200) | NOT NULL, 默认 `''` | 描述。上限 200 字（`validate_description()`）：新建/编辑超长直接 400，搬运抓来的站点简介按上限截断入库 |
| game_type | VARCHAR(50) | NOT NULL, 索引 | 类型值：`flash`（Ruffle 播放 SWF）、`h5`（上传 ZIP，播放时按需解包，沙箱 iframe 播放）或主机平台 `nes`/`snes`/`gb`/`gba`/`segaMD`/`segaGG`/`segaMS`（EmulatorJS 播放，值与 EJS system key 一致）。**由本体文件扩展名自动判定**（不手动指定），判定入口与白名单在 `backend/games/service.py` 的 `GAME_TYPES`/`_GAME_TYPE_EXTENSIONS`/`detect_game_type()`。中心列表按 `game_path != ''` 过滤 |
| size | INTEGER | NOT NULL, 默认 0 | 本体字节数（h5 为 ZIP 压缩包大小） |
| crc32 | VARCHAR(8) | NOT NULL, 默认 `''` | **当前本体内容**的 CRC32，8 位大写十六进制（如 `D445F698`）。上传或换本体时重算落库，只作记录、**不再作为锁定凭据**；空串表示尚未算出 |
| game_path | VARCHAR(500) | NOT NULL, 默认 `''` | 本体相对路径（`game/{game_type}/{卡带ID}/game.{后缀}`）；空串 = 尚未上传。h5 就是它的 zip（`game.zip`），解包产物不落库 |
| cover_path | VARCHAR(500) | NULL | 封面相对路径（`game/{game_type}/{卡带ID}/cover.{后缀}`）；NULL = 无封面 |
| guide_kind | VARCHAR(10) | NOT NULL, 默认 `''` | 攻略形态：`''` = 没有、`'zip'` = ZIP 静态站包、`'pdf'` = 单个 PDF。**上传攻略写值、删除攻略清空**；列表接口据此给出 `has_guide`，不再 stat 磁盘。老库补列时旧行一律空串（不回填磁盘已有文件） |
| created_at | DATETIME | NOT NULL | |
| updated_at | DATETIME | NOT NULL | 上传资源 / 改信息 / 传攻略 / 删攻略时更新 |

> **攻略状态落列、不建表**：形态记在 `games.guide_kind`（`''` / `'zip'` / `'pdf'`），上传写值、删除清空；接口载荷里的 `has_guide` 由它派生。旧库补列时不做磁盘回填，因此宿主手动放进数据根的文件不会自动变成攻略。文件本身见下文「路径规则」的攻略一条。

**`game_cloud_snapshots`**（一个云端存档 = 某(用户,游戏)此刻全部本地存档文件的整体快照：Flash 为多条 `.sol`，模拟器恒为 1 条 `.state`（该游戏本地只有一份档，固定名 `save.state`））

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 存档归属用户 |
| game_id | INTEGER | NOT NULL, 索引 | 所属游戏（仅索引，**无 FK** 到 `games`） |
| parent_id | INTEGER | NULL, 索引 | 父快照 id；NULL = 顶层。**无物理外键**（老库靠 ALTER 补列、SQLite 也不校验），归属、同游戏与防环由 service 保证：父级必须同属一个 `(user_id, game_id)`、不能指向自己、不能成环。**新建快照自动指向同组最新一条（created_at DESC, id DESC）；第一条为 NULL**。删除父快照时**直接子级改回 NULL（顶层）**，不接续祖父、不级联删除 |
| sort_order | REAL | NOT NULL, 默认 0 | **展示分数**（越小越靠前），列表与同级兄弟都按 `(sort_order, id)` 升序。新快照取「最大分 + 1000」追加到末尾（越新越靠下）；`POST /api/games/saves/{id}/move` 只改被移动那一行的分数（取相邻中值），间隙用尽时整份重铺。复合索引 `ix_game_cloud_snapshots_user_game_order (user_id, game_id, sort_order)`。注意它与 `game_cloud_snapshot_files.sort_order`（快照内文件序号）不是一回事 |
| remark | VARCHAR(100) | NOT NULL, 默认 `''` | 备注，上限 100 字（service 层校验，超长直接报错） |
| created_at | DATETIME | NOT NULL | 「最新一条」语义（新建快照自动挂到谁下面）按 `created_at DESC, id DESC` 判定；**列表顺序看 `sort_order`** |

> 快照之间是**同一 `(用户, 游戏)` 内的森林**（允许多个顶层，每个节点最多一个父级、可有多个子级），由 `PUT /api/games/saves/{id}/parent` 设置/清除；新建快照自动接到同组最新一条后面，第一条为顶层。**同级兄弟的上下顺序**由 `sort_order` 决定，`POST /api/games/saves/{id}/move`（body `{to_index}`，下标在同级内）调整，前端快捷键是 `Shift + ↑/↓`。树形模式只是前端的自动布局视图，**不存节点坐标**。老库启动时由 `database.py` 的 `_ensure_columns()` 补 `parent_id` 可空列与 `sort_order`（默认 0，按 id 升序即创建先后），并由 `_ensure_indexes()` 补 `ix_game_cloud_snapshots_parent_id` 与 `ix_game_cloud_snapshots_user_game_order` 索引。

> 快照随游戏一起消失：`GameService.delete` 会把该游戏所有账号的快照行、存档文件以及 `save/{用户名}/{类型}/{卡带ID}/` 目录一并清掉（游戏一删，快照就再也没有入口能列出来）。

**`game_cloud_snapshot_files`**（快照内的单个存档文件；字节透传，扩展名不限定）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | INTEGER | PK 自增 | |
| snapshot_id | INTEGER | NOT NULL, FK → `game_cloud_snapshots.id`, 索引 | 所属快照 |
| sort_order | INTEGER | NOT NULL, 默认 0 | 快照内顺序，从 0 起（列表按此排序） |
| local_key | VARCHAR(500) | NOT NULL | 还原时写回浏览器本地存储的键：Flash 为 localStorage 的 Ruffle 键；模拟器固定为 `x_emusave:{gameId}:state1`（内容经 IndexedDB 保存） |
| name | VARCHAR(255) | NOT NULL, 默认 `''` | 展示名；下载名按此——name 含扩展名时原样（模拟器固定 `save.state`），否则补 `.sol`（Flash 存档的后缀） |
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

另有复合索引 `ix_game_gallery_images_game_order(game_id, sort_order)`；与截图一样**刻意不加**唯一约束。上传校验同上（非空、单张 ≤16MB、按内容 magic 认格式、描述 ≤15 字、游戏不存在 404）。**图集落在游戏目录内**，游戏类型创建后不可变，所以目录不会跨类型迁移（截图目录带写入当时的类型，这点两者不同）；改卡带ID 时随游戏目录一起搬、行里的 `file_path` 同步换成新前缀；删游戏时行与文件一并清掉。

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

两个根都由 `backend/config.py` 决定：数据根 `STORAGE_ROOT`（本机默认 `<仓库>/data/storage`，容器内为 `/data`）、运行时根 `RUNTIME_ROOT`（不配时等于数据根，容器内为 `/runtime`），`create_app()` 各建一个 `LocalStorage` 实例（`app.state.storage` / `app.state.runtime_storage`），构造时自动建出根目录。**SQLite 里存的都是相对数据根的路径**，读取时 `LocalStorage._resolve()` 拼上对应的根并挡掉越界（绝对路径、`..` 一律拒绝）；两个根下的相对路径**逐字一致**。浏览器从不直连磁盘，所有上传/下载都由 API 经 `StorageBackend` 分块流式代理。

**根目录下还可能有一个不在表里的哨兵文件 `.mounted`**：空文件，**人工创建**（不由 `LocalStorage`、也不由任何代码代建）。**只有该根的宿主路径落在 Windows 盘挂载路径前缀下时**（`backend/config.py` 的 `WINDOWS_MOUNT_PREFIX`，默认 `/mnt`）服务启动才会检查它，缺了就打日志等 5 秒退出（`backend/mount_guard.py`）；放普通 Linux 目录下的根不做这个检查。**数据根与运行时根各查一份**（两个根相同时就是同一个文件）。它只用来判断「这个目录确实是挂上了的根目录」，不参与任何业务路径。

目录名一律用「游戏类型键 + 卡带ID」，**不随游戏名变化**——改游戏名不会挪动任何文件。
只有**显式改卡带ID**（`PUT /api/games/manage/<id>/cartridge-id`）会动磁盘：它把
`game/{类型}/{旧ID}` 一棵树、以及各账号的 `save/{用户名}/{类型}/{旧ID}` 与
`image/{用户名}/{类型}/{旧ID}` 整体改名，并同步改写 `games.game_path` / `games.cover_path` /
`game_gallery_images.file_path` / `game_screenshots.file_path` /
`game_cloud_snapshot_files.file_path` 这五处（详见下文各条）；运行时根下的旧解包产物直接作废。

### 路径规则

**数据根**（原始素材）：

| 内容 | 相对路径 | 例子 | 生成处 |
|--------|----------|------|--------|
| 游戏本体 | `game/{game_type}/{卡带ID}/game.{后缀}` | `game/nes/AB-12/game.nes`、`game/h5/AB-12/game.zip` | `backend/games/paths.py::body_path` / `h5_zip_path` |
| 游戏封面 | `game/{game_type}/{卡带ID}/cover.{后缀}` | `game/nes/AB-12/cover.png` | `paths.py::cover_path` |
| 攻略包 | `game/{game_type}/{卡带ID}/guide.zip` | `game/nes/AB-12/guide.zip` | `paths.py::guide_zip_path` |
| 攻略 PDF | `game/{game_type}/{卡带ID}/guide.pdf` | `game/nes/AB-12/guide.pdf` | `paths.py::guide_pdf_path` |
| 游戏图集 | `game/{game_type}/{卡带ID}/image/{uuid}.{后缀}` | `game/nes/AB-12/image/3f2a….png` | `paths.py::gallery_file_path` |
| 云端存档文件 | `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state` | `save/alice/nes/AB-12/3f2a….state` | `paths.py::save_file_path` |
| 游戏截图 | `image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}` | `image/alice/nes/AB-12/3f2a….png` | `paths.py::screenshot_file_path` |

**运行时根**（派生物，删了会自动重建）：

| 内容 | 相对路径 | 例子 | 生成处 |
|--------|----------|------|--------|
| H5 解包资源 | `game/{game_type}/{卡带ID}/h5/{包内相对路径}` | `game/h5/AB-12/h5/assets/app.js` | `paths.py::h5_asset_path`（入口 `h5_entry_path`） |
| 攻略解包资源 | `game/{game_type}/{卡带ID}/guide/{包内相对路径}` | `game/nes/AB-12/guide/pages/mc/1.html` | `paths.py::guide_asset_path`（入口 `guide_entry_path`） |
| 解包暂存 | `game/{game_type}/{卡带ID}/.{h5,guide}-{随机}` | — | `paths.py::h5_temp_dir` / `guide_temp_dir`（替换完即消失） |

细节说明：

- **类型目录名**：用 `game_type` 的键值（`flash` / `h5` / `nes` / `snes` / `gb` / `gba` / `segaMD` / `segaGG` / `segaMS`），与 SQLite 字段一致，纯标识符、无空格，后端不需要知道中文展示名。
- **游戏本体 / 封面**：路径随 `game_type` 与卡带ID 固定、不随上传文件名变，**同名重复上传会覆盖同一个文件**（先写同目录临时文件再改名）。本体后缀决定 `game_type`（扩展名与类型一一对应）：`.swf`→`flash`；`.zip`→`h5`；`.nes`→`nes`；`.sfc/.smc`→`snes`；`.gb/.gbc`→`gb`；`.gba`→`gba`；`.md/.gen`→`segaMD`；`.gg`→`segaGG`；`.sms`→`segaMS`；封面 `.jpg/.jpeg/.png/.gif/.webp`。**游戏类型创建后不可变**：换本体必须与当前类型一致（同类型内可换后缀，如 `.gb`→`.gbc`），跨类型 400 且旧档不动；同类型换后缀时，新本体落库成功后才删旧后缀文件，并重算 `crc32`/`size`/`game_path`。换封面后缀（如 `cover.png` → `cover.jpg`）同样在新文件写成功后删旧文件。
- **H5**：上传的 ZIP 本体存数据根的 `game/{类型}/{卡带ID}/game.zip`，**上传时只校验不解压、也不落任何清单**。播放时按需把整包解到**运行时根**的 `h5/` 下，每个文件按包内相对路径落盘；入口固定为根目录 `index.html`（大小写不敏感识别、落盘统一小写）；整包套在单一顶层目录时会剥掉该前缀。**磁盘上没有代际前缀**：解包先写同层暂存目录、再用目录改名整体替换；入口文件存在就直接复用，不重复解。重传 zip / 改卡带ID / 删游戏时由写路径显式作废运行时根那份（两个根相同时退化成一次 `exists()` 检查）。
- **攻略**：一份攻略可以是 **ZIP 静态站包或单个 PDF**，二者互斥，存数据根的 `game/{类型}/{卡带ID}/guide.zip` / `guide.pdf`。形态记在 `games.guide_kind`（`''` / `zip` / `pdf`），**上传写值、删除清空**，列表载荷的 `has_guide` / `guide_kind` 直接来自这一列，**不再 stat 磁盘**；宿主手动增删文件不会自动反映（手动删掉文件后打开会 404）。上传是**单个文件**（multipart 只有一个 `file`）：ZIP 与 H5 共用同一套校验（路径归一化、大小写不敏感查重、入口只认 `index.html`、zip/条目/单条/总量/压缩比上限），**只校验不解压**；PDF 只查后缀、大小（≤128MB）与前 1024 字节含 `%PDF-`，**原样存储**。**上传一种会删掉另一种**，并作废旧的解包产物。删除走 `DELETE /api/games/manage/<id>/guide`：ZIP/PDF 文件、运行时解包目录与 `guide_kind` 一起清掉，幂等。查看 ZIP 时按需解到运行时根的 `guide/`：没有代际前缀，先写同层暂存目录再一次目录改名整体替换；入口文件存在就直接复用。重传 / 改卡带ID / 删游戏时由写路径显式作废。读取 ZIP 资源走 `GET|HEAD /api/games/<id>/guide/<资源路径>`（**需登录**，与 H5 资源的免登录不同），路径归一化后从运行时根取；PDF 走 `GET|HEAD /api/games/<id>/guide.pdf`（同样需登录），从数据根直读并以 `application/pdf` inline 返回。文件不存在或形态不符即 404。删除游戏时，攻略文件随整个游戏目录一起清掉。
- **游戏截图**：与云端存档同构——目录按 `用户名/游戏类型/卡带ID` 分，一个截图一个 `{uuid}.{后缀}`（uuid 不可猜、不重名），原始文件名与游戏名都不进路径。后缀由**内容的 magic** 定（播放页截的是 `.png`，图库里手动上传的还可能是 `.jpg`/`.webp`/`.gif`），单张上限 16MB。**目录里的 `game_type` 是上传当时的类型**：历史数据里换过类型的游戏，同一游戏的截图可能分散在两个类型目录里，所以读取、单张删除、删游戏清理一律用行里的 `file_path`，绝不用游戏当前类型拼目录（功能不受影响）。**改卡带ID 同理**：只把 `file_path` 父目录的最后一段换成新 ID，那一层类型保持原样。
- **游戏图集**：与截图相反，它在**游戏目录内**（`game/{类型}/{卡带ID}/image/{uuid}.{后缀}`），一个游戏一套、按游戏共享、不记上传者（目录名 `image` 与顶层按账号隔离的截图目录同名，但一个挂在游戏目录下、一个挂在用户名下，是两回事）。**目录里的 `game_type` 跟游戏当前类型走**：游戏类型创建后不可变，所以 `image/` 目录不会跨类型迁移；读取、单张删除、删游戏清理同样按行里的 `file_path`。
- **云端存档**：目录按 `用户名/游戏类型/卡带ID` 分，一个快照的每个文件各一个 `{uuid}.state`，文件名不体现原文件名（原名只用于下载时的 `Content-Disposition`，见 `game_cloud_snapshot_files.name`）。用户名进路径是安全的——用户名规则本身就限定在数字/字母/中划线/下划线。下载/删除快照按 `file_path` 定位文件；快照删除时逐文件删；上传中途失败回滚已写的文件（避免孤儿文件）。**删除游戏时连同它的全部存档快照与 `save/{用户名}/{类型}/{卡带ID}/` 目录一起清掉**（目录名带的是快照当时的游戏类型；历史数据里换过类型的游戏与当前类型不同，所以按文件路径反推目录，而不是用游戏当前类型拼）。**改卡带ID 时同样按文件路径反推父目录**：把最后一段换成新 ID 并整目录改名，那一层类型保持原样。

## 游戏发现索引（`game.db`）

第三个页面（游戏发现）的数据源：**与平台游戏库无关**的外部数据——中英文名录（`机种 / 中文名 / 英文名`）
与游戏榜单（`序号 / 机种名称 / 游戏名称 / 游戏卡带ID`），所以它们单独一个库，
**与 `app.db` 没有任何外键关系**。

| 项 | 值 |
|----|----|
| 路径 | `<数据根>/db/game.db`（`backend/config.py` 的 `GAME_INDEX_FILENAME`；容器里就是 `/data/db/game.db`） |
| 写入方 | 只有 `backend/games/search_index.py` 这一个模块，两条写路径：① `build_index()` 整库重建——**服务启动自动补建**（`create_app()` → `ensure_game_index()`，文件不存在、或库里的 `schema_version` 与代码不符时建，`TESTING` 跳过、失败只记 warning）与 **`make index`**（`Makefile` → `python -m backend.cli index`，手动重建/更新；`--skip-ranking` 只重建检索）；② `ensure_ranking_loaded()` 启动时把榜单 CSV 就地补进已存在的库（指纹一致时连读写连接都不打开）。容器里也能建（CSV 随 `backend/` 进镜像） |
| 读取方 | `backend/games/search_service.py::GameSearchService` 与 `backend/games/ranking_service.py::GameRankingService`，一律 `mode=ro` + `PRAGMA query_only=1`，每请求一条短连接——**运行期只读，绝不写它** |
| 是否备份 | **不进备份**（`backend/backup.py` 只按固定文件名备份 `app.db`）。它可从 `backend/search/` 下的 CSV 完整重建 |
| 源数据 | 检索：`backend/search/csv/` 下 37 个 CSV（3 列无表头、UTF-8 带 BOM、CRLF）；榜单：`backend/search/ranking/ranking.csv`（4 列、表头可选）。都随 `backend/` 一起进 api 镜像 |
| 重建方式 | 整库重建 + 原子替换（写同目录 `game.db.tmp` → `chmod 0644` → `os.replace`）。**不开 WAL**，所以不会留 `-wal`/`-shm`；重建后无需重启 api。榜单的就地补载走短事务（`BEGIN IMMEDIATE` → 重建 `ranking` 表 → upsert meta），失败回滚、旧榜单原封不动 |

### 表

| 表 | 用途 |
|----|------|
| `console` | 检索的**统一机种**（`id` / `name` UNIQUE / `platform_id` / `raw_names`）。一行 = 一个机种（不是 CSV 里的一个原始机种名）：`name` 是词表里的统一显示名（如「任天堂 GB/GBC」）、`platform_id` 是 EmulatorJS 的 system key（如 `gb`，未收录机种为 NULL）、`raw_names` 是 JSON 数组文本、记下被合并进来的原始写法（如 `["任天堂GB", "任天堂GBC"]`，溯源用）。单独一张表是为了不给每行重复存机种名 |
| `game` | 名录一行（`id` / `console_id` / `zh` / `en` / `src`）。`src` 是来源 CSV 文件名，仅作溯源 |
| `game_fts` | FTS5 全文索引（`zh_uni` / `en_uni`），**contentless**（`content=''`，不重复存正文），`tokenize='unicode61 remove_diacritics 2'`；`rowid` 与 `game.id` 一一对应 |
| `ranking` | 榜单一行（`platform` / `console` / `rank` / `title` / `cartridge_ids`）。`PRIMARY KEY (platform, rank) WITHOUT ROWID`；`platform` 是归一后的机种键（认不出机种时是 `raw:{归一后的原文}`），`console` 是 CSV 原文（溯源与展示兜底）；`cartridge_ids` 是 JSON 数组文本（0~2 个卡带 ID，查不到编号时是空数组 `[]`）。机种存文本而不是外键——榜单的机种未必出现在检索名录里。**表结构不变**：与平台库存的关联（榜单行 → `games.cartridge_id`）是接口**运行期**的一次只读查询，结果**不落库、不进索引**（见下面「约定」） |
| `meta` | 键值元信息。检索：`schema_version`（与 `search_index.SCHEMA_VERSION` 比对，不符时接口 503）/ `built_at` / `rows` / `consoles`。榜单：`ranking_schema_version`（与 `RANKING_SCHEMA_VERSION` 比对，存在但不符时榜单接口 503）/ `ranking_fingerprint`（源 CSV 原始字节的 SHA-256，只有成功加载后才写）/ `ranking_source` / `ranking_rows` / `ranking_consoles` / `ranking_loaded_at` |
| `idx_game_console` | `game(console_id, en)` 上的普通索引：无关键词时按机种分页排序走它，搜索不走它 |
| `idx_console_platform` | `console(platform_id)` 上的普通索引 |

### 约定

- **机种经 `backend/games/platforms.py` 的词表归一**：两份 CSV 的「机种」都是自由文本
  （检索写 `任天堂GB`、榜单写 `GB/GBC`），建库时一律解析成统一机种，id 就是 EmulatorJS 的
  system key。`console.id` 按**词表顺序**分配（厂商分组），未收录机种按首次出现顺序排在最后。
  同一个机种的多个原始名在检索侧**合并成一行 console**（36 个原始机种 → 32 项：23 个统一机种
  + 9 个未收录）。**加机种名只改词表的 `aliases`，不用动这里。**
- `game_fts` 里的两列是**处理过**的文本（NFKC → 剥结尾的地区/语言/版本标签 → 汉字逐字拆成 token，
  见 `backend/games/search_text.py::index_text()`）；`game.zh` / `game.en` 存的是**原文**，
  接口返回的也是原文。索引期与查询期共用同一份实现。
- 建库时按 `(机种, 中文, 英文)` **三元组完全一致**去重（52,611 行源数据 → 51,359 行）；
  只中文或只英文相同的**不去重**——那是同款游戏的不同地区版本。
- 落库行数/机种数变了不用改代码，重跑 `make index` 覆盖即可。
- 榜单的**检索版本与榜单版本互不牵连**：往老库里加 `ranking` 表是纯新增，不 bump `schema_version`
  （否则老库在补表前就会被判「版本过旧」，检索一起 503）。榜单没加载（表在但没指纹、或表不存在）
  是正常状态，接口返回 `has_ranking: false` + 空列表，不是错误。
- 榜单 CSV 的格式契约（四列、表头可选、序号唯一、卡带 ID 可空、分隔符与数量上限）见
  `backend/search/ranking/README.md`；解析错误带文件名与行号。
- **榜单行与平台库存的关联是运行期的只读查询，不进这个库**：榜单接口每次请求把该机种整份榜单的
  卡带 ID 一次性交给 `GameService.map_for_cartridge_ids`（比对前经 `normalize_cartridge_id()`
  去首尾空白 + 转大写，只认 `games.game_path != ''` 的条目；一个机种最多 100 行 × 2 个 ID，
  所以不分块），命中的行在载荷里多出 `game_id` / `path`。**关联结果不落库、不进索引、不缓存**，
  所以增删游戏立刻生效，不需要 `make index`；索引库这边**一个字节都不写**。
