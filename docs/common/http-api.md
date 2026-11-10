# HTTP 端点总表

本文件回答：有哪些 HTTP 端点，登录与错误边界如何。

## 范围与权威

- 本文只列稳定 HTTP 契约，实现细节以 `backend/*/router.py` 为准；业务路径都在 `/api/` 下。
- 服务端不提供 HTML 页面路由，FastAPI 只返回 JSON 或文件流。
- 信封：成功 `{ "ok": true, "data": ... }`；失败 `{ "ok": false, "message": "中文" }`。

## 职责

- 列出稳定的 HTTP 契约与统一响应信封。
- 标明各端点的登录要求与 CSRF 要求。
- 汇总错误状态码与业务边界。

## 关键接口

- 实现分散在 `backend/*/router.py`，由 `backend/__init__.py::create_app()` 注册。
- 响应辅助在 `backend/http.py`；错误类型在 `backend/errors.py`。
- 鉴权依赖在 `backend/deps.py`。

## 依赖

- FastAPI 与 Pydantic。
- session cookie、`CSRFMiddleware` 与 `RequestBodyLimitMiddleware`。
- 各功能模块的 service。

## 行为与规则

- 除下表标「免登录」者外，所有端点都要求 session 登录，未登录返回 401。
- 写操作（非 GET / HEAD / OPTIONS）要带 `X-CSRFToken`。
- CSRF 白名单是 `/health`、`/api/csrf`、`/api/register`、`/api/login`。
- 唯一免登录的业务接口是 H5 资源；攻略资源不在此例外里。

### 健康检查与账号

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/health` | 免登录 | 纯文本 `ok`，不返回 JSON 信封 |
| GET | `/api/csrf` | 免登录 | 取 `csrf_token`，写操作前调用 |
| POST | `/api/register` | 免登录、免 CSRF | body `{username, password}`，成功即登录；重名 409 |
| POST | `/api/login` | 免登录、免 CSRF | body `{username, password}`；失败 401，锁定 429 |
| POST | `/api/logout` | 需登录 | 清 session，返回空对象 |
| GET | `/api/me` | 需登录 | 当前用户 `{username}` |
| GET | `/api/tools` | 需登录 | 功能注册表；前端目前不消费 |

### 用户快捷键

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/user-shortcuts` | 需登录 | 当前账号的覆盖列表 `{overrides: [{action_id, binding}]}` |
| PUT | `/api/user-shortcuts/{action_id}` | 需登录 | body `{binding}`；空串 = 关闭该快捷键 |
| DELETE | `/api/user-shortcuts/{action_id}` | 需登录 | 删除覆盖，恢复默认键位；幂等 |

`binding` 用 `KeyboardEvent.code` 表示主键，修饰键按 `Ctrl` / `Alt` / `Shift` / `Meta` 顺序，
例如 `Ctrl+Shift+KeyS`、`Alt+Backquote`、`Enter`。不支持的键、重复修饰键、
浏览器保留组合（如 `Ctrl+KeyW`）返回 400。动作清单与默认值只在前端维护。

### 游戏中心、模拟器设置与统计

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/games` | 需登录 | 游戏中心列表，含统计字段与攻略形态 |
| GET | `/api/games/status` | 需登录 | 类型元数据、可上传后缀、后缀候选、默认类型、BIOS 规格与上传阈值 |
| GET / POST | `/api/games/recent` | 需登录 | 最近游玩；POST body `{game_id}`，`limit` 默认 20 |
| POST | `/api/games/stats/playtime` | 需登录 | body `{game_id, seconds}`，单次收敛到 0..300 |
| PUT | `/api/games/stats/{id}/playtime` | 需登录 | body `{hours}`，覆盖总时长 |
| PUT | `/api/games/stats/{id}/progress` | 需登录 | body `{progress}`：三个固定取值 |
| GET / PUT | `/api/games/emulator-settings` | 需登录 | `game_type` 查询 / body，按平台读写整块设置 |

`/api/games` 与 `/api/games/recent` 的每条游戏都带 `bios`：无 BIOS 需求时为 `null`，
否则为 `{file, required_files, optional}`；`/api/games/status.types[]` 的每条类型也带同形状字段。
`file` 是 `emulatorjs/bios/` 下的 ZIP 文件名，`required_files` 是包内必需文件。
每条游戏还带 `threads`（布尔）：`true` 表示 PSP / DOS 这类必须开线程的机种。

`/api/games/status.upload` 为 `{single_file_max_bytes, chunk_size_bytes}`：前端据此决定
本体走单文件还是分片，阈值与后端常量一致；分片总数另由 init 响应返回。

`/api/games/status.types[]` 的每条类型另带 `multi_file`、`bundle_extensions`、
`bundle_entries`、`upload_extensions` 与 `threads`：前端据此决定文件框是否多选、accept、
类型候选，以及是否给播放器开线程，不手写机种映射。
`.zip` 的候选是 `h5` / `dos` / `arcade`，`extension_candidates[".zip"]` 会返回三项；
不传 `body_game_type` 时后端仍按历史默认落 `h5`。

### 游戏管理与入库

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/games/manage` | 需登录 | 服务端分页：`page` / `page_size` / `game_type` / `q` |
| GET | `/api/games/manage/{id}` | 需登录 | 管理详情，含 CRC32、创建与更新时间 |
| POST | `/api/games/manage` | 需登录 | multipart 新建：`name` / `cartridge_id` / `description` / 本体四选一（`file`、`body_url`、`upload_id`、`upload_ids`）/ 封面二选一（`cover`、`cover_url`）/ `body_game_type` |
| POST | `/api/games/uploads` | 需登录 | 开分片会话：body `{filename, size, game_type?}`，返回 `{upload_id, chunk_size, total_chunks}` |
| PUT | `/api/games/uploads/{upload_id}/chunks/{index}` | 需登录 | 原始分片字节流，长度必须等于约定值；返回 `{index, size}` |
| POST | `/api/games/uploads/{upload_id}/complete` | 需登录 | 校验分片齐全与总大小，返回 `{upload_id, filename, size}` |
| DELETE | `/api/games/uploads/{upload_id}` | 需登录 | 放弃上传并删除暂存目录；幂等 |
| POST | `/api/games/manage/import` | 需登录 | 搬运，body `{url}`；卡带 ID 服务端自动生成 |
| PUT | `/api/games/manage/{id}` | 需登录 | 改名 / 描述 / `cover_type` / `clear_cover` |
| PUT | `/api/games/manage/{id}/cartridge-id` | 需登录 | body `{cartridge_id}`，显式迁移磁盘与路径 |
| PUT | `/api/games/manage/{id}/game-type` | 需登录 | body `{game_type}`，显式迁移游戏/存档/截图目录 |
| DELETE | `/api/games/manage/{id}` | 需登录 | 删游戏，连同所有账号的存档与截图 |
| POST | `/api/games/manage/{id}/assets` | 需登录 | `kind=game\|cover`，`file` / `url` / `upload_id` / `upload_ids` 四选一[+类型字段] |
| POST | `/api/games/manage/{id}/guide` | 需登录 | multipart 单个 `file`，ZIP 或 PDF |
| DELETE | `/api/games/manage/{id}/guide` | 需登录 | 删除攻略，幂等，返回更新后的管理条目 |

`upload_id` 只能用于 `kind=game`（本体）；封面与攻略不分片。多文件本体用重复的
`upload_ids`（每个物理文件一个现有分片会话），与 `file` / `url` / `upload_id` 互斥。
新建与换本体时 `file` / `url` / `upload_id` / `upload_ids` 只能选一种。
分片会话绑定当前账号，别人的 `upload_id` 一律 404。
`.zip` 的 128MB 应用层上限只约束 H5；DOS 与街机不受。街机只接受本地上传，
`url` 方式返回中文 400（直链临时名无法满足 romset 名）。

### 素材读取

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/games/{id}/cover` | 需登录 | 封面 inline；`?download=1` 转附件 |
| GET / HEAD | `/api/games/{id}/play` | 需登录 | 本体下载；`.swf` 用 Flash 类型，其余 `octet-stream` |
| GET / HEAD | `/api/games/{id}/play/{文件名}` | 需登录 | 同上；文件名段必须是落盘名（如 `game.chd`，街机是 `mslug.zip`），供 EmulatorJS 识别格式 |
| GET / HEAD | `/api/games/{id}/play/manifest` | 需登录 | 多文件本体清单 `{entry, files, total_size}`；单文件也返回入口一条 |
| GET / HEAD | `/api/games/{id}/play/files/{name}` | 需登录 | 多文件本体的单个文件；只服务清单内 basename |
| GET / HEAD | `/api/games/{id}/h5/{资源路径}` | **免登录** | H5 资源；沙箱安全头，首次访问触发解包 |
| GET / HEAD | `/api/games/{id}/guide/{资源路径}` | 需登录 | ZIP 攻略资源；无 CSP sandbox |
| GET / HEAD | `/api/games/{id}/guide.pdf` | 需登录 | PDF 攻略，`application/pdf` inline |

### 云端存档

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET / POST | `/api/games/saves` | 需登录 | 列表 `?game_id=`；创建 multipart 带清单与文件 |
| GET / PUT / DELETE | `/api/games/saves/{id}` | 需登录 | 详情 / 改备注 / 删除；删除时直接子级改回顶层 |
| GET | `/api/games/saves/{id}/files/{file_id}/download` | 需登录 | 取单个 `.sol` / `.state` 文件 |
| PUT | `/api/games/saves/{id}/parent` | 需登录 | body `{parent_id}`；`null` = 顶层 |
| POST | `/api/games/saves/{id}/move` | 需登录 | body `{to_index}`，同级排序，返回整份列表 |

### 游戏截图（按账号隔离）

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET / POST | `/api/games/screenshots` | 需登录 | 列表 `?game_id=`；上传 multipart 带 `file` |
| POST | `/api/games/screenshots/{id}/move` | 需登录 | body `{to_index}`，返回整份有序列表 |
| GET | `/api/games/screenshots/{id}/image` | 需登录 | 截图 inline；越权一律 404 |
| PUT / DELETE | `/api/games/screenshots/{id}` | 需登录 | 改描述（≤15 字）/ 删除 |

### 游戏图集（按游戏共享）

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET / POST | `/api/games/gallery` | 需登录 | 列表 `?game_id=`；上传 multipart 字段同截图 |
| POST | `/api/games/gallery/{id}/move` | 需登录 | body `{to_index}`，返回整份有序列表 |
| GET | `/api/games/gallery/{id}/image` | 需登录 | 图集图片 inline；共享但不匿名开放 |
| PUT / DELETE | `/api/games/gallery/{id}` | 需登录 | 改描述（≤15 字）/ 删除 |

### 游戏发现（检索与榜单）

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/games/search` | 需登录 | `q` / `console_id` / `page` / `page_size`，服务端分页 |
| GET | `/api/games/search/consoles` | 需登录 | 机种下拉 `{id, name, platform_id}`，同名已合并 |
| GET | `/api/games/search/ranking` | 需登录 | `?console=` 机种键，省略则全部机种并按评分全局降序；item 含 `rank`（机种内序号）/ `score` / `zh` / `en` / `platform` |
| GET | `/api/games/search/ranking/consoles` | 需登录 | 榜单机种 `{platform, label, playable}` |

## 边界与错误

- 未登录访问业务接口：401；写操作缺 `X-CSRFToken`：400。
- 登录连续失败触发锁定：429；用户名或密码错误：401；注册重名：409。
- 游戏 / 快照 / 截图 / 图集不存在或越权：404；参数、类型、文件校验失败：400；索引版本不符：503。
- 请求体不符合 Pydantic 模型时也返回中文 400 信封，不返回 FastAPI 原生 422。
- 索引未构建返回 `indexed:false` 与空列表；榜单未加载返回 `has_ranking:false`，都是 200。
- 请求体超过上限：413；分块传输缺少长度：411（`backend/request_limit.py`）。
  例外是分片上传的 `POST /uploads` 完成接口与 `PUT /chunks/{index}`：允许无 `Content-Length`，
  分片长度由会话约定校验。
- 单文件本地本体超过 30MB：400，提示改用分片上传；分片本体不设总大小上限。
- `.cue` / `.m3u` 单文件上传或作为网络直链：400，提示改用多文件本地上传；
  `.bin` 单文件上传也 400，但直链会按所选类型补默认后缀（沿用旧规则）。
- `.zip` 不传 `body_game_type` 时按历史默认落 `h5`；要传 DOS / 街机必须显式指定。
- 街机 romset 文件名非法、不是 `.zip`、占用 `guide.zip`，或使用网络直链：400。
- 多文件本体缺入口、缺引用、引用子目录/远程地址/大小写不一致、重名、超过 64 个文件：400。

## 测试要点

- `/health` 未登录返回 200，其余业务接口未登录返回 401；仅 H5 资源可匿名访问。
- CSRF 白名单与写操作校验；缺 token 的写请求被拒。
- 分页、越界参数、索引缺失与坏库各分支都走统一信封；越权访问一律 404。

## 相关文档

- [账号与会话](../modules/auth.md)
- [游戏存储与入库](../modules/game-storage.md)
- [架构说明](../architecture.md)
- [编码约定](../../AGENTS.md)
