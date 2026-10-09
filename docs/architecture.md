# 架构说明

## 本文档覆盖什么

本文说明 **xgame**（个人自托管游戏平台）的目标架构，是给人读的设计源。编码 Agent 的实现约束见 [`AGENTS.md`](../AGENTS.md)；**数据库与文件存储的结构**是唯一权威，见 [`data_dict.md`](data_dict.md)，本文件不再逐列重复。

**读者：** 本仓库主人，以及之后生成或修改代码的 Agent。

**语言：** 项目默认中文。文档、界面文案、用户可见提示均使用中文。代码标识符与路由 path 保持英文。

**最后更新：** 2026-10-04

## 项目为什么存在

x 是私人游戏平台，不是对外 SaaS。只做一件事：把 Flash、HTML5 与 8/16-bit 主机（NES/SNES/GB/GBA/MD/GG/SMS）游戏收进自己的库里，在浏览器里即开即玩，并让每个账号有自己独立的模拟器配置与游戏存档。

两块界面（注册表 `backend/tools/registry.py`）：

1. **游戏中心**（`games`）— 列表 + 播放。Flash 走 Ruffle、主机 ROM 走 EmulatorJS、H5 走沙箱 iframe；Flash 与主机支持「本地存档 + 按账号的云端存档」，主机还支持截图入库（详情弹框里的图片栏），H5 仅游玩。
2. **游戏管理**（`games-manage`）— 上传/网络直链/搬运游戏本体与封面、改元数据、删除。

界面是 Vue 3 SPA。FastAPI 只提供 JSON API。**开放注册**（只填账号密码），除注册/登录接口与 H5 解包资源外，所有页面与接口都要求登录。账号不做安全机制，只用于隔离各人的模拟器配置与存档。

## 系统设计

### 高层架构（当前目标）

```
浏览器
   │  Vue SPA（nginx :443）＋ 播放页（Flash：SW / Ruffle；主机：EmulatorJS）
   │  页面 → api/* → request.js → /api/*
   ▼
┌─────────────┐   /api/*    ┌──────────────────────────────────────┐
│  web        │ ──────────▶ │  api（Gunicorn + uvicorn）            │
│  nginx      │             │  router 只返回 JSON                   │
│  静态 dist  │             │  auth/games 的 service                │
└─────────────┘             │  storage/access 跨模块流式下载通道    │
                            └──────────┬───────────┬───────────────┘
                                       ▼           ▼
                                 data/app.db   项目文件根目录
                                              （STORAGE_ROOT 挂载点）
```

浏览器只和 nginx 通信。API 负责会话和编排，领域逻辑在 service，I/O 在适配器。Router 不得直接访问 SQLite 或磁盘。游戏文件（本体/封面/H5 资源/攻略/云端存档/截图）落在宿主目录挂进容器的 `STORAGE_ROOT` 下，**SQLite 里存的是相对这个根目录的路径**；上传/下载都由 API 分块流式代理，浏览器不直连磁盘。

### 技术栈

| 层 | 技术 | 原因 |
|-------|------------|-----|
| Web 界面 | Vue 3 + Vite + Pinia + Element Plus + vue-router | 独立 SPA；无 i18n / 无 TypeScript |
| 播放运行 | Ruffle（Flash）+ EmulatorJS（8/16-bit 主机，构建期按固定版本打包静态资产）+ 前端 Service Worker | Flash SWF 与主机 ROM 在本站即开即玩；SW 缓存 Flash 资源 |
| API | FastAPI + Pydantic | 应用工厂、类型校验、OpenAPI 友好 |
| ORM | SQLModel（Pydantic + SQLAlchemy）+ SQLite | 模型与校验统一在 Pydantic |
| 应用服务器 | Gunicorn（uvicorn worker）+ nginx | api 跑 ASGI，web 托管静态并反代 |
| 语言 | Python 3.12 / JavaScript | 后端类型支持好；前端不加 TypeScript |
| 账号 | werkzeug 密码哈希 + 登录失败锁定 | 账号只隔离配置与存档，不做更强的安全机制 |
| 文件存储 | 宿主目录 bind 到容器内 `/data/storage`，后端 `LocalStorage` 直接读写普通文件 | 目录结构即业务结构，用户可直接拷走/备份；不需要对象存储那一层 |
| 配置 | Pydantic Settings + `.env` | 适合 Docker，密钥不进 git |
| 运行 | Docker Compose：`web` + `api` | 一条命令，浏览器可访问；本项目只在本地跑，没有远程发布流程 |

不要引入 React、Celery、Redis、PostgreSQL、MinIO/对象存储，除非后续功能明确需要。

### 目录结构

实现的目标树。以 AGENTS.md 的目录约定为权威，此处只列与架构相关的关键文件。

```
x/
├── AGENTS.md                 # 编码 Agent 约定（权威）
├── CLAUDE.md / README.md     # 给人看的上手说明
├── docs/
│   ├── architecture.md       # 本文件（设计源）
│   └── data_dict.md          # 数据字典：SQLite + 文件存储结构（唯一 schema 权威）
├── frontend/                 # Vue 3 SPA
│   ├── src/api/              # 按业务域；导出 xxxAPI（auth / games）
│   ├── src/views/            # login / games（index、manage、flash-player、emulator-player、h5-player）
│   ├── src/components/common/# AppDialog、AppButton、AppFilterBar、AppEmpty…
│   ├── src/components/games/ # 游戏专用：GameShell、GameCard、FlashPlayer、FlashSaveManager、EmuSaveManager、
│   │                         #   GameScreenshotGallery(详情图片栏)、ScreenshotManagerDialog、ScreenshotConfirmDialog
│   ├── src/utils/            # request / auth / gameSaves(Flash) / emulatorSaves(模拟器本地档) / emulatorSettings(模拟器设置) …
│   ├── scripts/              # copy-ruffle.mjs、fetch-emulatorjs.mjs（构建期拉取引擎资产）
│   ├── public/game-asset-sw.js   # Flash 播放页资源缓存 SW（按 key+updated_at）
│   ├── public/emulator-host.html # EmulatorJS 播放宿主（iframe 隔离，__ejsRpc：存档 + 截图 + 画面几何）
│   └── public/emulatorjs/    # EmulatorJS 引擎资产（构建生成，gitignore）
├── backend/                  # FastAPI JSON API（见下方路由树）
├── tests/                    # test_auth/local_storage/games/game_saves/game_screenshots/game_stats/game_recent/game_emulator_settings
├── data/                     # 本机开发默认的数据根目录 data/storage（含 db/，gitignore）
├── docker-compose.yml        # web + api（宿主数据根目录 bind：STORAGE_HOST_DIR → /data）
├── requirements.txt
├── .env.example              # 全部键、假值、中文注释
└── Makefile
```

```
backend/
├── __init__.py        # create_app()：装配 app.state.storage（LocalStorage）、注册全部 router
├── asgi.py / config.py / database.py / deps.py / csrf.py / cli.py / http.py / errors.py
├── auth/              # 注册/登录/退出、登录锁（router/service/login_lockout/models）
├── tools/             # 注册表 registry.py + /health 与 /api/tools
├── games/             # 游戏条目/资产（service/router/paths）+ 云端存档 save_router/save_service
│                      #   + 游戏截图 screenshot_router/screenshot_service + 模拟器设置 settings_*
│                      #   + 游玩统计 stats_* + 搬运 importer + 网络直链 remote
└── storage/           # 跨模块通用：types(StoredObject/StorageBackend 协议/StoredObjectStream)、
                       #   local(LocalStorage，相对路径 ↔ 磁盘)、access(流式下载响应)
```

### 分层规则

| 层 | 所在位置 | 可以引用 | 禁止引用 |
|-------|----------|------------|-----------------|
| 表现层 | `*/router.py` | services、Pydantic 请求体、deps、`storage/access` | 直接访问 SQLite / 文件系统、复杂查询 |
| 应用层 | `*/service.py` | models、paths、存储协议 | FastAPI `Request` / `session` |
| 适配器 | `*/models.py`（SQLModel）、`storage/local.py` | SQLAlchemy、标准库 | router |

`service.py` 是拆分边界：以后加微服务时，其公开方法就是 HTTP API。跨模块的「按相对路径流式下发」收敛到 `storage/access.py`（`build_download_response`），各 router 复用同一份。`service.py` 里禁止使用 FastAPI `Request`/`session`。

## 数据流

### 账号（开放注册 + 登录）

```
1. POST /api/register { username, password }（无需登录、免 CSRF）
   AuthService.create_user()：用户名 ^[0-9A-Za-z_-]{2,32}$、密码 6–64 字符、重名 409
   建号即写 session（注册成功即登录）
2. POST /api/login { username, password }
   AuthService.authenticate() 校验 users 表 werkzeug 哈希
   LoginLockoutService：同一 username 连续失败 ≥3 短锁 5 分钟，≥6 锁到当天 UTC 结束；成功即清行
3. 通过 → session 写入 user_id（HttpOnly、SameSite=Lax）；写操作带 X-CSRFToken
```

注册与登录都在 CSRF 白名单里（登录页此时还没有 token），其余写接口一律校验 `X-CSRFToken`。

没有游客模式：登录页可在「登录 / 注册」间切换，后端也**没有**「可登录可不登录」的依赖——所有业务端点都依赖 `CurrentUser`，未登录一律 401。唯一例外是 H5 解包资源 `GET /api/games/{id}/h5/{资源路径}`，原因是浏览器约束：H5 在不透明源沙箱 iframe 里播放，它发出的请求按跨站处理，`SameSite=Lax` 的 session cookie 不会带上（详见「决策 8」）。

### 游戏中心

```
管理（登录）：POST /api/games/manage（multipart：name/cartridge_id/description/file[+cover]）
  一步建条目并写本体；**卡带ID 必填、创建后不可改**（只能删掉重建），它全局唯一且是磁盘目录名
  游戏类型由本体文件扩展名自动判定，不接受手动指定（flash←.swf；h5←.zip；nes←.nes；snes←.sfc/.smc；
  gb←.gb/.gbc；gba←.gba；segaMD←.md/.gen；segaGG←.gg；segaMS←.sms），未收录的后缀一律 400
  网络上传：本体/封面也可以给 http/https 直链（建条目用 body_url+body_game_type / cover_url，
  换资源用 url[+game_type]），由服务端 backend/games/remote.py 下到临时目录再走同一条上传管线，
  单文件上限 512MB；本体走直链时类型以所选 game_type 为准——地址能认出类型就必须一致（否则 400），
  认不出（网盘式无后缀直链）就用该类型的默认后缀；封面直链必须是 jpg/jpeg/png/gif/webp
  换本体：POST /manage/{id}/assets(kind=game) 同样按新扩展名切换类型——先算新本体 CRC32 并与库里已锁定的比对
  （不一致直接 400，连旧文件都不覆盖），再写新本体，成功后才清理旧类型遗留（整个旧类型目录，
  封面会先挪到新类型目录，h5 清单行一并删），写入失败整体回滚、不动旧档；PUT /manage/{id} 只改
  名称/描述/清空封面（clear_cover），不接收 cartridge_id 也不接收 game_type；同一类型下游戏名唯一
  （联合唯一索引 uq_games_game_type_name），不同类型可重名；卡带ID 全局唯一（uq_games_cartridge_id）
  落盘路径：本体 game/{类型}/{卡带ID}/game.{后缀}、封面 game/{类型}/{卡带ID}/cover.{后缀}，重传即覆盖
  h5 的 .zip 另由后端解包：校验清单（路径/重名/上限/必须含 index.html，可剥单一顶层目录）后，
  整包解到同层暂存目录 .h5-{随机}，再用目录改名整体替换 h5/，单事务替换 game_h5_files 清单
攻略（登录）：POST /api/games/manage/{id}/guide（multipart：files 多个文件 + paths 与之一一对应的
  相对路径 JSON 数组；前端用 webkitdirectory 选整个文件夹并剥掉最外层目录名）
  落盘 game/{类型}/{卡带ID}/guide/{文件夹内相对路径}，入口固定根目录 index.html
  后端先全量校验（路径归一化／大小写不敏感查重／必须含 index.html／文件数与体积上限），
  再写同层暂存目录 .guide-{随机}、一次目录改名整体替换 guide/；失败清掉暂存目录、旧攻略不动
  读取 GET|HEAD /api/games/{id}/guide/{资源路径}（**需登录**）：路径归一化后直接拼磁盘路径，无清单表
  「有没有攻略」不落库：由 guide/index.html 是否存在现算（载荷里的 has_guide）
搬运（登录）：POST /api/games/manage/import { url, cartridge_id }
  backend/games/importer.py 解析 7k7k / 4399 / flash.homes 游戏页并下载到临时目录，
  再走上面同一条上传管线（Flash 单个 swf；H5 镜像 bundle 打成 zip 复用解包）；封面一并下载。
  仅接受 7k7k.com / 4399.com / flash.homes 域名的游戏页地址（防 SSRF），H5 会跟随页面引用的外部资源域名。
  flash.homes 是 Flash 存档站：作品一概是按 sha256 存在 CDN 上的单个 SWF（页面里播放器岛的 props
  给出 sha256 / 标题 / 封面文件名，JSON-LD 兜底），因此搬运结果必为 flash；其 id 是 12 位短码，
  页面上写作 F8YX-1DNE-JQG9 形式，会归一化成该形式后再拼页面地址
播放：
  Flash  → /games/flash/{id}   Ruffle 播放，SW（game-asset-sw.js）按 key+updated_at 缓存资源
  主机   → /games/play/{id}    外层 SPA 壳内嵌 iframe /emulator-host.html → EmulatorJS；
                              ROM 直连 /api/games/{id}/play（EmulatorJS 自带 IndexedDB 缓存 core/ROM）
                              标题栏按钮（自左向右）：截图 → 保存配置 → 窗口倍率 → 显示游戏机（GBA / FC / GBC 有）→ 存档管理；
                              显示游戏机：把机壳图按「洞宽 = 画面宽」放大后盖在画面上，洞正好露出游戏画面，
                              画面尺寸一变就跟着缩放。图与洞的几何按游戏类型放在 emulator-player.vue 的 SHELLS 表里，
                              FC 还按显示比例分两套（切比例一起换）：GBA = public/gba-shell.png（带透明屏幕洞的
                              机身，洞 1920×1280 = 精确 3:2 且居整图正中）；GBC = public/gbc-shell.png
                              （GBC 正面机身，洞 1285×1156.5 = 10:9，正是 GB/GBC 的 160×144；原素材
                              左右留白差 17px，入项目前从左边裁掉 17px 让屏幕左右对称）；FC 的「像素完美」列 =
                              public/nes-shell.png（CRT 电视机壳，洞 1084×948.5 = 256:224，原素材洞是 4:3，
                              入项目前把屏幕那段纵向拉长 7/6、下面带按键的控制条等比不动，再裁掉透明留白）；
                              FC 的「4:3」列 = public/nes-shell-43.png（原素材本身，洞 1084×813 = 4:3，
                              只裁掉顶部留白）。机壳比画面大得多（GBA 那张宽是画面的两倍），
                              故用 position: fixed 定位以免被 .game-shell__body 的 overflow 裁掉/顶出滚动条；
                              倍率调大后超出浏览器视口的部分看不见即可，不裁剪也不隐藏
                              截图 = __ejsRpc.screenshot：先要引擎自带截图（内核侧读帧缓冲 → 原生像素
                              如 256×224），拿不到/全黑则退回同一帧 rAF 里拷画布（引擎的 WebGL 上下文
                              preserveDrawingBuffer:false，合成后绘制缓冲即失效，个别浏览器会拷到全黑）；
                              截下来不直接下载：先弹确认框（180px 方框预览 + 下方一行描述 ≤15 字，
                              回车即确认），
                              点「确认」才带着描述上传进「游戏截图」图库，之后在游戏详情里看得见；
                              快捷键 Ctrl+Shift+S 同效（F12 是浏览器开发者工具的保留键，拦不住）；
                              焦点可能停在宿主 iframe 的引擎画布上，所以父页面与 iframe 的 window
                              都挂一份 keydown（iframe 那份用捕获阶段，免得被引擎的按键处理吞掉）；
                              窗口选择器（EmuWindowSelect.vue）是一张两列矩阵：行 = 倍率
                              （1×/1.5×/2×/2.5×/3×/3.5×/4×，另有「适应窗口」），列 = 显示比例，
                              基准是各平台帧缓冲分辨率（NES 256×224、SNES 256×224、GB/GBC 160×144、
                              GBA 240×160、MD 320×224、GG 160×144、SMS 256×192），按帧缓冲高度换算窗口
                              像素高度、宽度按舞台宽高比推出（菜单里就是真实窗口尺寸）。只有 FC 画第二列：
                              左「像素完美」（8:7）、右「4:3」（真机 CRT 观感，1× = 320×240，用的是完整
                              240 行帧）。舞台长宽比取 __ejsRpc.videoInfo().aspect（引擎上报的显示宽高比，
                              含内核 PAR 校正），不是帧缓冲比例——引擎按该比例等比摆放画面，画布（= 舞台）
                              填不满的地方就是黑边；引擎就绪前按选中模式的比例兜底。FC（nes → fceumm）
                              两种模式各一套内核选项（宿主页按 ?ratio= 设，运行中切换走
                              __ejsRpc.setDisplayMode）：pp → fceumm_aspect = PP + 上下各裁 8 行过扫描
                              （帧缓冲 256×224，显示 8:7）；wide → fceumm_aspect = 4:3 + 不裁过扫描
                              （帧缓冲 256×240，显示 4:3）
  H5     → /games/h5/{id}      外层 SPA 壳内嵌 sandbox iframe，入口 /api/games/{id}/h5/index.html，
                              页内相对资源落到同前缀（/api/games/{id}/h5/…）
  攻略   → 不在 SPA 里开页面：游戏中心右键「攻略」用 window.open 在**新标签页顶层**打开
          /api/games/{id}/guide/index.html，页内相对资源落到同前缀（/api/games/{id}/guide/…）
          资源接口**需登录**（同源顶层导航，cookie 正常带上），响应不带 CSP sandbox，只加 no-cache
  GET /api/games/{id}/play 的 content-type 按本体扩展名：.swf 保持 Flash 专用值，h5/其余统一 octet-stream
存档：
  Flash  ：Ruffle 把 SharedObject 写浏览器 localStorage；「本地/云端」双 tab 存档管理
  EmulatorJS：引擎浏览器档只维护“单份暂存”（EmulatorJS-states）；xgame 另存一份本地档，每游戏固定一份
            （.state 内容存 IndexedDB，键 x_emusave:{gameId}:state1，文件名固定 save.state，
             捕捉/导入/云还原都覆盖它）——由播放宿主
            /emulator-host.html 暴露的 __ejsRpc（capture/load，走引擎 storage.states）捕捉/放回
  H5     ：不接入云存档（沙箱不透明源下浏览器存储不可用，见「决策 6」）；播放页无存档管理
云端快照（登录，Flash/模拟器共用）：GET/POST /api/games/saves?game_id=…
  一次「同步至云端」= 把该游戏此刻全部本地存档文件上传为一个整体快照
  （Flash 一个游戏可有多条 .sol；模拟器恒 1 条 .state，固定名 save.state）
  manifest(local_key,name) 与文件一一对应；元数据落 game_cloud_snapshots(_files)，
  内容按 save/{用户名}/{类型}/{卡带ID}/{uuid}.state 落盘（文件名不体现原名；
  name 含扩展名时下载名原样）
  「同步至本地」按快照逐文件取回写回本地存储（Flash 写 localStorage；模拟器覆盖 x_emusave 的 state1）
  删除游戏：素材目录、所有账号在该游戏上的存档快照（行 + 文件 + save/…/{卡带ID}/ 目录）、
  最近游玩与游玩统计行一并清掉——游戏一删，它的快照就再也没有入口能列出来
游戏截图（登录，按账号）：GET/POST /api/games/screenshots · GET /{id}/image ·
  PUT /{id}（改描述 ≤15 字）· POST /{id}/move（拖动后落点下标）· DELETE /{id}
  两张来源：播放页截图（Ctrl+Shift+S / 标题栏按钮，PNG）与详情「截图 [管理]」里的上传按钮
  格式按内容 magic 判（PNG/JPG/WebP/GIF），后缀也由内容定，单张上限 16MB；mime 入库时定下，
  读图显式当 content-type 下发（`.webp` 在部分 Python 的 mimetypes 里不认识）
  截图按 (用户, 游戏) 隔离：只本人可见可改，越权一律 404；图片接口必须登录（不做公开静态路径）
  元数据落 game_screenshots，内容按 image/{用户名}/{类型}/{卡带ID}/{uuid}.{后缀} 落盘；
  读取一律用行里的 file_path（截图不参与「换游戏类型」的迁移，目录里的类型是上传当时的）
  排序是分数排序：sort_order 为浮点分数，新图追加到末尾，拖动重排只改被拖那一行的分数
  （取相邻两分数的中值），相邻间隔小到阈值以下才由后端把整份重新铺开（间隙不足时后台重排）
  封面渲染集中在 components/games/GameCover.vue，**只有游戏中心的卡片**用它
  （「全部游戏」网格与「最近游玩」rail 都走 GameCard → GameCover）；详情弹框图片栏、
  游戏管理列表缩略图与添加/编辑表单的封面预览一律显示封面原图：
  GB/GBC（gb）的卡片画的是一整张卡带（固定用 public/gbc-cart.png 一张），
  封面贴进卡带的贴纸窗里（几何在 constants/gameCartridges.js：贴纸窗按整图百分比定位，
  封面 object-fit: fill 拉伸填满、不留黑边；贴纸窗 528×464 = 正好 99/87）
  卡片尺寸规则（constants/gameCardAspect.js + GameCover.vue）：卡片宽就是「正方形限制框」
  的边长，封面按类型渲染后**等比缩放到长或宽触到框边**、水平垂直居中 ——
  「最近游玩」rail 传 CARD_ASPECT_RAIL（1/1）→ 卡片是正方形、整行高低一致；
  「全部游戏」网格不传 aspect → 卡片高 = 封面高（同类型封面形状一致，整行仍齐平）。
  于是同一盘卡在两处一样大；Flash 光盘固定占框边长的 84%（四周留一圈空）
游戏详情的图片栏把封面（全站共享的一张，第一格显示原图）与本人的截图排成一行 4 个 180px 正方形框
  （框内 object-fit: contain，长边到上限为止），放不下时左右翻页（封面固定第一页第一格）
  删除游戏：所有账号在该游戏上的截图行、文件与 image/…/{卡带ID}/ 目录一并清掉
模拟器设置（登录用户，按平台）：GET/PUT /api/games/emulator-settings?game_type=…
  内容 = 引擎 localStorage 那块 {controlSettings, settings, cheats}，整块 JSON 存 SQLite（不落文件）
  引擎只在启动流程里读一次设置键 → 播放页在设 iframe src 前先写回 localStorage（自动加载）
  保存由播放页标题栏「保存配置」按钮手动触发，不做自动侦测
游玩统计（登录用户，按游戏）：POST /api/games/stats/playtime · PUT /api/games/stats/{id}/playtime|progress
  与游戏类型无关：三个播放页共用 utils/gamePlaytime.js，在与「最近游玩」上报完全相同的
  时机起表、卸载时停表；每 30 秒心跳累加，document.hidden 期间不累计（切标签页不涨）
  play_seconds 存累计秒数（可手动改写为指定小时数，覆盖而非累加），progress 只由用户
  在游戏中心右键菜单手动设置（未开始/进行中/已通关），不随游玩自动变更；元数据落
  game_user_stats，GET /api/games 与 /api/games/recent 载荷都带这两个字段
```

## 关键设计决策

### 决策 1：Vue SPA + FastAPI JSON

**决定：** 界面用 Vue 3 SPA，FastAPI 只提供 `/api/` JSON。登录态用 HttpOnly session cookie；没有游客模式，登录墙覆盖全部页面与接口（H5 资源接口例外，见决策 8）。
**原因：** 需要可复用组件与独立前端迭代；session cookie 比 localStorage token 更不容易被页面脚本偷走。
**何时重评：** 需要实时推送时再考虑 WebSocket，而不是改认证方式。

### 决策 2：功能模块一套 router + service

**决定：** 每个功能一块（`router.py` + `service.py` + 按需 models）。注册表 `backend/tools/registry.py` 给导航；跨模块的下载响应收敛到 `backend/storage/access.py`。
**原因：** 模块彼此隔离；以后拆微服务只需换 service 实现。
**何时重评：** 多个模块共享很大领域模型时再抽 `backend/domain/`。

### 决策 3：SQLModel 作为 ORM

**决定：** 表模型用 SQLModel（Pydantic + SQLAlchemy），配置用 Pydantic Settings，请求体用 Pydantic。schema 汇总在 `docs/data_dict.md`。
**原因：** 与 FastAPI 同一套 Pydantic 生态。
**何时重评：** 若 ORM 需求超出 SQLModel 表达力，可在 adapter 层单独用 SQLAlchemy Core。

### 决策 4：不使用 docker 具名卷，数据全落宿主目录

**决定：** compose 里一个具名卷都不用：**数据是一个宿主目录** `STORAGE_HOST_DIR`（默认 `./data/storage` → 容器 `/data`，后端读 `STORAGE_ROOT`），里面装着游戏文件与 SQLite（库固定在其下的 `db/app.db`，月度备份也在这个 `db/` 里）；**证书**是仓库里的 `certs/`（`cert.pem` / `cert.key`），compose 只读挂给 web 的 `/etc/nginx/certs`。
**原因：** 数据要能被人直接拿到——存档要能自己拷出来备份、本体要能直接扔进模拟器、库要能用 sqlite3 打开看一眼，套一层 docker 卷管理就都得借容器。全部落宿主目录后，备份/迁移/排查都是普通文件操作。
**代价与时序要求：** 宿主 bind 在 WSL 发行版（或 Windows 盘）未就绪时会被挂成空目录（详见「排障」）。发行版起来后重启容器即恢复，但**窗口期内的写入会真丢**（落在空目录里）。

**挂载哨兵：** `backend/mount_guard.py` 在 `create_app()` 最开头（早于建目录、建库）确保数据根目录 `STORAGE_ROOT` 里有一个空的 `.mounted` 文件：没有就建出来（库就在这个根目录下的 `db/` 里，一个哨兵够了）。它是「这个目录就是数据根」的标记，**不拦启动**：上面那条时序问题会静默发生（api 在空目录里建空库），而判据只能是哨兵文件——目录可写、能 statvfs 都测不出空目录（tmpfs 同样可写），何况 bind 在容器创建时就解析完了，容器内等待也没用，拦不住。规避办法是把 `STORAGE_HOST_DIR` 指向 docker 启动前就可达的稳定路径，见「排障」。
**何时重评：** 多容器并发写或拆出的服务需要网络 SQL。

### 决策 5：账号只做隔离，不做安全机制

**决定：** 开放注册，只填用户名与密码；用户名 `^[0-9A-Za-z_-]{2,32}$`、密码 6–64 字符；密码用 werkzeug 单向哈希，登录带失败锁定。没有邮箱、验证码、找回密码、OAuth。
**原因：** 这套账号只用来隔离各人的模拟器配置与游戏存档，不承载敏感数据，加验证码只会让自托管变得难用。用户名收窄字符集不是为了安全，而是因为它会被直接当成存档目录名（`save/{用户名}/…`），限定在文件系统安全的那一档就不必再考虑转义。
**何时重评：** 真要放敏感数据时，得先补上多因子与权限模型。

### 决策 6：H5 游戏以 ZIP 上传并用沙箱隔离

**决定：** H5 游戏本体是 `.zip`，后端解包为多文件（`game_h5_files` 清单 + `game/{类型}/{卡带ID}/h5/{路径}` 文件），入口固定 `index.html`；播放时在 `GameShell` 内嵌 sandbox iframe，资源响应带 `Content-Security-Policy: sandbox`（不含 `allow-same-origin`）。H5 不接入云存档。
**原因：** H5 是从外部站点抓取/导入的第三方 HTML/JS，若与本站同源，游戏脚本可读取并操作本站接口。sandbox 不透明源让游戏读不到 cookie/DOM、无法注册 Service Worker、也无法调用 `/api`；资源另加 `Access-Control-Allow-Origin: *` 以放行不透明源下的 `fetch`/ES module/引擎 `.wasm` 读取。
**代价：** 不透明源下 `localStorage`/`IndexedDB`/Web Worker 不可用，依赖它们的游戏可能报错；`<video>/<audio>` 的 Range 请求不支持。若需兼容，升级路径是给 H5 单独端口/子域（本期不做）。
**何时重评：** 有大量依赖浏览器存储的 H5 游戏时，改为独立源承载。

### 决策 7：文件存储走「相对路径 + 本地目录」，保留流式协议

**决定：** `StorageBackend` 协议（`backend/storage/types.py`）只含 `upload`（分块流式写）/ `delete` / `stat` / `open_download`（流式读），唯一实现是 `LocalStorage`（`backend/storage/local.py`）：把 SQLite 里的相对路径拼上 `STORAGE_ROOT` 读写，写文件先落同目录临时文件再改名。目录级操作（`remove_tree` / `replace_tree` / `move`）由它单独提供（删游戏、H5 整包替换、类型切换挪封面）。列表来自 SQLite，协议没有 `list`。
**原因：** 磁盘上没有元数据存储，所以「上传时的 mime」不落盘，读取时按后缀现猜（H5 资源另有显式 MIME 表，由 router 传入 content-type）；相对路径 + 统一拼根路径既让 SQLite 的引用稳定（换盘只改一个环境变量），又保住了分块流式与「service 不知道根目录在哪」的分层。
**何时重评：** 需要多机共享或对象存储语义时再换实现，service 侧不用改。

### 决策 8：全部页面与接口需登录（H5 资源接口除外）

**决定：** 不做游客模式——前端所有路由经 `permission.js` 拦、后端除注册/登录接口外全部依赖 `CurrentUser`。唯一免登录的业务接口是 H5 解包资源 `GET /api/games/{id}/h5/{资源路径}`。
**原因：** 游戏库不需要对外公开，一道登录墙就能挡住爬取与围观。H5 例外不是设计选择而是浏览器约束：H5 在沙箱 iframe（不透明源，无 `allow-same-origin`）里播放，它发出的请求一律按跨站处理，`SameSite=Lax` 的 session cookie 不会随请求带上（只有 `SameSite=None` 才可能，而默认拦截三方 cookie 的浏览器连它也不发），给这个接口加登录依赖只会让游戏加载不了 JS/图片。播放页本身仍要登录，未登录也拿不到游戏 id 与入口地址。
**攻略不在例外里：** 它是登录用户上传的同源静态页，在**新标签页顶层导航**打开（不是沙箱 iframe），请求照常带 cookie，所以 `GET|HEAD /api/games/{id}/guide/{资源路径}` 与其它业务接口一样依赖 `CurrentUser`，响应也不加 CSP `sandbox`。**取舍**：同源意味着攻略里的脚本能以登录用户身份读写本站 localStorage、调 `/api`（只有登录用户能上传，威胁模型是家庭自托管；隔离方案见决策 6 的代价，需改承载方式）。
**何时重评：** 若要连 H5 资源也严格鉴权，得改承载方式（父页面代取后经 blob/postMessage 交给沙箱，或把 H5 放到独立源，见决策 6），而不是给资源接口加登录。攻略若要隔离，同样得改成沙箱承载（代价：资源接口必须免登录、攻略内不能用 localStorage）。

### 决策 9：云端存档按整体快照

**决定：** 「云端存档」不是逐键覆盖，而是把某(用户,游戏)此刻全部本地存档文件（Flash `.sol` / 模拟器 `.state`）上传成一个不可变快照（`game_cloud_snapshots` + `game_cloud_snapshot_files` 两行），内容按 `save/{用户名}/{类型}/{卡带ID}/{uuid}.state` 落盘；元数据按 (user_id, game_id) 隔离、越权访问返回 404。本地存储形态由前端决定：Flash 直接读写 Ruffle 的 localStorage（一个游戏可有多条），模拟器由 xgame 的 `emulatorSaves.js` 单一本地档（每游戏固定 `x_emusave:{gameId}:state1`，内容 IndexedDB）+ 播放宿主 `__ejsRpc` 维护，云快照对二者提供同一套接口与 local_key 语义。
**原因：** 存档是「回滚点」语义，快照保证还原一致性；文件名用 uuid 而非原名，是为了让磁盘上的存档文件不可猜、不重名，原始文件名仍留在 SQLite 里供下载时还原。
**何时重评：** 需要增量同步时再演进协议。

### 决策 10：卡带ID 是不可变的游戏身份

**决定：** 每盘「卡带」有一个全局唯一的卡带ID：创建时必填、自动转大写、只允许数字/字母/中划线/下划线；建后不可修改（`PUT` 不接受该字段），要换只能删掉重建。磁盘目录名用它而不是数据库自增 id 或游戏名。
**原因：** 游戏名会改、数据库 id 对人不友好，而目录名一旦跟着它们变，磁盘上就会留下孤儿目录或需要搬文件。用不可变且人可读的卡带ID 命名，改游戏名不会挪动任何文件，用户翻磁盘时也能一眼认出哪盘是哪盘。
**代价：** 想改卡带ID 就得删游戏重建（连同它在该账号下的存档快照记录一起重来）。
**何时重评：** 若真需要改，可加一条「移动整个目录 + 更新行」的显式迁移操作，而不是让 `PUT` 顺手改。

### 决策 11：模拟器设置按平台随账号同步

**决定：** 登录用户的模拟器设置（键位 + 画面/音量等选项 + 金手指）按 `(user_id, game_type)` 各存一套，整块 JSON 文本直接存 SQLite（`game_emulator_settings`），不落文件。播放页在设 iframe `src` 之前把云端值写回引擎读的那个 localStorage 键（自动加载）；保存是手动的——播放页标题栏「保存配置」按钮把当前整块配置整体 PUT 上去。云端无记录时不写不回传。
**原因：** 引擎只在 `startGame()` 里读一次设置（`started` 置位前），之后再写 localStorage 不会被采纳，所以「加载」只能发生在拉起 iframe 之前——宿主页与 SPA 同源、共用 localStorage，父页面可以直接预写。保存之所以做成显式按钮：引擎没有「设置已保存」事件也没有保存按钮，唯一变更信号是包装实例 `saveSettings`（试过，依赖宿主页与引擎内部实现、易受宿主页缓存影响），换成用户点一下更简单可靠，也顺带让「什么时候同步」由用户掌控。
**代价：** 键名公式 `ejs-{gameId}-{core}-{游戏名}-settings` 依赖引擎实现，升级 EmulatorJS 后可能失效（当前实测一致）。按平台存意味着同平台不同游戏互相覆盖（换平台才换一套），这是选定的语义。忘记点保存则改动只留在本机。多设备并发为后写覆盖。
**何时重评：** 若要改成每游戏一套或全平台共用一套，只需改表的唯一约束与接口维度。

### 决策 12：游戏截图按账号隔离，封面全站共享

**决定：** 截图是账号自己的东西——元数据按 (user_id, game_id) 存 `game_screenshots`，字节落 `image/{用户名}/{类型}/{卡带ID}/{uuid}.{后缀}`，只有本人能看、能改描述、能删能排序（越权一律 404，图片接口也要登录）。游戏封面仍然只有全站共享的一份（`games.cover_path`），所有人在详情里看到同一张。截图**不参与**「换游戏类型」的目录迁移：目录里的类型是上传当时的，读取、单张删除与删游戏清理一律按行里的 `file_path`。**排序用分数**：`sort_order` 是浮点分数，拖动重排只改被拖那一行的分数（相邻中值），间隙切没了才整份重排——顺序只在一处（后端）说了算，前端整份替换。
**原因：** 同一盘游戏可能多人玩，截图是「我的游玩记录」（还带自己的描述），混进一个共享视图没有意义；封面是这盘卡带的样子，本来就该只有一份。不做目录迁移是因为它只让磁盘更整齐，却要为此写一条跨用户、跨类型目录的搬移逻辑——按路径读写的代价为零，收益为负。

**图集是另一档**（`game_gallery_images`，与截图共用同一套相册实现）：一个游戏一套的展示图（宣传图、说明书扫描件之类），**按游戏共享**——不记上传者，任何登录用户都能传、改描述、删、拖动排序，字节落在**游戏目录内**的 `game/{类型}/{卡带ID}/image/`。两组图回答的是两个问题：「这盘卡带长什么样」（共享、随游戏类型一起迁移）与「我玩到哪儿了」（私有、不迁移）。
**代价：** 同一游戏的截图可能分散在 `image/{用户名}/旧类型/` 与 `image/{用户名}/新类型/` 两个目录里（删游戏时按 `file_path` 反推，两处都会清掉）。详情图片栏里封面恒占第一格，没有封面时第一格留空占位，截图从第二格起排。
**何时重评：** 若以后要让截图对所有人可见（例如做成公开画廊），需要给表加可见性字段并放宽 `_get_owned` 的过滤。

## 模块依赖

```
frontend views / api/*
        ↓
  routers（tools、auth、games、games/saves、games/screenshots、games/settings、games/stats）
        ↓
     services（auth/game/cloud-save/screenshot/emulator-settings/game-stats …）
        ↓
   adapters（models、storage/local、paths）
        ↓
   config / database / deps / http / errors
```

**规则：**

1. 下层永不引用 FastAPI 请求上下文（`deps.py` 只做装配）。
2. 模块间不互相引用对方的 router；跨模块通用下载由 `backend/storage/` 提供。
3. 禁止循环引用；`service.py` 依赖以参数传入（session、存储后端）。

## 数据模型

所有 SQLModel 表与文件路径规则见 **[`data_dict.md`](data_dict.md)**（auth 2 表、games 9 表，共 11 张 + 7 类文件路径规则）。模型定义在 `backend/games/models.py` / `backend/auth/models.py`，路径规则定义在 `backend/games/paths.py`；改结构时同步更新 data_dict.md。

## HTTP 表面

HTML 由 Vue 路由负责，JSON 一律在 `/api/` 下；信封 `{ "ok": true, "data": ... }` / `{ "ok": false, "message": "中文" }`。各前缀：

| 前缀 | 说明 |
|-------|-----|
| `/health` | 免登录纯文本 `ok` |
| `/api/csrf` | 取 CSRF token |
| `/api/register` `/api/login` `/api/logout` `/api/me` | 注册 / 登录 / 登出 / 当前用户 |
| `/api/tools` | 工具注册表（导航用，前端目前不消费） |
| `/api/games` | 列表、状态、`/manage`（增删改 + `/manage/import` 搬运 + `/manage/{id}/guide` 攻略上传）、`/{id}/cover`、`/{id}/play`、`/{id}/h5/{资源路径}`、`/{id}/guide/{资源路径}` |
| `/api/games/stats` | 游玩时长与进度：心跳累加时长、手动设置总时长、手动设置进度 |
| `/api/games/saves` | 云端存档整体快照 CRUD + 单文件下载 |
| `/api/games/screenshots` | 游戏截图：列表 / 上传 / 取图 / 改描述 / 拖动排序 / 删除（按账号隔离，全部需登录） |
| `/api/games/gallery` | 游戏图集：同一套接口，但**按游戏共享**（不记上传者，任何登录用户都能改） |
| `/api/games/emulator-settings` | 登录用户的模拟器设置（键位等）按平台读写，存 SQLite |

**免登录：** 只有 `/health`、`/api/csrf`、`/api/register`、`/api/login`，以及 H5 解包资源 `GET|HEAD /api/games/{id}/h5/{资源路径}`（沙箱不透明源带不上 cookie，见决策 8）。`/play` 的 content-type 按本体扩展名：`.swf` 保持 Flash 专用值，主机 ROM 与 h5 ZIP 统一 `octet-stream`。其余端点均需登录，写操作另带 `X-CSRFToken`。

## 安全架构

- Compose 只把 `web`（nginx :443）映射到宿主；`api` 不对外发端口，浏览器经 nginx 反代访问 `/api`。
- **只支持 HTTPS**：80 端口既不发布、也没有 http→https 跳转 server，浏览器一律走 `https://`。
- **对外端口可配（只影响发布端口，容器内仍听 443）**：`.env` 的 `WEB_HTTPS_PORT` 决定宿主侧映射，默认 `443`。证书固定是仓库里的 `certs/cert.pem` 与 `certs/cert.key`，compose 把该目录只读挂给 nginx 的 `/etc/nginx/certs`。
- Session cookie：HttpOnly、SameSite=Lax；生产 HTTPS 下 `Secure`（`SESSION_COOKIE_SECURE` 固定配置，测试环境自动关闭）。签名密钥是 `backend/config.py` 里写死的 `SECRET_KEY`（见「配置」）：它一旦泄露就等于任何人都能伪造登录态，所以换值后既有会话全部失效。
- 账号：密码 werkzeug 单向哈希；登录带失败锁定；开放注册意味着**任何能访问站点的人都能建号**，这是有意为之——站点本身应当只暴露在内网或自有网络里。
- 写操作（除 register/login/csrf/health 外）校验 `X-CSRFToken`。
- 免登录面只有注册/登录接口、`/health` 与 H5 资源（见上节）；攻略资源**需登录**（同源顶层导航，见决策 8）。
- H5 游戏内容按不可信处理：资源响应强制 CSP `sandbox`（不含 `allow-same-origin`）+ `nosniff` + `Referrer-Policy: no-referrer`，播放页 iframe 再加 `sandbox` 属性，双重保证游戏无法访问本站 cookie/DOM/接口或注册 Service Worker。
- 上传有大小上限（web nginx `client_max_body_size` 128m 为上传网关；游戏本体走直链另有 `MAX_REMOTE_BYTES` = 512MB）与每类型扩展名白名单；H5 ZIP 解包另有条目数/单条/总解压量/压缩比上限，并拒绝绝对路径、`..`、重名与加密条目；攻略整目录上传同样过路径归一化与大小/文件数上限（1000 个，Starlette 表单解析的硬上限）；上传内容不执行（H5 在沙箱 iframe 内运行；攻略是登录用户上传的同源页面，见决策 8 的取舍说明）。
- **所有落盘路径都经 `LocalStorage._resolve()` 校验**：拒绝绝对路径与含 `..` 的相对路径；卡带ID（`^[0-9A-Z_-]+$`）与用户名（`^[0-9A-Za-z_-]+$`）的字符集本身就是文件系统安全的，H5 包内路径与攻略内路径另有 `normalize_h5_path()` / `normalize_guide_path()` 归一化（同一套规则）。
- **搬运会发起服务端出站请求**：入口地址只接受 7k7k.com / 4399.com / flash.homes 域名（`importer.detect_site` 按 host 校验），避免被当作任意 URL 代理（SSRF）；H5 镜像会跟随被信任游戏页里引用的外部资源域名（抓的是静态资源，不跟着外链网页乱爬），并受文件数/单文件体积上限约束。
- 本应用只给主人与（游戏的）访客使用，不加 OAuth、多租户角色、公开分享。

## 运行架构

```
主机
└── docker compose（一条命令启动，**不用任何具名卷**）
     ├── api                    # backend/Dockerfile → Gunicorn+uvicorn :8910（仅内部）
     │    ├── 宿主目录 ${STORAGE_HOST_DIR} → /data
     │    │    ├── game/ save/ image/   游戏文件、存档与截图
     │    │    └── db/           app.db 与月度备份 <YYYY-MM>.db
     │    └── 配置：全部在 backend/config.py（后端不读 .env）
     └── web                    # frontend/Dockerfile → nginx :443，反代 /api 到 api
          └── 仓库 certs/ → /etc/nginx/certs（只读）
```

证书是随仓库提交的自签名证书（`certs/cert.pem` / `certs/cert.key`）；要换就 `scripts/gen-certs.sh`（`make certs`）重新生成，全程只用 openssl、不需要 docker。

**备份**：三份数据都在宿主目录里，想怎么备就怎么备——存档（`STORAGE_HOST_DIR/save/`）与截图（`STORAGE_HOST_DIR/image/`）不可重建，本体/封面/H5 资源/攻略可以重传。

**SQLite 的月度备份**（`backend/backup.py`）：`create_app()` 启动时检查一次，当月还没有备份就写一份 `<YYYY-MM>.db` 到库同目录（即 `<STORAGE_ROOT>/db/`），已有则跳过——一个自然月最多一份，文件名按**本机本地时间**取月份。用 `sqlite3` 的 backup API 而不是拷文件（WAL 下裸拷会撕裂），先写 `.tmp` 再改名，失败只记 warning、绝不拦住启动。**不做还原功能**：要回滚就停服务，把备份文件改名成 `app.db` 手动替换。

**开发 vs Docker：**

| | 开发 | Docker |
|--|-----|--------|
| 界面 | Vite `:5173`，代理 `/api` | nginx 静态 `dist` |
| API | `uvicorn backend.asgi:app --reload --port 8910` | Gunicorn + uvicorn worker |
| 数据库 | `<STORAGE_ROOT>/db/app.db`（默认 `./data/storage/db/app.db`） | 同一个根目录 → 容器 `/data/db/app.db` |
| 游戏文件 | `<STORAGE_ROOT>`（默认 `./data/storage`） | 宿主 `${STORAGE_HOST_DIR}` → 容器 `/data` |
| 证书 | 仓库 `certs/`（`make certs` 重新生成） | 同一个目录 → 容器 `/etc/nginx/certs`（只读） |
| 建号 | 浏览器打开站点自助注册 | 同左（不再有命令行建号） |

## 配置

配置**写死在代码里**：`backend/config.py` 放 `SECRET_KEY`、`SESSION_COOKIE_*`、`DB_SUBDIR` / `DB_FILENAME` 与本机默认的数据根目录，容器里的数据根目录由 `backend/Dockerfile` 的 `ENV STORAGE_ROOT=/data` 固定。`.env` 只剩两个键，而且**只有 docker compose 读它们，后端进程一个都不读**（`backend/config.py` 不加载 `.env`）；`.env.example` 列出这两个键与中文注释，`.env` 加入 gitignore，不建 `.env` 也能跑。

| 变量 | 默认 | 用途 |
|----------|----------|---------|
| `STORAGE_HOST_DIR` | `./data/storage` | **宿主侧**数据根目录；容器里挂到 `/data`。游戏文件在它下面，SQLite 固定在 `<根>/db/app.db` |
| `WEB_HTTPS_PORT` | `443` | 对外发布的 HTTPS 端口（容器内 nginx 固定听 443，见「安全架构」） |

代码内固定：`SECRET_KEY`（session cookie 的签名密钥，换值让所有已登录会话失效）、`STORAGE_ROOT`（容器 `/data`，本机 `<repo>/data/storage`）、SQLite 路径 `<STORAGE_ROOT>/db/app.db`、证书 `certs/cert.pem` / `certs/cert.key`、`SESSION_COOKIE_SECURE`；nginx `client_max_body_size 128m` 是上传网关（游戏 GBA 整卡 32MiB 等大文件经它放行）。

## 性能

v1 单用户。不要在应用内加缓存、队列或 CDN。

- 列表来自 SQLite；文件按相对路径直接读，没有额外的元数据查找。
- 上传/下载分块流式（`LocalStorage.upload` / `open_download`），上传正文按块落盘到临时文件后改名，下载按块下发，不把文件整读进应用内存。
- SQLite 单文件 + Gunicorn `--workers 1 --threads 8 --timeout 300`（300s 覆盖长上传/长下载；`--workers 1` 避免 SQLite 写冲突）。

## 测试期望

```
pytest            # 后端（临时 SQLite + 临时 STORAGE_ROOT + TestClient）
cd frontend && npm run lint
```

最低要求：未登录写接口 401；`/health` 未登录 200；注册（合法/非法用户名、重名、注册即登录）与登录锁定；`LocalStorage` 的读写/覆盖/删除/目录替换与越界路径拒绝；游戏创建必填卡带ID、转大写、唯一、`PUT` 改不动；上传后文件按 `game/{类型}/{卡带ID}/…` 真实落盘；未登录访问游戏接口（列表/状态/封面/本体/管理/存档/截图/攻略）一律 401、H5 资源接口可匿名访问；攻略整目录上传按目录落盘、缺 `index.html` / 路径越界 / 重名一律 400 且磁盘零残留、重传整体替换、无攻略 404、删游戏与换类型后目录不留、`has_guide` 跟磁盘走；模拟器设置按 (user, game_type) 隔离、非法平台或 payload 返回 400；截图按 (user, game) 隔离（越权 404）、落盘 `image/{用户名}/{类型}/{卡带ID}/{uuid}.{后缀}`、认不出的图片内容 / 空文件 / 超限 / 描述超 15 字返回 400、拖到越界位置返回 400、删游戏清干净。

## 排障（设计层面）

**问题：开机（`wsl --shutdown` 后重开）后 data 目录看起来是空的**
原因：数据目录所在的盘（WSL 挂载的 Windows 盘 `/mnt/…`）在容器起来时还没挂上，bind 把宿主的空目录挂进了容器，服务就在那儿建了一个新库。数据本身没丢，但**窗口期内的写入会真丢**（落在空目录里）。哨兵文件不拦这种情况——盘没挂上时它只会在空目录里再建一个。
处理：确认盘挂上（`mountpoint -q /mnt/d`），然后 `docker compose restart api`；治本是把 `STORAGE_HOST_DIR` 指向挂载稳定、docker 启动前就可达的路径，别放会被 `git pull` 覆盖的仓库里。

**问题：登录时提示「今日已禁止登录」/「请 5 分钟后再试」**
原因：同一用户名连续失败触发了登录锁定（≥3 短锁 5 分钟，≥6 锁到当天 UTC 结束）。
处理：换账号或等锁定到期；成功登录会清掉计数行。

**问题：上传游戏报「卡带 ID 已经被占用」**
原因：卡带ID 全局唯一（跨游戏类型也算），且创建后不可改。
处理：换一个卡带ID，或先删掉占用它的游戏。

**问题：H5 游戏页面能打开但资源 404**
原因：重传 ZIP 时入口路径变了（例如整包从带顶层目录变成不带），或包内路径大小写与引用不一致。
处理：H5 清单以包内路径为准，入口固定根目录 `index.html`；重传后刷新播放页（资源响应带 `no-cache`）。

## 相关资源

- [`AGENTS.md`](../AGENTS.md) — 编码 Agent 的实现约定（权威）
- [`data_dict.md`](data_dict.md) — SQLite 10 表 + 文件路径规则
- [FastAPI](https://fastapi.tiangolo.com/) / [SQLModel](https://sqlmodel.tiangolo.com/) / [Ruffle](https://ruffle.rs/) / [EmulatorJS](https://emulatorjs.org/)
