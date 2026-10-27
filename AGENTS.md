# AGENTS.md

本仓库中编码 Agent 必须遵守的约定。

本仓库是**个人自托管游戏平台**。人读 `docs/architecture.md`。写代码、改代码时以**本文件**为准。

## 当前状态

前后端分离已落地：Vue 3 SPA + FastAPI JSON API。只做游戏：游戏中心（Flash + HTML5 + 8/16-bit 主机 ROM，浏览器内 Ruffle/EmulatorJS/沙箱 iframe 游玩，Flash 与模拟器都支持按账号云端存档，H5 仅游玩）、游戏管理与游戏发现（外部中英文名录的只读全文检索 + 按机种的游戏榜单）。SQLite 与文件存储结构以 `docs/data_dict.md` 为 schema 权威。实现时以本文件「目标约定」为准。

两条交付路线并存：Docker（正式运行，nginx + gunicorn + HTTPS）与「解压即用」的 Windows 包
（`packaging/windows/`，后端自己托管前端 + 单进程 uvicorn + http，见下面那一节）。

若用户请求会违反本文件（不做 Docker、用 React 替换已选定的 Vue、把游戏文件整读进内存再中转），先停下来说明冲突，再写代码。

---

# 目标约定

## 语言（默认中文）

项目默认使用**中文**。后续生成代码、文档、注释、提交说明时都按中文处理，不要无故改回英文。

必须用中文：

- 界面文案（导航、按钮、表单标签、占位符、空状态、错误提示、设置页说明）
- Markdown 文档（`README.md`、`docs/`、注释型说明）
- `.env.example` 里的注释
- 用户可见的校验失败信息（含 API `message`）
- 给用户看的 CLI 帮助与提示

可以保留英文：

- 代码标识符（模块名、函数名、类名、变量名、路由 path、环境变量名、表名、列名）
- 第三方库名与官方术语（FastAPI、SQLModel、Pydantic、Vue、Vite、Pinia、Element Plus、SQLite、Gunicorn、uvicorn、nginx）
- 日志里的稳定机器字段名（message 本身仍用中文）

不要做：不要加 i18n / gettext / 多语言切换，除非用户明确要求。只做中文。

## 产品

**名称：** x
**使用者：** 仅本人与受邀的访客，自托管
**功能：** 游戏中心（Flash 用 Ruffle、HTML5 用沙箱 iframe、8/16-bit 主机 ROM 用 EmulatorJS 浏览器内游玩；Flash/模拟器含按账号的云端存档）+ 游戏管理（上传/网络直链/搬运、卡带ID 与元数据）
**账号：** 开放注册（账号 + 密码），仅用于隔离各人的模拟器配置与存档
**界面：** Vue 3 SPA（`frontend/`），纯前端，不承载服务端能力
**API：** FastAPI JSON（`backend/`），`create_app()` 工厂
**运行：** Docker Compose：`web`（nginx 托管 SPA）+ `api`（Gunicorn + uvicorn worker）。浏览器打开 `https://localhost`
**数据：** SQLite（业务库 `app.db` + 只读的发现页索引 `game.db`：检索名录 + 游戏榜单）+ 文件根目录的路径规则见 `docs/data_dict.md`；库单独放在另一个宿主目录（运行时根，默认 `./data/runtime`）

## 明确不做

- React；前端只 Vue 3 + Vite
- 照搬参考项目的 Vue 2 / Webpack 4 / 飞书 OAuth / 权限 ID / WebSocket / echarts / 表格列自定义（本仓库单用户用不上）
- Compose 里加 PostgreSQL、Redis、Celery（Nginx 仅用于托管 SPA 与反代 `/api`）
- OAuth、邮箱/验证码、找回密码（账号只做隔离，不做安全机制）
- 对象存储（MinIO / S3 之类）与任何外部依赖的服务；游戏文件就是宿主目录里的普通文件
- JWT / token 写入 `localStorage`（登录态用 HttpOnly session cookie）
- 上传/下载时把整个文件整读进内存再中转（应分块流式，浏览器不直连磁盘）
- 把密钥写进 git、前端源码、模板或日志

## 技术栈（锁定）

**后端**

- Python 3.12
- FastAPI + 应用工厂 `create_app()`
- SQLModel（Pydantic + SQLAlchemy）+ SQLite
- Starlette SessionMiddleware（session cookie）+ CSRF（请求头 `X-CSRFToken`）
- Docker 内用 Gunicorn + uvicorn worker
- Pydantic Settings（`backend/config.py`）
- 标准库文件 I/O（`backend/storage/local.py`，无对象存储 SDK）
- `requests`（游戏搬运的服务端出站抓取）
- pytest
- `requirements.txt`（钉死版本）

**前端**

- Vue 3（Options API 或 Composition API 均可；新页面优先 Composition）
- Vite
- vue-router 4
- Pinia
- Element Plus（Dialog 默认关闭「点击遮罩关闭」）
- axios（唯一实例在 `frontend/src/utils/request.js`）
- JavaScript（不加 TypeScript，除非用户明确要求）
- `package.json` 钉死版本
- 无 i18n

前端框架层对齐 iot-op-platform 的分层，而不是它的旧依赖版本。

## 目录（只建这些，不要多余目录）

```
frontend/                    # Vue SPA
  src/main.js                # 入口：Pinia、router、Element Plus、permission
  src/App.vue
  src/permission.js          # 路由守卫（登录态）
  src/router/index.js        # 唯一路由表；菜单由 meta 驱动
  src/layout/                # 侧栏 + 顶栏 + 内容区
  src/store/                 # Pinia：app / auth
  src/api/                   # 按业务域；导出 xxxAPI
  src/utils/request.js       # axios 实例 + 拦截器
  src/utils/auth.js          # 非敏感用户信息缓存 + 登出清理清单
  src/views/                 # login / games（index、manage、discover、flash-player、emulator-player、h5-player）
  src/components/common/     # 跨工具复用（必须有）：AppDialog、AppButton、AppSegmented、分页、空状态、复制等
  src/components/games/      # 游戏专用：GameShell、GameCover(游戏中心卡片的封面渲染：Flash 光盘/GB-GBC 卡带/普通封面)、
                             #   FlashPlayer、SaveManager(本地+云端一套)、SaveManagerDialog、CloudSavePanel、SaveTreeView、
                             #   GameScreenshotGallery(详情图片栏)、ScreenshotManagerDialog、ScreenshotConfirmDialog、
                             #   GalleryManagerDialog/ImageAlbumDialog(相册式弹框，截图与图集共用)
  src/utils/                 # request / auth / gameSaves(Flash) / emulatorSaves(模拟器本地档) / emulatorSettings(模拟器设置) / gamePlaytime(游玩计时) / gameAssetCache(封面/本体 SW 缓存) …
  src/components/<tool>/     # 仅某工具用的组件，有了再加
  src/styles/
  package.json
  scripts/                   # copy-ruffle.mjs、fetch-emulatorjs.mjs（构建期拉取 EmulatorJS 引擎资产）
  vite.config.js
  nginx.conf.template
  Dockerfile
  public/game-asset-sw.js    # Flash 播放页资源缓存 SW（按 key+updated_at）
  public/emulator-host.html  # EmulatorJS 播放宿主（iframe 隔离；__ejsRpc：capture/load/screenshot/videoInfo/fastForward/setFastForward）
  public/emulatorjs/         # EmulatorJS 引擎资产（构建生成，gitignore）
backend/__init__.py          # create_app()；装配 app.state 存储后端/mailer，注册 router
backend/asgi.py              # 生产 ASGI 入口
backend/config.py            # 配置（全部写死在这里，含 SECRET_KEY）
backend/database.py          # engine、init_db、SQLite 路径解析
backend/backup.py            # SQLite 滚动备份（启动一次 + 每小时一次，当月一份、整份重写，不做还原）
backend/mount_guard.py       # 启动前的根目录哨兵检查（数据根与运行时根在 Windows 盘挂载前缀下时才查：缺 .mounted 就打日志、等 5 秒、退出）
backend/deps.py              # 依赖注入：session、登录态、各 service 依赖
backend/csrf.py              # CSRF 中间件
backend/cli.py               # init-db / index（构建游戏检索索引与游戏榜单；--skip-ranking 只重建检索）/ serve（本机直跑生产形态，可选托管前端）
backend/static_site.py       # 可选：后端托管前端 dist（只有 Windows 包设 STATIC_DIR 时生效，行为对齐 nginx.conf.template）
backend/request_limit.py     # 请求体上限中间件（顶替 nginx 的 client_max_body_size）
backend/entrypoint.sh        # api 容器的 ENTRYPOINT：先过哨兵检查，再 exec CMD 里的 gunicorn
backend/Dockerfile           # api 镜像（ENV STORAGE_ROOT=/data + ENV RUNTIME_ROOT=/runtime + ENTRYPOINT entrypoint.sh + gunicorn）
backend/auth/                # 注册/登录/退出（密码 + 失败锁定）
backend/tools/registry.py    # 功能列表（给 /api/tools）
backend/games/               # 游戏 router/service/paths + 机种词表 platforms + 云端存档 save_* + 游戏截图 screenshot_* + 游戏图集 gallery_* + 模拟器设置 settings_* + 游玩统计 stats_* + 发现页 search_*(text/index/service/router) 与 ranking_*(service/router) + 搬运 importer + 网络上传 remote
backend/search/csv/          # 游戏检索的 37 个中英文名录 CSV（纯数据目录，只被建索引读；随 backend/ 进 api 镜像）
backend/search/ranking/      # 游戏榜单的 ranking.csv（四列：序号/机种名称/游戏名称/游戏卡带ID；纯数据目录，只被建索引读）
backend/storage/             # 跨模块：types(协议与 StoredObject) / local(LocalStorage) / access(流式下载响应)
packaging/windows/           # 「解压即用」Windows 包：Dockerfile.build（构建环境镜像，预置运行时/轮子/前端依赖/引擎资产）
                             #   + build-in-docker.sh（make win 入口）+ build-win-dist.sh（组装）
                             #   + runtime.env（Windows 版 CPython 钉版）+ fetch-runtime.sh（下载+校验）
                             #   + launcher.py（启动器）+ winops.py（外壳操作）
                             #   + allow-lan.ps1/允许局域网访问.bat + 启动游戏平台.cmd
                             #   + smoke_win.py（自检）+ make_zip.py（打包，UTF-8 文件名）+ requirements-win.txt
                             #   + 说明.txt + README.md
                             #   + xgame.png（快捷方式图标的源图，随仓库提交；换图标 = 替换它再跑 make_icon.py 生成 xgame.ico）
tests/                       # pytest（test_auth / test_backup / test_mount_guard / test_local_storage / test_platforms / games / game_saves / game_screenshots / game_emulator_settings / game_recent / game_stats / game_search / game_ranking / static_site / request_limit / win_launcher）
docker-compose.yml           # web + api（宿主目录 bind：STORAGE_HOST_DIR → /data、RUNTIME_HOST_DIR → /runtime）
requirements.txt
.env.example
.gitignore
```

不要再加 Jinja2 模板或 `backend/static/`。

`data/` 只放本地运行时的 SQLite 与默认的文件根目录，加入 gitignore。

**本项目不使用任何 docker 具名卷**：compose 里 **数据是两个宿主目录**——数据根 `STORAGE_HOST_DIR`（默认 `./data/storage` → 容器 `/data`，后端读 `STORAGE_ROOT`）装游戏文件、检索索引与备份；运行时根 `RUNTIME_HOST_DIR`（默认 `./data/runtime` → 容器 `/runtime`，后端读 `RUNTIME_ROOT`）装 SQLite 库（固定是 `<运行时根>/db/app.db`，见配置项 `DB_SUBDIR`）与 H5/攻略的**解包产物**（派生物，删掉会自动重建）。库单独放是为了让数据根整个能交给网盘备份（外部客户端拷不动一个一直被写着的库文件）；`.env` 里那行留空则退回与数据根同一个目录。**证书**是仓库里的 `certs/`（`cert.pem` / `cert.key`，随仓库提交），compose 只读挂给 web 的 `/etc/nginx/certs`。**不要新增 `volumes:` 具名卷**。**注意宿主 bind 的时序要求**（源目录必须在 docker 启动前可达，否则会被挂成空 tmpfs），见 `docker-compose.yml` 末尾注释与 `docs/architecture.md` 的「排障」。

## 架构规则（必须遵守）

1. **应用工厂。** 对外入口是 `create_app()`；生产 ASGI 入口为 `backend/asgi.py` 的 `app`。
2. **一个工具一个包。** `router.py` 管 HTTP（只返回 JSON）；`service.py` 管领域逻辑。SQLModel、文件读写、加密不要写进 router。
3. **service 是以后拆微服务的边界。** `service.py` 里禁止使用 FastAPI `Request` / `session`；存储后端等依赖一律由构造函数传入。
4. **前端分层。** 页面(view) → `api/*`（`xxxAPI`）→ `request.js` → FastAPI。新增接口只改 api 层和后端 router，不碰 `request.js`。
5. **通用组件。** 自定义风格的弹窗、按钮、筛选、空状态放 `frontend/src/components/common/`，页面不要复制一份。只被一个工具用的放 `components/<tool>/`。带路由的页面只放 `views/`。
6. **导航由路由表驱动。** 侧栏菜单由 `router` 的 `meta.title` 运行时生成（顺序即 `children` 声明顺序），不要在页面里写死链接。`backend/tools/registry.py` 与 `GET /api/tools` 仍在，但自首页改为游戏中心后暂无前端使用方。
7. **配置写死在代码里。** 全部配置在 `backend/config.py`（含 `SECRET_KEY`、`SESSION_COOKIE_*`、`DB_SUBDIR` / `DB_FILENAME`、`BACKUP_INTERVAL_SECONDS`、`WINDOWS_MOUNT_PREFIX`）与 `backend/Dockerfile` 的 `ENV STORAGE_ROOT=/data` / `ENV RUNTIME_ROOT=/runtime`。`.env` 只剩 `STORAGE_HOST_DIR`、`RUNTIME_HOST_DIR` 与 `WEB_HTTPS_PORT` 三个键，都**只给 docker compose 读，后端不读 `.env` 文件**——加配置项一律进 `config.py`，不要新增 `.env` 键。唯一例外是那两个 `*_HOST_DIR`：compose 把它们作为**环境变量**传进 api 容器，后端只拿它们做启动时的哨兵前缀判断（容器里看不出宿主路径，见 `backend/mount_guard.py`），业务代码不碰它们。文件根目录（`STORAGE_ROOT`）不存在时 `LocalStorage` 会自己建出来，没有「未配置」状态——**存储永远可用，不要复活 `configured` 这类开关**。唯一会拦住启动的是根目录哨兵 `.mounted`，且**只在那个根的宿主路径落在 Windows 盘挂载前缀下时**才要求（数据根与运行时根各查一份，见下面「宿主目录 bind 的时序要求」）：它**不是**配置开关，只拦启动、不表示存储不可用，也绝不代建。
8. **SQLite 路径。** 写死为 `<运行时根>/db/app.db`（`backend/config.py` 的 `DB_SUBDIR` / `DB_FILENAME`，运行时根不配就是数据根），**没有 `DATABASE_URL` 可配**；启动时确保该目录存在。备份写在**数据根**的 `db/` 里（`Settings.backup_dir`），不要让它跟着库走——它得留在会被外部备份的那个根里。
9. **Gunicorn + SQLite：** `gunicorn backend.asgi:app -k uvicorn.workers.UvicornWorker --workers 1 --threads 8`。必须单进程以免 SQLite 写冲突；多线程用于并发处理 keep-alive 连接。

数据 schema（SQLite 表 + 文件路径规则）见 `docs/data_dict.md`；设计取舍见 `docs/architecture.md`。

## 功能：账号（开放注册 + 登录）

除 `/health`、`/api/csrf`、`/api/register`、`/api/login`、H5 资源 `GET /api/games/{id}/h5/{资源路径}` 外，所有 **API** 都要登录。SPA 路由除 `/login` 外由 `permission.js` 拦。

- **开放注册。** `POST /api/register`（免登录、免 CSRF）只收用户名与密码，建号即登录。界面在登录页的「登录 / 注册」切换里。**没有命令行建号**（`backend/cli.py` 只有 `init-db`），也不做邮箱/验证码/找回密码
- `users` 表：用户名 + werkzeug `password_hash`。用户名规则 `^[0-9A-Za-z_-]{2,32}$`（`backend/auth/models.py` 的 `USERNAME_PATTERN`，大小写敏感），密码 6–64 字符；校验入口 `backend/auth/service.py` 的 `validate_username()` / `validate_password()`。**用户名会被直接当成存档目录名**（`save/{用户名}/…`），字符集收窄就是为了不必再考虑转义——改规则时必须同时保证它仍是文件名安全的
- **失败锁定。** 同一 username 连续失败 ≥3 次锁 5 分钟、≥6 次锁到当天 UTC 结束（`login_attempts`，成功即删行）
- Session cookie：HttpOnly、SameSite=Lax；axios `withCredentials: true`；签名密钥是 `backend/config.py` 里写死的 `SECRET_KEY`。**不要 Redis/JWT，不要搞多因子**
- CSRF：`GET /api/csrf`，之后写操作带 `X-CSRFToken`；`/api/register`、`/api/login`、`/api/csrf`、`/health` 在白名单里（登录页此时还没拿到 token）
- 登录态**不要**放进 `localStorage` 当 token；401：拦截器单飞清本地非敏感缓存，跳 `/login`
- **不做游客模式。** 后端没有 `OptionalUser` 这类可登录可不登录的依赖。唯一免登录的业务接口是 H5 资源（下条），原因是浏览器约束而非设计选择：H5 在沙箱 iframe（不透明源）里播放，它发出的请求一律按跨站处理，`SameSite=Lax` 的 session cookie 不会带上，加了登录依赖只会让游戏加载不了 JS/图片——播放页自身仍要登录，未登录拿不到游戏 id 与入口地址。该接口在首次访问时会触发**按需解包写盘**（写运行时根），代价上界是一份已上传内容的解压副本。**攻略资源不在这个例外里**（它是同源顶层导航打开的普通静态页，cookie 照常带上，与其它业务接口一样要登录）
- 本地存档与引擎本地设置本就只在浏览器里，不涉及鉴权

## 功能：游戏中心（Flash、HTML5 与主机 ROM）

自托管 Flash、HTML5 与 8/16-bit 主机游戏：列表页（按平台分组）+ 管理页 + 播放页（Flash 用 Ruffle、主机 ROM 用 EmulatorJS、H5 用沙箱 iframe，均在浏览器内）。

- 元数据在本地 SQLite（`games` 表），文件按相对路径落在项目文件根目录下。**游戏类型由本体文件扩展名自动判定，不接受手动指定**：`backend/games/service.py` 的 `detect_game_type()` 是唯一判定入口，`_GAME_TYPE_EXTENSIONS` 是扩展名与类型的唯一对应表（**从 `platforms.py` 的机种词表派生**，单向一一对应，无歧义：`flash`→`.swf`；`h5`→`.zip`；`nes`→`.nes`；`snes`→`.sfc/.smc`；`gb`→`.gb/.gbc`；`gba`→`.gba`；`segaMD`→`.md/.gen`；`segaGG`→`.gg`；`segaMS`→`.sms`），未收录后缀一律 400；封面统一 jpg/png/gif/webp
- **机种词表（全项目唯一权威）。** `backend/games/platforms.py` 是「这是哪台机器」的唯一来源，**机种 id 就是 EmulatorJS 的 system key**——游戏最终要在 EJS 里跑，能玩不能玩由引擎决定，所以引擎的机种表就是标准。id 集合与每个机种的 `cores` **逐字**取自 EJS 4.2.3 的 `EmulatorJS.getCores()`（`frontend/public/emulatorjs/data/emulator.min.js`，升级 `EJS_VERSION` 时两处要一起对，`tests/test_platforms.py` 会红）。共 **36 个机种**，每条含 `id` / `label`（统一中文显示名）/ `aliases`（外部名录的各种写法）/ `cores` / `extensions`（**非空才代表本项目已收录、可上传可玩**，值即 `game_type`）/ `default_extension`。`PLATFORMS` 的顺序即下拉顺序（按厂商分组），**`service.GAME_TYPES` 直接从 `playable_platforms()` 派生**，所以那 7 个可玩机种在表里的先后 = 管理页下拉与游戏中心分组的先后（刻意保持既有顺序 `nes` `snes` `gb` `gba` `segaMD` `segaGG` `segaMS`）。别名匹配走 `normalize_name()`（**去掉所有空白 + casefold**，所以榜单的 `SEGA CD` 与检索的 `世嘉cd游戏` 都能命中同一机种）；`id`、`label` 也当别名收，保证「认不出的原始名」永远撞不上机种键。`resolve_platform()` / `platform_label()` / `platform_order()` / `playable_platforms()` 是唯一入口，**别在别处手写机种名对照表**。**加机种只改这一张表**：id 用 EJS 的 system key、cores 照抄 EJS、别名要覆盖两份 CSV 的写法。
- **类型的显示名**：`flash`→`Flash`、`h5`→`HTML5`（这两个**不是机种**，是载体类型，名字写在 `service.GAME_TYPE_LABELS` 里），7 个机种取词表的 `label`（`任天堂 FC` / `任天堂 SFC` / `任天堂 GB/GBC` / `任天堂 GBA` / `世嘉 MD` / `世嘉 GG` / `世嘉 SMS`）。后端那份只用于拼中文报错文案；前端展示层镜像在 `frontend/src/constants/gameTypes.js` 的 `GAME_TYPE_LIST`（纯展示，**不进任何键名/路径/存储**），**两边逐字一致由 `tests/test_platforms.py` 钉住**。游戏管理、游戏检索、游戏榜单三处显示的是同一套名字，所以「任天堂 FC」在哪儿都写作「任天堂 FC」。
- **游戏中心卡片外观**：**所有游戏类型一视同仁，就是封面原图**——按自身比例等比缩放到「正方形限制框」内、居中，不裁不拉（比 1:1 宽的卡片更矮，比 1:1 高的左右留空条）；没有封面时摆类型图标。**卡片封面框的尺寸规则**统一在 `components/games/GameCover.vue`：卡片宽 = **正方形限制框**边长（框上 `container-type: inline-size`，内部用 `cqw`，所以 rail 与网格里同一盘卡一样大）。**只有游戏中心的卡片**（「全部游戏」网格与「最近游玩」rail）走这层渲染；详情弹框图片栏、游戏管理列表缩略图与添加/编辑表单的封面预览都显示**封面原图**。**卡片高度规则**：rail 传 `CARD_ASPECT_RAIL`（`1 / 1`）→ 卡片是正方形、整行高低一致；「全部游戏」不传 aspect → 卡片高 = 封面高（同类型封面形状一致，整行仍齐平，扁封面的行更矮）。**渲染层不按游戏类型分支**：光盘 / 卡带的观感一律由下面的「封面美化」合成进封面文件本身
- **封面美化（游戏管理页编辑弹框）**：编辑弹框「游戏封面」那行，在「本地上传 / 网络上传」右边还有**美化封面**按钮（`components/games/CoverBeautifyDialog.vue`）——把该游戏**当前的封面**合成成光盘 / 卡带的外观，确认后存回去覆盖原封面。**样式由游戏类型给一组、用户在这一组里选**（`constants/coverStyles.js` 的 `beautifyStylesFor()`，返回数组、顺序就是单选顺序、第一个是默认）：`flash`→DISK、`gb`→**GB / GBC 两种**、`gba`→GBA、`nes`→**FC / NES 两种**；**弹框标题右边始终有一排样式分段按钮**（`AppSegmented`，走 `AppDialog` 的可选 `#header` 插槽），切换只重新合成、不重新下载原封面；**只有一种样式的类型（flash / gba）也出这排按钮，那一项 `disabled`、点不动**，为的是每个类型都露出自己的样式名。**打开弹框时按游戏当前的封面类型默认选中**（`cover_type` 就是上次美化用的样式 id，命中列表里哪个就选哪个；没设过——新建的游戏都是空的——就是列表第一个）。**不在这张表里的类型（h5/snes/sega*）整条不显示按钮**。按钮的显示与可用条件：只在**编辑**模式（新建时游戏还没落库、也没封面，与「图集」「攻略」两项一致）且类型支持时出现；**该游戏还没有封面时按钮在但点不动**（美化的输入就是当前封面）。弹出即自动合成、没有「制作」这一步，左右两栏分别是原封面与美化后（右栏铺棋盘格底，透明区一眼可见），底部「取消 / 确认」；弹框里按类型提示建议输入尺寸与输出尺寸。确认走 `uploadAsset(id, "cover", { file, coverType })`（`POST /api/games/manage/{id}/assets`，多带一个 `cover_type` 表单字段）——canvas 出来的 Blob 没有名字，要包一层带 `.png` 的 `File`，后端靠文件名后缀定扩展名；**所选样式 id 与封面文件在同一次调用里落库**（写进 `games.cover_type`，也就是「封面类型」，见下面那条），分两步会留下「封面换了、类型没跟上」的中间态。**覆盖不可逆**：后端对 cover 分支会 `_delete_storage_key(old)`，原封面文件直接删掉。
- **封面美化的合成算法**（`utils/coverCompose.js`，纯 canvas、无 Vue 依赖）：两种做法。**卡带**（GB/GBC/GBA/FC）是「**先把封面缩放到洞口的长宽比，再与底图合并**」——底图是成品素材——一张**没贴过贴纸的原始卡带**（中间贴纸窗已填成机身色），封面直接盖到洞口位置即可；缩放是 `object-fit: fill` 的做法，**拉伸填满、不裁切不留边**，比例不符就是变形。贴之前必须按洞口圆角 `clip()` 一刀：底图洞口是按圆角填的，**圆角之外仍是机身像素**（GBA 是机身灰，GBC 是贴纸凹槽的阴影），不裁的话方形封面会盖掉这圈、接缝就不自然了。**圆角可以按角给**（`cornerRadii()`，写数字 = 四角相同、写对象 = 按角指定、没写的角算直角，`roundRectPath()` 里直角跳过 `arcTo`），目前五个样式四角都一样。**「底图填色」与「封面裁切」是两件事，FC 美版那张最容易搞混**：它的洞口上边就是画布顶边（源图顶部被裁掉了），所以**底图填色时上两角是直角**（那两块本来就是洞口的一部分，必须一起填上，否则底图上留两个透明缺口），而**封面裁切仍是四角 r=10**——裁掉的上两角露出的是底图填好的机身色。**Flash 光盘**是**程序化绘制**（没有底图）：画布 1024×1024，盘直径占 84%（四周留透明）、整盘一次性圆形 `clip()`，依次画「盘面底色（135deg 线性渐变）→ 封面（`object-fit: cover`，目标是正方形所以源矩形恒为居中的 `min(宽,高)` 正方形）→ 盘心 `src/assets/flash-logo.png`（边长占**盘直径**的 15%）→ 三层反光」。三层反光**由底到顶**依次是 118deg 斜向高光、外圈暗调与塑料边、盘心积层环，**顺序反了上面那层会把下面的盖掉**；两个径向渐变的**百分比基准是盘半径不是盘直径**（盘心标志那个数才是占直径的，这是整套几何最容易错的地方），同色双位置 stop（`91%` 与 `92.5%` 之间不过渡）要写成两条同色 stop。渐变线要自己算端点：`0deg` 朝上、顺时针，方向向量 `(sinθ, −cosθ)`、长度 `|W·sinθ| + |H·cosθ|`——**别拿 `(0,0)→(W,H)` 当端点**，那只在 45° 整数倍上碰巧对。几个必须避开的坑：`toBlob` 只出 **PNG**（jpeg 会把透明区压成黑底）、**不要传 `{ alpha: false }`**（那是模拟器截图的写法，这里会让画布变成不透明黑底，圆角与光盘圆外全废）、素材图必须 `await` 到 load 完（`drawImage` 收到没加载完的 Image 会静默什么都不画）。素材与洞口几何（**换素材必须同步改这三组数字**）：`gb-cart.png` 426×500、洞口 (53,151) 322×287、圆角 8；`gbc-cart.png` 438×503、洞口 (58,163) 322×287、圆角 8；`gba-cart.png` 640×370、洞口 (88,86) 464×235、圆角 12；`fc-cart.png` 700×460、洞口 (56,54) 592×290、圆角 10；`nes-cart.png` 700×779、洞口 (283,0) 323×527、圆角 10（底图填色时上两角是直角，见上）。底图文件名一律 `<样式 id>-cart.png`。**要贴同一张画的多个样式，洞口尺寸必须做成一样**（同一张封面贴进哪个样式，占的区域都得是同一个大小）——底图按 `sx = 目标洞口宽 / 原洞口宽`、`sy = 目标洞口高 / 原洞口高` 整图重采样，再按整数坐标重填一遍洞口；**加卡带样式照这个规矩来**。但**本来就该贴不同画的样式各按自己的素材来，别去对齐**：FC 日版挖的是整块横版标签（2.04:1）、美版挖的是竖版贴纸（0.61:1），形状差得远。没有现成底图时，用 `.claude/skills/cartridge-clear-scene` 把卡带成品图的贴纸窗清掉并补上机身色（窗外不是机身时要 `--color` 手工给，比如透明壳的 GBC）
- **文件落盘位置固定**（与源文件名、游戏名都无关，改名不挪动任何文件）。**两个根**：数据根 `STORAGE_ROOT` 放原始素材（会被整体拷走备份），运行时根 `RUNTIME_ROOT`（不配时等于数据根）放 SQLite 库与解包产物。SQLite 里只存相对路径，两个根下的相对路径**逐字一致**，读取时由 `backend/storage/local.py` 的 `LocalStorage` 拼上对应的根（并挡住绝对路径与 `..`）；`create_app()` 各建一个实例挂在 `app.state.storage` / `app.state.runtime_storage`。路径规则集中在 `backend/games/paths.py`，别在别处手拼字符串。**数据根**：
  - 本体：`game/{game_type}/{卡带ID}/game.{后缀}`，如 `game/nes/AB-12/game.nes`；H5 为原始 ZIP `game/h5/AB-12/game.zip`
  - 封面：`game/{game_type}/{卡带ID}/cover.{后缀}`，如 `game/nes/AB-12/cover.png`
  - 攻略包：`game/{game_type}/{卡带ID}/guide.zip`（与 `guide.pdf` 二选一）
  - 攻略 PDF：`game/{game_type}/{卡带ID}/guide.pdf`（与 `guide.zip` 二选一，不解包）
  - 图集：`game/{game_type}/{卡带ID}/image/{uuid}.{后缀}`
  - 云端存档：`save/{用户名}/{game_type}/{卡带ID}/{uuid}.state`
  - 截图：`image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}`

  **运行时根**（派生物，删了会自动重建）：
  - H5 解包资源：`game/{game_type}/{卡带ID}/h5/{包内相对路径}`
  - 攻略解包资源：`game/{game_type}/{卡带ID}/guide/{包内相对路径}`
  - 解包暂存：`game/{game_type}/{卡带ID}/.{h5,guide}-{随机}`（与最终目录同层，靠改名做到原子）

  类型那层用 `game_type` 的**键值**（`flash`/`h5`/`nes`/…），不是前端显示名。
- **本地目录就是普通文件**：用户可以直接从宿主目录拷走/浏览；不需要引入任何对象存储或元数据缓存。上传先写同目录临时文件再 `os.replace` 改名；目录级操作（`remove_tree` / `replace_tree` / `move`）由 `LocalStorage` 提供，用于删游戏、解包整体替换与改卡带ID 时搬目录
- **卡带ID（`cartridge_id`）**：创建时**必填**（新建表单与搬运弹窗都要填），全局唯一（唯一索引 `uq_games_cartridge_id`，跨类型也唯一），只允许数字/字母/中划线/下划线、**落库前统一转大写**，校验入口 `validate_cartridge_id()`。它是磁盘目录名与「同一盘卡带」的身份标识：**普通编辑改不动它**（`PUT /manage/{id}` 不接受该字段，传了也当普通字段忽略），要换走**显式改名接口** `PUT /api/games/manage/<id>/cartridge-id`（管理页编辑弹框的「修改 ID」，`GameService.rename_cartridge_id()`）——它把 `game/{类型}/{旧ID}`、各账号的 `save/{用户名}/{类型}/{旧ID}` 与 `image/{用户名}/{类型}/{旧ID}` 三类目录整体改名，并在同一个事务里改写 `games.cartridge_id`/`game_path`/`cover_path` 与 `game_gallery_images`/`game_screenshots`/`game_cloud_snapshot_files` 三张表的 `file_path`；改完名运行时根下的旧解包产物直接作废（下次访问重新解包）。两条硬规矩：① 存档与截图目录名里的类型是**写入当时的**，只能从 `file_path` 反推父目录再换最后一段，**绝不用当前类型拼**（与删游戏同一口径）；② **先搬磁盘、后提交数据库**，中途失败把已搬的按相反顺序搬回去、库一个字节不动（顺序反过来一旦搬不动，库里所有路径就都指向不存在的位置）。源目录不在（本体没上传过/宿主手删过）照常成功；源不在而目标在则 400 拦下（否则这盘游戏会指向那个陌生目录）；新旧相同是空操作。管理页详情里展示它
- **封面类型（`cover_type`）**：这盘封面被「美化」成了哪种外观，**值就是封面样式 id**（`flash` DISK / `gb` GB / `gbc` GBC / `gba` GBA / `fc` FC / `nes` NES）。**可空**（不是「始终有值」），空 = 没有封面类型。可选集合按游戏类型给，在 `backend/games/models.py` 的 `COVER_TYPES_BY_GAME_TYPE` / `cover_types_for()`（**不支持美化封面的 `h5`/`snes`/`sega*` 返回空元组**，这些类型永远为空），校验入口 `service.py::validate_cover_type()`（**先判空再判类型**：空值合法、返回 `None`，非法值中文 400），前端展示层镜像在 `frontend/src/constants/coverStyles.js` 的 `STYLE_BY_GAME_TYPE` / `coverTypesFor()`——**两边的 id 集合与顺序必须逐字一致**（后端是接口只认的权威来源）。**只有两条写入路径**：① 管理页**编辑**弹框的单选（`PUT /manage/{id}` 的 `cover_type`：`None` = 不改、空串 = 清空、非法值 400；**新建弹框没有这一行**，`create()` 也**不接受**这个字段，所以新建 / 网络上传 / 搬运一律留空）；② **美化封面**（`POST /manage/{id}/assets` 的 `cover_type` 表单字段，只在 `kind="cover"` 且非空时生效、`kind="game"` 静默忽略，写在写文件之前，校验不过连封面文件都不换）。**游戏类型创建后不可变**，封面类型不会随换本体变化。游戏中心「全部游戏」在游戏类型分组内**再按封面类型分子网格**（同一种封面严格同一行，顺序 = `coverTypesFor(slug)`，认不出的值兜到末尾，**空的那一组固定排最后**，见 `views/games/index.vue` 的 `gameRows`）；卡片封面框规则见 `frontend/src/constants/gameCardAspect.js` 与 `components/games/GameCover.vue`（rail 正方形框、网格高度随封面）；**详情弹框展示它**（文字，空值显示「—」）、**编辑弹框用文字单选改它**（不用图片）。老库由 `backend/database.py` 的 `_ensure_columns()` 在启动时补列（**可空列，DDL 里不带 `NOT NULL`**）
- **建条目 / 换本体**：新建走 `POST /api/games/manage`（multipart：`name`/`cartridge_id`/`description`/`file`[+`cover`]）一步建条目并写本体，任一步失败整体回滚（不留半成品条目与文件）；换本体/换封面走 `POST /manage/{id}/assets`(kind=game|cover)——**换本体只接受与当前 `game_type` 相同的本体**（按扩展名判定，类型创建后不可变），同类型内可换后缀（`.gb↔.gbc`、`.sfc↔.smc`、`.md↔.gen`），跨类型直接中文 400 且旧档不动；成功后重算并覆盖 `crc32`/`size`/`game_path`，写新本体、落库成功后才删旧后缀文件；`PUT /manage/{id}` 只改名称/描述/`clear_cover`，不接收 `cartridge_id` 也不接收 `game_type`（改 ID 是另一个接口，见上一条）；管理页删除时要**手打一次卡带ID**才放行（会连磁盘文件、所有账号在该游戏上的云端存档与截图一起删掉，不可撤销）
- **网络上传**（管理页弹窗的「网络上传」按钮 → `backend/games/remote.py`）：本体与封面除了本地文件，还可以给一个 http/https 直链，由**服务端**下载到临时目录再走同一条上传管线（浏览器直连任意域名会被 CORS 拦）。建条目用 `body_url`/`cover_url`（multipart 字段），换资源用 `url`；两类来源可混用（如本体本地文件 + 封面直链）。**下载只走 `importer.download_file`**，上限 `remote.MAX_REMOTE_BYTES`（512MB，nginx 与 gunicorn 的 300s 也一并构成实际天花板）。类型判定：本体走直链时**以用户在下拉里选的 `game_type` 为准**——地址能认出类型就必须与所选一致（不一致 400），认不出（网盘式无后缀直链，或不是已收录格式）就用 `_DEFAULT_EXTENSIONS` 里该类型的默认后缀补上；封面地址的扩展名必须是 jpg/jpeg/png/gif/webp。原始文件名**一律不落盘也不入库**（临时文件固定叫 `remote{后缀}`），地址里带什么路径分隔符都影响不到库里。下载失败、超限、协议不对都转成中文 400（注意 `remote` 抛的是 `DownloadError`，service 侧必须经 `_remote_extension`/`_fetch_remote` 转成领域错误，否则会变成 500）
- **本体 CRC32**：上传本体时顺手算 CRC32 落 `games.crc32`（分块读完再 `seek(0)` 交给存储，不整读内存；8 位大写十六进制，如 `D445F698`）。它只是**当前本体内容的摘要**，不是锁定凭据：换同类型本体时重算并覆盖，管理页编辑弹框与详情弹窗展示它。空串表示尚未算出
- **同类型下游戏名唯一**：`games` 上有联合唯一索引 `uq_games_game_type_name(game_type, name)`，新建/改名都会先查重并回中文 400；不同类型之间可以重名。卡带ID 则**跨类型唯一**
- **游戏名要同时是合法的 Windows 文件名与百度网盘文件名**（导出/上传时它就是「游戏名.后缀」）：校验入口 `backend/games/service.py::validate_game_name()`，新建与改名都过它，规则取两边限制的交集——不能含 `\ / : * ? " < > |`（全角版如 `：／？` 合法）、不能含控制字符、不能以点结尾、不能是 Windows 保留设备名（`CON`/`PRN`/`AUX`/`NUL`/`COM0-9`/`LPT0-9`/`CONIN$`/`CONOUT$`/`CLOCK$`，带扩展名与大小写不敏感）、不超过 255 个字符；首尾空白自动去掉。**搬运**（`import_from_url`）抓到的站点标题走 `sanitize_game_name()` 无害化（非法字符换 `_`、去掉结尾的点、截断、空则回退「未命名游戏」）后再入库，不会因标题带斜杠就整个失败
- **描述上限 200 字**（`DESCRIPTION_MAX_LENGTH`）：新建与编辑都过 `validate_description()`，超长报中文 400、**不静默截断**（前端输入框同样 `maxlength=200`）；**搬运**抓到的站点简介按上限截断后入库，不因简介过长整个失败
- 上传/下载都走 `LocalStorage` 分块流式（不整读进内存）；下载：`GET /api/games/{id}/play` 附件返回本体，content-type 按本体扩展名——`.swf` 保持 Flash 专用值、其余（ROM/H5 ZIP）统一 `octet-stream`；`GET /api/games/{id}/cover` inline 预览（`?download=1` 附件下载封面）。两者都需登录
- **H5（`h5`）**：上传 `.zip`（根目录需含 `index.html`，整包套单层目录会自动剥前缀）时**只校验、不解压**——`backend/games/archive.py` 的 `read_manifest()` 只读中央目录，校验路径/重名/条目数/单条与总解压量/压缩比，拒绝绝对路径、`..`、加密条目；zip 本体原样存数据根的 `game/{类型}/{卡带ID}/game.zip`（即 `games.game_path`），**没有任何清单表**。播放时 `backend/games/runtime_assets.py` 的 `RuntimeAssets.ensure()` 按需把整包解到**运行时根**的 `h5/`：先 stat 入口文件，在就不再解；否则解到同层暂存目录 `.h5-{随机}`，写完用目录改名整体替换（原子，磁盘上没有代际前缀）。同一 (类型, 卡带ID) 用模块级 `threading.Lock` 串行——**必须保持 `--workers 1`**，多进程下并发 `os.replace` 覆盖非空目录会在 POSIX 上报 `ENOTEMPTY`。重传 zip / 改卡带ID / 删游戏时由写路径显式作废运行时根那份（`drop_tree`）；两个根相同时这些清理退化成一次 `exists()` 检查。播放时 `GET /api/games/{id}/h5/{资源路径}` 免登录 inline 下发（入口固定 `index.html`，MIME 按后缀用 `guess_asset_mime()` 现算），响应强制 CSP `sandbox`（不含 `allow-same-origin`）+ `nosniff` + `Referrer-Policy: no-referrer` + `ACAO: *` + `no-cache`。沙箱下无 localStorage/Worker，H5 不接入云存档
- 播放路由：Flash → `/games/flash/{gameId}`；H5 → `/games/h5/{gameId}`（嵌套 sandbox iframe 指向 H5 资源入口）；主机 → `/games/play/{gameId}`（外层 SPA 壳内嵌 iframe `/emulator-host.html`，EmulatorJS 官方要求 iframe 隔离）。EmulatorJS 引擎资产由 `frontend/scripts/fetch-emulatorjs.mjs` 构建期从固定版本拉取到 `public/emulatorjs/`（gitignore，nginx 以 immutable 静态服务），运行时不依赖外网
- **攻略**：一份攻略可以是 **ZIP 静态站包或单个 PDF**，二者互斥（数据根 `game/{game_type}/{卡带ID}/guide.zip` / `guide.pdf`；ZIP 入口固定包内根目录 `index.html`，子页面/图片/CSS/字体都是包里的普通文件，整包套单层目录会自动剥掉）。攻略形态存在 `games.guide_kind`（`""` / `"zip"` / `"pdf"`）——列表载荷的 `has_guide` 由它派生、`guide_kind` 原样给前端，**列表接口不再 stat 磁盘**；上传写值、删除清空，宿主手动增删文件不会自动反映。上传只在**游戏管理页的编辑弹框**（「上传封面」下方「上传攻略」，新建弹框没有这一项）：multipart 里只有一个 `file`（`POST /api/games/manage/{id}/guide`）。ZIP 与 H5 **共用同一套校验**（`archive.read_manifest(kind=guide)`：只读中央目录、不解压；入口只认 `index.html`，不收 `index.htm`；zip ≤128MB、条目 ≤2000、单条 ≤64MB、解压后 ≤256MB、压缩比 ≤200）；PDF 只查后缀、大小（≤128MB）与前 1024 字节含 `%PDF-`。两者都**在写任何字节之前全量校验**，**上传一种会删掉另一种**（删除失败会回滚新文件），**不动 `game_path/size/crc32`**。按钮右边的「删除攻略」二次确认后立即删除（`DELETE /api/games/manage/{id}/guide`：ZIP/PDF 文件、运行时解包目录与 `guide_kind` 一起清掉，幂等，删文件失败返回 500 且不清列）。查看 ZIP 时 `RuntimeAssets.ensure()` 按需解到**运行时根**的 `game/{类型}/{卡带ID}/guide/`（入口在就不再解）；重传 / 改卡带ID / 删游戏时由写路径显式作废。读取 ZIP 资源 `GET|HEAD /api/games/{id}/guide/{资源路径}`（**需登录**，与 H5 的免登录不同）：路径归一化后从运行时根直接取、按后缀给 MIME（`guess_asset_mime` 那张显式表）；PDF 读取 `GET|HEAD /api/games/{id}/guide.pdf`（同样需登录），直接从数据根流式返回 `application/pdf` + `Content-Disposition: inline`，交给浏览器内置查看器。两条都只加 `nosniff` + `no-cache`（重传后立刻生效），**不加 CSP sandbox**；文件不存在或形态不符即 404。入口在游戏中心卡片右键菜单「详情」下方的「攻略」（**没有攻略就不显示这一项**），`window.open(..., "_blank", "noopener")` 在**新标签页顶层**打开：PDF 打开 `/guide.pdf`，ZIP 打开 `/guide/index.html`。**删游戏**时随整个游戏目录一起清掉。**做攻略**（把网上现成的静态攻略站变成可导入的包）用 `.claude/skills/make-guide`：镜像原站 → 剥掉站点外壳 → 转中文（专有名词只在标题/词条位置保留原文 `中文（原文）`）→ 跑 `check_guide.py` 自检 → 打成 zip 上传
- **主机播放页标题栏**（自左向右）：加速模式 → 截图 → 保存配置 → 窗口倍率 → 显示机壳（GBA / FC / GBC 有）→ 存档管理。**「加速模式」与「显示机壳」这两个开关按钮都是固定文案 + 点亮高亮**（`.emulator-player__action--on` + `aria-pressed`），不随状态改文案。**加速模式**是持续快进开关（点亮即一直加速，再按恢复），开关的就是引擎自己的 `Fast Forward` 设置项：宿主页 `__ejsRpc.setFastForward` 调 `EJS_emulator.changeSettingOption("fastForward", "enabled"|"disabled")`——它会设好 `settings` 并经设置行的监听触发 `menuOptionChanged` → `handleSpecialOptions`，把 `isFastForward` 与内核的 `toggle_fastforward` 一起改掉、刷新引擎设置菜单里的单选高亮并 `saveSettings()`，所以它与引擎设置菜单里那一项**是同一份状态**、也会随「保存配置」整块进账号（下次进游戏直接加速）；按钮的亮灭每轮轮询读 `__ejsRpc.fastForward`（即引擎的 `isFastForward`）对齐，用户在引擎设置菜单里改过也认。**绝不碰按键**：加速模式关着时用户在引擎 Control Settings 里给动作 **27（FAST FORWARD）**绑的键按住即加速、松手恢复，与改动前完全一致；开着时按住该键临时回到正常速度（引擎自身语义，不读 `controls`、不拦 keydown）。倍率用引擎默认 3.0×，要改去引擎设置菜单的 Fast Forward Ratio。**截图**走宿主页 `__ejsRpc.screenshot`，**两条路**：先要引擎自带截图（内核侧读帧缓冲 → **原生像素**，如 FC 256×224），拿不到或整幅全黑时退回「在**同一帧的 requestAnimationFrame 里**拷画布」（画布尺寸 = 显示尺寸；引擎 WebGL 上下文是 `preserveDrawingBuffer: false`，合成后绘制缓冲即失效——Chromium 下同帧拷贝可靠，个别浏览器会拷到全黑，故有内核侧那条路兜底），两条都黑时按原生帧返回、不报错；返回的 `width`/`height` 是 PNG 真实像素尺寸，提示里显示的就是它。**截完不下载**：先弹 `ScreenshotConfirmDialog.vue`（弹框 320px：上面 180px 正方形限制框预览、下面一行描述（单行 `input`，刚好放下 15 字、没有计数行），**描述框自动获得焦点、按回车即确认**，点「确认」同效），确认后才带描述 `POST /api/games/screenshots` 存入图库并提示 `截图已存入图库（宽 × 高）`，取消/ESC/✕ 就整张丢掉（预览用的 objectURL 在关闭与卸载时 `revokeObjectURL`）。快捷键 **Ctrl+Shift+S** 与按钮同效（F12 是浏览器开发者工具的保留键，页面拦不住）：**父页面 window 与宿主 iframe 的 window 各挂一份 `keydown`**（玩游戏时焦点在引擎画布上，父页面收不到），iframe 那份用**捕获阶段**挂（引擎自己也在它的容器上监听 keydown），换 iframe / 卸载时解绑；守卫：引擎已就绪、不在截图中、确认框未开、事件目标不是 INPUT/TEXTAREA/contenteditable（引擎自己的设置面板里也是输入框）。**同一套挂载点还挂着快捷键 `·`（Backquote，数字 1 左边那个键）**：立刻「捕捉当前进度 → 上传成一个云端快照」，两步顺次跑完**只**弹一句 `已同步至云端`（直接复用 `onUploadCloud()`——它内部就是 `__ejsRpc.capture` → 写本地 `save.state` → `uploadCloudSaveAPI`，捕捉不暂停引擎），模块级 `syncingCloud` 挡连发；按键用 `event.code` 匹配（同一物理键在别的布局/输入法下 `event.key` 可能是 `` ` ``/`~`/`·`）且不带任何修饰键，命中后与截图一样 `preventDefault + stopPropagation`。**Flash 播放页同一个键**也要先 `ElMessageBox.confirm` 提醒**会重启游戏**（Ruffle 只在播放器销毁时才落盘，`onUploadCloud()` 第一步就是 `reloadForSave(null)`），确认后才同步、`onUploadCloud()` 返回 true 才弹那句提示（存档管理弹框那条调用路径忽略返回值，行为不变），监听用**捕获阶段**挂在 window 上（Ruffle 在同一个文档里也监听键盘），开始门未过 / 加载中 / 存档弹框开着 / 正在同步时不响应；**H5 播放页**按 `·` 只弹「HTML5 游戏不支持云存档。」（沙箱 iframe 不带 `allow-same-origin`，父页拿不到它的 window，焦点在游戏画面里时收不到这个键）。**窗口倍率**的基准是各平台帧缓冲分辨率（`emulator-player.vue` 的 `EMU_NATIVE`：NES 256×224、SNES 256×224、GB/GBC 160×144、GBA 240×160、MD 320×224、GG 160×144、SMS 256×192），倍率可选 `1×`/`1.5×`/`2×`/`2.5×`/`3×`/`3.5×`/`4×`，按帧缓冲**高度**换算窗口像素高度、宽度再按舞台宽高比推出，菜单里括号中的尺寸就是这套算法的结果（真实窗口尺寸，不是帧缓冲像素数）。**窗口选择器是 `components/games/EmuWindowSelect.vue`，不是原生 `<select>`**：按钮点开的面板是一张**两列矩阵**（行 = 倍率，列 = 显示比例），最上面一行是「适应窗口」。**只有 FC 画第二列**（传 `wide` 配置 `WIDE_MODE.nes = { aspect: 4/3, native: 256×240 }`）：左列「像素完美」（1:1 方像素，就是上面那套 256×224 的尺寸），右列「4:3」（真机 CRT 观感）。取值是 `<倍率>|<显示比例>`（`"2|pp"` / `"1.5|wide"` / `"fit|pp"`，存 localStorage 的 `games.emu.window`），老值只有倍率时按像素完美读；面板在标题栏内就地弹出（不 teleport），鼠标移进面板仍算在标题栏内、标题栏不会收起把它带走，点外面/ESC 收起。**舞台长宽比取引擎上报的显示宽高比，不是帧缓冲比例**：引擎（宿主页 `__ejsRpc.videoInfo` 的 `aspect`，来自引擎 `getVideoDimensions("aspect")`）把画面按内核上报的 aspect 等比摆进画布，画布（= 舞台）填不满的地方就是黑边——内核会按像素宽高比（PAR）校正，舞台若按帧缓冲比例定尺寸就会留黑边（SNES 默认 4:3、MD 默认 auto 同理）。引擎就绪前（以及取不到 aspect 时）用帧缓冲比例兜底，就绪后每秒跟随一次，用户改内核 aspect 选项也会跟着变。**FC（系统名 `nes` → fceumm 内核）的内核选项由宿主页 `emulator-host.html` 按显示比例模式设两套**（模式经 iframe 的 `?ratio=` 传进来，运行中切换走 `__ejsRpc.setDisplayMode(mode)`）：`pp`（像素完美，默认）→ `fceumm_aspect = "PP"` + 上下过扫描各裁 8 行（内核默认值），帧缓冲 **256×224**、显示 **8:7 = 256:224**（**引擎默认的 8:7 PAR 会让同一个帧缓冲按 ≈1.306 摆放，1× 窗口就不是 256×224 了，所以这一项必须设**）；`wide`（4:3）→ `fceumm_aspect = "4:3"` + **过扫描裁切关掉**，帧缓冲 **256×240**、显示 **4:3**（**必须用完整 240 行**：224 行按内核的 4:3 摆放会被它按完整帧归一化成 ≈1.43，填进 4:3 屏幕会上下留黑边）。引擎把 `defaultOptions` 在菜单初始化时经 `changeDiskOption` → `menuOptionChanged` → `setVariable` 下发给内核，`loadSettings()` 加载的账号本机设置排在它之后、优先级更高；为了不让引擎里存过的旧值把机壳的洞带偏，播放页在引擎就绪、第一次读到 aspect 时对一次（`aspectSynced`）：与选中模式的比例不符就调一次 `setDisplayMode` 掰回来——**窗口选择器是显示比例的唯一入口**
- **搬运（`POST /api/games/manage/import`，需登录）**：传入 7k7k / 4399 / flash.homes 的游戏页地址**与卡带ID**（`{ url, cartridge_id }`，卡带ID 规则同上、必填），由 `backend/games/importer.py`（服务端唯一的站点解析与下载实现）解析游戏信息与资源地址、下载 Flash SWF 或镜像 H5 bundle 到临时目录，再走普通上传管线入库（H5 打成 zip 复用解包逻辑），封面一并下载。**只接受 7k7k.com / 4399.com / flash.homes 域名**（避免服务端被当作任意 URL 代理）；H5 镜像会跟随页面引用的外部资源域名。站点差异：7k7k / 4399 的 Flash 资源地址藏在页面 JS 变量或资源页里，flash.homes 是 Flash 存档站、作品一律是按 sha256 存放在 CDN 上的单个 SWF（游戏页用 Astro 渲染，播放器岛 `PlayerStage` 的 `props` 属性里给出 `sha256` / 标题 / 封面文件名，另有 JSON-LD 兜底；其作品 id 为 12 位短码，页面上写作 `F8YX-1DNE-JQG9` 形式），搬运结果可能是 `flash`（SWF）或 `h5`（页面里是 H5 入口时打包成 zip，复用解包流程）。前端入口在游戏管理页「搬运游戏」弹窗
- **云端存档**（`/api/games/saves`，需登录）对 Flash/模拟器两类播放是同一套后端：把某(用户,游戏)此刻全部本地存档文件上传成一个不可变整体快照。元数据在 `game_cloud_snapshots`(+`_files`)；`manifest(local_key,name)` 与文件一一对应、按 (user,game) 隔离、越权一律 404；内容按 `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state` 落盘（文件名用 uuid 是为了不可猜、不重名，原始文件名留在 SQLite 里供下载时还原）。`name` 下载名规则：含扩展名时原样（模拟器固定 `save.state`）、否则补 `.sol`（Flash）。模拟器一个快照恒为 1 个文件（该游戏只有一份本地档），Flash 仍是一次全量。**快照之间可有父子关系**（`game_cloud_snapshots.parent_id`，**可空、无物理外键**）：NULL = 顶层、允许多个顶层；`PUT /api/games/saves/{snapshot_id}/parent`（body `{parent_id}`，null = 顶层）设置/清除，service 校验父级属同一 `(user, game)`、非自身、沿祖先链不成环；**删除一个快照时直接子级改回顶层**（不级联删除、不接续祖父）。**新建快照自动接在同 (user, game) 下最新一条后面；第一条为顶层**。**展示顺序看 `sort_order` 分数**（升序，越新越靠下）：新快照取「最大分 + 1000」追加到末尾；同级兄弟的上下顺序用 `POST /api/games/saves/{id}/move`（body `{to_index}`，下标在同级内）调整，只改被移动那一行的分数、间隙用尽时整份重铺；**`created_at` 只决定「最新一条」是谁**（自动父级），不再决定列表顺序。两个播放页共用一套 `components/games/SaveManager.vue`（`platform` 只区分本地存档差异）：一个弹框，上半本地、下半云端；云端左侧列默认展示全部节点（只有标题），「只看起点」按下后只展示顶层，右侧按 `parent_id` **自动布局**（不存坐标）的画布，可拖动建树、拖到空白处或右键「设为顶层」脱离、滚轮缩放、空白拖动、方向键平移（**方向与内容移动一致：按哪个方向，画面往哪边走**）、**选中节点后 `Shift + ↑/↓` 调整同级顺序**、全屏；节点只显示描述第一行（没有描述显示时间戳），右键节点弹出详情 + 同步至本地 / 设为顶层 / 删除；**左列与画布节点双击都在原地改描述（不弹详情），详情弹框里的描述也可双击改**。**删游戏时连同该游戏所有账号的存档快照（行 + 文件 + 存档目录）一起清掉**。结构见 `docs/data_dict.md`
- **游戏截图**（`/api/games/screenshots`，需登录，**按账号隔离**）：图库里的图来自两处——主机播放页截图（PNG）与详情「截图 [管理]」里的「上传截图」按钮（本地图片）；**只有本人看得见、管得着**（越权一律 404），封面则是全站共享的一张。元数据在 `game_screenshots`（`user_id` FK + `game_id` 仅索引 + `sort_order` 分数 + `description`(15) + `file_path`，列表恒按 (用户, 游戏) 过滤 + 排序，复合索引 `ix_game_screenshots_user_game_order`；**不加** `(user_id, game_id, sort_order)` 唯一约束——分数排序靠中值插入，唯一约束只会碍事）；内容按 `image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}` 落盘。上传校验（全 400、中文）：游戏存在（否则 404）、非空、单张 ≤16MB、**按内容 magic 认格式**（PNG/JPG/WebP/GIF，认不出就 400；**不看文件名与 content-type**，后缀也由内容定，读完 `seek(0)` 复位）、描述 ≤15 字（不静默截断）。**排序是分数排序**：`sort_order` 是浮点分数，新图取「最大分 + `_SCORE_STEP`(1000)」追加到末尾；拖动重排 `POST /{id}/move`（body `{to_index}`，落点在当前列表里的下标，越界 400）**只改被拖那一行的分数**（取相邻两分数的中值），相邻间隔 ≤`_MIN_GAP`(1e-3) 时才把整份按步长重新铺开（间隙不足时的后台重排）；接口一律**返回整份有序列表**（顺序的真相在后端，前端整体替换）。删除不做重排（分数稀疏无所谓）。`GET /{id}/image` 走 `build_download_response(stream, content_type=行的 mime)`（不传 filename 即 inline，同封面；mime 用入库时 magic 定下的值，不能按后缀现猜——`.webp` 在部分 Python 的 `mimetypes` 里不认识）且**必须登录**——不能做成公开静态路径，否则会泄漏他人截图。**删游戏时**所有账号在该游戏上的截图行、文件与目录一并清掉，目录按 `file_path` 反推（目录里的类型是上传当时的；历史数据里换过类型的游戏，同一游戏的截图可能分散在两个类型目录里）。结构见 `docs/data_dict.md`
- **游戏图集**（`/api/games/gallery`，需登录，**按游戏共享**）：与截图**正好相反**——不记上传者，任何登录用户都能看、能传、能改描述、能删、能拖动排序（`GalleryService` 就是 `ScreenshotService` 去掉「用户」这一维，校验/分数排序/上传删除流程同一套）。元数据在 `game_gallery_images`（`game_id` 仅索引 + `sort_order` 分数 + `description`(15) + `file_path`，复合索引 `ix_game_gallery_images_game_order`）；内容是宣传图、说明书扫描件这类展示图，上传校验同截图（非空、单张 ≤16MB、按内容 magic 认 PNG/JPG/WebP/GIF、描述 ≤15 字、游戏不存在 404）。**字节落在游戏目录内**的 `game/{game_type}/{卡带ID}/image/{uuid}.{后缀}`；游戏类型创建后不可变，目录不会跨类型迁移；改卡带ID 时随游戏目录一起搬（`move_tree`）并把行里的 `file_path` 换成新前缀，删游戏时行与文件一并清掉。**入口在游戏管理页的编辑弹框**（「图集 → 管理」，新建弹框没有——新建时还没有卡带目录可落），详情弹框的图片栏只做只读展示
- **机壳覆盖**（播放页「显示机壳」按钮，GBA / FC / GBC 有）：把机壳图盖在游戏画面上，看起来像真机在玩。图与洞的几何在 `emulator-player.vue` 的 `SHELLS` 表里**按游戏类型**取（`gba` / `gb` / `nes`），每项含 `url` / `image`（整图像素尺寸）/ `hole`（透明屏幕洞的 x/y/宽/高），**换图必须同步改洞的几何**（洞的位置一变就会错位）：`gba` = `frontend/src/assets/shells/gba-shell.png`（画好的 GBA 机身，3840×2160，中间 **1920×1280 是透明的屏幕洞**——精确 3:2 = GBA 原生 240×160，且居整图正中）；`gb`（GB/GBC 一类共用这张，项目里 `.gb`/`.gbc` 是同一个游戏类型）= `frontend/src/assets/shells/gbc-shell.png`（GBC 正面机身，2131×1996，屏幕洞 **1285×1156.5 = 正好 10:9**，y 从 338 起，左右留白各 423px——原素材洞是 1285×1157、左右差 17px，入项目前从左边裁掉 17px 让屏幕左右对称；剩下半个像素差按小数声明，不必真拉伸图画；GB/GBC 的帧缓冲 160×144 与 gambatte 上报的显示比例 160/144 都正好是 10:9）；`nes` 有两套（对应窗口选择器里的两列显示比例，切比例时一起换）：`pp` = `frontend/src/assets/shells/nes-shell.png`（一台 CRT 电视机壳，1326×1237，屏幕洞 **1084×948.5 = 正好 256:224**，y 从 146.3333 起）；`wide` = `frontend/src/assets/shells/nes-shell-43.png`（**原素材本身**，1326×1077，屏幕洞 **1084×813 = 正好 4:3**，y 从 125 起）。**洞的比例必须与画面比例一致**，所以 `pp` 那套入项目前做过处理：原素材屏幕洞是 1084×813（4:3），而这一列显示的是 256×224（8:7），于是把**屏幕那一段纵向拉长 7/6 倍**（813 → 948.5）——下面 121 行的控制条（扬声器网/按键/指示灯，`y ≥ 965`）保持原样等比，不被压扁；最后把四周的透明留白裁掉（只有顶部 10 行是空的，左右下都顶到机身）。`hole` 里的 `y`/`height` 因此带小数（原素材洞坐标 × 7/6 再减去裁掉的 10 行），与图上的透明像素一一对应；`wide` 那套没有拉伸，`y` 是原素材洞坐标减去裁掉的 9 行。`shellStyle` 按「洞宽 = 画面宽」定比例再按洞的偏移把整图挪到画面左上角；洞的比例与舞台一致（GBA 3:2、FC 8:7），舞台又是按引擎上报的 aspect 摆的，所以洞会四边严丝合缝对齐画面，画面尺寸一变（换倍率/缩窗口/全屏）自动跟着缩放。定位必须用 **`position: fixed`**：机壳比画面大得多（GBA 那张宽是画面的两倍），`absolute` 会被 `.game-shell__body` 的 `overflow: auto` 裁掉并顶出滚动条，`fixed` 不参与滚动容器的溢出计算（代价是要 `getBoundingClientRect` 同步舞台的视口位置，滚动/缩放/全屏都要重算）；倍率调大后机壳比浏览器窗口大也**照常显示**——同比放大、超出视口的部分看不见即可，不裁剪、不隐藏、不提示（用 `fixed` 正是为了让它不产生滚动条）——但「适应窗口」模式下要塞进可用空间的从画面换成整张机壳，所以那个模式一定会把整个机身放在窗口里
- **模拟器设置云同步**（`/api/games/emulator-settings`，需登录）：登录用户的模拟器设置（键位 + 选项 + 金手指）按**平台**（`game_type`，7 个主机类型）各存一套，整块 JSON 文本存 SQLite（`game_emulator_settings`，不落文件）。引擎把设置写在 localStorage 的 `ejs-{gameId}-{core}-{gameName}-settings`，且**只在启动流程里读一次**，所以播放页在设 iframe `src` 之前先把云端值写回去（这就是「自动加载」）；保存是**手动**的——播放页标题栏的「保存配置」按钮（在「窗口倍率」左边）把当前整块配置 PUT 上去。**不做任何自动侦测**：引擎不发设置变更事件、也没有保存按钮，只能靠用户点。键名公式在 `frontend/src/utils/emulatorSettings.js` 的 `engineSettingsKey`，父页面与宿主页同源、共用一份 localStorage
- **最近游玩**（`GET` / `POST /api/games/recent`，需登录）：游戏中心列表页顶部「最近游玩」rail（只占一行、不滚动；列定义与下方网格相同，卡片尺寸一致）的数据源，下面是完整的「全部游戏」（重复资源不剔除）。记录**按账号**存 SQLite（`game_recent_plays`）：唯一 `(user_id, game_id)`、一个游戏只留一行、只记最后一次 `played_at`，因此无需裁剪与分页；行随游戏删除由 `GameService.delete` 一并清掉。列表 join `games` 且只返回 `game_path != ''`（与中心列表同口径），默认 20 条、上限 50（**在 service 收敛而非 `Query(ge=,le=)`**：参数校验失败走 422 会绕开统一错误信封）。**上报只能由播放页发起**：Flash/模拟器走 `GET /api/games/{id}/play`、H5 走免登录的 H5 资源接口，三条路径不共用同一个带登录态的入口，所以后端不在资源接口上记 user，而由三个播放页在「真正拉起播放器」的那一刻（有手势即开始；无手势是点过「开始游戏」）调 `utils/recentGames.js` 的 `reportGamePlayed()` best-effort 上报（`notShowError` + `skipAuthRedirect`，失败只丢一条记录，不影响游玩）
- **游玩时长与进度**（`/api/games/stats`，需登录）：按账号存 SQLite（`game_user_stats`，唯一 `(user_id, game_id)`，一行含 `play_seconds` 与 `progress`），**与游戏类型无关**。**时长**是平台级通用方案——`frontend/src/utils/gamePlaytime.js` 是个模块级单例，Flash / H5 / 模拟器三个播放页在**与 `reportGamePlayed()` 完全相同的时机**（真正拉起播放器时）调 `startGamePlaytime(gameId)`、在 `onBeforeUnmount` 调 `stopGamePlaytime()`；每 30 秒发一次心跳（`POST /stats/playtime` 累加，service 里把单次秒数收敛到 0..300 防时钟跳变），页面 `document.hidden` 期间**不累计**（切标签页/最小化不涨，回来接着算），离开播放页时把剩余一次性发出。**进度**（`not_started` 未开始 / `in_progress` 进行中 / `completed` 已通关）**只由用户手动设置**，不会因游玩自动变更。`GET /api/games` 与 `/recent` 载荷都带 `play_seconds` / `progress`（无记录时 `0` / `not_started`）。游戏中心页面**只在游戏卡上接管右键**（`GameCard.vue` 根节点 `@contextmenu.prevent` 后 emit，卡片外仍是浏览器原生菜单），弹 `GameContextMenu.vue`：**详情**（弹 `components/games/GameDetailDialog.vue`，与游戏管理页的「详情」是同一个组件：打开时按 id 现取 `GET /api/games/manage/{id}`——中心列表载荷里没有 CRC32 / 创建时间——并与截图列表并行取一次；弹框宽 `min(810px, 96vw)`）、**设置进度**（纯 CSS `:hover` 的右滑子菜单，三选一点完即存、没有确认步骤）与**设置时长**（`AppDialog` + `el-input-number`，单位小时，**覆盖**为该值而非累加；输入被清空时值是 null，必须校验后拒绝，不能 `|| 0` 兜底——那会静默把记录清成 0）；保存后本地 patch 两个列表里的对应字段，不重新请求。工具栏类型下拉**左边**是进度下拉，与类型/关键词一起做**纯前端**联合筛选；卡片封面下方是居中一行 **进度标签 + 总时长**（<10 小时保留 1 位小数、≥10 小时取整，见 `utils/gamePlaytime.js` 的 `formatPlayHours`）；**进度还是 `not_started` 就只渲染空的状态行容器、不渲染内容**（`GameCard.vue` 的 `showMeta`；容器始终存在并由 `min-height: 14px` 占住一行，同排卡片有没有状态都不影响标题位置）——未开始既没有进度标签也不显示时长，所以「有时长但没标过进度」的卡片这一行同样是空的，不写「未玩过」之类的占位
- **详情弹框的图片栏**（`components/games/GameScreenshotGallery.vue`，纯展示 + 内部翻页状态）：一行 **4 个 180px 正方形限制框**（180 = 「最近游玩」rail 卡片的最小列宽，格间距 14px，总宽 762px，框内 `object-fit: contain`——长边到上限为止，不裁不拉），**截图框不加底色、不做圆角**，图片栏与下方信息区之间也**没有分隔线**；**封面恒占第一格**（这一格显示封面原图：框内 `object-fit: contain` 等比缩放；没有封面就留虚线空占位框，位置不留给截图），其后依次是**共享图集**与本人的截图；每格下方一行**定高 18px 的描述**（水平居中、超出省略，封面那格留空但同样占位，换页/有无描述都不跳版）。**所有格子排在一条 flex 轨道上**（`.gallery__viewport` 只露一页宽、`overflow: hidden` 裁掉多余的），翻页是轨道 `translateX(-page × 776px)` 的水平**滑动过渡**（776 = 4 格宽 + 4 道缝，0.3s ease；格宽/间距在样式里，JS 的 `PAGE_OFFSET` 必须与之一致），不是直接换一屏；离屏的格子带 `loading="lazy"`（滑进可视区才开始取图）。放不下时左右两个圆形翻页按钮压在画面左右边缘上（图片栏正好 4 格宽、两侧没地方放），**在图片栏上滚滚轮也能翻**（上滚前翻、下滚后翻；只有真能翻的时候才 `preventDefault`，到边界与只有一页时完全放行，页面该滚还是滚）：`ceil(槽位数 / 4)` 页、**第 1 页 = 封面 + 3 张图（图集与截图同处一条轨道，按「图集 → 截图」排），第 2 页起每页 4 张且不再有封面**，只有一页不出按钮、到边界禁用，图增删后页码收敛回最后一页；封面、图集与截图都没有时整条图片栏不渲染。两类图**不走** Service Worker（SW 只拦 `/game-assets/`），URL 分别是 `/api/games/screenshots/{id}/image` 与 `/api/games/gallery/{id}/image`（id 唯一、内容不可变，无需版本参数）
- **截图管理弹框**（`components/games/ScreenshotManagerDialog.vue`，详情信息区右栏「截图 [管理]」打开）：**相册式平铺视图**（`grid` 自适应列，tile = 上面截图、下面描述），**一进来就是管理界面、没有「还没有截图」这类空态文案**，左上角恒有「上传截图」（本地图片，`accept` 只收 png/jpeg/webp/gif）。
  - **描述就地改**：单击描述，原地换成单行 `input`（与描述行**同宽同高同字号**，只多一圈边框，排版一点不动），**没有取消/保存按钮、也没有字数计数**（`maxlength=15` 静默限长），回车或失焦存下、ESC 放弃、内容没变就不发请求；同一时刻只有一张处于编辑态，选择模式下点描述算勾选（描述那层 `@click.stop` 拦了冒泡，所以要在处理函数里转给勾选）。
  - **多选删除（像手机相册）**：图片上**不放**任何按钮，删除入口是工具条**右上角固定的「删除」**——第一下进删除模式（右侧出现「已选 N 张」+ 取消），选择模式下点整块切换勾选（右上角出现 ✓），再点一次「删除 N 张」才真删，**这一步就是要用户确认的那一步，不再弹 `ElMessageBox`**；删除逐张调接口（中途失败也统一重拉对齐），完成后 `@changed`。
  - **滚动条不吃排版**：网格 `overflow-y: auto` + `scrollbar-gutter: stable`，有没有滚动条，列宽都一样。
  - **拖动排序**：整块 `draggable`（选择模式与描述编辑中禁用拖动；`img` 上 `draggable="false"`），原生 HTML5 DnD——`dragstart` 记 id（**必须 `setData`**，Firefox 否则不启动拖拽）、`dragover.prevent` 记落点（高亮 `--drop` 边框）、`drop` 时**先按同一套语义本地挪一下**（`splice(to, 0, splice(from, 1)[0])`，与后端「插到第 to_index 位」一致）再调 `move` 接口，用返回的整份列表覆盖；失败就重拉。任何变更成功后都 `@changed` 让详情弹框重拉截图，避免弹框后面的图片栏数据陈旧
- **详情弹框信息区**：`dl` 是 `grid-auto-flow: column` + `repeat(6, auto)` 的两栏，12 条正好左右各 6 行——左栏 名称/卡带ID/类型/封面类型/大小/CRC32，右栏 **截图 [管理]**/描述/本体/封面/创建时间/更新时间（「截图」这行让原本右下角空着的那格填满）；标签用「本体」「封面」而不是「游戏本体」「游戏封面」
- Flash 本地存档：Ruffle 把 SharedObject 写浏览器 localStorage（落盘时机见 Ruffle issue #798），`SaveManager.vue`（`platform="flash"`）统一封装本地多档与云端，SW 缓存本体/封面；**统一存档管理弹框支持 ESC 关闭**（`window` 冒泡阶段监听，打开时挂、关闭/卸载时摘）：按层级由内到外收——正在编辑云端描述先结束编辑，开着「同步至云端」描述面板先收面板，否则才关弹窗；监听特意挂在 `window` 而不是 `document`，这样 Element Plus 确认框（`ElMessageBox`）自己吃掉 ESC（它会 `stopPropagation`）时不会连带把存档管理弹框也关掉
- 模拟器本地存档：**每个游戏固定只有一份**（覆盖式，不做多槽位）。引擎浏览器档只维护单份暂存（`EmulatorJS-states`）；x 用 `frontend/src/utils/emulatorSaves.js` 把它另存为唯一本地档（`.state` 内容存 IndexedDB，键 `x_emusave:{gameId}:state1`，避免 localStorage 配额；元数据索引在 localStorage `x_emusave_index_v1`）——捕捉、导入 `.state`、云端还原都是覆盖这一份，`ensureSingleSlotModel()` 在进入播放页/存档面板时一次性清掉旧版多槽位档。播放宿主 `emulator-host.html` 暴露 `window.__ejsRpc`（`capture`/`load`，走引擎 `storage.states` 与 `elements.bottomBar` 存/读档）供捕捉与放回；`SaveManager.vue`（`platform="emulator"`）本地区只展示这一份（载入/下载/删除），云端仍与 Flash 共用一套快照模型、保留多份历史，只是每个快照只含 1 个文件，local_key 即 `x_emusave:{gameId}:state1`。存档固定叫 `save.state`（本地展示/下载与云端快照文件名都用它，名称不随时间变化，时间看展示的更新时间）

## 功能：游戏发现（游戏检索 + 游戏榜单）

第三个页面，侧栏叫「游戏发现」（`/games/discover`，旧路径 `/games/search` 重定向过来，保留 query）。页内是**单选栏**「游戏检索 / 游戏榜单」，标签状态写在 URL 查询参数里（默认检索，`?tab=ranking` 是榜单）。两块数据都来自**与平台游戏库完全无关**的外部名录，都放在同一个派生只读库 `game.db` 里，**页面与接口全只读**：检索查 `backend/search/csv/` 下 37 个 `机种,中文,英文` 三列 CSV（5 万余行、36 个机种），榜单查 `backend/search/ranking/ranking.csv`（四列，见下）。**索引的构建期**与 `games` 表没有任何联动（`ranking` 表结构与 CSV 格式都不变，不需要 `make index`）；但**接口的运行期**会按卡带 ID 把榜单行与平台库存**只读地**关联一次（见下「与平台库存的关联」），命中的行在页面上游戏名是可跳转的链接。

- **机种归一（三处共用一套名字）。** 两份 CSV 的「机种」都是自由文本，建库时一律经 `backend/games/platforms.py` 的词表解析成**统一机种**（id = EmulatorJS 的 system key）：检索的 `任天堂GB` 与 `任天堂GBC` 都落到 `gb`、榜单的 `SEGA CD` 与检索的 `世嘉cd游戏` 都落到 `segaCD`。所以页面上的机种名与游戏管理页的类型名是同一套（`任天堂 FC`、`世嘉 MD`…），不再出现「任天堂FC / FC / FC NES」三种写法。**认不出机种的**（`任天堂Wii`、`3DS`、`CD-I`…）保留原文、`platform_id` 留空，自成一组。**检索侧同一个机种的多个原始名在建库时就合并成一行 console**（36 个原始机种 → 32 项：23 个统一机种 + 9 个未收录），所以下拉天然不会出现两个同名项，选「任天堂 GB/GBC」一次就覆盖 GB 与 GBC 的全部条目。`tests/test_platforms.py` 拿**真实 CSV** 跑，钉住「每个机种名都能解析，或明确列在『未收录』名单里」。

- **独立的只读索引库。** 索引是 `<STORAGE_ROOT>/db/game.db`（`backend/config.py` 的 `GAME_INDEX_FILENAME`；在**数据根**里，**不跟库走**，与 `app.db` **无外键关系**）。写入方**只有 `backend/games/search_index.py` 这一个模块**，两条写路径：① `build_index()` 整库重建（`make index` 与**服务启动时的自动补建** `ensure_game_index()`，后者只在文件不存在、或库里的 `schema_version` 与代码不符时建）；② `ensure_ranking_loaded()` 启动时把榜单 CSV 就地补进已存在的库（源文件指纹没变就一个字节都不写）。平台运行期的读一律经 `backend/games/search_service.py` 的 `GameSearchService` 与 `backend/games/ranking_service.py` 的 `GameRankingService`，都用 `Path.as_uri()` + `?mode=ro` + `PRAGMA query_only=1` 打开，每请求一条短连接、用完即关，**运行期绝不写它**。**它刻意不参与备份**（`backend/backup.py` 只备份 `app.db`）——它是可从 CSV 重建的派生数据。
- **构建是整库重建 + 原子替换。** `make index` → `python -m backend.cli index` → `build_index()`：写到同目录 `game.db.tmp`、`chmod 0644`、`os.replace()` 覆盖旧库（可重复执行，直接覆盖）。**不开 WAL**（WAL 会留 `-wal`/`-shm`，`os.replace` 只换主库，新库配旧 `-wal` 必坏）。所以**重建索引不需要重启 api**：已打开的连接继续读旧 inode，新请求自动拿到新库。
- **索引不存在时服务自己补一次。** `create_app()` 启动时调 `ensure_game_index()`（紧跟 `backup_database()`，风格与备份一致）：文件不存在就整库建一次（检索 + 榜单同一次构建），已存在且版本一致就只就地补榜单；**全程 best-effort，失败只记 warning、绝不拦住启动**（建不出来最多是检索页提示「尚未构建索引」、榜单页提示「榜单尚未加载」）。`TESTING` 下直接跳过——否则每个测试用例都要白建一次 5 万行的索引，也会让「索引缺失」那组用例失去意义。`make index` 仍是手动重建/更新索引的正规入口（换 CSV、改分词规则之后用它覆盖；`--skip-ranking` 可只重建检索）。
- **版本对不上就自动重建。** `SCHEMA_VERSION` 升过之后，已存在的老库会被接口一律判 503（「索引版本过旧」），而 `ensure_ranking_loaded()` 在检索版本不符时也会直接跳过——两条路都不会自愈。所以 `ensure_game_index()` 除了「文件不存在」，**文件在但 `meta.schema_version` 与代码不符时也整库重建一次**（重建失败只记 warning、旧库原封不动）。这样 Docker 升级与 Windows 包「解压新包 + 搬 data」都不需要人工跑 `make index`。
- **宿主机与容器都能补建**：CSV 随 `backend/` 一起进 api 镜像（根目录 `.dockerignore` **没有**排除它），所以容器启动时也能自建一次。两边写的是**同一个数据目录**（bind 进去的），所以在哪边建都一样：宿主机 `make index` 建出来的库容器立刻能读到，不用重建镜像、也不用重启 api。
- **索引缺失/损坏时的表现**：没有文件 → 接口返回 `indexed:false` + 空列表（200，**不是错误**），页面给中文引导；文件在但打不开 / `meta.schema_version` 不匹配 → 503 + 中文提示（`IndexUnavailableError`）。榜单另有一套状态：`ranking` 表与 `meta.ranking_fingerprint` 都在才算 `has_ranking:true`，缺失一律 200 + 空列表（榜单还没加载不是错误），只有 `meta.ranking_schema_version` **存在但不匹配**才 503。**接口永不建它**——只有 `search_index.py` 那两条写路径会。
- **写权限是唯一的拦路虎**：数据根若是 Docker 以 root 建的（默认的 `./data/storage` 跑过一次 compose 之后就是这样），**宿主用户**写不进去（容器里跑的是 root，不受影响）。此时宿主机直跑服务时的自动补建会失败（只记一条 warning，检索页提示尚未构建），`make index` 也会先 `test -w` 预检并提示 `sudo chown -R "$USER" "$STORAGE_HOST_DIR"`。
- **分词选型（别「优化」掉）。** FTS5 用 `unicode61 remove_diacritics 2` + **汉字逐字拆开**：裸 `unicode61` 会把整串中文当一个 token（搜任何子串都 0 命中），`trigram` 少于 3 字全废。所以 `backend/games/search_text.py` 的 `index_text()` 把每个汉字变成独立 token，查询时把词包成**短语**（`"马 里 奥"` ⇒ 子串语义），词间用 `AND`（整句拼一个短语会让 `final fantasy vii` 搜不到 `Final Fantasy VII`）。**索引期与查询期只有这一份实现**（`search_index.py` 与 `search_service.py` 都调它），任一处漏调中文就搜不到。顺带做 NFKC（全角字母/数字与半角互搜）。
- **结尾的地区/语言/版本标签不进索引**：`(Japan)`、`(En,Ja)`、`(Rev A)`、`[a1]`、`（日版）`、`(美版, 欧版)`、`[PS2]` 都在建库时由 `strip_tags()` 剥掉（名录里 76% 的英文名、38% 的中文名带这种后缀，不剥的话搜 `japan` 命中一万多条）。**落库与展示仍是原文**，剥的只有喂 FTS 的两列；整串都是标签的行回退成保留原串。
- **按三元组去重**：`(机种, 中文, 英文)` 完全一致才合并（含跨源文件；52,611 → 51,359 行）。只中文或只英文相同的必须都留着——那是同款游戏的不同地区版本。
- **查询与表结构**（`search_service.py`，四条都实测过）：

  ```sql
  SELECT c.id, c.name, g.id, g.zh, g.en
  FROM game_fts JOIN game g ON g.id = game_fts.rowid JOIN console c ON c.id = g.console_id
  WHERE game_fts MATCH :q   -- [+ AND g.console_id = :cid]
  ORDER BY bm25(game_fts, 8.0, 1.0), g.id     -- 中文列权重 8.0；g.id 是必须的 tiebreaker
  LIMIT :limit OFFSET :offset
  ```

  - **FTS 表不能起别名**：`FROM game_fts f … WHERE f MATCH ?` 直接报 `no such column: f`，`bm25(f, …)` 同样；`MATCH` 与 `bm25()` 只认真表名。
  - `ORDER BY bm25(...)` 是**升序**（bm25 返回负值，越小越相关）；`bm25()` 的权重顺序 = FTS 表的列顺序。
  - 末尾必须有 `g.id`：去重后仍有「同机种 + 同英文名」的行，少了它 `LIMIT/OFFSET` 翻页会重复/丢行。
  - **不能**用 `COUNT(*) OVER ()` 一条查询同时拿 total 和 bm25 排序（实测报 `unable to use function bm25 in the requested context`），total 走同条件的第二条 `count(*)`。
  - 机种过滤按有无拼 `AND g.console_id = :cid` 片段，**不写 `:cid IS NULL OR …`**（OR 会让 SQLite 放弃 `idx_game_console`）。
  - 无关键词时不做 MATCH，走 `ORDER BY g.console_id, g.en, g.id` 的全量分页。
  - contentless FTS 表没有 `snippet()`/`highlight()`（返回 NULL），**高亮在前端做**：`views/games/discover/index.vue` 把命中片段切成数组渲染成 `<mark>`，**不用 `v-html`**（文本来自外部 CSV）。
- **页面与接口（检索）。** `views/games/discover/index.vue`（一个组件装两个标签：关键词 300ms 防抖 + 回车即搜、机种下拉、三列表格、`<el-pagination>` 服务端分页、请求序号丢弃过期响应；检索区状态在切标签时保留）。**标签栏是一对普通按钮、只能点**：不用 `el-radio-group` / `el-segmented`——它们是原生单选控件，焦点落在里面时按左右键浏览器会直接换选中项（同名 radio 的默认行为），而这页的左右键必须留给当前标签里的分页条（`AppPagination`，同一时刻只开一个，见下面「分页条」那条）；`api/games.js` 的 `searchGamesAPI()` / `listSearchConsolesAPI()`。`GET /api/games/search`（`q`/`console_id`/`page`/`page_size`，越界在 service 收敛，别放 `Query(ge=,le=)`）与 `GET /api/games/search/consoles`（每项 `{id, name, platform_id}`，`name` 是统一显示名、`platform_id` 是机种键、未收录机种为 null），都要登录。路由 `search_router.py` 路径不会被 `games/router.py` 的 `/{game_id}/…` 抢走（那些第二段字面量只有 cover/play/h5/guide，且没有单段 `/{game_id}`）——以后加单段动态路由就会撞车。
- **游戏榜单（榜单 CSV 与 game.db 里的 `ranking` 表）。** 数据源是 `backend/search/ranking/ranking.csv`（**单独目录**：`backend/search/csv/` 会被整目录扫成检索索引，四列的榜单混进去会被当成坏行；文件格式契约见该目录的 README）。四列固定 `序号,机种名称,游戏名称,游戏卡带ID`，表头可有可无（首行第一格是 `序号`/`排名` 就跳过），UTF-8（可带 BOM）、CRLF/LF 均可。**序号**：正整数、同一机种内唯一（重复报错），页面按它升序展示、原样显示不重排；**机种名称**：非空，建库时经词表归一成机种键（`GBA` 与 `gba` 因此自然合并，「同一机种内序号唯一」这条也按归一后的机种判），页面下拉显示词表里的统一名、值为机种键、默认选 `nes`（FC；没有就取词表里最靠前的，未收录的排最后）；**游戏卡带ID**：每行 0~2 个，用 `;` 分隔（也兼容 `、` `,` `，` `/` `；`），**空格/连字符/下划线不是分隔符**（卡带 ID 里常有空格），超过 2 个报错；**可以为空**（查不到编号的游戏留空即可，第 4 列可整列省掉，`4,GBA,某游戏` 等价于 `4,GBA,某游戏,`）。空行跳过、Excel 行尾多余空列裁掉，空文件/只有表头报错；解析错误消息必须带**文件名与行号**。落库是单表 `ranking(platform, console, rank, title, cartridge_ids)`（`PRIMARY KEY (platform, rank) WITHOUT ROWID`；`platform` 是归一后的机种键、认不出机种时用 `raw:{归一后的原文}`，`console` 留一份 CSV 原文供溯源与展示兜底；`cartridge_ids` 存 JSON 数组文本，0~2 个、空就是 `[]`）；meta 记 `ranking_schema_version`（常量 `RANKING_SCHEMA_VERSION`，**独立于检索的 `SCHEMA_VERSION`**）、`ranking_fingerprint`（CSV 原始字节的 SHA-256，只有成功加载后才写）、`ranking_source` / `ranking_rows` / `ranking_consoles` / `ranking_loaded_at`。**不 bump 检索的 `SCHEMA_VERSION`**：加榜单表是纯新增，老库要继续能检索；榜单补载失败也不能把检索变成 503。`ensure_ranking_loaded()` 先用**只读连接**比对指纹，一致就直接返回（**连读写连接都不打开**）；需要更新时 `PRAGMA journal_mode = DELETE` → `BEGIN IMMEDIATE` → 事务内二次比对 → `DROP TABLE IF EXISTS ranking` + 建表 + 全量插入 + upsert meta → commit，异常 rollback 且旧榜单原封不动；CSV 缺失时保留库里已有榜单、不删不改。接口 `GET /api/games/search/ranking/consoles`（`indexed` / `has_ranking` / `consoles[{platform,label,playable}]` / `default_console`）与 `GET /api/games/search/ranking?console=`（`console` 传的是机种键，回显也是机种键；`indexed` / `has_ranking` / `console` / `items[{rank,title,cartridge_ids,game_id,path}]`，**不分页**），都要登录；挂在 `/api/games/search/ranking` 下是为了不与 `/api/games/<单段>` 将来撞车。前端 `api/games.js` 的 `listRankingConsolesAPI()` / `getGameRankingAPI()`；榜单区第一次切到榜单标签才请求（`rankingLoaded` 标记），卡带 ID 是并排的可点按钮，点击复制（复用 `utils/clipboard.js` 的 `writeClipboard()`，`CopyButton.vue` 也用同一份），**不用 `title` / `el-tooltip`**。
- **与平台库存的关联（请求期，只读）。** 榜单行里**任意一个**卡带 ID 与库存某游戏的 `games.cartridge_id` 相同就算关联上（一行最多 2 个 ID，命中多个时取**该行第一个命中的**；比对是「去首尾空白 + 转大写」，即 `service.normalize_cartridge_id()`，与落库时的大写形式对齐——**绝不能拿 `validate_cartridge_id()` 去比**，它遇到 CSV 里 `Part No. 7004 0894` 这类含空格的原文会抛校验错、把只读接口打挂）。命中的行多两个载荷字段：`game_id` 与 `path`（播放页路径，由 `service.play_path()` 按游戏类型给，与 `GameItem.path` **同一份实现**），没命中都是 `null`。
  - **关联只在请求期做，不落库、不进索引、不缓存**：`GameRankingService` 的构造函数收一个窄回调 `cartridge_lookup`（`deps.py` 注入 `GameService.map_for_cartridge_ids`），`get()` 把整份榜单的卡带 ID **一次性**交给它（**一次查询，不是逐行查**；一个机种最多 100 行 × 2 个 ID = ≤200 个宿主参数，所以不分块），命中结果用 `dataclasses.replace` 附到 `RankingItem` 上。所以**增删游戏立刻生效**（不需要 `make index`、不用重启），代价是每次打开/切换榜单多一条走 `uq_games_cartridge_id` 唯一索引的小查询；榜单页内翻页不查（榜单是一次全取的）。
  - **只认有本体的游戏**（`game_path != ''`，与 `list_center` / `list_recent` 同口径）——没有本体的条目点进去只会 404。**不校验机种**：卡带 ID 是「同一盘卡带」的全局身份，榜单的 `platform` 还有 `raw:3ds` 这类永远等不上 `game_type` 的值。**不为 CSV 里的怪 ID 放宽 `validate_cartridge_id`**（它是磁盘目录名）。
  - 页面：命中的行游戏名渲染成**真的 `<a href>`**（`<router-link :to="item.path">`，**不加 `@click` 也不加 `custom`**——vue-router 对 Ctrl/中键点击一律放行给浏览器，加了拦截就没法在新标签页打开），没命中就是纯文本。**工具栏 = 机种下拉 + 搜索框 + 「已入库」按钮**（三者自左向右挨着，按钮**不**推到工具栏最右）：
  - **搜索框**与检索区那个同一个 class（240px、`clearable`、紧跟在机种下拉右边，样式与位置逐像素一致），但**纯前端过滤**：榜单本来就是一个机种整份取回、前端分页，所以逐字即时筛，**没有防抖、没有回车/清空处理**（裸 `v-model` + `clearable`，computed 自己会跟着变；`el-input` 在输入法组字期间不发 `input`，中文打字不会把列表打空）。匹配口径是**对游戏名称做不区分大小写的裸子串**（`item.title.toLowerCase().includes(needle)`，`needle` 取 `trim().toLowerCase()`），**不匹配卡带 ID**、不做 `<mark>` 高亮、**不认检索区那套 FTS 语法**（`mario*` 的前缀星号在这里是普通字符；也不做 NFKC 与剥尾部标签）——榜单侧的关键词与检索区的 `keyword` 是**两个独立的 ref**，语义不同、别合并。搜索词一变页码回第一页（`watch(rankingKeyword)`），**不写进 URL**（与检索区一致）。
  - **「已入库比例」按钮**（`已入库 25 / 100`）：分子分母都由前端按**整份** `rankingItems` 现算（`path` 非空的行数 / 总行数），加载中先隐藏以免切机种时闪上一个机种的数字。它就挨在搜索框右边（**不用 `margin-left: auto` 推到最右**）。**它同时是「只看已入库」的开关**：单击即按下（点亮成实心主色 + `aria-pressed`，与播放页「加速模式」那类开关同一套写法），再点一下恢复全部。**按钮上的比例不随搜索/过滤变**（分母恒为该机种榜单的总行数，它表达的是「这个机种收集了多少」）。
  - **两者是 AND**：`rankingKeywordMatches`（先按词筛）→ `rankingVisibleItems`（再按库存筛），表格与分页条都按 `rankingVisibleItems` / `rankingVisibleTotal` 来，任一个条件变化都把页码打回第一页。空态按「是谁把结果清空的」分流：有关键词 → `没有匹配到名称含「xxx」的游戏。`；关键词 + 已入库同时开着且词是搜得到的 → `匹配「xxx」的游戏都还没入库。`（否则用户看着按钮上的 25 / 100 会以为是搜索词的问题）；只有已入库 → `这个类型下还没有已入库的游戏。`
- **已知取舍**：中文为空的约 2,632 行只能靠英文搜到；缩写（`ff vii`）搜不到，因为英文按整词索引；不做拼音、错别字容错、中英互搜。

## HTTP

HTML 由 Vue 路由负责，FastAPI **只返回 JSON**。路径一律在 `/api/` 下。稳定路径以下文「前端路由」「后端（摘要）」两表为准。

信封：成功 `{ "ok": true, "data": ... }`；失败 4xx/5xx + `{ "ok": false, "message": "中文" }`。

### 前端路由

| path | 说明 |
|------|------|
| `/login` | 登录 / 注册（无 Layout，页内切换） |
| `/` | 重定向到 `/games`（首页即游戏中心） |
| `/games` `/games/manage` `/games/discover` `/games/flash/:gameId` `/games/play/:gameId` `/games/h5/:gameId` | 游戏中心 / 游戏管理 / 游戏发现（检索 + 榜单） / Flash 播放页 / 主机(EmulatorJS)播放页 / H5 播放页；旧路径 `/games/search` 重定向到 `/games/discover`（保留 query） |

### 后端（摘要）

以 `backend/*/router.py` 为准，下表列稳定路径；除注明外都要登录，写操作带 `X-CSRFToken`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 免登录纯文本 `ok` |
| GET | `/api/csrf` | 免登录取 CSRF token |
| POST | `/api/register` | 注册（免登录，body `{username, password}`，成功即登录） |
| POST | `/api/login` | 登录（免登录，body `{username, password}`） |
| POST | `/api/logout` | 退出 |
| GET | `/api/me` | 当前用户（body `{username}`） |
| GET | `/api/tools` | 功能注册表（导航用，前端目前不消费） |
| GET | `/api/games` · `/api/games/status` | 游戏列表 / 类型与可上传格式 |
| GET / POST | `/api/games/recent?limit=` | 最近游玩列表（倒序）/ 上报一次开玩（body `{game_id}`） |
| POST | `/api/games/stats/playtime` | 累加一段游玩时长（body `{game_id, seconds}`，播放页心跳 best-effort 上报） |
| PUT | `/api/games/stats/<id>/playtime` | 手动设置总时长（body `{hours}`，覆盖为该值） |
| PUT | `/api/games/stats/<id>/progress` | 手动设置游戏进度（body `{progress}`：`not_started`/`in_progress`/`completed`） |
| GET / POST | `/api/games/manage`；GET / PUT / DELETE `/manage/<id>` | 游戏管理（POST 为 multipart：name/cartridge_id/description/file[+cover]，一步建条目并按本体扩展名定类型；本体/封面也可改用直链 `body_url`+`body_game_type` / `cover_url`）。**GET 是服务端分页**：`page`（默认 1）/ `page_size`（默认 5，上限 100）+ `game_type` / `q` 过滤，返回 `{total, page, page_size, items}`；排序固定为**更新时间倒序 → id**（`_manage_order_clauses()`，最近改动的排最前；编辑、换本体/封面、传攻略都会刷新 `updated_at`）；越界参数在 service 里收敛（不返回 422），页码越界返回空 items + 真 total，页码收敛交给前端 |
| PUT | `/api/games/manage/<id>/cartridge-id` | 改卡带ID（body `{cartridge_id}`）：搬三类磁盘目录 + 改写库里所有引用它的路径列。非法/被占用/目标目录被占/搬不动 → 400，游戏不存在 → 404，新旧相同 → 200 空操作 |
| POST | `/api/games/manage/<id>/assets` | 换本体/换封面（kind=game\|cover，给 `file` 或直链 `url`[+`game_type`]；h5 传 .zip 由后端校验后保存）。**换本体必须与当前 `game_type` 一致**（按扩展名判定，同类型内可换后缀），跨类型返回 400 且旧档不动；成功后更新 `crc32`/`size`/`game_path` 并删除旧后缀文件 |
| POST | `/api/games/manage/import` | 从 7k7k/4399/flash.homes 游戏页地址搬运（body `{url, cartridge_id}`，解析下载后入库，Flash 或 H5） |
| POST | `/api/games/manage/<id>/guide` | 上传攻略（multipart：单个 `file`，ZIP 或 PDF；ZIP 解压后根目录必须含 `index.html`，整包套单层目录会自动剥掉、只校验不解压；PDF 校验 `%PDF-` 头、原样存储；一种会替换另一种） |
| DELETE | `/api/games/manage/<id>/guide` | 删除攻略（ZIP/PDF 都删）并清空 `games.guide_kind`；幂等，没有攻略也返回 200，返回更新后的管理条目 |
| GET | `/api/games/<id>/cover` · `/play` | 封面 inline / 本体下载 |
| GET | `/api/games/<id>/h5/<资源路径>` | H5 资源 inline（沙箱安全头；唯一免登录业务接口，入口固定 index.html；首次访问会按需解包到运行时根） |
| GET / HEAD | `/api/games/<id>/guide/<资源路径>` | ZIP 攻略的静态资源（**需登录**，无沙箱头，入口固定 index.html；首次访问会按需解包到运行时根） |
| GET / HEAD | `/api/games/<id>/guide.pdf` | PDF 攻略（**需登录**，从数据根直读，`application/pdf` inline，不解包） |
| GET / PUT | `/api/games/emulator-settings?game_type=` | 模拟器设置（键位/选项/金手指）按平台读 / 整体覆盖写（存 SQLite） |
| GET / POST | `/api/games/saves?game_id=` | 云端存档列表 / 创建快照 |
| PUT | `/api/games/saves/<snapshot_id>/parent` | 设置/清除快照父级（body `{parent_id}`；null = 顶层；父级须同用户同游戏、不能是自身、不能成环） |
| POST | `/api/games/saves/<snapshot_id>/move` | 在同级兄弟中挪到第 `to_index` 位（0 起，body `{to_index}`），返回整份有序列表；只改被移动那一行的分数 |
| GET / PUT / DELETE | `/api/games/saves/<snapshot_id>` | 快照详情 / 改备注 / 删除（删除时直接子级改回顶层） |
| GET | `/api/games/saves/<id>/files/<file_id>/download` | 取单个存档文件（.sol/.state） |
| GET / POST | `/api/games/screenshots?game_id=` | 本人该游戏的截图列表 / 上传一张（multipart：game_id/description/file） |
| GET | `/api/games/screenshots/<id>/image` | 截图本体 inline（需登录，越权 404） |
| PUT / DELETE | `/api/games/screenshots/<id>` | 改截图描述（≤15 字）/ 删除 |
| POST | `/api/games/screenshots/<id>/move` | 拖到指定位置（body `{to_index}`），返回整份有序列表 |
| GET / POST | `/api/games/gallery?game_id=` | 该游戏的**共享**图集列表 / 上传一张（同上 multipart） |
| GET | `/api/games/gallery/<id>/image` | 图集图片本体 inline（需登录；共享，但不匿名开放） |
| PUT / DELETE | `/api/games/gallery/<id>` | 改图集图片描述（≤15 字）/ 删除 |
| POST | `/api/games/gallery/<id>/move` | 拖到指定位置（body `{to_index}`），返回整份有序列表 |
| GET | `/api/games/search?q=&console_id=&page=&page_size=` | 游戏检索（只读名录索引，服务端分页；索引未构建时返回 `indexed:false` 与空列表） |
| GET | `/api/games/search/consoles` | 游戏检索的机种下拉候选项（`{id, name, platform_id}`；同名机种已合并成一项） |
| GET | `/api/games/search/ranking?console=` | 游戏榜单（只读，不分页；`console` 传机种键；榜单未加载时返回 `has_ranking:false` 与空列表；与库存关联上的行带 `game_id`/`path`，没命中为 `null`） |
| GET | `/api/games/search/ranking/consoles` | 游戏榜单的机种下拉候选项（只列榜单里出现过的机种，`{platform,label,playable}`）与 `default_console` |

服务端只提供 `/api/` 与 `/health`，没有服务端渲染的页面路由。

## 前端框架层

1. **`request.js`：** 唯一 axios 实例。注入 CSRF、cookie；401 单飞跳登录；错误信封转中文 Message；`notShowError` 可关弹窗。失败一律 reject 一个带 `reported` 标记的 Error（`reported=true` = 拦截器已经弹过提示），所以页面 catch 里要补提示得写成 `if (!err.reported) ElMessage.error(...)`，否则同一条错误会弹两次。
2. **`permission.js`：** 白名单 `/login`；未登录去登录页；已登录访问登录页去 `/`。
3. **`auth.js`：** 可缓存用户名等展示字段。登出必须清约定 key 清单；新增「记住的页面状态」时同步维护。
4. **路由 meta：** `title`、`hiddenInMenu`、`icon`。Layout 里 `buildMenuFromRoutes()` 生成菜单。新增页面 = 加一条带 meta 的子路由。
5. **`components/common/`：** 跨工具复用目录，必须存在。自定义弹窗 `AppDialog`、按钮 `AppButton`、分段控件 `AppSegmented`、分页 `AppPagination`、空状态 `AppEmpty`、复制 `CopyButton` 放这里；在 Element Plus 上包一层，不要在 `views/` 里堆样式。**按钮统一走 `AppButton`**：只有两种类型——`secondary`（白底、`#0098EE` 字与框，除删除外的所有操作）与 `danger`（白底、`#FF3320` 字与框，删除类操作）；`text` 是去掉背景和边框的形态（行内文字、浮动 `✕`），`pressed` 是开关的选中态（浅蓝底 + 深蓝边），都不算第三种类型。`size`（sm 28 / md 32 / lg 40）× `tone`（light / dark / image / overlay，只换配色），另有 `block` / `iconOnly` / `round`；播放器标题栏与存档管理用 `tone="dark"`，不再手写深色按钮 CSS。禁用态背景/边框 `#EEEEEE`、文字 `#AAAAAA`，不用透明度；焦点只变边框色，不加外环。**分段/标签统一走 `AppSegmented`**（tone / size 同一套 token）。尺寸、圆角、状态色、深色表面全部来自 `styles/index.css` 的 `--app-*` token，同时覆盖 Element Plus 的 `--el-color-primary*` / `--el-color-danger*` / `--el-border-radius-*` / `.el-button` 尺寸；**页面里不要再新写原生 `<button>` 或按钮 CSS**（唯一例外是 `AppSegmented` 自身），需要新外观先扩 `AppButton` 的 `text` 或 `tone`。CopyButton 的 20px 卡带 ID 药丸是可复制的数据 chip，不是第三种按钮类型。`AppDialog` 的 `footer-mode` 支持 default / confirm-only / close-only / custom / none；确认框统一走 `utils/confirm.js` 的 `confirmAction` / `dangerConfirm` / `dangerPrompt`，页面里不再直接调 `ElMessageBox`。小件（按钮、分段、空状态、复制、分页）在 `main.js` 全局注册；弹窗按需引入。Vite 别名 `@components` → `src/components`。
   分页条 `AppPagination`（游戏管理 / 游戏发现共用）：父级给 `page` / `total` / `pageSize`，翻页时先发 `update:page` 再发 `change`（父级的 `change` 处理函数读自己的 page ref，顺序反了会拿旧页码去请求）；**只有一页时整块不渲染**；**左右方向键翻页**在组件内部（挂在 window 冒泡阶段），守卫：带修饰键的放行（`Alt+←` 是后退、`Ctrl/Shift+←` 是选词）、按住连发与输入法组字忽略、焦点在 input/textarea/contenteditable/`.el-select/.el-popper` 里放行、`body.el-popup-parent--hidden`（Element Plus 的 `useLockscreen`，dialog/message-box/drawer 都加）时放行、单页时不拦默认行为。
6. **Pinia：** 不要把 Fernet 密钥放进 store。不要做参考项目那种全表列配置，除非以后明确要求。
7. **不要**上 WebSocket，除非以后某个工具明确需要实时。

## 界面

- Layout：侧栏菜单由路由 `meta` 动态生成，顺序为游戏中心、游戏管理、游戏发现。**侧栏是浮层**：常驻收起、鼠标靠近屏幕左边缘滑出，展开时盖在页面之上，不占位、不挤压内容
- 所有界面文案必须是中文
- **一律不做鼠标悬浮提示**：图片、按钮、文案都不要 `title`（原生悬浮小黄条）也**不要 `el-tooltip`**。需要说明就写成常驻小字，或者用「点开才看到」的展开层；凡是加内容默认都不加悬浮提示。唯一例外是**模拟器/引擎自己渲染的按钮**（EmulatorJS 播放器内部那套 UI，不是我们写的）。两个保留项也不是悬浮提示，别误删：弹窗标题 `AppDialog` 的 `title` prop、`<iframe title="…">`（无障碍用，浏览器不会弹提示）
- 表单在 Vue 里提交到 `/api/`；复制密码、上传进度可用少量本地逻辑
- 用 Element Plus 作底；自定义外观走 `components/common/` 的 `App*` 封装，不要再加 Bootstrap/Tailwind，除非用户明确要求
- 空状态要覆盖：未登录（守卫处理）、列表加载失败、暂无游戏（统一用 `AppEmpty`）

## Docker（分离完成后必须有）

**基础镜像一律固定到「补丁版本 + 发行版代号」，不许用浮动标签**（`python:3.12-slim`、`node:22-alpine`、`nginx:1.27-alpine` 这类会在上游重发时悄悄换掉语言版本与 Debian/Alpine 基线，构建产物跟着变且难排查）。升级基础镜像 = 手动改 Dockerfile 里那一行 + 跑一遍 `make test`，不是自动跟随。

**api 镜像（`backend/Dockerfile`）**

- 构建上下文为仓库根目录（`docker-compose` 中 `context: .`，`dockerfile: backend/Dockerfile`）
- `python:3.12.15-slim-trixie`，工作目录 `/app`
- 安装根目录 `requirements.txt`，仅复制 `backend/` 包，给 `backend/entrypoint.sh` 加执行位
- `EXPOSE 8910`
- 游戏检索的 CSV 名录（`backend/search/csv/`，约 4MB）与游戏榜单的 `backend/search/ranking/ranking.csv` **随镜像一起走**：`COPY backend/ ./backend/`
  把它带进 api 镜像，容器启动时才能在缺索引时自建一次。换名录数据要重建镜像。
- `ENTRYPOINT` 是 `/app/backend/entrypoint.sh`：先调 `backend/mount_guard.py::require_mounted()`（**两个根的宿主路径在 Windows 盘挂载前缀下**——按 compose 传进来的 `STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR` 判断，前缀可配、默认 `/mnt`——而容器里缺 `.mounted` 哨兵时，打中文日志 → 等 5 秒 → 以非零码退出，退的是**容器主进程**，compose 的 `api.restart: unless-stopped` 随即把容器重新拉起，循环重试直到哨兵出现；宿主目录不在那个前缀下就直接放行），再 `exec "$@"` 跑 CMD。判断与日志只有 `mount_guard.py` 一份，脚本不重复实现
- `CMD`：`gunicorn backend.asgi:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8910 --workers 1 --threads 8 --timeout 300`（300s 是为了长上传/流式下载不被 worker 超时杀）

**web 镜像（`frontend/Dockerfile`）**

- 构建上下文为 `frontend/`
- 构建阶段 `node:22.23.3-alpine3.24` 打出 `dist`
- 运行阶段 `nginx:1.27.5-alpine3.21`，`try_files` 回 `index.html`
- `/api/` 与 `/health` 反代到 `http://api:8910`；`client_max_body_size 128m` 是上传网关
- 只为站点开一个 443 server（**没有 9443，也没有任何对象存储反代**）

**`docker-compose.yml`**

- `api`：`build.context: .` + `dockerfile: backend/Dockerfile`，两个宿主目录 bind `${STORAGE_HOST_DIR:-./data/storage}:/data` 与 `${RUNTIME_HOST_DIR:-${STORAGE_HOST_DIR:-./data/storage}}:/runtime`，不对外发端口，**没有 `env_file`**（后端不读 `.env` 文件）；`environment` 里只把 `STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR` 传进容器，供启动时的哨兵前缀判断（见 `backend/mount_guard.py`）
- `web`：`build: ./frontend`，`ports: ["${WEB_HTTPS_PORT:-443}:443"]`（**只支持 HTTPS**：不发布 80，也没有 http→https 跳转；只发布宿主侧端口，容器内固定听 443，换端口只改 `.env`），证书目录 bind `./certs:/etc/nginx/certs:ro`（证书随仓库提交），`depends_on: [api]`
- **没有 `volumes:` 段**
- api / web `restart: unless-stopped`

**宿主目录 bind 的时序要求：** 目录若在 WSL 发行版（Ubuntu-22.04）的文件系统上（`/mnt/…` 这类 Windows 盘挂载路径），而 Docker Desktop 守护进程先于该发行版启动——开机时 bind 源路径不可达，docker 会挂一个空 tmpfs 顶上，容器里看起来就像「文件全没了」。**这种根由哨兵拦住**：判断按宿主路径 `STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR`（容器里的 `STORAGE_ROOT` / `RUNTIME_ROOT` 固定是 `/data` 与 `/runtime`，看不出宿主路径），落在 Windows 盘挂载前缀（`config.WINDOWS_MOUNT_PREFIX`，默认 `/mnt`）下、而容器里又没有 `.mounted`（空挂载天然没有它）时 `require_mounted()` 拒绝启动 → 容器退出 → `restart: unless-stopped` 反复重启，直到盘挂上、哨兵可见，服务自己恢复（窗口期内不会有任何写入，也就不会丢）。**根不在那个前缀下（普通 Linux 目录）不做任何检查，直接启动**。前缀下的目录**要人工建一次哨兵**：`touch "$STORAGE_HOST_DIR/.mounted"`、`touch "$RUNTIME_HOST_DIR/.mounted"`（两行指向同一个目录时就是同一个文件），换新目录要重新建一次；两个 `*_HOST_DIR` 本身仍应指向 docker 启动前就可达的固定路径（别指外挂盘的临时挂载点，也别放会被 `git pull` 覆盖的仓库内）。

**备份**：没有内置备份脚本，数据都在宿主目录里（`STORAGE_HOST_DIR`），直接拷就行——**SQLite 库不在里面**（它在运行时根里，一直被写、外部客户端拷不动），所以这份备份天然干净。SQLite 另有一层自动兜底：`create_app()` 启动时调 `backend/backup.py::backup_database()`，之后每 `BACKUP_INTERVAL_SECONDS`（1 小时）由一个守护线程再备一次；**当月只有一份** `<YYYY-MM>.db`，写在**数据根**的 `db/` 里（不是库所在目录），**每次整份重写**（先写 `.tmp` 再 `os.replace`，读的人永远看到完整文件），所以快照最多落后一小时。用 sqlite3 的 backup API 而非拷文件（服务一直在写，裸拷会撕裂），失败只记 warning 不拦启动，**不做还原功能**。存档（`save/`）不可重建，本体/封面/H5 资源都能重传。

`docker compose up --build` 之后，浏览器打开 **https://localhost**（只支持 HTTPS，80 端口不发布）。

本地开发：`uvicorn backend.asgi:app --reload --port 8910` + `cd frontend && npm run dev`。本机数据根默认是仓库下的 `data/storage`，不在 `/mnt` 下、**不需要哨兵文件**；只有你把数据根（或运行时根）指到 WSL 的 Windows 盘（如 `STORAGE_ROOT=/mnt/x/xgame/storage`）时才要先 `touch /mnt/x/xgame/storage/.mounted`，否则 uvicorn 起来就打一条日志、等 5 秒退出。测试不受影响（`TESTING` 下跳过检查）。

**游戏发现要先建索引**：在项目根目录跑一次 `make index`，它会在 `<数据根>/db/game.db` 生成只读名录索引与榜单（可重复执行、直接覆盖）。没建时页面会提示、接口返回 `indexed:false`，不会报错；榜单 CSV 后放进来的话，重启服务也会就地补一次。数据根若是 Docker 以 root 建的（默认 `./data/storage` 跑过一次 compose 之后就是），先 `sudo chown -R "$USER" ./data/storage`——`make index` 也会自己提示这一步。

## Windows 解压即用包（第二条交付路线，与 Docker 并存）

Docker 是正式运行方式；「解压即用」包是给**一台 Windows、用户不懂命令行**的场景。两者
**数据格式完全一致**（同一份数据目录两边都能读），但**绝不允同时打开同一份数据目录**：
Windows 侧与 WSL/容器侧的文件锁互相看不见，同时写就是坏库。

```bash
make win        # 在容器里组装（构建环境镜像没有就先建一次）：dist-win/xgame_v<版本>.zip
make win-image  # 只构建/更新那个构建环境镜像
```

**整个组装在容器里跑**（`packaging/windows/Dockerfile.build`），宿主机只要有 Docker——不需要
node / python / curl / zip，也不碰宿主机自己的 `frontend/node_modules`。**能固定的依赖全预置在
镜像的 `/opt/winbuild` 下**（Windows 版 CPython、win 轮子、前端 node_modules、EmulatorJS 资产），
所以组装那一步不联网；镜像 tag =「Dockerfile + 它 COPY 的那些输入文件」的哈希，改了自动重建、
没改一直复用（`WINBUILD_NO_CACHE=1 make win-image` 强制刷新）。构建环境用 **Debian（glibc）而不是
Alpine（musl）**，才能让容器里装的前端依赖（rolldown 之类是平台相关二进制）与宿主机同一套。
容器以宿主机用户身份跑；包内自检（`smoke_win.py`）由宿主机在构建后补跑（容器里没有 binfmt_misc）。
运行时是 python-build-standalone 的可重定位 CPython，**release 与 sha256 钉死在 `runtime.env`**
（唯一的供应链入口，升级时只改它）。

**版本号只有一个出处：`scripts/version.sh`**（Docker 路线与 Windows 包共用）。HEAD 停在最新 tag
上就是 `v1.0.0`，在 tag 之后的提交上则是 `v1.0.0-<HEAD 提交时间毫秒>`。前端在构建期拿到它显示在
侧栏标题后，同时写进 `web/version.txt` 供已打开的页面探测更新，也进 zip 的文件名。包里**不做版本
比较**（没有自动升级，谁新谁旧看文件名就行）。

这条路线与 Docker 的差异，逐条都是被逼的，改动时要一起考虑：

- **没有 nginx**：前端 dist 由后端托管（`backend/static_site.py`），**只在 `STATIC_DIR` 非空时注册**，
  Docker 路线一条静态路由都没有。它的行为规范是 `frontend/nginx.conf.template`，七条语义
  （SPA 回落、`/version.txt` 缺失即 404、三个 immutable 前缀未命中即 404、两个入口文件 no-cache、
  **MIME 用显式表不用 `mimetypes`**、路径安全）由 `tests/test_static_site.py` 钉住。
  改 nginx 配置时**必须同步改这个模块**。
- **没有 gunicorn**：Windows 上跑不了（依赖 fork/fcntl），改单进程 uvicorn，由启动器**进程内**跑
  （不起子进程：Windows 上 terminate 是硬杀，SQLite 会留在半路）。`--workers 1` 的语义靠单进程满足。
- **走 http 不走 https**：局域网里手机/平板不会信任自签证书。但 session cookie 默认带 `Secure`
  （`SESSION_COOKIE_SECURE`），http 下浏览器不保存它、登录会静默失效，所以启动器把它设成 false。
- **没有 `client_max_body_size`**：`backend/request_limit.py` 顶上（超限 413、分块传输 411），
  两条路线都挂，Docker 上 nginx 先拦。
- **升级是手动的，包里一行自动升级的代码都没有**：关窗口 → 解压新包到新目录 → 把 `data` 搬过去。
  自动升级要停下来改自己的目录，于是每一步都在跟 Windows 的文件锁较劲（脚本得先复制到 `%TEMP%`
  再执行、服务得先优雅退出、旧目录可能删不掉），换来的只是少点几下鼠标。
- **打 zip 用 `packaging/windows/make_zip.py`，不用命令行的 `zip`**：条目直接躺在压缩包根上
  （不套一层目录），且非 ASCII 名字必须带 UTF-8 标记位（bit 11）——Info-ZIP 不设它，Windows
  资源管理器就按 OEM 代码页解释，中文文件名全成乱码（WinRAR 会自己猜 UTF-8，所以预解压窗口里
  看着正常，最容易骗过构建者）。

包内脚本的编码约定：`.cmd`/`.bat` **内容纯 ASCII**（cmd 按 OEM 代码页解析批处理，中文混进去
是乱码与解析出错的经典来源），面向用户的中文一律由 Python 或 PowerShell 输出；`.ps1` 存成
**UTF-8 带 BOM**（否则 PowerShell 5.1 按 ANSI 读，中文乱码）；`说明.txt` 也带 BOM（记事本）。

**「来自 Internet」标记（MOTW）**：从网上下载的 zip 解压出来的每个文件都带它，于是**每双击
一次 `.cmd`/`.bat`**，Windows 都先弹一次「打开文件 - 安全警告：无法验证发布者」（点「运行」
能继续，所以不致命，但每次都得点）。没有代码签名、没有安装程序就绕不过去——只能让用户
**解压之前**右键 zip 勾「解除锁定」（`说明.txt` 第一节第 1 步），或者解压后跑一次
`解除锁定.bat` 补上。启动器 `still_locked()` 启动时探一下自己那几个 `.cmd` 的
`:Zone.Identifier` 数据流，还在就提醒一句。

## 实现时要生成的配置文件

- `.env.example` — 全部键（`STORAGE_HOST_DIR`、`RUNTIME_HOST_DIR`、`WEB_HTTPS_PORT`）、默认值、**每个键一行中文注释**
- `.gitignore` — `.env`、`data/`、`__pycache__/`、`.venv/`、`*.pyc`、`frontend/node_modules/`、`frontend/dist/`
- `README.md` — 中文：如何 Docker 运行、如何同时起 Vite 与 FastAPI、如何注册第一个账号、游戏文件放在哪

不要提交真实密钥。

## 代码风格

- Python 3.12，service 对外方法写类型标注；4 空格缩进
- 拆模块，不要把 SQL 写进 router
- service 抛领域异常；router 转成 JSON 4xx（`message` 用中文）
- 不要大段注释掉的代码；功能路径里不要留「TODO: 以后再实现」
- 日志：请求/操作用 INFO；**禁止**记录登录密码、`SECRET_KEY`
- 代码注释仅在需要解释「为什么」时使用，用中文
- 前端：4 空格；api 函数命名 `xxxAPI`

## Git 分支与提交命名规范

分支名与提交标题统一用**类型前缀**表达意图：类型是英文小写单词，描述部分用中文或英文短词。

**常用类型**

| 类型 | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复缺陷 |
| `docs` | 文档改动 |
| `refactor` | 重构（行为不变） |
| `test` | 补写或修改测试 |
| `chore` | 构建、依赖、配置等杂项 |

**分支名**

格式：`<类型>/<描述>`，小写，单词用 `-` 连接，描述尽量简短（两三词内）。

- 好：`feat/cartridge-id`、`fix/h5-upload`、`docs/architecture-note`
- 坏：`feature_eye`（下划线）、`fix/login_timeout_issue`（太长）、`FEAT/x`（大写）

**提交标题**

格式：`<类型>: <中文短语>`，冒号后跟一个空格，短语用中文。

- 好：`feat: 游戏增加卡带ID`、`fix: 修复 H5 重传后资源 404`、`docs: 补充分支命名规范`
- 坏：`feat`（只有类型）、`feat:xx`（冒号没空格）、`fix: 修 bug`（太模糊）

一个提交只做一件事；一次提交包含多个改动时，按改动拆分提交。

## 测试（实现时必须带）

```
make test
```

等价于分开跑 `python -m pytest` 与 `cd frontend && npm run lint`。都在本机执行、不需要 Docker（测试用临时 SQLite + 临时 `STORAGE_ROOT`，直接打真实文件系统）。
用 `python -m pytest` 而不是裸 `pytest`：后者不把仓库根加进 `sys.path`，会 import 不到 `backend`。

**跑测试的粒度**：实现过程中只跑**本次改动涉及功能**的用例（`-k` 选择器或单个测试文件），不要每改完一处就全量跑——
全量 `make test` 由用户定期执行。**只改文档（含本文件、`CLAUDE.md`、`docs/`、技能说明）不需要跑任何测试**。

最低要求：

- 注册（合法/非法用户名、重名、注册即登录）与登录锁定
- `LocalStorage` 读写/覆盖/删除/目录替换，以及越界路径（`..`、绝对路径）被拒
- 游戏创建必填卡带ID、自动转大写、全局唯一、`PUT` 改不动；上传后文件按 `game/{类型}/{卡带ID}/…` 真实落盘
- 改卡带ID：三类目录都搬了（含**换过类型**的历史 `save/{用户}/{旧类型}/{旧ID}`、`image/{用户}/{旧类型}/{旧ID}`）、三张子表的 `file_path` 都改了、多账号都搬、改完素材与存档截图仍读得到、磁盘上不留旧 ID 的残迹（数据根与运行时根都要断言）；非法/被占用/游戏不存在/新旧相同/源不在而目标在/搬不动回滚/Windows 路径过长各分支
- `/health` 未登录返回 200
- 未登录访问游戏接口（列表/状态/封面/本体/管理/存档/截图/最近游玩/攻略）一律 401，仅 H5 资源接口可匿名访问
- 云端存档按 (user, game) 隔离：读他人快照返回 404；父子层级：第一条 NULL、后续自动挂同组最新、设父/清父、他人快照或他人父级 404、跨游戏 400、自父 400、成环 400、删除父节点后直接子级变顶层（孙级不变）、同一 `created_at` 按 id 倒序、删游戏连整棵树一起清、老库补 `parent_id`/`sort_order` 列与索引；**同级排序**：新快照追加到末尾（越新越靠下）、`move` 越界 400、原位空操作、只改被移动那一行的分数、间隙耗尽时整份重排后顺序仍正确、他人快照 404
- 游戏截图按 (user, game) 隔离（列表看不到、图片/改描述/移动/删除一律 404）、落盘 `image/{用户名}/{类型}/{卡带ID}/{uuid}.{后缀}`、认不出的图片内容 / 空文件 / 超限 / 描述超 15 字 / 拖动下标越界返回 400、分数耗尽时的整份重排后顺序仍正确、删游戏后行与文件都不留
- 模拟器设置写接口未登录 401、按 (user, game_type) 隔离、非法 game_type 或 payload 返回 400
- 机种词表（`tests/test_platforms.py`，拿真实数据跑）：机种 id 与 EmulatorJS `getCores()` 的键集合逐字一致（引擎升级后这条会红）、别名索引无冲突且 `id`/`label` 也能反查、可玩机种的扩展名互不重叠且默认后缀在白名单里、`GAME_TYPES` = flash/h5 + 可玩机种且顺序一致、前端 `gameTypes.js` 的 label 与词表逐字一致、**两份真实 CSV 的每个机种名都能解析或明确列在「未收录」名单里**、检索侧合并后正好 32 项、榜单侧没有两个写法落到同一机种
- 游戏发现：未登录 401；索引缺失时返回 `indexed:false` + 空列表且**服务端不建文件**；坏库/版本不符 503（中文 message）；结尾标签不进索引而主标题搜得到；三元组去重口径；归一化不变量（中文名中间取两个相邻汉字必命中）；`ORDER BY` 的 `g.id` tiebreaker 让翻页不重不漏；**跑完全部只读路径后索引文件逐字节与 mtime 都不变**、库文件与目录置为只读后接口照常工作；机种归一的落库结果（`console.name` 是统一名、`platform_id` 是机种键、未收录机种保留原文且为 null、机种按词表顺序排）、`ensure_game_index()` 在版本不符时会重建而重建失败时保留旧库。榜单：CSV 解析边界（BOM/CRLF/表头/引号内逗号/机种大小写与写法归一/卡带 ID 分隔符与数量上限/列数与序号错误带行号）、`build_index` 的 strict 与非 strict、**启动就地补载幂等（指纹一致时字节与 mtime 都不变）**、内容变了要按 SHA-256 重载、CSV 缺失保留旧榜单、只读库降级、榜单接口的 `indexed`/`has_ranking`/机种清单带统一名与 `playable`/默认机种 `nes`（FC）/未知机种/版本过旧 503。榜单与库存的关联：卡带 ID 命中给出 `game_id` 与按类型算的 `path`、大小写不敏感、一行两个 ID 第二个命中也算、带空格/点的原文不报错也不命中（**钉住「不复用 `validate_cartridge_id`」**）、`game_path` 为空的不链、**删掉游戏后下一次请求就不再链**（证明是请求期现算）、不注入回调时完全不关联、比例的数据契约（`path` 非空的行数 / 总行数）；`map_for_cartridge_ids` 的归一与原样键、空入参不查库、`play_path()` 三个分支与 `GameItem.path` 一致

## 首次搭建已完成

SPA + API 分离、开放注册、游戏中心（Flash/HTML5/主机 ROM 三播放、Flash/模拟器双云端存档、主机截图图库）、游戏管理（上传/直链/搬运 + 卡带ID）、compose（web+api，游戏文件走宿主目录）均已落地。新增/修改直接走上文各「功能：」段与「以后再加工具」；动手前先读 `docs/architecture.md` 与 `docs/data_dict.md`。

## 以后再加工具

1. `backend/<name>/`，含 router（`/api/<name>`）+ service
2. 在 `create_app()` 注册 router
3. 写入 `registry.py`（名称、描述用中文）
4. `frontend/src/api/<name>.js` + `views/<name>/` + 路由 meta
5. 工具专用组件放 `components/<name>/`；跨工具 UI 只改 `components/common/`
6. 测试；除导航/注册表外，不要改其它工具

若工具变重，保持同一套 service 接口，以便以后迁到 Compose 微服务。

## 用户意图

用户要求写代码时：直接实现，不要只复述本文档。

用户只要文档时：不要加应用代码。

**默认不做截图 / 浏览器验证**：除非用户当次明确要求，改动完成后不要起浏览器或容器去截图核对（很慢、很费 token），跑 `npm run lint`（必要时 `pytest`）即可交付，由用户自己看效果。
