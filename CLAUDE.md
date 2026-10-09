# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 本仓库是什么

个人自托管的**游戏平台**。Vue 3 SPA（`frontend/`）+ FastAPI JSON API（`backend/`），ORM 用 SQLModel + SQLite。两块内容：**游戏中心**（Flash 用 Ruffle、HTML5 上传 ZIP 解包后用沙箱 iframe、8/16-bit 主机 ROM 用 EmulatorJS 浏览器内游玩；Flash 与模拟器含本地与云端存档，主机另有按账号的游玩截图图库，H5 仅游玩）与**游戏管理**（上传/直链/搬运、卡带 ID 与元数据、整目录上传**攻略**）。账号开放注册，只用于隔离各人的模拟器配置与存档。

**编码约定以 [`AGENTS.md`](AGENTS.md) 为准**——写代码、改代码前先读它。人读的设计文档在 [`docs/architecture.md`](docs/architecture.md)；SQLite 表与文件路径规则的完整结构在 [`docs/data_dict.md`](docs/data_dict.md)。

## 语言约定（重要）

项目默认**中文**：界面文案、Markdown 文档、注释、提交说明、API 错误 `message` 全用中文。代码标识符、路由 path、环境变量名保持英文。**不加 i18n / 多语言切换**。

## 常用命令

后端（开发）：

```bash
python -m backend.cli init-db
uvicorn backend.asgi:app --reload --port 8910
```

前端（另开终端）：

```bash
cd frontend
npm install
npm run dev        # Vite :5173，/api 与 /health 代理到 :8910
```

测试与 lint：

```bash
make test                   # 等价于 python -m pytest + cd frontend && npm run lint，本机跑，不动 Docker
pytest                      # 后端（用临时 SQLite + 临时 STORAGE_ROOT，直接打真实文件系统）
cd frontend && npm run lint
```

Docker（正式运行方式）：

```bash
cp .env.example .env        # 可选：只放 STORAGE_HOST_DIR（数据放宿主哪里）与 WEB_HTTPS_PORT
make all                    # 等价 docker compose build && up -d
# 浏览器 https://localhost，进站点直接点「注册一个」建号（没有命令行建号）
```

镜像与编排：`backend/Dockerfile`（api）、`frontend/Dockerfile`（web），由根目录 `docker-compose.yml` 编排（web + api，**没有对象存储**）。**基础镜像全部固定到补丁版本 + 发行版代号**（`python:3.12.15-slim-trixie`、`node:22.23.3-alpine3.24`、`nginx:1.27.5-alpine3.21`），加新镜像或升级都别用浮动标签。

## 架构要点

- **应用工厂。** `backend/__init__.py` 的 `create_app()` 是唯一入口；生产 ASGI 入口 `backend/asgi.py`。配置来自环境变量（Pydantic Settings，`backend/config.py`）。
- **一个功能一块。** 每块含 `router.py`（只管 HTTP，只返回 JSON）+ `service.py`（领域逻辑）。`service.py` 是以后拆微服务的边界：**禁止在里面使用 FastAPI `Request` / `session`**；存储后端等依赖由构造函数传入。跨模块的流式下载响应收敛在 `backend/storage/access.py`。
- **前端分层。** 页面 `views/` → `api/*`（导出 `xxxAPI`）→ `src/utils/request.js`（唯一 axios 实例）→ FastAPI。新增接口只改 api 层和后端 router，不碰 `request.js`。跨模块 UI 组件放 `src/components/common/`（AppDialog、AppButton、AppFilterBar、AppEmpty、CopyButton），游戏专用组件放 `src/components/games/`。
- **导航与浮层。** 首页即游戏中心（`/` 重定向到 `/games`，无导航中心页）；侧栏菜单项与顺序由 `router/index.js` 的子路由声明顺序 + `meta.title` 生成（游戏中心、游戏管理）。左侧侧栏与游戏播放页的 `GameShell` 标题栏都是**浮层**：常驻收起、鼠标靠近屏幕边缘时滑出，展开时盖在页面之上，不占位、不引起内容缩放。
- **登录态。** 开放注册（账号 + 密码，`POST /api/register`），登录失败锁定；无游客模式，除注册/登录接口与 H5 解包资源外全部接口与页面都要登录（H5 是沙箱不透明源的浏览器约束，拿不到 cookie；**攻略资源是新标签页顶层打开的普通静态页，照常带 cookie，要登录**）。session cookie（HttpOnly、SameSite=Lax），axios `withCredentials`；写操作带 `X-CSRFToken`。路由守卫在 `frontend/src/permission.js`。**不把 token 写进 localStorage**。
- **响应信封。** 成功 `{ "ok": true, "data": ... }`；失败 `{ "ok": false, "message": "中文" }`。
- **配置。** 配置写死在代码里（`backend/config.py`，含 `SECRET_KEY`）；`.env` 只有两个键、且**只给 compose 读**：`STORAGE_HOST_DIR`（宿主数据目录，默认 `./data/storage`）、`WEB_HTTPS_PORT`（对外端口，默认 443），不建 `.env` 也能跑。证书随仓库提交在 `certs/`（`cert.pem` / `cert.key`），compose 只读挂到 web 的 `/etc/nginx/certs`。
- **数据。** **不使用任何 docker 具名卷**：compose 里数据是一个宿主目录 `STORAGE_HOST_DIR`（默认 `./data/storage` → 容器 `/data`，后端读 `STORAGE_ROOT`），游戏文件与 SQLite 都在这个根目录下。**SQLite 路径在代码里写死为 `<STORAGE_ROOT>/db/app.db`**（`backend/config.py` 的 `DB_SUBDIR` / `DB_FILENAME`，没有 `DATABASE_URL` 可配），月度备份也在同一个 `db/` 里。SQLite 里只存游戏文件相对根目录的路径。Gunicorn 必须 `--workers 1`（单进程避免 SQLite 写冲突），多线程处理并发。

## 必须遵守的关键规则

- **文件存储。** 游戏本体/封面/H5 资源/攻略/云端存档/截图都是项目文件根目录（`STORAGE_ROOT`）下的普通文件，**没有对象存储**。相对路径规则集中在 `backend/games/paths.py`，别在别处手拼字符串：本体 `game/{game_type}/{卡带ID}/game.{后缀}`、封面 `game/{game_type}/{卡带ID}/cover.{后缀}`、H5 `game/{game_type}/{卡带ID}/h5/{包内相对路径}`、攻略 `game/{game_type}/{卡带ID}/guide/{文件夹内相对路径}`、存档 `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state`、截图 `image/{用户名}/{game_type}/{卡带ID}/{uuid}.png`（类型那层用 `game_type` 的**键值**，不是中文显示名）。读写一律经 `backend/storage/local.py` 的 `LocalStorage`（`upload/delete/stat/open_download` + 目录级的 `remove_tree/replace_tree/move`），它负责拼根路径并挡掉绝对路径与 `..`；写入先落同目录临时文件再 `os.replace` 改名。`StorageBackend` 协议在 `backend/storage/types.py`。**没有「待配置」状态**：根目录不存在会自己建出来，storage 永远可用。
- **卡带ID。** `games.cartridge_id`：创建时必填（新建、网络上传建条目、搬运都要）、全局唯一（唯一索引 `uq_games_cartridge_id`）、只允许数字/字母/中划线/下划线且**落库前转大写**（`validate_cartridge_id()`）、**建后不可改**（`PUT /manage/{id}` 不接受该字段）。它同时是磁盘目录名，所以改名游戏不会挪动任何文件；要换卡带ID 只能删掉重建。管理页详情里展示它；管理页删除该游戏时要**手打一次卡带ID**才能确认（删除会连磁盘文件与所有账号在该游戏上的云端存档一起清掉）。
- **卡带类型。** `games.cartridge_type`：卡带版本，**始终有值**，`default` 默认 / `jp` 日版 / `us` 美版。目前**只有 FC NES 区分日版/美版**，其余游戏类型只允许 `default`；可选集合在 `backend/games/models.py`（`cartridge_types_for()`），校验入口 `validate_cartridge_type()`（空值取默认、非法值中文 400），前端展示层镜像在 `frontend/src/constants/cartridgeTypes.js`。新建（multipart `cartridge_type`，按所选本体落成的类型给选项）与编辑弹框（`PUT /manage/{id}`，这个字段**可以**手改）两处可设，**只有管理页的添加/编辑弹框能改，用单选（国旗）而不是下拉，单选里「默认」固定第一、其余按取值排序**，游戏中心右键菜单没有这一项；换本体换了游戏类型后，新类型不认的值自动回落 `default`。游戏中心「全部游戏」在游戏类型分组内**再按卡带类型分子网格**，同一种卡带严格同一行，**卡片封面框规则见 `constants/gameCardAspect.js` + `components/games/GameCover.vue`：卡片宽就是**正方形限制框**的边长，封面按类型渲染后等比缩放到长或宽触到框边（rail 传 `CARD_ASPECT_RAIL` 正方形框、整行高低一致；「全部游戏」不传 aspect = 卡片高随封面高，同类型整行仍齐平）。**封面渲染集中在 `components/games/GameCover.vue`，只有游戏中心的卡片用**（「全部游戏」网格与「最近游玩」rail；详情弹框图片栏、游戏管理缩略图与表单预览都显示封面原图）（Flash 画实体光盘、GB/GBC 把封面合成进卡带、其余是普通封面）；**GB/GBC（`gb`）画的是一整张卡带**（固定用 `public/gbc-cart.png` 一张，封面贴进卡带的贴纸窗，几何在 `constants/gameCartridges.js`：贴纸窗按整图百分比定位、封面 `object-fit: fill` 拉伸填满，贴纸窗 528×464 = 正好 99/87；卡片框比值保持 **1/1 正方形**，与 rail 一致，两处卡带一样大）；**界面上只显示国旗不显示文字**（详情弹框、添加/编辑弹框的单选）：图片在 `frontend/public/flags/`（22×16，按 URL 引用的静态文件，文件名是国家/地区英文全称如 `Japan.png`、`USA.png`），「默认」用空白图 `Default.png`。老库由 `backend/database.py` 的 `_ensure_columns()` 启动时补列（无迁移框架）。
- **游戏中心。** 元数据在 SQLite，文件按上面的相对路径落盘。**游戏类型不用手动选，按上传的本体扩展名自动判定**（`backend/games/service.py` 的 `detect_game_type()`：`flash`←`.swf`、`h5`←`.zip`、主机 `nes/snes/gb/gba/segaMD/segaGG/segaMS`←`.nes/.sfc/.smc/.gb/.gbc/.gba/.md/.gen/.gg/.sms`；未收录后缀 400），换本体即随之切换类型（**但本体 CRC32 已锁定时只接受同一个文件**：上传时算好 CRC32 落 `games.crc32`（8 位大写十六进制），再换本体比对不一致就 400 且不覆盖旧文件；`crc32` 为空表示未锁定）；**同类型下游戏名唯一**（联合唯一索引 `uq_games_game_type_name`）、**名字须是合法的 Windows 与百度网盘文件名**（`validate_game_name()`；搬运标题自动无害化）。**换类型时的目录收尾**：先把封面从旧类型目录挪到新类型目录（`LocalStorage.move`），新本体就位后再递归删掉整个旧类型目录。**H5** 上传 `.zip`（根目录含 `index.html`）由后端校验并解包为多文件：整包解到同层暂存目录 `game/{类型}/{卡带ID}/.h5-{随机}`，再用 `replace_tree` 整体替换 `h5/`（**磁盘上没有代际前缀**），清单在 `game_h5_files`（`path` 包内路径 / `file_path` 磁盘相对路径）；播放经 `GET /api/games/{id}/h5/{资源路径}`（唯一免登录业务接口——沙箱里带不上 cookie；响应强制 CSP `sandbox` 不含 `allow-same-origin`），前端 `views/games/h5-player.vue` 用嵌套 sandbox iframe 呈现；沙箱下无 localStorage/Worker，H5 不接入云存档。**攻略**：一个游戏可挂一份静态攻略，就是 `game/{类型}/{卡带ID}/guide/` 下的一整套文件（入口固定根目录 `index.html`，子页面/图片/CSS/字体都是里面的普通文件）；**没有清单表、库里也不存标记**，「有没有攻略」由 `guide/index.html` 是否存在现算（载荷字段 `has_guide`），所以从宿主目录手动拷走/删掉攻略界面立刻跟着变。上传是**整目录**：管理页编辑弹框「上传封面」下方的「上传攻略」（新建弹框没有）用 `webkitdirectory` 选文件夹、剥掉最外层目录名，把文件夹内相对路径按顺序做成 `paths`（JSON 数组，与 `files` 多个 part 按下标一一对位）一次 multipart 提交 `POST /api/games/manage/{id}/guide`（≤1000 个文件，Starlette 表单解析硬上限，前端先拦）；后端先全量校验（路径归一化、大小写不敏感查重、必须含 `index.html`、大小上限）再写同层暂存目录 `.guide-{随机}`、最后一次目录改名整体替换 `guide/`（重传即整体替换，失败零残留），**不动本体路径与 CRC32**。读取走 `GET|HEAD /api/games/{id}/guide/{资源路径}`（**需登录**，与 H5 免登录不同；只加 `nosniff` + `no-cache`，**不加 CSP sandbox**——它是新标签页顶层导航打开的同源页面），文件不存在即 404。入口在游戏中心卡片右键菜单「详情」下方的「攻略」（**没有攻略就不显示这一项**），`window.open(..., "_blank", "noopener")` 开新标签页。删游戏、换本体换类型都随整个旧游戏目录一起清掉。**搬运**：`POST /api/games/manage/import` 传 `{url, cartridge_id}`（7k7k/4399/flash.homes 游戏页地址），由 `backend/games/importer.py` 服务端解析下载后入库，前端在游戏管理页「搬运游戏」弹窗。**网络上传**：管理页本体/封面的「网络上传」按钮弹框填 http/https 直链（本体还要下拉选类型，服务端下载后走同一条上传管线，上限 512MB），实现见 `backend/games/remote.py`。播放：Flash 走 Ruffle、H5 走沙箱 iframe、主机走 EmulatorJS（引擎资产由 `frontend/scripts/fetch-emulatorjs.mjs` 构建期按固定版本拉取到 `public/emulatorjs/`，nginx immutable 静态服务，运行时不依赖外网）。`GET /api/games/{id}/play`（附件下载，content-type 按扩展：`.swf` 保持 Flash 值、ROM/H5 ZIP 为 `octet-stream`）、`GET /api/games/{id}/cover`（inline 预览，`?download=1` 附件下载）。模拟器播放页标题栏按钮自左向右为**截图**、保存配置、窗口倍率、**显示游戏机**（GBA / FC / GBC 有）、存档管理；「显示游戏机」把机壳图（`public/gba-shell.png` 一块带透明屏幕洞的 GBA 机身，洞 1920×1280 = 精确 3:2 且居整图正中；`public/gbc-shell.png` GBC 正面机身，洞 1285×1156.5 = 10:9（= 160×144），左右留白各 423px；FC 的电视机壳按显示比例分两张：`public/nes-shell.png` 洞 1084×948.5 = 256:224，即入项目前把原素材的屏幕那段纵向拉长 7/6、下面 121 行控制条等比不动再裁掉透明留白；`public/nes-shell-43.png` 是原素材本身，洞 1084×813 = 4:3）盖在画面上，按「洞宽 = 画面宽」放大并偏移，洞就严丝合缝露出游戏画面，任何画面尺寸都跟着缩放；两张图的几何在 `views/games/emulator-player.vue` 的 `SHELLS` 表里按游戏类型取（换图必须同步改洞的几何）；机壳比画面大得多（GBA 那张宽是画面的两倍、电视机壳 1.22 倍），所以用 `position: fixed` 定位（absolute 会被 `.game-shell__body` 的 `overflow: auto` 裁掉并顶出滚动条），倍率调大后超出浏览器视口的部分看不见即可、不做裁剪也不隐藏；「适应窗口」模式下要塞进可用空间的从画面换成整张机壳。截图（按钮或快捷键 **Ctrl+Shift+S**）截下后**不再下载**：先弹确认框（180px 正方形限制框预览 + 可选描述 ≤15 字），点「确认」才带描述上传进**按账号隔离的截图图库**（`/api/games/screenshots`，内容落 `image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}`，只本人可见可改；格式按内容 magic 认，PNG/JPG/WebP/GIF，单张 ≤16MB）；详情弹框顶部是一条图片栏（一行 4 个 180px 正方形框，无底色无圆角、与信息区之间无分隔线，封面共享且恒占第一格，其后本人的截图，可左右翻页——格子排在一条轨道上水平滑动，按钮与滚轮都能翻，截图下方居中显示描述），右栏「截图 [管理]」打开的是**相册式平铺管理页**：可上传本地图片、单击描述就地改（同高同字号，回车/失焦存、ESC 放弃，无按钮无计数，≤15 字）、工具条右上角固定的「删除」进多选删除、整块拖动排序（后端分数排序：只改被拖那一行，间隙不足才整份重排）。图片栏支持滚轮翻页（上滚前翻、下滚后翻）。截图优先要引擎自带截图（内核侧读帧缓冲 → 原生像素），拿不到或全黑则退回同帧拷贝画布（引擎上下文 `preserveDrawingBuffer: false`，个别浏览器会拷到全黑），窗口选择器（`EmuWindowSelect.vue`，按钮 + 就地弹出的**两列矩阵**：行 = 倍率、「适应窗口」，列 = 显示比例）以各平台**帧缓冲分辨率**为基准（`EMU_NATIVE`：NES 256×224——fceumm 默认裁掉上下各 8 行过扫描，宿主页把显示比例设成像素完美，见下；SNES 256×224；GB/GBC 160×144；GBA 240×160；MD 320×224；GG 160×144；SMS 256×192），倍率 1×–4× 含 .5 档，按帧缓冲高度换算、宽度按舞台宽高比推出（菜单里显示真实窗口尺寸）；**只有 FC 有第二列「4:3」**（真机 CRT 观感：内核改 `fceumm_aspect = 4:3` 并关掉过扫描裁切 → 帧缓冲 256×240、1× 窗口 320×240，机壳换成原素材那张），默认仍是左列「像素完美」（8:7，1× = 256×224）；**舞台长宽比取引擎上报的显示宽高比**（`__ejsRpc.videoInfo().aspect`），不是帧缓冲比例——引擎按内核上报的 aspect（含像素宽高比校正；FC 由宿主页 `emulator-host.html` 按 `?ratio=`（运行中切换走 `__ejsRpc.setDisplayMode`）设成像素完美或 4:3）等比摆放画面，画布填不满处即黑边。云端存档（`/api/games/saves`，需登录）把某(用户,游戏)此刻全部本地存档文件（Flash `.sol` / 模拟器 `.state`）存为整体快照：元数据在 `game_cloud_snapshots(_files)`，内容按 `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state` 落盘；**删游戏时会把该游戏所有账号的存档快照行、存档文件与存档目录一并清掉**（快照目录按文件路径反推，因为换过类型的游戏目录名是快照当时的类型；截图同样一并清掉，理由相同）。模拟器本地档固定只有一份、固定叫 `save.state`（每游戏键 `x_emusave:{gameId}:state1`，捕捉/导入/云还原都是覆盖），由前端 `utils/emulatorSaves.js`（内容存 IndexedDB）维护，播放宿主 `public/emulator-host.html` 暴露 `__ejsRpc`（capture/load/screenshot/videoInfo）。登录用户的模拟器设置（键位/选项/金手指）另按平台随账号同步：存 SQLite（`game_emulator_settings`，不落文件），进游戏时自动写回 localStorage，改完点标题栏「保存配置」手动上传。**最近游玩**（`/api/games/recent`，需登录）按账号存 SQLite（`game_recent_plays`，唯一 `(user_id, game_id)`），由三个播放页在真正拉起播放器时各自调 `utils/recentGames.js` 的 `reportGamePlayed()` 上报。**游玩时长与进度**（`/api/games/stats`，需登录）存 `game_user_stats`（唯一 `(user_id, game_id)`，`play_seconds` + `progress`），`utils/gamePlaytime.js` 是模块级单例，三个播放页在与 `reportGamePlayed()` 完全相同的时机起停表、每 30 秒心跳累加（单次上报在 service 里收敛到 0..300 秒），`document.hidden` 期间不累计；进度只由用户手动设置，不随游玩自动变。游戏中心页**只在游戏卡上接管右键**，可设置进度与时长（覆盖式）；类型下拉**左边**有进度下拉可联合筛选；卡片封面下方是居中一行**进度标签 + 总时长**，**进度还是「未开始」就整行不渲染**。
- **游戏图集。** `game_gallery_images`：一个游戏一套的展示图（宣传图、说明书扫描件之类），**按游戏共享**——不记上传者，任何登录用户都能传、改描述、删、拖动排序（`/api/games/gallery`，与截图的 `/api/games/screenshots` 共用同一套相册实现，只少了「用户」这一维）。内容落**游戏目录内**的 `game/{类型}/{卡带ID}/image/{uuid}.{后缀}`，所以**随换游戏类型一起迁移**（搬目录的同时把行里的 `file_path` 换成新前缀）；删游戏时行与文件一并清掉。管理入口在**游戏管理页的编辑弹框**（「图集 → 管理」，新建弹框没有），详情弹框的图片栏只读展示，顺序是封面 → 图集 → 本人的截图。
- **数据根目录哨兵。** `create_app()` 最开头调 `backend/mount_guard.py::ensure_mounted()`，早于建目录与建库：数据根目录 `STORAGE_ROOT` 里没有 `.mounted` 就建一个（空的，只是「这是数据根」的标记）。**它不拦启动**——数据目录在 WSL 挂载的 Windows 盘上（`/mnt/…`）而 docker 先于盘起来时，bind 会把宿主空目录挂进容器，服务会在空目录里建新库；这层风险不拦，靠把数据目录指向 docker 启动前就可达的路径规避（见 DEVELOP.md「排障」）。
- **SQLite 月度备份。** `create_app()` 启动时调一次 `backend/backup.py::backup_database()`：当月还没有 `<YYYY-MM>.db`（写在库同目录 `<STORAGE_ROOT>/db/`）就备一份，已有则跳过。用 `sqlite3` 的 backup API 而不是拷文件（WAL 下裸拷会撕裂），先写 `.tmp` 再改名，失败只记 warning、**绝不拦住启动**。不做还原功能，回滚靠手工替换 `app.db`。
- **会话签名密钥写死。** `SECRET_KEY` 在 `backend/config.py` 里写成一个常量（session cookie 签名用），跟仓库一起走、不从环境变量读；换值使所有已登录会话失效。
- **明确不做。** React、TypeScript、i18n、OAuth/邮箱验证码/找回密码、对象存储（MinIO/S3）、JWT、WebSocket、Redis/PostgreSQL/Celery、把密钥写进前端或 git。

## 目录结构（约定，只建这些）

```
frontend/                 # Vue 3 SPA（main.js / permission.js / router / layout / store / api / utils / views / components/common）
frontend/src/components/games/  # 游戏专用组件（GameCard、GameDetailDialog、GameScreenshotGallery 图片栏、ScreenshotManagerDialog/ScreenshotConfirmDialog、GalleryManagerDialog/ImageAlbumDialog、Flash/EmuSaveManager、播放器与 GameShell）
backend/__init__.py       # create_app() 工厂
backend/{auth,games,tools,storage}/  # auth 与 games 各有 router.py + service.py；games 另有 paths.py、save_*（云端存档）、screenshot_*（截图）、gallery_*（图集）、settings_*、stats_*、importer.py、remote.py
backend/storage/          # 跨模块：types（协议与 StoredObject）、local（LocalStorage）、access（流式下载响应）
backend/cli.py            # python -m backend.cli（只剩 init-db）
docs/                     # architecture.md（设计源）+ data_dict.md（数据字典）
tests/                    # pytest（test_auth / test_local_storage / test_games / test_game_saves / test_game_screenshots / test_game_emulator_settings / test_game_recent / test_game_stats）
```

## Git 约定

- 分支名：`<类型>/<描述>`（小写，`-` 连接，简短）。如 `feat/cartridge-id`。
- 提交标题：`<类型>: <中文短语>`。类型用英文小写：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`。一个提交只做一件事。
