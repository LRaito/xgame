# 架构说明

## 文档定位

本文说明 xgame 的目标架构与设计取舍，是给人读的设计源。

- 编码约定见 [`AGENTS.md`](../AGENTS.md)。
- 数据与文件结构见 [`data_dict.md`](data_dict.md)。
- 功能实现细节见 [`specs/`](specs/README.md)。

读者：仓库主人，以及之后修改代码的 Agent。

## 项目定位

x 是私人游戏平台，不是对外 SaaS。

只做一件事：把 Flash、HTML5 与 8/16/32-bit 主机游戏收进自己的库里，
在浏览器里即开即玩，并让每个账号有独立的模拟器配置与存档。

三块界面：

1. **游戏中心**（`/games`）— 列表 + 播放。
   - Flash 走 Ruffle。
   - 主机 ROM 走 EmulatorJS。
   - H5 走沙箱 iframe。
   - Flash 与主机支持本地存档 + 按账号云端存档。
   - 主机支持截图入库。
2. **游戏管理**（`/games/manage`）— 上传/直链/搬运本体与封面、改元数据、攻略、删除。
3. **游戏发现**（`/games/discover`）— 外部中英文名录的只读全文检索 + 按机种榜单。

界面是 Vue 3 SPA，FastAPI 只提供 JSON API。
开放注册；除注册/登录接口与 H5 资源外，所有页面与接口都要求登录。
账号不做安全机制，只用于隔离模拟器配置与存档。

## 高层架构

```
浏览器
   │  Vue SPA（nginx :443）＋ 播放页（Ruffle / EmulatorJS / sandbox iframe）
   │  页面 → api/* → request.js → /api/*
   ▼
┌─────────────┐   /api/*    ┌──────────────────────────────────────┐
│  web        │ ──────────▶ │  api（Gunicorn + uvicorn）            │
│  nginx      │             │  router 只返回 JSON                   │
│  静态 dist  │             │  auth/games 的 service                │
└─────────────┘             │  storage/access 跨模块流式下载通道    │
                            └──────────┬───────────┬───────────────┘
                                       ▼           ▼
                     运行时根（RUNTIME_ROOT）   数据根（STORAGE_ROOT）
                     db/app.db + 解包产物        原始素材
```

- 浏览器只和 nginx 通信。
- Router 不直接访问 SQLite 或磁盘；领域逻辑在 service，I/O 在适配器。
- 原始素材落在数据根；SQLite 里存相对根目录的路径。
- SQLite 库与 H5/攻略的解包产物放在运行时根；解包产物可随时删除重建。
- 上传/下载都由 API 分块流式代理，浏览器不直连磁盘。

## 技术栈

| 层 | 技术 | 原因 |
|---|---|---|
| Web 界面 | Vue 3 + Vite + Pinia + Element Plus | 独立 SPA；无 i18n / 无 TypeScript |
| 播放运行 | Ruffle + EmulatorJS + Service Worker | 浏览器内即开即玩 |
| API | FastAPI + Pydantic | 应用工厂、类型校验 |
| ORM | SQLModel + SQLite | 模型与校验统一 |
| 应用服务器 | Gunicorn（uvicorn worker）+ nginx | API 跑 ASGI，web 托管静态并反代 |
| 语言 | Python 3.12 / JavaScript | 后端类型支持好；前端不加 TypeScript |
| 账号 | werkzeug 哈希 + 登录失败锁定 | 账号只隔离配置与存档 |
| 文件存储 | 宿主目录 + `LocalStorage` | 目录结构即业务结构，便于直接备份 |
| 配置 | Pydantic Settings | 三个 `.env` 键，其余写死 |
| 运行 | Docker Compose（web + api） | 一条命令启动 |

不引入 React、Celery、Redis、PostgreSQL、MinIO/对象存储，除非后续功能明确需要。

## 分层规则

| 层 | 位置 | 可以引用 | 禁止引用 |
|---|---|---|---|
| 表现层 | `*/router.py` | services、Pydantic 请求体、deps、`storage/access` | 直接访问 SQLite / 文件系统 |
| 应用层 | `*/service.py` | models、paths、存储协议 | FastAPI `Request` / `session` |
| 适配器 | `*/models.py`、`storage/local.py` | SQLAlchemy、标准库 | router |

`service.py` 是拆分边界：以后加微服务时，其公开方法就是 HTTP API。
跨模块的流式下载收敛在 `backend/storage/access.py`。

## 项目结构

完整目录约定见 [`AGENTS.md`](../AGENTS.md) 的「目录约定」，这里只列宏观分区。

```
frontend/     Vue 3 SPA：views / api / components / utils / router
backend/      FastAPI：auth / games / tools / storage
tests/        pytest
docs/         architecture / data_dict / specs
packaging/    Windows 解压即用包
certs/        自签名证书
scripts/      版本号与证书脚本
```

- `create_app()` 是唯一入口。
- 一个功能一块：`router.py` + `service.py`。
- 游戏相关代码集中在 `backend/games/`。
- 跨模块存储与下载在 `backend/storage/`。
- 各功能细节见 [`specs/`](specs/README.md)。

## 关键设计决策

### 决策 1：Vue SPA + FastAPI JSON

- **决定：** 界面用 Vue 3 SPA，FastAPI 只提供 `/api/` JSON。
- **原因：** 组件可复用、前端可独立迭代；session cookie 比 localStorage token 安全。
- **何时重评：** 需要实时推送时再考虑 WebSocket，而不是改认证方式。

### 决策 2：功能模块一套 router + service

- **决定：** 每个功能一块（`router.py` + `service.py` + 按需 models）。
- **原因：** 模块彼此隔离；以后拆微服务只需换 service 实现。
- **何时重评：** 多个模块共享很大领域模型时再抽 `backend/domain/`。

### 决策 3：SQLModel 作为 ORM

- **决定：** 表模型、配置、请求体都用 Pydantic 生态。
- **原因：** 与 FastAPI 同一套类型系统。
- **何时重评：** ORM 需求超出 SQLModel 表达力时，在 adapter 层用 SQLAlchemy Core。

### 决策 4：不使用 docker 具名卷，数据全落宿主目录

- **决定：** 数据根与运行时根都是宿主目录。
  - 数据根放游戏文件、检索索引与备份。
  - 运行时根放 SQLite 库与 H5/攻略解包产物。
- **原因：** 数据要能直接拿到，备份/迁移/排查都是普通文件操作。
- **为什么库单独放：** 库一直被写，网盘客户端拷不动；数据目录则要能整体备份。
- **代价：** 宿主 bind 有时序要求，`/mnt` 盘上缺 `.mounted` 会拒绝启动。
- **细节：** 见 [`delivery-docker.md`](specs/delivery-docker.md) 与
  [`DEVELOP.md`](../DEVELOP.md) 的「根目录哨兵（操作）」。

### 决策 5：账号只做隔离，不做安全机制

- **决定：** 开放注册，只填用户名与密码；无邮箱、验证码、找回密码、OAuth。
- **原因：** 只用于隔离配置与存档，不承载敏感数据。
- **用户名收窄字符集：** 它会被直接当成存档目录名。
- **何时重评：** 真要放敏感数据时，先补多因子与权限模型。

### 决策 6：H5 游戏以 ZIP 上传并用沙箱隔离

- **决定：** H5 本体是 `.zip`，上传只校验不解压；播放时解到运行时根。
  播放用嵌套 sandbox iframe，资源响应带 CSP `sandbox`（不含 `allow-same-origin`）。
- **原因：** H5 是第三方 HTML/JS；不透明源让它读不到 cookie/DOM、无法调 `/api`。
- **代价：** 沙箱下 `localStorage` / IndexedDB / Worker 不可用；H5 不接云存档。
- **何时重评：** 大量 H5 依赖浏览器存储时，改为独立源承载。
- **细节：** 见 [`guide-and-h5.md`](specs/guide-and-h5.md)。

### 决策 7：文件存储走「相对路径 + 本地目录」，保留流式协议

- **决定：** `StorageBackend` 协议只含 `upload` / `delete` / `stat` / `open_download`；
  唯一实现是 `LocalStorage`；目录级操作用 `remove_tree` / `replace_tree` / `move`。
- **原因：** SQLite 只存相对路径，换盘只改环境变量；分层上 service 不知道根在哪。
- **代价：** 磁盘没有元数据，读取时按后缀猜 MIME。
- **何时重评：** 需要多机共享或对象存储语义时再换实现。
- **细节：** 见 [`game-storage.md`](specs/game-storage.md)。

### 决策 8：全部页面与接口需登录（H5 资源接口除外）

- **决定：** 不做游客模式；前端路由经 `permission.js`，后端接口依赖 `CurrentUser`。
- **唯一例外：** H5 资源 `GET /api/games/{id}/h5/{路径}`。
- **原因：** H5 在沙箱不透明源里，`SameSite=Lax` cookie 带不上，加登录只会让资源加载失败。
- **攻略不在例外里：** 它是新标签页顶层导航的同源页面，照常带 cookie。
- **何时重评：** 要严格鉴权 H5 时，改承载方式，而不是给资源接口加登录。
- **细节：** 见 [`auth.md`](specs/auth.md)。

### 决策 9：云端存档按整体快照

- **决定：** 把某 (用户, 游戏) 此刻全部本地存档上传成一个不可变快照。
- **原因：** 存档是回滚点，快照保证还原一致性。
- **边界：** 快照之间是同一 (用户, 游戏) 内的父子森林，不是通用 DAG。
- **细节：** 见 [`game-saves-stats.md`](specs/game-saves-stats.md)。

### 决策 10：卡带 ID 是游戏身份，改名走显式迁移

- **决定：** 每盘游戏有全局唯一的卡带 ID；目录名用它而不是数据库 id 或游戏名。
- **原因：** 游戏名会改；卡带 ID 可读、稳定，改游戏名不挪文件。
- **代价：** 改名要搬三类目录、改写五处路径列，做成独立接口便于回滚。
- **细节：** 见 [`game-storage.md`](specs/game-storage.md)。

### 决策 11：模拟器设置按平台随账号同步

- **决定：** 设置按 (用户, 平台) 各存一套，整块 JSON 存 SQLite。
- **原因：** 引擎只在启动时读一次设置，必须在拉起 iframe 前写回。
- **代价：** 按平台存，同平台不同游戏互相覆盖；忘记点「保存配置」只留在本机。
- **细节：** 见 [`game-saves-stats.md`](specs/game-saves-stats.md)。

### 决策 12：游戏截图按账号隔离，封面全站共享

- **决定：** 截图元数据按 (用户, 游戏) 存，字节按账号目录落盘。
- **图集不同：** 按游戏共享，存在游戏目录内。
- **原因：** 截图是「我的游玩记录」；封面与图集是「这盘卡带长什么样」。
- **细节：** 见 [`game-assets.md`](specs/game-assets.md)。

### 决策 13：游戏发现是独立只读派生库

- **决定：** 检索与榜单落在 `<数据根>/db/game.db`，与 `app.db` 无外键。
- **写入：** 只有 `search_index.py`；整库重建 + `os.replace` 原子替换。
- **运行期：** 只读连接，每请求一条短连接；不参与备份。
- **原因：** 数据可从 CSV 重建，不该混进业务库。
- **细节：** 见 [`game-discover.md`](specs/game-discover.md)。

### 决策 14：H5 与 ZIP 攻略只上传 zip，按需解到运行时根

- **决定：** 上传只校验；首次播放/查看时解到运行时根，入口在就不再解。
- **PDF 攻略：** 原样存数据根，不解包。
- **原因：** 解包产物是派生物，放进数据根会让备份体积膨胀。
- **代价：** 首次访问多一次解压；解包锁要求 Gunicorn 单进程。
- **细节：** 见 [`guide-and-h5.md`](specs/guide-and-h5.md)。

## 模块依赖

```
frontend views / api/*
        ↓
  routers（tools、auth、games、games/saves、games/screenshots、games/settings、games/stats）
        ↓
     services（auth/game/cloud-save/screenshot/emulator-settings/game-stats …）
        ↓
   adapters（models、storage/local、paths、games/archive、games/runtime_assets）
        ↓
   config / database / deps / http / errors
```

规则：

1. 下层永不引用 FastAPI 请求上下文（`deps.py` 只做装配）。
2. 模块间不互相引用对方的 router；跨模块下载由 `backend/storage/` 提供。
3. 禁止循环引用；`service.py` 的依赖以参数传入。

## 数据流

### 账号

- 登录页调 `POST /api/register` 或 `/api/login`，成功后拿到 session cookie。
- 前端再取 `GET /api/csrf`，写操作带 `X-CSRFToken`。
- 所有页面经 `permission.js`，所有业务接口经 `CurrentUser`。
- 细节见 [`auth.md`](specs/auth.md)。

### 游戏入库与播放

- 管理页上传/直链/搬运 → 服务端写入数据根 → SQLite 落一条 `games` 行。
- 游戏中心列表读 SQLite，按类型给出播放路径。
- 播放页按类型分派：Flash/Ruffle、H5/sandbox iframe、主机/EmulatorJS。
- 细节见 [`game-storage.md`](specs/game-storage.md) 与
  [`game-center-playback.md`](specs/game-center-playback.md)。

### 存档与统计

- 播放页把本地存档整体上传成云端快照；快照按 (用户, 游戏) 隔离。
- 模拟器设置按平台随账号同步；游玩时长每 30 秒心跳累加。
- 进度只由用户手动设置，不随游玩自动变化。
- 细节见 [`game-saves-stats.md`](specs/game-saves-stats.md)。

### 游戏发现

- 37 个名录 CSV + 1 个榜单 CSV 构建成只读库 `game.db`。
- 检索走 FTS5；榜单在请求期按卡带 ID 关联库存。
- 细节见 [`game-discover.md`](specs/game-discover.md)。

### 交付

- Docker：web + api 两服务，两个宿主目录 bind 进容器。
- Windows：后端托管前端 dist，单进程 uvicorn，http。
- 细节见 [`delivery-docker.md`](specs/delivery-docker.md) 与
  [`delivery-windows.md`](specs/delivery-windows.md)。

## 数据模型

- 业务库 `app.db`：auth 2 表 + games 8 表，共 10 张。
- 文件路径规则：数据根 7 类 + 运行时根 3 类。
- 表结构、列定义、索引与路径规则见 [`data_dict.md`](data_dict.md)。
- 模型定义在 `backend/games/models.py` / `backend/auth/models.py`，
  路径规则在 `backend/games/paths.py`。

## HTTP 表面

JSON 一律在 `/api/` 下。信封：

- 成功：`{ "ok": true, "data": ... }`
- 失败：`{ "ok": false, "message": "中文" }`

| 前缀 | 说明 |
|---|---|
| `/health` | 免登录纯文本 `ok` |
| `/api/csrf` | 取 CSRF token |
| `/api/register` `/api/login` `/api/logout` `/api/me` | 账号 |
| `/api/tools` | 工具注册表（前端目前不消费） |
| `/api/games` | 列表、状态、管理、封面、本体、H5、攻略 |
| `/api/games/saves` | 云端存档快照与父子层级 |
| `/api/games/screenshots` | 截图（按账号隔离） |
| `/api/games/gallery` | 图集（按游戏共享） |
| `/api/games/emulator-settings` | 模拟器设置 |
| `/api/games/stats` | 游玩时长与进度 |
| `/api/games/recent` | 最近游玩 |
| `/api/games/search` | 游戏检索与榜单 |

完整端点表见 [`specs/api.md`](specs/api.md)。

## 安全架构

- 只支持 HTTPS；80 端口不发布。对外端口由 `WEB_HTTPS_PORT` 决定。
- session cookie：HttpOnly、SameSite=Lax、HTTPS 下 Secure。
- 写操作（除 register/login/csrf/health）校验 `X-CSRFToken`。
- 免登录面只有注册/登录、`/health` 与 H5 资源；攻略资源需登录。
- H5 内容按不可信处理：CSP `sandbox` + `nosniff` + `Referrer-Policy: no-referrer`。
- 上传有大小上限与后缀白名单；ZIP 另有条目数、总量、压缩比、加密条目校验。
- 所有落盘路径经 `LocalStorage._resolve()`，拒绝绝对路径与 `..`。
- 搬运只接受白名单站点域名，避免被当作任意 URL 代理。

## 运行架构

```
docker compose
├── api    # entrypoint.sh → 哨兵检查 → Gunicorn + uvicorn :8910（仅内部）
│   ├── ${STORAGE_HOST_DIR} → /data
│   └── ${RUNTIME_HOST_DIR} → /runtime
└── web    # nginx :443，托管 SPA 并反代 /api
    └── certs/ → /etc/nginx/certs（只读）
```

- 不用任何 docker 具名卷。
- 证书随仓库提交，`make certs` 可重新生成。
- SQLite 滚动备份：启动一次 + 每小时一次，当月一份，整份重写。
- 数据根可整体拷走；运行时根不备份，解包产物自动重建。

开发与 Docker 的差异、备份细节见 [`DEVELOP.md`](../DEVELOP.md) 与
[`delivery-docker.md`](specs/delivery-docker.md)。

## 配置

配置写死在 `backend/config.py`。`.env` 只有三个键，且只给 docker compose 读：

| 变量 | 默认 | 用途 |
|---|---|---|
| `STORAGE_HOST_DIR` | `./data/storage` | 宿主侧数据根 |
| `RUNTIME_HOST_DIR` | `./data/runtime` | 宿主侧运行时根；留空则同数据根 |
| `WEB_HTTPS_PORT` | `443` | 对外 HTTPS 端口 |

不建 `.env` 时 compose 把两个根都退回 `./data/storage`；
`.env.example` 才给出分开的默认值（`./data/runtime`）。

代码内固定：`SECRET_KEY`、两个根路径、`WINDOWS_MOUNT_PREFIX`、
SQLite 路径、备份间隔、证书路径、session cookie 策略。

## 性能

v1 单用户。不要在应用内加缓存、队列或 CDN。

- 列表来自 SQLite；文件按相对路径直接读。
- 上传/下载分块流式，不把文件整读进内存。
- SQLite 单文件 + Gunicorn `--workers 1 --threads 8`。

## 测试策略

```bash
make test        # pytest + 前端 lint
python -m pytest # 只跑后端
```

- 实现过程中只跑改动涉及的用例；全量测试由用户定期执行。
- 只改文档不跑测试。
- 覆盖重点：账号、存储、入库、卡带 ID、H5/攻略、存档、截图/图集、
  设置、统计、检索/榜单、静态站、请求上限、Windows 启动器。
- 每个功能的测试要点见对应 [`specs/*.md`](specs/README.md) 的「测试要点」。

## 排障索引

| 症状 | 先看 |
|---|---|
| `/mnt` 盘上数据像是空的、api 反复重启 | [`DEVELOP.md`](../DEVELOP.md) 的「排障」 |
| 登录被锁定 | [`auth.md`](specs/auth.md) |
| 卡带 ID 被占用 | [`game-storage.md`](specs/game-storage.md) |
| H5 资源 404 | [`guide-and-h5.md`](specs/guide-and-h5.md) |
| 页面还是旧版 | [`DEVELOP.md`](../DEVELOP.md) 的「排障」 |
| 索引构建失败 / 榜单没加载 | [`game-discover.md`](specs/game-discover.md) |
| Windows 包被系统拦截 | [`packaging/windows/说明.txt`](../packaging/windows/说明.txt) |

## 相关资源

- [`AGENTS.md`](../AGENTS.md) — 编码约定
- [`data_dict.md`](data_dict.md) — SQLite 表与文件路径
- [`specs/README.md`](specs/README.md) — 功能规格索引
- [FastAPI](https://fastapi.tiangolo.com/) / [SQLModel](https://sqlmodel.tiangolo.com/)
- [Ruffle](https://ruffle.rs/) / [EmulatorJS](https://emulatorjs.org/)
