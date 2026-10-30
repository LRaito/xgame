# Windows 解压即用包

## 范围与权威

- 这是第二条交付路线，与 Docker 并存。
- 面向一台 Windows、用户不懂命令行的场景。
- 不用装 Python、不用装 Docker、不需要管理员权限。
- 后端自己托管前端 dist，单进程 uvicorn，走 http。
- 解压后双击即玩，局域网里手机/平板也能连。
- 启动器是 `packaging/windows/launcher.py`。
- 外壳操作在 `winops.py`，打包脚本是 `make_zip.py`。
- 后端静态托管见 `backend/static_site.py`。
- 请求体上限见 `backend/request_limit.py`。
- 设计背景见 `../architecture.md`；包内分工见 `packaging/windows/README.md`。

## 数据与路径

- 两条路线数据格式完全一致，同一份数据目录两边都能读。
- 但**绝不允许同时打开同一份数据目录**。
- Windows 侧与 WSL/容器侧的文件锁互相看不见，同时写就是坏库。
- 压缩包里没有多余的一层目录，条目直接躺在根上。
- 包内主要条目：`python/`、`backend/`、`web/`、`launcher.py`。
- 还有 `启动游戏平台.cmd`、`允许局域网访问.bat` 与 `allow-lan.ps1`。
- `data/` 是数据目录，首次启动自动建。
- `runtime/` 是包内临时目录，放 `port.txt` 与 `last-error.txt`。
- 数据库固定在 `data/runtime/db/app.db`。
- H5/攻略解包缓存在 `data/runtime/game/...`。
- 数据目录可以改到包外，用 `xgame.ini` 的 `data_dir` 指绝对路径。
- `runtime_dir` 不填就跟着 `data_dir` 走。
- 可直接指向以前 WSL 的数据目录；切过来前先 `docker compose down`。
- 版本号同时写进包根 `version.txt` 与前端 `web/version.txt`。
- NDS BIOS 是用户自备文件，不随仓库提交。

## 行为与规则

**构建。**

- `make win` 组装出 `dist-win/xgame_v<版本>.zip`。
- `make win-image` 只构建/更新构建环境镜像，不出包。
- 整个组装在容器里跑，宿主机只要有 Docker。
- 宿主机不需要 node / python / curl / zip。
- 构建环境镜像是 `packaging/windows/Dockerfile.build`。
- 能固定的依赖全预置在镜像的 `/opt/winbuild` 下。
- 预置 Windows 版 CPython，release 与 sha256 钉死在 `runtime.env`。
- 预置 win 轮子，依赖清单是 `requirements-win.txt`。
- 预置前端 `node_modules`，按 `package-lock.json` 安装。
- 预置 EmulatorJS 引擎资产，版本钉在 `fetch-emulatorjs.mjs`。
- 镜像 tag 是 Dockerfile + 那些输入文件的哈希，改了自动重建。
- 构建环境用 Debian（glibc）而不是 Alpine（musl）。
- 原因是前端依赖里有平台相关的原生二进制。
- 只有建镜像那一次要联网；之后每次出包都是离线的。
- 包内自检 `smoke_win.py` 由宿主机在构建后补跑。
- 容器里没有 binfmt_misc，执行不了包里的 `python.exe`。

**版本号。**

- 版本号唯一出处是 `scripts/version.sh`，Docker 与 Windows 包共用。
- HEAD 正好停在最新 tag 上：`v1.0.0`。
- HEAD 在 tag 之后：`v1.0.0-<HEAD 提交时间毫秒>`。
- 包里不做版本比较，也没有自动升级。

**前端静态托管。**

- `static_site.py` 只在 `STATIC_DIR` 非空时注册。
- Docker 路线不设 `STATIC_DIR`，一条静态路由都没有。
- 行为规范是 `frontend/nginx.conf.template`。
- 改 nginx 配置时必须同步改 `static_site.py`。
- 语义一：`/api/` 下未匹配路径回 JSON 404，不回落 `index.html`。
- 语义二：`/version.txt` 不缓存，缺失即 404，不回落。
- 语义三：三个 immutable 前缀未命中即 404。
- 三个前缀是 `assets/`、`ruffle/`、`emulatorjs/`。
- 语义四：`index.html` 与 `emulator-host.html` 必须 no-cache。
- 语义五：其余未命中回落 `index.html`，支持 SPA 深链。
- 语义六：MIME 用显式表，不用 `mimetypes`。
- Windows 上 `mimetypes` 读注册表，`.js` 可能被注册成 `text/plain`。
- 那样会整站白屏，所以必须显式给 MIME。
- 语义七：路径安全自己兜，拒绝 `..`、反斜杠、NUL 与含 `:` 的段。

**请求体上限。**

- `request_limit.py` 顶替 nginx 的 `client_max_body_size`。
- 带了 `Content-Length` 且超限：直接 413，请求体一个字节都不读。
- 写方法却没带 `Content-Length`（分块传输）：411 拒掉。
- Docker 路线也挂它，但 nginx 的 512m 先拦，这里只是兜底。

**启动器。**

- `launcher.py` 在进程内跑 uvicorn，不起子进程。
- Windows 上 terminate 是硬杀，会留半截 SQLite。
- 进程内跑时关窗口 / Ctrl+C 都能走优雅退出。
- 启动器设置 `STORAGE_ROOT` 与 `RUNTIME_ROOT`。
- 还设 `STATIC_DIR`，让后端托管前端 dist。
- 还设 `SESSION_COOKIE_SECURE=false`。
- 原因是局域网走 http，Secure cookie 不会被浏览器保存，登录会静默失效。
- `xgame.ini` 的键：`data_dir`、`host`、`port`、`open_browser`。
- 默认 `data_dir = data`、`host = 0.0.0.0`、`port = 8910`、`open_browser = yes`。
- 自检先查 MSVC 运行库 `vcruntime140.dll`。
- 再探本机 SQLite 有没有 FTS5。
- 数据目录里有 `.mounted` 时提醒这是 Docker/WSL 在用的目录。
- 服务就绪后打开浏览器，并打印本机与局域网两个地址。

**升级与停止。**

- 包里没有任何自动升级的代码。
- 升级三步：关窗口 → 解压新包到新目录 → 把 `data` 搬过去。
- 解压新包要先建空目录，别直接覆盖旧目录。
- 桌面快捷方式与开机自启指向旧路径，升级后要重跑那两个 `.bat`。
- 从更早版本升级：先把 `data\db` 改名为 `data\runtime\db`。
- 不改名的话新版会当成全新安装，账号全部消失。
- 停止服务 = 关掉那个控制台窗口。
- 硬杀不会坏库，SQLite 有回滚日志，未提交事务下次打开时回滚。
- 包不写注册表、不装系统服务、不碰系统目录。
- 删掉文件夹就算卸载。

**打包与编码。**

- 打 zip 用 `make_zip.py`，不用命令行的 `zip`。
- 条目直接躺在压缩包根上，不套一层目录。
- 非 ASCII 文件名必须带 UTF-8 标记位（general purpose bit 11）。
- Info-ZIP 不设这个标记位，Windows 资源管理器会按 OEM 代码页解释。
- 于是 `启动游戏平台.cmd` 会显示成乱码。
- WinRAR 会自己猜 UTF-8，预解压窗口里看着正常，最容易骗过构建者。
- 包内 `.cmd` / `.bat` 内容纯 ASCII。
- 原因是 cmd 按 OEM 代码页解析批处理，中文混在里面会乱码或解析出错。
- `.ps1` 存成 UTF-8 **带 BOM**，否则 PowerShell 5.1 会按 ANSI 读。

**MOTW。**

- 从网上下载的 zip 解压出来，每个文件都带「来自 Internet」标记。
- 带标记时每双击一次 `.cmd` / `.bat` 都会弹一次安全警告。
- 最干净的办法：解压**之前**右键 zip → 属性 → 勾「解除锁定」。
- 已经解压了也可以双击一次 `解除锁定.bat` 补上。
- 具体步骤见 `说明.txt` 第一节；启动器还会探 `.cmd` 的数据流并提醒。

**与 Docker 的差异。**

| 项 | Docker | Windows 包 |
|----|--------|------------|
| 前端静态站 | nginx `:443` | 后端 `static_site.py` 托管 |
| 应用服务器 | gunicorn + uvicorn | 单进程 uvicorn |
| 协议 | HTTPS | HTTP |
| session cookie | `Secure` | 启动器设成 false |
| 上传闸门 | nginx 512m | `request_limit.py` |
| 后端配置 | 只认 `STORAGE_ROOT` | 启动器另设 `STATIC_DIR` |

- EmulatorJS 不需要跨源隔离（`EJS_threads=false`），不用 COOP/COEP。
- NDS BIOS 缺失时播放页会在启动前给中文提示。

## 边界与错误

- `\\wsl$` 路径不支持作为数据目录，9p 上的 SQLite 又慢又脆。
- 包路径别太长、别太深，Windows 完整路径有上限。
- 解包前会按运行时根检查 240 字符预算，超了给中文 400。
- 端口被占用时启动器会明确报出来，改 `xgame.ini` 的 `port`。
- 换端口等于换了站点，浏览器里的本地存档不会跟着走。
- 同一账号在不同地址下算两个站点；本地存档是两套，云端存档跟账号走。
- 没有代码签名，也没有安装程序。
- 不做安装向导（无 setup.exe / Inno Setup），也不做自动升级。
- 启动失败时看 `data/logs/xgame.log`。
- 还会在包目录 `runtime/last-error.txt` 留一份原因。

## 测试要点

- `tests/test_static_site.py` 钉住七条静态站语义。
- 覆盖 SPA 回落、`/version.txt` 404、immutable 前缀未命中 404。
- 覆盖两个入口 no-cache、显式 MIME、API 404 保持 JSON。
- 覆盖路径穿越与非法路径拒绝、未设 `STATIC_DIR` 时不挂载。
- `tests/test_request_limit.py` 覆盖超限 413、分块 411 与正常放行。
- `tests/test_win_launcher.py` 覆盖版本号形状与同一提交的稳定性。
- 还覆盖 `runtime.env` 只钉一套运行时、INI 默认值与 `runtime_dir` 跟随。
- 还覆盖 MOTW 探测只在 Windows 生效、局域网 IP 排序。
- 平时只跑改动涉及的用例，全量由用户定期执行。

## 相关文档

- [Docker 交付](./delivery-docker.md)
- [Windows 包说明](../../packaging/windows/README.md)
- [给最终用户的说明](../../packaging/windows/说明.txt)
- [开发与排障](../../DEVELOP.md)
- [编码约定](../../AGENTS.md)
