# Windows「解压即用」包

把这个平台打包成**解压就能玩**的一份：不用装 Python、不用装 Docker、不需要管理员权限，
双击 `启动游戏平台.cmd` 就在浏览器里跑起来，局域网里手机/平板也能连。

Docker/WSL 那条路线**原样保留**，两条路并存；同一份数据目录不要两边同时打开。

```bash
make win          # 需要 Docker；产物 dist-win/xgame_v<版本>.zip
make win-image    # 只构建/更新那个构建环境镜像，不出包
```

**构建在容器里跑，分两步**：构建环境镜像（`packaging/windows/Dockerfile.build`）不存在就先建
一次，然后在里面跑 `build-win-dist.sh` 组装。宿主机只要有 Docker，**不需要 node / python /
curl / zip**。

**能固定的依赖全都在构建环境镜像里**（`/opt/winbuild`），所以组装那一步不联网、也不看宿主机
装了什么：

| 镜像里预置的 | 从哪来 |
|---|---|
| `runtime/` Windows 版 CPython | `runtime.env` 钉死 release + sha256 |
| `wheels/` 包的 Python 依赖 | `requirements-win.txt`（传递依赖也一起冻住） |
| `frontend/node_modules/` 前端依赖 | `frontend/package-lock.json` |
| `frontend/public/emulatorjs/` 引擎资产 | `fetch-emulatorjs.mjs` 里钉死的 EJS_VERSION |

镜像 tag 是「Dockerfile + 上面这几个输入文件」的哈希：改了任一处就自动重建，没改就一直复用。
要强制刷新（比如拿传递依赖的安全更新）：`WINBUILD_NO_CACHE=1 make win-image`。

由 `build-in-docker.sh` 驱动：容器以宿主机用户身份跑（产出的 `dist-win/` 与前端产物属主正常，
不会变成 root 所有）；前端在容器内的临时目录里构建，**宿主机自己的 `frontend/node_modules`
一个字节都不碰**（没有也照样出包）。只有建镜像那一次要联网（apt / npm / PyPI / GitHub /
EmulatorJS CDN），之后每次出包都是离线的。

包内自检（`smoke_win.py`）由宿主机在构建后补跑——容器里没有 binfmt_misc，执行不了包里那份
Windows 的 `python.exe`；宿主机不是 WSL 就跳过。

版本号由 `scripts/version.sh` 从 git tag 算（就是 `xgame_v<版本>.zip` 里那个），
规则见 [`DEVELOP.md`](../../DEVELOP.md) 的「版本号」。

## 包里是什么

**压缩包里没有多余的一层目录**：条目直接躺在根上，解压到哪、哪就是包本体
（`make_zip.py` 打的时候刻意不套一层 `xgame/`）。

```
python/                  python-build-standalone 的可重定位 CPython 3.12（含 MSVC 运行库）
backend/                 后端源码（含 search/csv 名录）
web/                     前端构建产物（vite dist）
launcher.py              启动器：自检 → 起 uvicorn → 开浏览器
winops.py                桌面快捷方式 / 开机自启 / 解除 MOTW 锁定
smoke_win.py             自检脚本（构建后由宿主机跑一遍）
xgame.ico                快捷方式图标（由 make_icon.py 从 xgame.png 生成，不进构建流程）
xgame.ini                数据目录、监听地址、端口、是否开浏览器
version.txt              构建版本号（启动横幅上显示）
启动游戏平台.cmd          双击入口
允许局域网访问.bat + allow-lan.ps1   防火墙放行（只放行这个包的 python.exe）
创建桌面快捷方式.bat / 设置开机自启.bat / 解除锁定.bat
说明.txt                 给最终用户看的说明
data/                    数据根（首次启动自动建）
runtime/                 运行时文件（首次启动自动建：port.txt / last-error.txt）
```

构建侧的文件（**不进包**）：

```
Dockerfile.build          构建环境镜像：工具链 + 预置的运行时/轮子/前端依赖/引擎资产
Dockerfile.build.dockerignore  构建上下文是仓库根，用它**代替**根目录那份 .dockerignore
                          （那份给 api 镜像用、把整个 frontend 排除了，而这里正要 frontend 里的几个文件）
build-in-docker.sh        make win 的入口：建镜像 + 在容器里组装 + 宿主机补自检
build-win-dist.sh         真正的组装脚本（在容器里跑，也可以直接在 Linux 上跑）
runtime.env               Windows 版 CPython 的 release / 文件名 / sha256（唯一出处）
fetch-runtime.sh          按 runtime.env 下载并校验运行时（建镜像与兜底路径都用它）
requirements-win.txt      包内依赖（去掉 gunicorn，uvicorn 不带 [standard]）
make_zip.py               打 zip：条目不套一层目录 + 中文名带 UTF-8 标记（见下）
make_icon.py / xgame.png  从源图生成 xgame.ico（换图标 = 替换 xgame.png 再跑它）
```

## 与 Docker 路线的差异（都是刻意的）

| | Docker | 解压即用包 |
|---|---|---|
| 前端静态站 | nginx :443 | 后端自己托管（`backend/static_site.py`，行为对着 `frontend/nginx.conf.template` 复刻） |
| 应用服务器 | gunicorn + uvicorn worker | 单进程 uvicorn（gunicorn 不支持 Windows） |
| 协议 | HTTPS（自签证书） | HTTP（局域网里手机/平板不会信任自签证书） |
| session cookie | `Secure` | 由启动器设 `SESSION_COOKIE_SECURE=false`，否则浏览器不保存 cookie |
| 上传闸门 | nginx `client_max_body_size 128m` | `backend/request_limit.py`（默认 512MB，可配） |
| 后端配置 | 只认 `STORAGE_ROOT`（库就在 `data/db/` 里） | 启动器额外设 `STATIC_DIR`（让后端托管前端 dist） |

HTTP 的代价：非 localhost 下 Service Worker 不注册（封面缓存退化直连，只是慢）、
剪贴板 API 不可用（「复制」按钮已加兜底）。EmulatorJS 不需要跨源隔离
（`EJS_threads=false`），所以不用 COOP/COEP。

## 升级（手动，包里没有任何自动升级的代码）

1. 关掉启动窗口（服务随之停止）；
2. 把新 zip 解压到一个**新的空目录**（压缩包里没有多余的一层目录，所以先建目录再解压；
   别覆盖旧目录，旧版本留下的文件会混在里面）；
3. 把旧目录的 `data/`（或 `xgame.ini` 里 `data_dir` 指的那个目录）整个搬到新目录，
   双击新的 `启动游戏平台.cmd`；
4. 桌面快捷方式 / 开机自启指向的还是旧路径，重新跑一次那两个 `.bat`。

**为什么不做自动升级**：它要停下来改自己的目录，于是每一步都得跟 Windows 的文件锁较劲
（脚本得先复制到 `%TEMP%` 再执行、服务得先优雅退出、旧目录可能删不掉……），换来的只是
「少点几下鼠标」。手动的三步没有一处会失败，而且出问题时用户看得见自己在做什么。

**停止服务 = 关掉那个控制台窗口**。硬杀不会坏库（SQLite 有回滚日志，未提交的事务下次打开时
回滚），只是可能丢掉最后几秒的写入。

## 构建细节

- **Python 运行时**钉死 release + sha256，只写在 `runtime.env` 一处（建镜像与组装脚本共用），
  升级时只改它。
- **依赖**用 `pip install --platform win_amd64 --only-binary=:all:` 在 Linux 上直接装 Windows
  轮子；`uvicorn` 不带 `[standard]`（避开 uvloop），`gunicorn` 直接去掉。
  组装时是 `--no-index --find-links` 从镜像里的轮子仓库装，所以装出来的东西与镜像一一对应。
- **组装完自动跑一次 `smoke_win.py`**：借 WSL interop 直接执行包里那份 `python.exe`，
  验证 FTS5、依赖 import、没有混进 gunicorn/uvloop、MSVC 运行库在位。
  这几条是「缺了会悄悄坏掉」的地方，所以放进构建流程而不是留给运气。
- **版本号**由 `scripts/version.sh` 算（规则见 DEVELOP.md 的「版本号」），
  同时写进包根 `version.txt` 与前端 `web/version.txt`，前端那套「服务端换了新构建」的
  提示因此照常工作。
- **打 zip 用 `make_zip.py`（Python 的 zipfile），不用命令行的 `zip`**：Info-ZIP 把非 ASCII
  文件名按本地编码原样写进去、却不设「UTF-8 名字」标志位（general purpose bit 11），
  Windows 资源管理器读不到标记就按 OEM 代码页解释，`启动游戏平台.cmd` 会显示成乱码；
  而 WinRAR 会自己猜 UTF-8，预解压窗口里一切正常——最容易骗过构建者的一类 bug。
  顺带这个脚本让条目直接躺在压缩包根上，不套一层目录。

## 换图标

图标是桌面快捷方式与开机自启用的那张，源图就是本目录下的 **`xgame.png`**（随仓库提交的静态
资源，**换图标 = 换掉它**）：

```bash
# 换一张正方形 PNG（至少 256×256 更清楚）覆盖 xgame.png，然后：
python3 packaging/windows/make_icon.py     # 从源图生成 xgame.ico（需要 Pillow）
make win                                   # 重新组装
```

`xgame.ico` 是提交进仓库的产物（Windows 快捷方式只认 .ico/.exe/.dll 里的图标，不认 PNG，
且里面要塞 16/32/48/256 好几档尺寸），**不在每次构建时生成**。构建脚本发现源图比 `.ico` 新时
会顺手重生成一次；本机没有 Pillow 就只提醒一声，继续用仓库里那份图标。

## 还没做的事

- 包里的 `.cmd` / `.bat` 内容是纯 ASCII：cmd 按 OEM 代码页解析批处理，中文混在里面是
  乱码与解析出错的经典来源。面向用户的中文一律由 Python 或 PowerShell 输出
  （`.ps1` 存成 UTF-8 **带 BOM**，否则 PowerShell 5.1 会按 ANSI 读）。
- 没有代码签名，也没有安装程序，所以「从网上下载的 zip 解压出来带 MOTW」这件事只能靠
  文档和脚本消化：带标记时**每双击一次 `.cmd`/`.bat`**，Windows 都会先弹一次
  「打开文件 - 安全警告：无法验证发布者」（点「运行」能继续，所以不致命，但每次都要点）。
  对付它的办法只有两个：解压**之前**右键 zip 勾「解除锁定」（`说明.txt` 第一节第 1 步，
  最干净），或者解压后双击一次 `解除锁定.bat`。启动器启动时会探一下自己的 `.cmd` 有没有
  那个数据流，还在就提醒一句（`launcher.py` 的 `still_locked()`）。
- `\\wsl$` 路径不支持作为数据目录（9p 上的 SQLite 又慢又脆）。
