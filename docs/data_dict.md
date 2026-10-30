# 数据字典

本项目结构化数据的权威清单：**SQLite 关系结构** 与 **文件存储结构**。

**准确性约定：** 以代码为准，本文件只是索引。

- SQLite 结构源头：`backend/*/models.py`（SQLModel `table=True`）。
- 文件路径规则源头：`backend/games/paths.py`。
- 业务行为与边界见 [`specs/`](specs/README.md)。

## 存储总览

| 存储 | 位置 | 用途 |
|---|---|---|
| SQLite 业务库 | `<运行时根>/db/app.db` | 全部业务元数据 |
| SQLite 备份 | `<数据根>/db/<YYYY-MM>.db` | 每月一份，整份重写 |
| SQLite 发现索引 | `<数据根>/db/game.db` | 检索与榜单的派生只读库 |
| 数据根 | `STORAGE_ROOT` | 原始素材，整体备份 |
| 运行时根 | `RUNTIME_ROOT` | SQLite 库 + 解包产物 |
| 哨兵文件 | 每个根下的 `.mounted` | 人工创建；只拦启动 |

分工原则：

- 所有元数据在 SQLite。
- SQLite 里存**相对文件根目录的路径**，两个根下逐字一致。
- 文件本身是普通文件，可直接拷走、备份、浏览。
- 相对路径统一用 `/` 分隔，由 `LocalStorage` 拼上根路径。

类型映射：`str(max_length=n)` → `VARCHAR(n)`；`str` → `TEXT`；
`int` → `INTEGER`；`datetime` → `DATETIME`；整型主键即自增 `INTEGER PRIMARY KEY`。

## SQLite 结构

- 库路径写死为 `<运行时根>/db/app.db`。
- `create_app()` 启动时 `init_db()` 建全部表。
- 没有迁移框架：
  - 新列由 `backend/database.py` 的 `_ensure_columns()` 补。
  - 已删除的表由 `_drop_tables()` 清理。
- 数据根下的 `game.db` 是独立派生库，见文末「游戏发现索引」。

### 表索引

| # | 表 | 定义文件 | 一句话用途 |
|---|---|---|---|
| 1 | `users` | `backend/auth/models.py` | 平台账号 |
| 2 | `login_attempts` | 同上 | 登录失败计数与锁定 |
| 3 | `games` | `backend/games/models.py` | 游戏条目 |
| 4 | `game_cloud_snapshots` | 同上 | 云端存档快照 |
| 5 | `game_cloud_snapshot_files` | 同上 | 快照内的单个存档文件 |
| 6 | `game_screenshots` | 同上 | 按账号隔离的截图 |
| 7 | `game_gallery_images` | 同上 | 按游戏共享的图集 |
| 8 | `game_emulator_settings` | 同上 | 按账号与平台的模拟器设置 |
| 9 | `game_recent_plays` | 同上 | 最近游玩 |
| 10 | `game_user_stats` | 同上 | 游玩时长与进度 |

> `game_h5_files` 已删除：H5 改成「zip 存数据根、按需解到运行时根」，不再有清单表。
> 老库里的空表由启动时的 `_drop_tables()` 清掉。

### auth — 账号

**`users`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | |
| username | VARCHAR(32) | NOT NULL, UNIQUE | 登录名；规则见 [`auth.md`](specs/auth.md) |
| password_hash | VARCHAR(255) | NOT NULL | werkzeug 单向哈希 |
| created_at | DATETIME | NOT NULL | UTC |

**`login_attempts`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| username | VARCHAR(32) | PK | 锁定对象 |
| failed_count | INTEGER | NOT NULL | 累计失败次数 |
| locked_until | DATETIME | NULL | 解锁时刻；NULL = 未锁定 |

锁定阈值与行为见 [`auth.md`](specs/auth.md)。

### games — 游戏中心

**`games`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | 路由 `{game_id}`；与磁盘目录无关 |
| name | VARCHAR(255) | NOT NULL, 唯一 `(game_type, name)` | 合法的 Windows / 网盘文件名 |
| cartridge_id | VARCHAR(64) | NOT NULL, 唯一 | 大写；见 [`game-storage.md`](specs/game-storage.md) |
| cover_type | VARCHAR(20) | NULL | 封面样式 id；见 [`game-storage.md`](specs/game-storage.md) |
| description | VARCHAR(200) | NOT NULL, 默认 `''` | 上限 200 字 |
| game_type | VARCHAR(50) | NOT NULL, 索引 | `flash` / `h5` / 主机平台键 |
| size | INTEGER | NOT NULL, 默认 0 | 本体字节数 |
| crc32 | VARCHAR(8) | NOT NULL, 默认 `''` | 当前本体 CRC32，8 位大写十六进制 |
| game_path | VARCHAR(500) | NOT NULL, 默认 `''` | 本体相对路径；空 = 未上传 |
| cover_path | VARCHAR(500) | NULL | 封面相对路径；NULL = 无封面 |
| guide_kind | VARCHAR(10) | NOT NULL, 默认 `''` | `''` / `zip` / `pdf` |
| created_at | DATETIME | NOT NULL | |
| updated_at | DATETIME | NOT NULL | |

索引：

- `uq_games_cartridge_id`：卡带 ID 全局唯一。
- `uq_games_game_type_name`：同类型下游戏名唯一。
- 中心列表按 `game_path != ''` 过滤。

卡带 ID 改名、封面类型、命名规则见 [`game-storage.md`](specs/game-storage.md)。

**`game_cloud_snapshots`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 归属用户 |
| game_id | INTEGER | NOT NULL, 索引 | 所属游戏；无 FK |
| parent_id | INTEGER | NULL, 索引 | NULL = 顶层；无物理外键 |
| sort_order | REAL | NOT NULL, 默认 0 | 展示分数，越小越靠前 |
| remark | VARCHAR(100) | NOT NULL, 默认 `''` | 备注，上限 100 字 |
| created_at | DATETIME | NOT NULL | 决定「最新一条」 |

- 复合索引：`ix_game_cloud_snapshots_user_game_order`。
- 父子关系、排序、删除父节点行为见
  [`game-saves-stats.md`](specs/game-saves-stats.md)。

**`game_cloud_snapshot_files`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | |
| snapshot_id | INTEGER | NOT NULL, FK → 快照, 索引 | 所属快照 |
| sort_order | INTEGER | NOT NULL, 默认 0 | 快照内顺序 |
| local_key | VARCHAR(500) | NOT NULL | 还原时写回浏览器的键 |
| name | VARCHAR(255) | NOT NULL, 默认 `''` | 展示名与下载名 |
| size | INTEGER | NOT NULL, 默认 0 | 字节数 |
| mime | VARCHAR(200) | NULL | 默认 `application/octet-stream` |
| file_path | VARCHAR(500) | NOT NULL, 默认 `''` | 磁盘相对路径 |
| created_at | DATETIME | NOT NULL | |

**`game_screenshots`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 归属用户 |
| game_id | INTEGER | NOT NULL, 索引 | 所属游戏；无 FK |
| sort_order | REAL | NOT NULL, 默认 0 | 展示分数 |
| description | VARCHAR(15) | NOT NULL, 默认 `''` | 描述，上限 15 字 |
| file_path | VARCHAR(500) | NOT NULL, 默认 `''` | 磁盘相对路径；不下发前端 |
| size | INTEGER | NOT NULL, 默认 0 | 字节数 |
| mime | VARCHAR(200) | NULL | 按内容 magic 判定 |
| created_at | DATETIME | NOT NULL | |

- 复合索引：`ix_game_screenshots_user_game_order`。
- 刻意不加唯一约束：分数排序靠中值插入。
- 上传、删除、排序行为见 [`game-assets.md`](specs/game-assets.md)。

**`game_gallery_images`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | |
| game_id | INTEGER | NOT NULL, 索引 | 所属游戏；无 FK |
| sort_order | REAL | NOT NULL, 默认 0 | 展示分数 |
| description | VARCHAR(15) | NOT NULL, 默认 `''` | 描述，上限 15 字 |
| file_path | VARCHAR(500) | NOT NULL, 默认 `''` | 磁盘相对路径；不下发前端 |
| size | INTEGER | NOT NULL, 默认 0 | 字节数 |
| mime | VARCHAR(200) | NULL | 按内容 magic 判定 |
| created_at | DATETIME | NOT NULL | |

- 复合索引：`ix_game_gallery_images_game_order`。
- 与截图相反：按游戏共享，不记上传者。
- 行为见 [`game-assets.md`](specs/game-assets.md)。

**`game_emulator_settings`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 归属用户 |
| game_type | VARCHAR(50) | NOT NULL, 唯一 `(user_id, game_type)` | 平台键 |
| payload | TEXT | NOT NULL, 默认 `''` | `{controlSettings, settings, cheats}` |
| updated_at | DATETIME | NOT NULL | |

- 只覆盖 8 个主机平台，不含 flash/h5。
- 内容只存 SQLite，不落文件。
- 行为见 [`game-saves-stats.md`](specs/game-saves-stats.md)。

**`game_recent_plays`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | 同时间排序兜底 |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 归属用户 |
| game_id | INTEGER | NOT NULL, 索引, 唯一 `(user_id, game_id)` | 所属游戏；无 FK |
| played_at | DATETIME | NOT NULL | 最近一次开玩时间 |

- 每 (用户, 游戏) 一行；重玩只刷新时间。
- 行为见 [`game-saves-stats.md`](specs/game-saves-stats.md)。

**`game_user_stats`**

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK 自增 | |
| user_id | INTEGER | NOT NULL, FK → `users.id`, 索引 | 归属用户 |
| game_id | INTEGER | NOT NULL, 索引, 唯一 `(user_id, game_id)` | 所属游戏；无 FK |
| play_seconds | INTEGER | NOT NULL, 默认 0 | 累计游玩秒数 |
| progress | VARCHAR(20) | NOT NULL, 默认 `not_started` | 未开始 / 进行中 / 已通关 |
| updated_at | DATETIME | NOT NULL | |

- 与游戏类型无关：三类播放都往同一张表累加。
- 心跳、覆盖式改写、进度规则见 [`game-saves-stats.md`](specs/game-saves-stats.md)。

## 文件存储结构

两个根都由 `backend/config.py` 决定：

- 数据根 `STORAGE_ROOT`：本机默认 `<仓库>/data/storage`，容器内 `/data`。
- 运行时根 `RUNTIME_ROOT`：不配时等于数据根，容器内 `/runtime`。

`create_app()` 各建一个 `LocalStorage`：

- `app.state.storage`：数据根。
- `app.state.runtime_storage`：运行时根。

`LocalStorage._resolve()` 负责拼根并挡掉越界：绝对路径与 `..` 一律拒绝。
浏览器从不直连磁盘，上传/下载都由 API 分块流式代理。

根目录下可能有一个 `.mounted`：

- 空文件，**人工创建**，代码不代建。
- 只在宿主路径落在 `WINDOWS_MOUNT_PREFIX`（默认 `/mnt`）下时检查。
- 数据根与运行时根各查一份；两个根相同时就是同一个文件。
- 机制与排障见 [`delivery-docker.md`](specs/delivery-docker.md) 与
  [`DEVELOP.md`](../DEVELOP.md)。

目录名一律用「游戏类型键 + 卡带 ID」，不随游戏名变化。
改卡带 ID 的迁移范围见 [`game-storage.md`](specs/game-storage.md)。

### 路径规则

**数据根**（原始素材）：

| 内容 | 相对路径 | 生成处 |
|---|---|---|
| 游戏本体 | `game/{game_type}/{卡带ID}/game.{后缀}` | `paths.py::body_path` / `h5_zip_path` |
| 游戏封面 | `game/{game_type}/{卡带ID}/cover.{后缀}` | `paths.py::cover_path` |
| 攻略包 | `game/{game_type}/{卡带ID}/guide.zip` | `paths.py::guide_zip_path` |
| 攻略 PDF | `game/{game_type}/{卡带ID}/guide.pdf` | `paths.py::guide_pdf_path` |
| 游戏图集 | `game/{game_type}/{卡带ID}/image/{uuid}.{后缀}` | `paths.py::gallery_file_path` |
| 云端存档 | `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state` | `paths.py::save_file_path` |
| 游戏截图 | `image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}` | `paths.py::screenshot_file_path` |

**运行时根**（派生物，删了会自动重建）：

| 内容 | 相对路径 | 生成处 |
|---|---|---|
| H5 解包资源 | `game/{game_type}/{卡带ID}/h5/{包内路径}` | `paths.py::h5_asset_path` |
| 攻略解包资源 | `game/{game_type}/{卡带ID}/guide/{包内路径}` | `paths.py::guide_asset_path` |
| 解包暂存 | `game/{game_type}/{卡带ID}/.{h5,guide}-{随机}` | `paths.py::h5_temp_dir` / `guide_temp_dir` |

说明：

- **类型目录名**用 `game_type` 的键值，与 SQLite 字段一致。
- **本体 / 封面**路径固定，不随上传文件名变；同名重复上传会覆盖。
- **换本体**只允许同类型；跨类型 400 且旧档不动。
- **H5** 上传只校验不解压；播放时按需解到运行时根。
- **攻略**是 ZIP 或 PDF，二者互斥；`guide_kind` 记录形态。
- **截图**目录带写入当时的类型；读取/删除按行里的 `file_path`，
  绝不用当前类型拼目录。
- **图集**在游戏目录内，随游戏类型迁移。
- **云端存档**目录带快照当时的类型；同样按 `file_path` 反推。
- 具体行为见 [`game-storage.md`](specs/game-storage.md)、
  [`guide-and-h5.md`](specs/guide-and-h5.md)、
  [`game-assets.md`](specs/game-assets.md)、
  [`game-saves-stats.md`](specs/game-saves-stats.md)。

## 游戏发现索引（`game.db`）

外部中英文名录与游戏榜单的只读派生库，与 `app.db` 无外键关系。

| 项 | 值 |
|---|---|
| 路径 | `<数据根>/db/game.db`（`GAME_INDEX_FILENAME`） |
| 写入方 | 只有 `backend/games/search_index.py` |
| 写路径 | `build_index()` 整库重建；`ensure_ranking_loaded()` 就地补榜单 |
| 读取方 | `GameSearchService` / `GameRankingService` |
| 连接 | `mode=ro` + `PRAGMA query_only=1`，每请求一条短连接 |
| 是否备份 | 不备份；可从 CSV 重建 |
| 源数据 | 37 个检索 CSV + `ranking.csv` |
| 重建 | 整库重建 + `os.replace`；不开 WAL |

### 表

| 表 | 用途 |
|---|---|
| `console` | 检索的统一机种：`id` / `name` / `platform_id` / `raw_names` |
| `game` | 名录一行：`id` / `console_id` / `zh` / `en` / `src` |
| `game_fts` | FTS5 全文索引，contentless，`zh_uni` / `en_uni` |
| `ranking` | 榜单一行：`platform` / `console` / `rank` / `title` / `cartridge_ids` |
| `meta` | 键值元信息：检索版本、榜单版本与指纹 |
| `idx_game_console` | `game(console_id, en)` 索引 |
| `idx_console_platform` | `console(platform_id)` 索引 |

### 约定

- 机种经 `backend/games/platforms.py` 的词表归一。
- 检索引擎的机种合并：36 个原始机种 → 32 项。
- `game_fts` 存处理过的文本；`game.zh` / `game.en` 存原文。
- 索引期与查询期共用 `search_text.py::index_text()`。
- 按 `(机种, 中文, 英文)` 三元组去重。
- 榜单版本独立于检索版本；加榜单表不 bump `SCHEMA_VERSION`。
- 榜单与库存的关联在请求期做，不落库、不进索引、不缓存。
- 榜单 CSV 格式见
  [`backend/search/ranking/README.md`](../backend/search/ranking/README.md)。
- 详细行为见 [`game-discover.md`](specs/game-discover.md)。
