# AGENTS.md

本仓库中编码 Agent 必须遵守的约定。

本仓库是**个人自托管游戏平台**。人读 `docs/architecture.md`。写代码、改代码时以**本文件**为准。

## 当前状态

前后端分离已落地：Vue 3 SPA + FastAPI JSON API。只做游戏：游戏中心（Flash + HTML5 + 8/16-bit 主机 ROM，浏览器内 Ruffle/EmulatorJS/沙箱 iframe 游玩，Flash 与模拟器都支持按账号云端存档，H5 仅游玩）与游戏管理。SQLite 与文件存储结构以 `docs/data_dict.md` 为 schema 权威。实现时以本文件「目标约定」为准。

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
**数据：** SQLite 10 表 + 文件根目录的路径规则见 `docs/data_dict.md`

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
  src/views/                 # login / games（index、manage、flash-player、emulator-player、h5-player）
  src/components/common/     # 跨工具复用（必须有）：AppDialog、AppButton、筛选、空状态等
  src/components/games/      # 游戏专用：GameShell、GameCover(游戏中心卡片的封面渲染：Flash 光盘/GB-GBC 卡带/普通封面)、
                             #   FlashPlayer、FlashSaveManager、EmuSaveManager、
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
  public/flags/              # 卡带类型（地区）国旗，22×16 PNG，按国家/地区英文全称命名（Japan/USA/…）
  public/game-asset-sw.js    # Flash 播放页资源缓存 SW（按 key+updated_at）
  public/emulator-host.html  # EmulatorJS 播放宿主（iframe 隔离；__ejsRpc：capture/load/screenshot/videoInfo）
  public/emulatorjs/         # EmulatorJS 引擎资产（构建生成，gitignore）
backend/__init__.py          # create_app()；装配 app.state 存储后端/mailer，注册 router
backend/asgi.py              # 生产 ASGI 入口
backend/config.py            # 配置（全部写死在这里，含 SECRET_KEY）
backend/database.py          # engine、init_db、SQLite 路径解析
backend/backup.py            # 启动时的 SQLite 月度备份（当月一份，不做还原）
backend/mount_guard.py       # 数据根目录的哨兵文件 .mounted（启动时缺了就建）
backend/deps.py              # 依赖注入：session、登录态、各 service 依赖
backend/csrf.py              # CSRF 中间件
backend/cli.py               # init-db
backend/Dockerfile           # api 镜像（ENV STORAGE_ROOT=/data + gunicorn）
backend/auth/                # 注册/登录/退出（密码 + 失败锁定）
backend/tools/registry.py    # 功能列表（给 /api/tools）
backend/games/               # 游戏 router/service/paths + 云端存档 save_* + 游戏截图 screenshot_* + 游戏图集 gallery_* + 模拟器设置 settings_* + 游玩统计 stats_* + 搬运 importer + 网络上传 remote
backend/storage/             # 跨模块：types(协议与 StoredObject) / local(LocalStorage) / access(流式下载响应)
tests/                       # pytest（test_auth / test_backup / test_mount_guard / test_local_storage / games / game_saves / game_screenshots / game_emulator_settings / game_recent / game_stats）
docker-compose.yml           # web + api（宿主数据根目录 bind：STORAGE_HOST_DIR → /data）
requirements.txt
.env.example
.gitignore
```

不要再加 Jinja2 模板或 `backend/static/`。

`data/` 只放本地运行时的 SQLite 与默认的文件根目录，加入 gitignore。

**本项目不使用任何 docker 具名卷**：compose 里 **数据是一个宿主目录** `STORAGE_HOST_DIR`（默认 `./data/storage` → 容器 `/data`，后端读 `STORAGE_ROOT`），游戏文件与 SQLite 都在这一个根目录下（库固定是 `<根>/db/app.db`，见配置项 `DB_SUBDIR`）；**证书**是仓库里的 `certs/`（`cert.pem` / `cert.key`，随仓库提交），compose 只读挂给 web 的 `/etc/nginx/certs`。**不要新增 `volumes:` 具名卷**。**注意宿主 bind 的时序要求**（源目录必须在 docker 启动前可达，否则会被挂成空 tmpfs），见 `docker-compose.yml` 末尾注释与 `docs/architecture.md` 的「排障」。

## 架构规则（必须遵守）

1. **应用工厂。** 对外入口是 `create_app()`；生产 ASGI 入口为 `backend/asgi.py` 的 `app`。
2. **一个工具一个包。** `router.py` 管 HTTP（只返回 JSON）；`service.py` 管领域逻辑。SQLModel、文件读写、加密不要写进 router。
3. **service 是以后拆微服务的边界。** `service.py` 里禁止使用 FastAPI `Request` / `session`；存储后端等依赖一律由构造函数传入。
4. **前端分层。** 页面(view) → `api/*`（`xxxAPI`）→ `request.js` → FastAPI。新增接口只改 api 层和后端 router，不碰 `request.js`。
5. **通用组件。** 自定义风格的弹窗、按钮、筛选、空状态放 `frontend/src/components/common/`，页面不要复制一份。只被一个工具用的放 `components/<tool>/`。带路由的页面只放 `views/`。
6. **导航由路由表驱动。** 侧栏菜单由 `router` 的 `meta.title` 运行时生成（顺序即 `children` 声明顺序），不要在页面里写死链接。`backend/tools/registry.py` 与 `GET /api/tools` 仍在，但自首页改为游戏中心后暂无前端使用方。
7. **配置写死在代码里。** 全部配置在 `backend/config.py`（含 `SECRET_KEY`、`SESSION_COOKIE_*`、`DB_SUBDIR` / `DB_FILENAME`）与 `backend/Dockerfile` 的 `ENV STORAGE_ROOT=/data`。`.env` 只剩 `STORAGE_HOST_DIR` 与 `WEB_HTTPS_PORT` 两个键，而且**只给 docker compose 读，后端进程一个都不读**（`backend/config.py` 不加载 `.env`）——加配置项一律进 `config.py`，不要新增 `.env` 键。文件根目录（`STORAGE_ROOT`）不存在时 `LocalStorage` 会自己建出来，没有「未配置」状态——**存储永远可用，不要复活 `configured` 这类开关**。
8. **SQLite 路径。** 写死为 `<STORAGE_ROOT>/db/app.db`（`backend/config.py` 的 `DB_SUBDIR` / `DB_FILENAME`），**没有 `DATABASE_URL` 可配**；启动时确保该目录存在。
9. **Gunicorn + SQLite：** `gunicorn backend.asgi:app -k uvicorn.workers.UvicornWorker --workers 1 --threads 8`。必须单进程以免 SQLite 写冲突；多线程用于并发处理 keep-alive 连接。

数据 schema（SQLite 表 + 文件路径规则）见 `docs/data_dict.md`；设计取舍见 `docs/architecture.md`。

## 功能：账号（开放注册 + 登录）

除 `/health`、`/api/csrf`、`/api/register`、`/api/login`、H5 解包资源 `GET /api/games/{id}/h5/{资源路径}` 外，所有 **API** 都要登录。SPA 路由除 `/login` 外由 `permission.js` 拦。

- **开放注册。** `POST /api/register`（免登录、免 CSRF）只收用户名与密码，建号即登录。界面在登录页的「登录 / 注册」切换里。**不再有命令行建号**（`backend/cli.py` 只剩 `init-db`），也不做邮箱/验证码/找回密码
- `users` 表：用户名 + werkzeug `password_hash`。用户名规则 `^[0-9A-Za-z_-]{2,32}$`（`backend/auth/models.py` 的 `USERNAME_PATTERN`，大小写敏感），密码 6–64 字符；校验入口 `backend/auth/service.py` 的 `validate_username()` / `validate_password()`。**用户名会被直接当成存档目录名**（`save/{用户名}/…`），字符集收窄就是为了不必再考虑转义——改规则时必须同时保证它仍是文件名安全的
- **失败锁定。** 同一 username 连续失败 ≥3 次锁 5 分钟、≥6 次锁到当天 UTC 结束（`login_attempts`，成功即删行）
- Session cookie：HttpOnly、SameSite=Lax；axios `withCredentials: true`；签名密钥是 `backend/config.py` 里写死的 `SECRET_KEY`。**不要 Redis/JWT，不要搞多因子**
- CSRF：`GET /api/csrf`，之后写操作带 `X-CSRFToken`；`/api/register`、`/api/login`、`/api/csrf`、`/health` 在白名单里（登录页此时还没拿到 token）
- 登录态**不要**放进 `localStorage` 当 token；401：拦截器单飞清本地非敏感缓存，跳 `/login`
- **不做游客模式。** 后端没有 `OptionalUser` 这类可登录可不登录的依赖。唯一免登录的业务接口是 H5 解包资源（下条），原因是浏览器约束而非设计选择：H5 在沙箱 iframe（不透明源）里播放，它发出的请求一律按跨站处理，`SameSite=Lax` 的 session cookie 不会带上，加了登录依赖只会让游戏加载不了 JS/图片——播放页自身仍要登录，未登录拿不到游戏 id 与入口地址。**攻略资源不在这个例外里**（它是同源顶层导航打开的普通静态页，cookie 照常带上，与其它业务接口一样要登录）
- 本地存档与引擎本地设置本就只在浏览器里，不涉及鉴权

## 功能：游戏中心（Flash、HTML5 与主机 ROM）

自托管 Flash、HTML5 与 8/16-bit 主机游戏：列表页（按平台分组）+ 管理页 + 播放页（Flash 用 Ruffle、主机 ROM 用 EmulatorJS、H5 用沙箱 iframe，均在浏览器内）。

- 元数据在本地 SQLite（`games` 表），文件按相对路径落在项目文件根目录下。**游戏类型由本体文件扩展名自动判定，不接受手动指定**：`backend/games/service.py` 的 `detect_game_type()` 是唯一判定入口，`_GAME_TYPE_EXTENSIONS` 是扩展名与类型的唯一对应表（单向一一对应，无歧义：`flash`→`.swf`；`h5`→`.zip`；`nes`→`.nes`；`snes`→`.sfc/.smc`；`gb`→`.gb/.gbc`；`gba`→`.gba`；`segaMD`→`.md/.gen`；`segaGG`→`.gg`；`segaMS`→`.sms`），未收录后缀一律 400；封面统一 jpg/png/gif/webp
- **类型的显示名**只在前端 `frontend/src/constants/gameTypes.js` 的 `GAME_TYPE_LIST` 里定义（纯展示，**不进任何键名/路径/存储**；落库与接口一律用上面的类型值）：`flash`→`Flash`、`h5`→`HTML5`、`nes`→`FC NES`、`snes`→`SFC SNES`、`gb`→`Game_Boy Color`、`gba`→`Game_Boy_Advance`、`segaMD`→`Mega_Drive Genesis`、`segaGG`→`Game_Gear`、`segaMS`→`Sega_Master_System`。命名规则：同一平台的两个叫法并列时用一个空格分隔（如 `FC NES`、`Mega_Drive Genesis` 各是两个叫法），叫法内部的空格用下划线（如 `Game_Boy`）。改显示名只需改这张表。
- **游戏中心卡片外观（卡带图）**：**GB/GBC 类型（`gb`）的卡片画的是一整张卡带**，封面贴进卡带的贴纸窗里，不单独出封面图。卡带图是 `frontend/public/gbc-cart.png` **固定一张**（702×807 的 GBC 机身，所有 GB/GBC 游戏共用），配置在 `frontend/src/constants/gameCartridges.js` 的 `GAME_CARTRIDGES`（`url` 单张图 + `image` 整图尺寸 + `label` 贴纸窗矩形=84,248 **528×464 = 正好 99/87**（实测内沿 529×467，取整数精确值），**换图必须同步改这两组数字**）；渲染直接用 `cartridge.url`，不按卡带ID 挑图；**只有游戏中心的卡片**（「全部游戏」网格与「最近游玩」rail）这样渲染，走 `components/games/GameCover.vue`；详情弹框图片栏、游戏管理列表缩略图与添加/编辑表单的封面预览都显示**封面原图**，不套光盘/卡带这层。卡片封面框的尺寸规则统一在 `GameCover.vue`：卡片宽 = **正方形限制框**边长（框上 `container-type: inline-size`，内部用 `cqw`），卡带按自身比例缩到**高度触到框边**（竖长形状）、水平居中，封面用**整图百分比**绝对定位到贴纸窗（`cartridgeLabelStyle`），`object-fit: fill` 一律**拉伸填满**（不裁切、不留黑边，这就是这个类型的封面算法）、圆角 2% 对齐窗角；没有封面时窗里摆类型图标。`.gb` 与 `.gbc` 是同一个游戏类型，两类共用这张卡带
- **游戏中心封面外观（Flash）**：Flash 类型的**卡片**渲染成一张**实体光盘**（`components/games/GameCover.vue` 的 `.game-cover__disc`）——盘是正方形、圆形裁切、封面 `object-fit: cover` 铺满盘面，**直径 = 卡片宽（正方形限制框边长）的 84%**（`--disc-size: 84cqw`，四周刻意留一圈空、不放大到触满），所以「最近游玩」rail 与「全部游戏」里看到的盘一样大；盘心用 `public/flash-logo.png` 那枚 Flash 标志填住（`.game-cover__disc-hub`，尺寸 `--hub`），`.game-cover__disc-sheen` 叠盘面细节：盘心外积层环、外圈弧度暗调、透明塑料边的反光、斜向高光。径向渐变一律用 `circle closest-side`，百分比即「占盘半径的比例」（半径是直径的一半，所以 `--hub` 一个数在图片宽度和渐变里通用）；没有封面时露出金属感渐变的空白盘。**盘面不加落影**（试过接触影 + 散影，效果不好，已去掉；边缘感靠 sheen 里那几圈弧度暗调与塑料边反光），盘面的明暗也必须放在 sheen 层——`inset` 阴影画在封面图下面，有封面时看不见。**不做**「Adobe Flash Player」文案/徽标那一行（原 `flash-badge.webp` 与 nginx 里那条无长缓存规则都已删掉）。其它类型仍是普通封面图（等比缩放到不超出限制框）。**卡片高度规则**：rail 传 `CARD_ASPECT_RAIL`（`1 / 1`）→ 卡片是正方形、整行高低一致；「全部游戏」不传 aspect → 卡片高 = 封面高（同类型封面形状一致，整行仍齐平，扁封面的行更矮）。别改回按游戏类型硬编码框比值的老做法（那会让 rail 与网格里同一盘卡大小不一致）
- **文件落盘位置固定**（与源文件名、游戏名都无关，改名不挪动任何文件）。根目录是 `STORAGE_ROOT`，SQLite 里只存相对路径，读取时由 `backend/storage/local.py` 的 `LocalStorage` 拼上根路径（并挡住绝对路径与 `..`）。路径规则集中在 `backend/games/paths.py`，别在别处手拼字符串：
  - 本体：`game/{game_type}/{卡带ID}/game.{后缀}`，如 `game/nes/AB-12/game.nes`；H5 为原始 ZIP `game/h5/AB-12/game.zip`
  - 封面：`game/{game_type}/{卡带ID}/cover.{后缀}`，如 `game/nes/AB-12/cover.png`
  - H5 解包资源：`game/{game_type}/{卡带ID}/h5/{包内相对路径}`，清单在 `game_h5_files`（`path` 是包内路径、`file_path` 是磁盘相对路径）
  - 云端存档：`save/{用户名}/{game_type}/{卡带ID}/{uuid}.state`
  - 类型那层用 `game_type` 的**键值**（`flash`/`h5`/`nes`/…），不是前端显示名
- **本地目录就是普通文件**：用户可以直接从宿主目录拷走/浏览；不需要引入任何对象存储或元数据缓存。上传先写同目录临时文件再 `os.replace` 改名；目录级操作（`remove_tree` / `replace_tree` / `move`）由 `LocalStorage` 提供，用于删游戏、H5 整包替换与换类型时挪封面
- **卡带ID（`cartridge_id`）**：创建时**必填**（新建表单与搬运弹窗都要填），全局唯一（唯一索引 `uq_games_cartridge_id`，跨类型也唯一），只允许数字/字母/中划线/下划线、**落库前统一转大写**，校验入口 `validate_cartridge_id()`。它是磁盘目录名与「同一盘卡带」的身份标识，**建后不可修改**：`PUT /manage/{id}` 不接受该字段（传了也当普通字段忽略），想换只能删掉重建。管理页详情里展示它
- **卡带类型（`cartridge_type`）**：卡带版本，**始终有值**（不是可空字段），取值 `default` 默认 / `jp` 日版 / `us` 美版。目前**只有 FC NES 区分日版/美版**（`nes` 允许三者），其余游戏类型只允许 `default`；可选集合在 `backend/games/models.py` 的 `CARTRIDGE_TYPES_BY_GAME_TYPE` / `cartridge_types_for()`，校验入口 `service.py::validate_cartridge_type()`（空值取 `default`，非法值中文 400），前端展示层镜像在 `frontend/src/constants/cartridgeTypes.js`。它在新建（multipart `cartridge_type`）与编辑（`PUT /manage/{id}`，与 `game_type` 不同、这个字段**可以**手改）两处可设——**只有管理页的添加/编辑弹框能改**（`el-radio-group` 单选，游戏中心右键菜单没有这一项；单选里**「默认」固定第一，其余按取值字符串排序**，见 `sortedCartridgeTypes()`——这与游戏中心分行用的 `CARTRIDGE_TYPE_LIST` 顺序是两回事）；**换本体导致游戏类型变化时，新类型不认的值回落 `default`**。游戏中心「全部游戏」在游戏类型分组内**再按卡带类型分子网格**（同一种卡带严格同一行，顺序为日版、美版、默认，见 `views/games/index.vue` 的 `gameRows`）；卡片封面框规则见 `frontend/src/constants/gameCardAspect.js` 与 `components/games/GameCover.vue`（rail 正方形框、网格高度随封面）；详情弹框展示它（国旗）、添加/编辑弹框用**单选**改它。**界面上只显示国旗、不显示文字**：详情与单选组（含「默认」那一项）都只给图片，中文名只作 `<img alt>`。图片在 `frontend/public/flags/`（22×16，与 flash-logo/gba-shell 一样按 URL 引用的普通静态文件，nginx 走 `location /`，无需加规则），**文件名是国家/地区英文全称**（`Japan.png`、`USA.png`、`United Kingdom.png`…）；「默认」用一张空白图 `Default.png`（不借用任何国家的旗）。目录里已放好其它地区（Australia/Brazil/Canada/Europe/France/Germany/Italy/Scandinavia/Spain…），以后扩取值直接加一项即可。老库由 `backend/database.py` 的 `_ensure_columns()` 在启动时补列
- **建条目 / 换本体**：新建走 `POST /api/games/manage`（multipart：`name`/`cartridge_id`/`description`/`file`[+`cover`]）一步建条目并写本体，任一步失败整体回滚（不留半成品条目与文件）；换本体/换封面走 `POST /manage/{id}/assets`(kind=game|cover)——换本体即按新扩展名切换类型，**先写新本体，成功后才清理旧类型遗留**（先把这个游戏的封面挪到新类型目录，再递归删掉整个旧类型目录，h5 清单行一并删），失败整体回滚不动旧档；`PUT /manage/{id}` 只改名称/描述/`clear_cover`，不接收 `cartridge_id` 也不接收 `game_type`；管理页删除时要**手打一次卡带ID**才放行（会连磁盘文件、所有账号在该游戏上的云端存档与截图一起删掉，不可撤销）
- **网络上传**（管理页弹窗的「网络上传」按钮 → `backend/games/remote.py`）：本体与封面除了本地文件，还可以给一个 http/https 直链，由**服务端**下载到临时目录再走同一条上传管线（浏览器直连任意域名会被 CORS 拦）。建条目用 `body_url`/`cover_url`（multipart 字段），换资源用 `url`；两类来源可混用（如本体本地文件 + 封面直链）。**下载只走 `importer.download_file`**，上限 `remote.MAX_REMOTE_BYTES`（512MB，nginx 与 gunicorn 的 300s 也一并构成实际天花板）。类型判定：本体走直链时**以用户在下拉里选的 `game_type` 为准**——地址能认出类型就必须与所选一致（不一致 400），认不出（网盘式无后缀直链，或不是已收录格式）就用 `_DEFAULT_EXTENSIONS` 里该类型的默认后缀补上；封面地址的扩展名必须是 jpg/jpeg/png/gif/webp。原始文件名**一律不落盘也不入库**（临时文件固定叫 `remote{后缀}`），地址里带什么路径分隔符都影响不到库里。下载失败、超限、协议不对都转成中文 400（注意 `remote` 抛的是 `DownloadError`，service 侧必须经 `_remote_extension`/`_fetch_remote` 转成领域错误，否则会变成 500）
- **本体 CRC32 锁**：上传本体时顺手算 CRC32 落 `games.crc32`（分块读完再 `seek(0)` 交给存储，不整读内存；8 位大写十六进制，如 `D445F698`）。`crc32` 非空即锁定：再换本体只接受 CRC32 完全相同的文件（rom 丢了补传同一个文件没问题），不同则 400 且**不覆盖旧对象**；`crc32` 为空（对象已丢、尚未补传）视为未锁定。管理页详情弹窗展示 CRC32
- **同类型下游戏名唯一**：`games` 上有联合唯一索引 `uq_games_game_type_name(game_type, name)`，新建/改名/换本体换类型都会先查重并回中文 400；不同类型之间可以重名。卡带ID 则**跨类型唯一**
- **游戏名要同时是合法的 Windows 文件名与百度网盘文件名**（导出/上传时它就是「游戏名.后缀」）：校验入口 `backend/games/service.py::validate_game_name()`，新建与改名都过它，规则取两边限制的交集——不能含 `\ / : * ? " < > |`（全角版如 `：／？` 合法）、不能含控制字符、不能以点结尾、不能是 Windows 保留设备名（`CON`/`PRN`/`AUX`/`NUL`/`COM0-9`/`LPT0-9`/`CONIN$`/`CONOUT$`/`CLOCK$`，带扩展名与大小写不敏感）、不超过 255 个字符；首尾空白自动去掉。**搬运**（`import_from_url`）抓到的站点标题走 `sanitize_game_name()` 无害化（非法字符换 `_`、去掉结尾的点、截断、空则回退「未命名游戏」）后再入库，不会因标题带斜杠就整个失败
- **描述上限 200 字**（`DESCRIPTION_MAX_LENGTH`）：新建与编辑都过 `validate_description()`，超长报中文 400、**不静默截断**（前端输入框同样 `maxlength=200`）；**搬运**抓到的站点简介按上限截断后入库，不因简介过长整个失败
- 上传/下载都走 `LocalStorage` 分块流式（不整读进内存）；下载：`GET /api/games/{id}/play` 附件返回本体，content-type 按本体扩展名——`.swf` 保持 Flash 专用值、其余（ROM/H5 ZIP）统一 `octet-stream`；`GET /api/games/{id}/cover` inline 预览（`?download=1` 附件下载封面）。两者都需登录
- **H5（`h5`）**：上传 `.zip`（根目录需含 `index.html`，整包套单层目录会自动剥前缀）后由 service 解包——校验路径/重名/条目数/单条与总解压量/压缩比，拒绝绝对路径、`..`、加密条目；整包解到同层的暂存目录 `game/{类型}/{卡带ID}/.h5-{随机}`，全部写完后再用目录改名整体替换 `h5/`（旧目录先改名挪开、新的就位、再删挪开的），单事务替换 `game_h5_files` 清单。**磁盘上没有代际前缀**，重传就是整包替换。播放时 `GET /api/games/{id}/h5/{资源路径}` 免登录 inline 下发（入口固定 `index.html`），响应强制 CSP `sandbox`（不含 `allow-same-origin`）+ `nosniff` + `Referrer-Policy: no-referrer` + `ACAO: *` + `no-cache`。沙箱下无 localStorage/Worker，H5 不接入云存档
- 播放路由：Flash → `/games/flash/{gameId}`；H5 → `/games/h5/{gameId}`（嵌套 sandbox iframe 指向 H5 资源入口）；主机 → `/games/play/{gameId}`（外层 SPA 壳内嵌 iframe `/emulator-host.html`，EmulatorJS 官方要求 iframe 隔离）。EmulatorJS 引擎资产由 `frontend/scripts/fetch-emulatorjs.mjs` 构建期从固定版本拉取到 `public/emulatorjs/`（gitignore，nginx 以 immutable 静态服务），运行时不依赖外网
- **攻略**：一份攻略就是 `game/{game_type}/{卡带ID}/guide/` 下的一个静态目录树（入口固定根目录 `index.html`，子页面/图片/CSS/字体都是里面的普通文件），**没有清单表也没有库里的标记**——「这个游戏有没有攻略」由 `guide/index.html` 是否存在现算（`GameService._has_guide`，载荷字段 `has_guide`），所以从宿主目录手动拷走/删掉攻略，界面立刻跟着变。上传只在**游戏管理页的编辑弹框**（「上传封面」下方「上传攻略」，新建弹框没有这一项）：前端用 `<input type="file" webkitdirectory>` 选整个文件夹、**剥掉最外层目录名**（只传文件夹内的内容），把文件夹内相对路径按顺序做成 `paths`（JSON 数组，与 `files` 多个 part **按下标一一对位**），**一次 multipart 提交**（`POST /api/games/manage/{id}/guide`，文件数上限 1000 = Starlette `MultiPartParser.max_files` 的硬上限、整体大小受 nginx 128m 兜底，前端会先拦并给中文提示）。后端先在**写任何字节之前**全量校验（逐个 `normalize_guide_path` 归一化、大小写不敏感查重、大小写不敏感识别入口并统一落成小写 `index.html`、根目录没有它就 400、单文件与总量上限），再全部写进同层暂存目录 `.guide-{随机}`，最后一次目录改名整体替换 `guide/`（**磁盘上没有代际前缀**，重传就是整体替换，失败清掉暂存目录、旧攻略还在，磁盘零残留）；**不动 `game_path/size/crc32`**，与本体 CRC32 锁互不干扰。读取 `GET|HEAD /api/games/{id}/guide/{资源路径}`（**需登录**，与 H5 的免登录不同）：路径归一化后直接拼磁盘路径、按后缀给 MIME（`guess_asset_mime` 那张显式表），文件不存在即 404；响应只加 `nosniff` + `no-cache`（重传后立刻生效），**不加 CSP sandbox**。入口在游戏中心卡片右键菜单「详情」下方的「攻略」（**没有攻略就不显示这一项**），`window.open(..., "_blank", "noopener")` 在**新标签页顶层**打开。**删游戏**与**换本体换类型**都随整个旧游戏目录一起清掉（不参与跨类型迁移）
- **主机播放页标题栏**（自左向右）：截图 → 保存配置 → 窗口倍率 → 显示游戏机（GBA / FC / GBC 有）→ 存档管理。**截图**走宿主页 `__ejsRpc.screenshot`，**两条路**：先要引擎自带截图（内核侧读帧缓冲 → **原生像素**，如 FC 256×224），拿不到或整幅全黑时退回「在**同一帧的 requestAnimationFrame 里**拷画布」（画布尺寸 = 显示尺寸；引擎 WebGL 上下文是 `preserveDrawingBuffer: false`，合成后绘制缓冲即失效——Chromium 下同帧拷贝可靠，个别浏览器会拷到全黑，故有内核侧那条路兜底），两条都黑时按原生帧返回、不报错；返回的 `width`/`height` 是 PNG 真实像素尺寸，提示里显示的就是它。**截完不下载**：先弹 `ScreenshotConfirmDialog.vue`（弹框 320px：上面 180px 正方形限制框预览、下面一行描述（单行 `input`，刚好放下 15 字、没有计数行），**描述框自动获得焦点、按回车即确认**，点「确认」同效），确认后才带描述 `POST /api/games/screenshots` 存入图库并提示 `截图已存入图库（宽 × 高）`，取消/ESC/✕ 就整张丢掉（预览用的 objectURL 在关闭与卸载时 `revokeObjectURL`）。快捷键 **Ctrl+Shift+S** 与按钮同效（F12 是浏览器开发者工具的保留键，页面拦不住）：**父页面 window 与宿主 iframe 的 window 各挂一份 `keydown`**（玩游戏时焦点在引擎画布上，父页面收不到），iframe 那份用**捕获阶段**挂（引擎自己也在它的容器上监听 keydown），换 iframe / 卸载时解绑；守卫：引擎已就绪、不在截图中、确认框未开、事件目标不是 INPUT/TEXTAREA/contenteditable（引擎自己的设置面板里也是输入框）。**窗口倍率**的基准是各平台帧缓冲分辨率（`emulator-player.vue` 的 `EMU_NATIVE`：NES 256×224、SNES 256×224、GB/GBC 160×144、GBA 240×160、MD 320×224、GG 160×144、SMS 256×192），倍率可选 `1×`/`1.5×`/`2×`/`2.5×`/`3×`/`3.5×`/`4×`，按帧缓冲**高度**换算窗口像素高度、宽度再按舞台宽高比推出，菜单里括号中的尺寸就是这套算法的结果（真实窗口尺寸，不是帧缓冲像素数）。**窗口选择器是 `components/games/EmuWindowSelect.vue`，不是原生 `<select>`**：按钮点开的面板是一张**两列矩阵**（行 = 倍率，列 = 显示比例），最上面一行是「适应窗口」。**只有 FC 画第二列**（传 `wide` 配置 `WIDE_MODE.nes = { aspect: 4/3, native: 256×240 }`）：左列「像素完美」（1:1 方像素，就是上面那套 256×224 的尺寸），右列「4:3」（真机 CRT 观感）。取值是 `<倍率>|<显示比例>`（`"2|pp"` / `"1.5|wide"` / `"fit|pp"`，存 localStorage 的 `games.emu.window`），老值只有倍率时按像素完美读；面板在标题栏内就地弹出（不 teleport），鼠标移进面板仍算在标题栏内、标题栏不会收起把它带走，点外面/ESC 收起。**舞台长宽比取引擎上报的显示宽高比，不是帧缓冲比例**：引擎（宿主页 `__ejsRpc.videoInfo` 的 `aspect`，来自引擎 `getVideoDimensions("aspect")`）把画面按内核上报的 aspect 等比摆进画布，画布（= 舞台）填不满的地方就是黑边——内核会按像素宽高比（PAR）校正，舞台若按帧缓冲比例定尺寸就会留黑边（SNES 默认 4:3、MD 默认 auto 同理）。引擎就绪前（以及取不到 aspect 时）用帧缓冲比例兜底，就绪后每秒跟随一次，用户改内核 aspect 选项也会跟着变。**FC（系统名 `nes` → fceumm 内核）的内核选项由宿主页 `emulator-host.html` 按显示比例模式设两套**（模式经 iframe 的 `?ratio=` 传进来，运行中切换走 `__ejsRpc.setDisplayMode(mode)`）：`pp`（像素完美，默认）→ `fceumm_aspect = "PP"` + 上下过扫描各裁 8 行（内核默认值），帧缓冲 **256×224**、显示 **8:7 = 256:224**（**引擎默认的 8:7 PAR 会让同一个帧缓冲按 ≈1.306 摆放，1× 窗口就不是 256×224 了，所以这一项必须设**）；`wide`（4:3）→ `fceumm_aspect = "4:3"` + **过扫描裁切关掉**，帧缓冲 **256×240**、显示 **4:3**（**必须用完整 240 行**：224 行按内核的 4:3 摆放会被它按完整帧归一化成 ≈1.43，填进 4:3 屏幕会上下留黑边）。引擎把 `defaultOptions` 在菜单初始化时经 `changeDiskOption` → `menuOptionChanged` → `setVariable` 下发给内核，`loadSettings()` 加载的账号本机设置排在它之后、优先级更高；为了不让引擎里存过的旧值把机壳的洞带偏，播放页在引擎就绪、第一次读到 aspect 时对一次（`aspectSynced`）：与选中模式的比例不符就调一次 `setDisplayMode` 掰回来——**窗口选择器是显示比例的唯一入口**
- **搬运（`POST /api/games/manage/import`，需登录）**：传入 7k7k / 4399 / flash.homes 的游戏页地址**与卡带ID**（`{ url, cartridge_id }`，卡带ID 规则同上、必填），由 `backend/games/importer.py`（服务端唯一的站点解析与下载实现）解析游戏信息与资源地址、下载 Flash SWF 或镜像 H5 bundle 到临时目录，再走普通上传管线入库（H5 打成 zip 复用解包逻辑），封面一并下载。**只接受 7k7k.com / 4399.com / flash.homes 域名**（避免服务端被当作任意 URL 代理）；H5 镜像会跟随页面引用的外部资源域名。站点差异：7k7k / 4399 的 Flash 资源地址藏在页面 JS 变量或资源页里，flash.homes 是 Flash 存档站、作品一律是按 sha256 存放在 CDN 上的单个 SWF（游戏页用 Astro 渲染，播放器岛 `PlayerStage` 的 `props` 属性里给出 `sha256` / 标题 / 封面文件名，另有 JSON-LD 兜底；其作品 id 为 12 位短码，页面上写作 `F8YX-1DNE-JQG9` 形式），搬运结果可能是 `flash`（SWF）或 `h5`（页面里是 H5 入口时打包成 zip，复用解包流程）。前端入口在游戏管理页「搬运游戏」弹窗
- **云端存档**（`/api/games/saves`，需登录）对 Flash/模拟器两类播放是同一套后端：把某(用户,游戏)此刻全部本地存档文件上传成一个不可变整体快照。元数据在 `game_cloud_snapshots`(+`_files`)；`manifest(local_key,name)` 与文件一一对应、按 (user,game) 隔离、越权一律 404；内容按 `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state` 落盘（文件名用 uuid 是为了不可猜、不重名，原始文件名留在 SQLite 里供下载时还原）。`name` 下载名规则：含扩展名时原样（模拟器固定 `save.state`）、否则补 `.sol`（Flash）。模拟器一个快照恒为 1 个文件（该游戏只有一份本地档），Flash 仍是一次全量。**删游戏时连同该游戏所有账号的存档快照（行 + 文件 + 存档目录）一起清掉**。结构见 `docs/data_dict.md`
- **游戏截图**（`/api/games/screenshots`，需登录，**按账号隔离**）：图库里的图来自两处——主机播放页截图（PNG）与详情「截图 [管理]」里的「上传截图」按钮（本地图片）；**只有本人看得见、管得着**（越权一律 404），封面则是全站共享的一张。元数据在 `game_screenshots`（`user_id` FK + `game_id` 仅索引 + `sort_order` 分数 + `description`(15) + `file_path`，列表恒按 (用户, 游戏) 过滤 + 排序，复合索引 `ix_game_screenshots_user_game_order`；**不加** `(user_id, game_id, sort_order)` 唯一约束——分数排序靠中值插入，唯一约束只会碍事）；内容按 `image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}` 落盘。上传校验（全 400、中文）：游戏存在（否则 404）、非空、单张 ≤16MB、**按内容 magic 认格式**（PNG/JPG/WebP/GIF，认不出就 400；**不看文件名与 content-type**，后缀也由内容定，读完 `seek(0)` 复位）、描述 ≤15 字（不静默截断）。**排序是分数排序**：`sort_order` 是浮点分数，新图取「最大分 + `_SCORE_STEP`(1000)」追加到末尾；拖动重排 `POST /{id}/move`（body `{to_index}`，落点在当前列表里的下标，越界 400）**只改被拖那一行的分数**（取相邻两分数的中值），相邻间隔 ≤`_MIN_GAP`(1e-3) 时才把整份按步长重新铺开（间隙不足时的后台重排）；接口一律**返回整份有序列表**（顺序的真相在后端，前端整体替换）。删除不做重排（分数稀疏无所谓）。`GET /{id}/image` 走 `build_download_response(stream, content_type=行的 mime)`（不传 filename 即 inline，同封面；mime 用入库时 magic 定下的值，不能按后缀现猜——`.webp` 在部分 Python 的 `mimetypes` 里不认识）且**必须登录**——不能做成公开静态路径，否则会泄漏他人截图。**删游戏时**所有账号在该游戏上的截图行、文件与目录一并清掉，目录按 `file_path` 反推（截图**不参与**「换游戏类型」的迁移，目录里的类型是上传当时的，同一游戏的截图可能分散在两个类型目录里）。结构见 `docs/data_dict.md`
- **游戏图集**（`/api/games/gallery`，需登录，**按游戏共享**）：与截图**正好相反**——不记上传者，任何登录用户都能看、能传、能改描述、能删、能拖动排序（`GalleryService` 就是 `ScreenshotService` 去掉「用户」这一维，校验/分数排序/上传删除流程同一套）。元数据在 `game_gallery_images`（`game_id` 仅索引 + `sort_order` 分数 + `description`(15) + `file_path`，复合索引 `ix_game_gallery_images_game_order`）；内容是宣传图、说明书扫描件这类展示图，上传校验同截图（非空、单张 ≤16MB、按内容 magic 认 PNG/JPG/WebP/GIF、描述 ≤15 字、游戏不存在 404）。**字节落在游戏目录内**的 `game/{game_type}/{卡带ID}/image/{uuid}.{后缀}`，所以**它随「换游戏类型」一起迁移**：搬目录（`move_tree`）的同时把行里的 `file_path` 换成新类型前缀；删游戏时行与文件一并清掉。**入口在游戏管理页的编辑弹框**（「图集 → 管理」，新建弹框没有——新建时还没有卡带目录可落），详情弹框的图片栏只做只读展示
- **机壳覆盖**（播放页「显示游戏机」按钮，GBA / FC / GBC 有）：把机壳图盖在游戏画面上，看起来像真机在玩。图与洞的几何在 `emulator-player.vue` 的 `SHELLS` 表里**按游戏类型**取（`gba` / `gb` / `nes`），每项含 `url` / `image`（整图像素尺寸）/ `hole`（透明屏幕洞的 x/y/宽/高），**换图必须同步改洞的几何**（洞的位置一变就会错位）：`gba` = `frontend/public/gba-shell.png`（画好的 GBA 机身，3840×2160，中间 **1920×1280 是透明的屏幕洞**——精确 3:2 = GBA 原生 240×160，且居整图正中）；`gb`（GB/GBC 一类共用这张，项目里 `.gb`/`.gbc` 是同一个游戏类型）= `frontend/public/gbc-shell.png`（GBC 正面机身，2131×1996，屏幕洞 **1285×1156.5 = 正好 10:9**，y 从 338 起，左右留白各 423px——原素材洞是 1285×1157、左右差 17px，入项目前从左边裁掉 17px 让屏幕左右对称；剩下半个像素差按小数声明，不必真拉伸图画；GB/GBC 的帧缓冲 160×144 与 gambatte 上报的显示比例 160/144 都正好是 10:9）；`nes` 有两套（对应窗口选择器里的两列显示比例，切比例时一起换）：`pp` = `frontend/public/nes-shell.png`（一台 CRT 电视机壳，1326×1237，屏幕洞 **1084×948.5 = 正好 256:224**，y 从 146.3333 起）；`wide` = `frontend/public/nes-shell-43.png`（**原素材本身**，1326×1077，屏幕洞 **1084×813 = 正好 4:3**，y 从 125 起）。**洞的比例必须与画面比例一致**，所以 `pp` 那套入项目前做过处理：原素材屏幕洞是 1084×813（4:3），而这一列显示的是 256×224（8:7），于是把**屏幕那一段纵向拉长 7/6 倍**（813 → 948.5）——下面 121 行的控制条（扬声器网/按键/指示灯，`y ≥ 965`）保持原样等比，不被压扁；最后把四周的透明留白裁掉（只有顶部 10 行是空的，左右下都顶到机身）。`hole` 里的 `y`/`height` 因此带小数（原素材洞坐标 × 7/6 再减去裁掉的 10 行），与图上的透明像素一一对应；`wide` 那套没有拉伸，`y` 是原素材洞坐标减去裁掉的 9 行。`shellStyle` 按「洞宽 = 画面宽」定比例再按洞的偏移把整图挪到画面左上角；洞的比例与舞台一致（GBA 3:2、FC 8:7），舞台又是按引擎上报的 aspect 摆的，所以洞会四边严丝合缝对齐画面，画面尺寸一变（换倍率/缩窗口/全屏）自动跟着缩放。定位必须用 **`position: fixed`**：机壳比画面大得多（GBA 那张宽是画面的两倍），`absolute` 会被 `.game-shell__body` 的 `overflow: auto` 裁掉并顶出滚动条，`fixed` 不参与滚动容器的溢出计算（代价是要 `getBoundingClientRect` 同步舞台的视口位置，滚动/缩放/全屏都要重算）；倍率调大后机壳比浏览器窗口大也**照常显示**——同比放大、超出视口的部分看不见即可，不裁剪、不隐藏、不提示（用 `fixed` 正是为了让它不产生滚动条）——但「适应窗口」模式下要塞进可用空间的从画面换成整张机壳，所以那个模式一定会把整个机身放在窗口里
- **模拟器设置云同步**（`/api/games/emulator-settings`，需登录）：登录用户的模拟器设置（键位 + 选项 + 金手指）按**平台**（`game_type`，7 个主机类型）各存一套，整块 JSON 文本存 SQLite（`game_emulator_settings`，不落文件）。引擎把设置写在 localStorage 的 `ejs-{gameId}-{core}-{gameName}-settings`，且**只在启动流程里读一次**，所以播放页在设 iframe `src` 之前先把云端值写回去（这就是「自动加载」）；保存是**手动**的——播放页标题栏的「保存配置」按钮（在「窗口倍率」左边）把当前整块配置 PUT 上去。**不做任何自动侦测**：引擎不发设置变更事件也没有保存按钮，曾试过包装实例 `saveSettings` 暴露变更版本号，已废弃。键名公式在 `frontend/src/utils/emulatorSettings.js` 的 `engineSettingsKey`，父页面与宿主页同源、共用一份 localStorage
- **最近游玩**（`GET` / `POST /api/games/recent`，需登录）：游戏中心列表页顶部「最近游玩」rail（只占一行、不滚动；列定义与下方网格相同，卡片尺寸一致）的数据源，下面是完整的「全部游戏」（重复资源不剔除）。记录**按账号**存 SQLite（`game_recent_plays`）：唯一 `(user_id, game_id)`、一个游戏只留一行、只记最后一次 `played_at`，因此无需裁剪与分页；行随游戏删除由 `GameService.delete` 一并清掉。列表 join `games` 且只返回 `game_path != ''`（与中心列表同口径），默认 20 条、上限 50（**在 service 收敛而非 `Query(ge=,le=)`**：参数校验失败走 422 会绕开统一错误信封）。**上报只能由播放页发起**：Flash/模拟器走 `GET /api/games/{id}/play`、H5 走免登录的 H5 资源接口，三条路径不共用同一个带登录态的入口，所以后端不在资源接口上记 user，而由三个播放页在「真正拉起播放器」的那一刻（有手势即开始；无手势是点过「开始游戏」）调 `utils/recentGames.js` 的 `reportGamePlayed()` best-effort 上报（`notShowError` + `skipAuthRedirect`，失败只丢一条记录，不影响游玩）
- **游玩时长与进度**（`/api/games/stats`，需登录）：按账号存 SQLite（`game_user_stats`，唯一 `(user_id, game_id)`，一行含 `play_seconds` 与 `progress`），**与游戏类型无关**。**时长**是平台级通用方案——`frontend/src/utils/gamePlaytime.js` 是个模块级单例，Flash / H5 / 模拟器三个播放页在**与 `reportGamePlayed()` 完全相同的时机**（真正拉起播放器时）调 `startGamePlaytime(gameId)`、在 `onBeforeUnmount` 调 `stopGamePlaytime()`；每 30 秒发一次心跳（`POST /stats/playtime` 累加，service 里把单次秒数收敛到 0..300 防时钟跳变），页面 `document.hidden` 期间**不累计**（切标签页/最小化不涨，回来接着算），离开播放页时把剩余一次性发出。**进度**（`not_started` 未开始 / `in_progress` 进行中 / `completed` 已通关）**只由用户手动设置**，不会因游玩自动变更。`GET /api/games` 与 `/recent` 载荷都带 `play_seconds` / `progress`（无记录时 `0` / `not_started`）。游戏中心页面**只在游戏卡上接管右键**（`GameCard.vue` 根节点 `@contextmenu.prevent` 后 emit，卡片外仍是浏览器原生菜单），弹 `GameContextMenu.vue`：**详情**（弹 `components/games/GameDetailDialog.vue`，与游戏管理页的「详情」是同一个组件：打开时按 id 现取 `GET /api/games/manage/{id}`——中心列表载荷里没有 CRC32 / 创建时间——并与截图列表并行取一次；弹框宽 `min(810px, 96vw)`）、**设置进度**（纯 CSS `:hover` 的右滑子菜单，三选一点完即存、没有确认步骤）与**设置时长**（`AppDialog` + `el-input-number`，单位小时，**覆盖**为该值而非累加；输入被清空时值是 null，必须校验后拒绝，不能 `|| 0` 兜底——那会静默把记录清成 0）；保存后本地 patch 两个列表里的对应字段，不重新请求。工具栏类型下拉**左边**是进度下拉，与类型/关键词一起做**纯前端**联合筛选；卡片封面下方是居中一行 **进度标签 + 总时长**（<10 小时保留 1 位小数、≥10 小时取整，见 `utils/gamePlaytime.js` 的 `formatPlayHours`）；**进度还是 `not_started` 就整行不渲染**（`GameCard.vue` 的 `showMeta`）——未开始既没有进度标签也不显示时长，所以「有时长但没标过进度」的卡片这一行同样是空的，不写「未玩过」之类的占位
- **详情弹框的图片栏**（`components/games/GameScreenshotGallery.vue`，纯展示 + 内部翻页状态）：一行 **4 个 180px 正方形限制框**（180 = 「最近游玩」rail 卡片的最小列宽，格间距 14px，总宽 762px，框内 `object-fit: contain`——长边到上限为止，不裁不拉），**截图框不加底色、不做圆角**，图片栏与下方信息区之间也**没有分隔线**；**封面恒占第一格**（这一格显示封面原图：框内 `object-fit: contain` 等比缩放；没有封面就留虚线空占位框，位置不留给截图），其后依次是**共享图集**与本人的截图；每格下方一行**定高 18px 的描述**（水平居中、超出省略，封面那格留空但同样占位，换页/有无描述都不跳版）。**所有格子排在一条 flex 轨道上**（`.gallery__viewport` 只露一页宽、`overflow: hidden` 裁掉多余的），翻页是轨道 `translateX(-page × 776px)` 的水平**滑动过渡**（776 = 4 格宽 + 4 道缝，0.3s ease；格宽/间距在样式里，JS 的 `PAGE_OFFSET` 必须与之一致），不是直接换一屏；离屏的格子带 `loading="lazy"`（滑进可视区才开始取图）。放不下时左右两个圆形翻页按钮压在画面左右边缘上（图片栏正好 4 格宽、两侧没地方放），**在图片栏上滚滚轮也能翻**（上滚前翻、下滚后翻；只有真能翻的时候才 `preventDefault`，到边界与只有一页时完全放行，页面该滚还是滚）：`ceil(槽位数 / 4)` 页、**第 1 页 = 封面 + 3 张图（图集与截图同处一条轨道，按「图集 → 截图」排），第 2 页起每页 4 张且不再有封面**，只有一页不出按钮、到边界禁用，图增删后页码收敛回最后一页；封面、图集与截图都没有时整条图片栏不渲染。两类图**不走** Service Worker（SW 只拦 `/game-assets/`），URL 分别是 `/api/games/screenshots/{id}/image` 与 `/api/games/gallery/{id}/image`（id 唯一、内容不可变，无需版本参数）
- **截图管理弹框**（`components/games/ScreenshotManagerDialog.vue`，详情信息区右栏「截图 [管理]」打开）：**相册式平铺视图**（`grid` 自适应列，tile = 上面截图、下面描述），**一进来就是管理界面、没有「还没有截图」这类空态文案**，左上角恒有「上传截图」（本地图片，`accept` 只收 png/jpeg/webp/gif）。
  - **描述就地改**：单击描述，原地换成单行 `input`（与描述行**同宽同高同字号**，只多一圈边框，排版一点不动），**没有取消/保存按钮、也没有字数计数**（`maxlength=15` 静默限长），回车或失焦存下、ESC 放弃、内容没变就不发请求；同一时刻只有一张处于编辑态，选择模式下点描述算勾选（描述那层 `@click.stop` 拦了冒泡，所以要在处理函数里转给勾选）。
  - **多选删除（像手机相册）**：图片上**不放**任何按钮，删除入口是工具条**右上角固定的「删除」**——第一下进删除模式（右侧出现「已选 N 张」+ 取消），选择模式下点整块切换勾选（右上角出现 ✓），再点一次「删除 N 张」才真删，**这一步就是要用户确认的那一步，不再弹 `ElMessageBox`**；删除逐张调接口（中途失败也统一重拉对齐），完成后 `@changed`。
  - **滚动条不吃排版**：网格 `overflow-y: auto` + `scrollbar-gutter: stable`，有没有滚动条，列宽都一样。
  - **拖动排序**：整块 `draggable`（选择模式与描述编辑中禁用拖动；`img` 上 `draggable="false"`），原生 HTML5 DnD——`dragstart` 记 id（**必须 `setData`**，Firefox 否则不启动拖拽）、`dragover.prevent` 记落点（高亮 `--drop` 边框）、`drop` 时**先按同一套语义本地挪一下**（`splice(to, 0, splice(from, 1)[0])`，与后端「插到第 to_index 位」一致）再调 `move` 接口，用返回的整份列表覆盖；失败就重拉。任何变更成功后都 `@changed` 让详情弹框重拉截图，避免弹框后面的图片栏数据陈旧
- **详情弹框信息区**：`dl` 是 `grid-auto-flow: column` + `repeat(6, auto)` 的两栏，12 条正好左右各 6 行——左栏 名称/卡带ID/类型/卡带类型/大小/CRC32，右栏 **截图 [管理]**/描述/本体/封面/创建时间/更新时间（「截图」这行让原本右下角空着的那格填满）；标签用「本体」「封面」而不是「游戏本体」「游戏封面」
- Flash 本地存档：Ruffle 把 SharedObject 写浏览器 localStorage（落盘时机见 Ruffle issue #798），FlashSaveManager 双 tab（本地/云端）封装读写，SW 缓存本体/封面；**`FlashSaveManager.vue` 与 `EmuSaveManager.vue` 这两个存档管理弹框都支持 ESC 关闭**（`window` 冒泡阶段监听，打开时挂、关闭/卸载时摘）：按层级由内到外收——正在编辑云端描述先结束编辑，开着「同步至云端」描述面板先收面板，否则才关弹窗；监听特意挂在 `window` 而不是 `document`，这样 Element Plus 确认框（`ElMessageBox`）自己吃掉 ESC（它会 `stopPropagation`）时不会连带把存档管理弹框也关掉
- 模拟器本地存档：**每个游戏固定只有一份**（覆盖式，不做多槽位）。引擎浏览器档只维护单份暂存（`EmulatorJS-states`）；x 用 `frontend/src/utils/emulatorSaves.js` 把它另存为唯一本地档（`.state` 内容存 IndexedDB，键 `x_emusave:{gameId}:state1`，避免 localStorage 配额；元数据索引在 localStorage `x_emusave_index_v1`）——捕捉、导入 `.state`、云端还原都是覆盖这一份，`ensureSingleSlotModel()` 在进入播放页/存档面板时一次性清掉旧版多槽位档。播放宿主 `emulator-host.html` 暴露 `window.__ejsRpc`（`capture`/`load`，走引擎 `storage.states` 与 `elements.bottomBar` 存/读档）供捕捉与放回；`EmuSaveManager.vue` 本地 tab 只展示这一份（载入/下载/删除），云端仍与 Flash 共用一套快照模型、保留多份历史，只是每个快照只含 1 个文件，local_key 即 `x_emusave:{gameId}:state1`。存档固定叫 `save.state`（本地展示/下载与云端快照文件名都用它，名称不随时间变化，时间看展示的更新时间）

## HTTP

HTML 由 Vue 路由负责，FastAPI **只返回 JSON**。路径一律在 `/api/` 下。稳定路径以下文「前端路由」「后端（摘要）」两表为准。

信封：成功 `{ "ok": true, "data": ... }`；失败 4xx/5xx + `{ "ok": false, "message": "中文" }`。

### 前端路由

| path | 说明 |
|------|------|
| `/login` | 登录 / 注册（无 Layout，页内切换） |
| `/` | 重定向到 `/games`（首页即游戏中心） |
| `/games` `/games/manage` `/games/flash/:gameId` `/games/play/:gameId` `/games/h5/:gameId` | 游戏中心 / 游戏管理 / Flash 播放页 / 主机(EmulatorJS)播放页 / H5 播放页 |

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
| GET / POST | `/api/games/manage`；GET / PUT / DELETE `/manage/<id>` | 游戏管理（POST 为 multipart：name/cartridge_id/description/file[+cover]，一步建条目并按本体扩展名定类型；本体/封面也可改用直链 `body_url`+`body_game_type` / `cover_url`） |
| POST | `/api/games/manage/<id>/assets` | 换本体/换封面（kind=game\|cover，给 `file` 或直链 `url`[+`game_type`]；h5 传 .zip 由后端解包）。换本体会按新扩展名切换类型，但**本体 CRC32 已锁定时只接受同一个文件**（不一致返回 400，且不覆盖旧文件） |
| POST | `/api/games/manage/import` | 从 7k7k/4399/flash.homes 游戏页地址搬运（body `{url, cartridge_id}`，解析下载后入库，Flash 或 H5） |
| POST | `/api/games/manage/<id>/guide` | 整目录上传攻略（multipart：`files` 多个文件 + `paths` 与之一一对应的文件夹内相对路径 JSON 数组；前端已剥掉最外层目录名，根目录必须含 `index.html`） |
| GET | `/api/games/<id>/cover` · `/play` | 封面 inline / 本体下载 |
| GET | `/api/games/<id>/h5/<资源路径>` | H5 解包资源 inline（沙箱安全头；唯一免登录业务接口，入口固定 index.html） |
| GET / HEAD | `/api/games/<id>/guide/<资源路径>` | 攻略静态资源（**需登录**，无沙箱头，入口固定 index.html） |
| GET / PUT | `/api/games/emulator-settings?game_type=` | 模拟器设置（键位/选项/金手指）按平台读 / 整体覆盖写（存 SQLite） |
| GET / POST | `/api/games/saves?game_id=` | 云端存档列表 / 创建快照 |
| GET / PUT / DELETE | `/api/games/saves/<snapshot_id>` | 快照详情 / 改备注 / 删除 |
| GET | `/api/games/saves/<id>/files/<file_id>/download` | 取单个存档文件（.sol/.state） |
| GET / POST | `/api/games/screenshots?game_id=` | 本人该游戏的截图列表 / 上传一张（multipart：game_id/description/file） |
| GET | `/api/games/screenshots/<id>/image` | 截图本体 inline（需登录，越权 404） |
| PUT / DELETE | `/api/games/screenshots/<id>` | 改截图描述（≤15 字）/ 删除 |
| POST | `/api/games/screenshots/<id>/move` | 拖到指定位置（body `{to_index}`），返回整份有序列表 |
| GET / POST | `/api/games/gallery?game_id=` | 该游戏的**共享**图集列表 / 上传一张（同上 multipart） |
| GET | `/api/games/gallery/<id>/image` | 图集图片本体 inline（需登录；共享，但不匿名开放） |
| PUT / DELETE | `/api/games/gallery/<id>` | 改图集图片描述（≤15 字）/ 删除 |
| POST | `/api/games/gallery/<id>/move` | 拖到指定位置（body `{to_index}`），返回整份有序列表 |

切换期已结束：Jinja2 页面路由已删除，只保留 `/api/` 与 `/health`。

## 前端框架层

1. **`request.js`：** 唯一 axios 实例。注入 CSRF、cookie；401 单飞跳登录；错误信封转中文 Message；`notShowError` 可关弹窗。失败一律 reject 一个带 `reported` 标记的 Error（`reported=true` = 拦截器已经弹过提示），所以页面 catch 里要补提示得写成 `if (!err.reported) ElMessage.error(...)`，否则同一条错误会弹两次。
2. **`permission.js`：** 白名单 `/login`；未登录去登录页；已登录访问登录页去 `/`。
3. **`auth.js`：** 可缓存用户名等展示字段。登出必须清约定 key 清单；新增「记住的页面状态」时同步维护。
4. **路由 meta：** `title`、`hiddenInMenu`、`icon`。Layout 里 `buildMenuFromRoutes()` 生成菜单。新增页面 = 加一条带 meta 的子路由。
5. **`components/common/`：** 跨工具复用目录，必须存在。自定义弹窗 `AppDialog`、按钮 `AppButton`、筛选 `AppFilterBar`、空状态 `AppEmpty`、复制 `CopyButton` 放这里；在 Element Plus 上包一层，不要在 `views/` 里堆样式。小件（按钮、空状态、复制）在 `main.js` 全局注册；弹窗/筛选按需引入。Vite 别名 `@components` → `src/components`。
6. **Pinia：** 不要把 Fernet 密钥放进 store。不要做参考项目那种全表列配置，除非以后明确要求。
7. **不要**上 WebSocket，除非以后某个工具明确需要实时。

## 界面

- Layout：侧栏菜单由路由 `meta` 动态生成，顺序为游戏中心、游戏管理。**侧栏是浮层**：常驻收起、鼠标靠近屏幕左边缘滑出，展开时盖在页面之上，不占位、不挤压内容
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
- 安装根目录 `requirements.txt`，仅复制 `backend/` 包，创建 `/app/data`
- `EXPOSE 8910`
- `CMD`：`gunicorn backend.asgi:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8910 --workers 1 --threads 8 --timeout 300`（300s 是为了长上传/流式下载不被 worker 超时杀）

**web 镜像（`frontend/Dockerfile`）**

- 构建上下文为 `frontend/`
- 构建阶段 `node:22.23.3-alpine3.24` 打出 `dist`
- 运行阶段 `nginx:1.27.5-alpine3.21`，`try_files` 回 `index.html`
- `/api/` 与 `/health` 反代到 `http://api:8910`；`client_max_body_size 128m` 是上传网关
- 只为站点开一个 443 server（**没有 9443，也没有任何对象存储反代**）

**`docker-compose.yml`**

- `api`：`build.context: .` + `dockerfile: backend/Dockerfile`，数据根目录 bind `${STORAGE_HOST_DIR:-./data/storage}:/data`，不对外发端口，**没有 `env_file`**（后端不读 `.env`）
- `web`：`build: ./frontend`，`ports: ["${WEB_HTTPS_PORT:-443}:443"]`（**只支持 HTTPS**：不发布 80，也没有 http→https 跳转；只发布宿主侧端口，容器内固定听 443，换端口只改 `.env`），证书目录 bind `./certs:/etc/nginx/certs:ro`（证书随仓库提交），`depends_on: [api]`
- **没有 `volumes:` 段**
- api / web `restart: unless-stopped`

**宿主目录 bind 的时序要求：** 数据目录若在 WSL 发行版（Ubuntu-22.04）的文件系统上，而 Docker Desktop 守护进程先于该发行版启动——开机时 bind 源路径不可达，docker 会挂一个空 tmpfs 顶上，容器里看起来就像「文件全没了」（api 在空目录里建了个空库），重启服务才恢复，且窗口期内的写入会真丢。所以 `STORAGE_HOST_DIR` 必须指向 docker 启动前就可达的固定路径（别指外挂盘的临时挂载点，也别放会被 `git pull` 覆盖的仓库内）。

**数据根目录哨兵**：`create_app()` 第一步（早于建目录、建库）调 `backend/mount_guard.py::ensure_mounted()`——数据根目录 `STORAGE_ROOT` 里没有 `.mounted`（空的标记文件，库就在这个根目录下的 `db/` 里，一个哨兵够了）就建一个。**它不拦启动**：判据只能是哨兵文件（目录可写、能 statvfs 都测不出空目录），而盘没挂上时 bind 已经把空目录挂进容器了，拦也拦不回来——所以这里只做标记与排障线索，风险靠上面那条「把 `STORAGE_HOST_DIR` 指向稳定的路径」规避。

**备份**：不再内置备份脚本。数据都在宿主目录里（`STORAGE_HOST_DIR`），直接拷就行。SQLite 另有一层自动兜底：`create_app()` 启动时调 `backend/backup.py::backup_database()`，当月还没有 `<YYYY-MM>.db`（写在库同目录 `<STORAGE_ROOT>/db/`）就备一份、有就跳过；用 sqlite3 的 backup API 而非拷文件（WAL 下裸拷会撕裂），失败只记 warning 不拦启动，**不做还原功能**。存档（`save/`）不可重建，本体/封面/H5 资源都能重传。

`docker compose up --build` 之后，浏览器打开 **https://localhost**（只支持 HTTPS，80 端口不发布）。

本地开发：`uvicorn backend.asgi:app --reload --port 8910` + `cd frontend && npm run dev`。

## 实现时要生成的配置文件

- `.env.example` — 全部键（只有 `STORAGE_HOST_DIR` 与 `WEB_HTTPS_PORT`）、默认值、**中文注释**
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

最低要求：

- 注册（合法/非法用户名、重名、注册即登录）与登录锁定
- `LocalStorage` 读写/覆盖/删除/目录替换，以及越界路径（`..`、绝对路径）被拒
- 游戏创建必填卡带ID、自动转大写、全局唯一、`PUT` 改不动；上传后文件按 `game/{类型}/{卡带ID}/…` 真实落盘
- `/health` 未登录返回 200
- 未登录访问游戏接口（列表/状态/封面/本体/管理/存档/截图/最近游玩/攻略）一律 401，仅 H5 解包资源接口可匿名访问
- 云端存档按 (user, game) 隔离：读他人快照返回 404
- 游戏截图按 (user, game) 隔离（列表看不到、图片/改描述/移动/删除一律 404）、落盘 `image/{用户名}/{类型}/{卡带ID}/{uuid}.{后缀}`、认不出的图片内容 / 空文件 / 超限 / 描述超 15 字 / 拖动下标越界返回 400、分数耗尽时的整份重排后顺序仍正确、删游戏后行与文件都不留
- 模拟器设置写接口未登录 401、按 (user, game_type) 隔离、非法 game_type 或 payload 返回 400

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
