# HTTP 端点总表

## 范围与权威

- 本文只列稳定 HTTP 契约，实现细节以 `backend/*/router.py` 为准；业务路径都在 `/api/` 下。
- 服务端不提供 HTML 页面路由，FastAPI 只返回 JSON 或文件流。
- 信封：成功 `{ "ok": true, "data": ... }`；失败 `{ "ok": false, "message": "中文" }`。

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

### 游戏中心、模拟器设置与统计

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/games` | 需登录 | 游戏中心列表，含统计字段与攻略形态 |
| GET | `/api/games/status` | 需登录 | 类型列表与可上传本体扩展名 |
| GET / POST | `/api/games/recent` | 需登录 | 最近游玩；POST body `{game_id}`，`limit` 默认 20 |
| POST | `/api/games/stats/playtime` | 需登录 | body `{game_id, seconds}`，单次收敛到 0..300 |
| PUT | `/api/games/stats/{id}/playtime` | 需登录 | body `{hours}`，覆盖总时长 |
| PUT | `/api/games/stats/{id}/progress` | 需登录 | body `{progress}`：三个固定取值 |
| GET / PUT | `/api/games/emulator-settings` | 需登录 | `game_type` 查询 / body，按平台读写整块设置 |

### 游戏管理与入库

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/games/manage` | 需登录 | 服务端分页：`page` / `page_size` / `game_type` / `q` |
| GET | `/api/games/manage/{id}` | 需登录 | 管理详情，含 CRC32、创建与更新时间 |
| POST | `/api/games/manage` | 需登录 | multipart 新建：`name` / `cartridge_id` / `description` / `file`[+`cover`] |
| POST | `/api/games/manage/import` | 需登录 | 搬运，body `{url}`；卡带 ID 服务端自动生成 |
| PUT | `/api/games/manage/{id}` | 需登录 | 改名 / 描述 / `cover_type` / `clear_cover` |
| PUT | `/api/games/manage/{id}/cartridge-id` | 需登录 | body `{cartridge_id}`，显式迁移磁盘与路径 |
| DELETE | `/api/games/manage/{id}` | 需登录 | 删游戏，连同所有账号的存档与截图 |
| POST | `/api/games/manage/{id}/assets` | 需登录 | `kind=game\|cover`，`file` 或 `url`[+类型字段] |
| POST | `/api/games/manage/{id}/guide` | 需登录 | multipart 单个 `file`，ZIP 或 PDF |
| DELETE | `/api/games/manage/{id}/guide` | 需登录 | 删除攻略，幂等，返回更新后的管理条目 |

### 素材读取

| 方法 | 路径 | 登录 | 用途 / 关键字段 |
|---|---|---|---|
| GET | `/api/games/{id}/cover` | 需登录 | 封面 inline；`?download=1` 转附件 |
| GET / HEAD | `/api/games/{id}/play` | 需登录 | 本体下载；`.swf` 用 Flash 类型，其余 `octet-stream` |
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
| GET | `/api/games/search/ranking` | 需登录 | `?console=` 机种键，整份榜单不分页 |
| GET | `/api/games/search/ranking/consoles` | 需登录 | 榜单机种 `{platform, label, playable}` 与默认机种 |

## 边界与错误

- 未登录访问业务接口：401；写操作缺 `X-CSRFToken`：400。
- 登录连续失败触发锁定：429；用户名或密码错误：401；注册重名：409。
- 游戏 / 快照 / 截图 / 图集不存在或越权：404；参数、类型、文件校验失败：400；索引版本不符：503。
- 索引未构建返回 `indexed:false` 与空列表；榜单未加载返回 `has_ranking:false`，都是 200。
- 请求体超过上限：413；分块传输缺少长度：411（`backend/request_limit.py`）。

## 测试要点

- `/health` 未登录返回 200，其余业务接口未登录返回 401；仅 H5 资源可匿名访问。
- CSRF 白名单与写操作校验；缺 token 的写请求被拒。
- 分页、越界参数、索引缺失与坏库各分支都走统一信封；越权访问一律 404。

## 相关文档

- [账号与会话](./auth.md)
- [游戏存储与入库](./game-storage.md)
- [架构说明](../architecture.md)
- [编码约定](../../AGENTS.md)
