# Windows「解压即用」包

把这个平台打包成**解压就能玩**的一份：不用装 Python、不用装 Docker、不需要管理员权限，
双击 `启动游戏平台.cmd` 就在浏览器里跑起来，局域网里手机/平板也能连。

Docker/WSL 那条路线**原样保留**，两条路并存；同一份数据目录不要两边同时打开。

```bash
bash packaging/windows/build-win-dist.sh     # 产物：dist-win/xgame_v<最新 tag>.zip
```

整个组装过程**在 WSL / Linux 上完成**，不需要 Windows 机器。首次构建要联网
（npm 依赖、EmulatorJS 引擎资产、Windows 版 Python）。

## 包里是什么

```
xgame/
  python/                 python-build-standalone 的可重定位 CPython 3.12（含 MSVC 运行库）
  backend/                后端源码（含 search/csv 名录）
  web/                    前端构建产物（vite dist）
  launcher.py             启动器：自检 → 查更新 → 起 uvicorn → 开浏览器
  winops.py               桌面快捷方式 / 开机自启 / 解除 MOTW 锁定
  smoke_win.py            自检脚本（组装时自动跑一遍）
  xgame.ico               快捷方式图标（由 make_icon.py 从 xgame.png 生成，不进构建流程）
  xgame.ini               数据目录、监听地址、端口、是否自动升级
  启动游戏平台.cmd         双击入口
  升级.bat + upgrade.ps1   自动升级
  允许局域网访问.bat + allow-lan.ps1   防火墙放行（只放行这个包的 python.exe）
  创建桌面快捷方式.bat / 设置开机自启.bat / 解除锁定.bat
  说明.txt                给最终用户看的说明
  updates/                把新版 xgame_v*.zip 丢这里，下次启动自动升级
  data/                   数据根（首次启动自动建）
```

## 与 Docker 路线的差异（都是刻意的）

| | Docker | 解压即用包 |
|---|---|---|
| 前端静态站 | nginx :443 | 后端自己托管（`backend/static_site.py`，行为对着 `frontend/nginx.conf.template` 复刻） |
| 应用服务器 | gunicorn + uvicorn worker | 单进程 uvicorn（gunicorn 不支持 Windows） |
| 协议 | HTTPS（自签证书） | HTTP（局域网里手机/平板不会信任自签证书） |
| session cookie | `Secure` | 由启动器设 `SESSION_COOKIE_SECURE=false`，否则浏览器不保存 cookie |
| 上传闸门 | nginx `client_max_body_size 128m` | `backend/request_limit.py`（默认 512MB，可配） |
| 后端配置 | 只认 `STORAGE_ROOT` | 启动器额外设 `STATIC_DIR` / `LOCAL_CONTROL` / `LOCAL_CONTROL_TOKEN` |

HTTP 的代价：非 localhost 下 Service Worker 不注册（封面缓存退化直连，只是慢）、
剪贴板 API 不可用（「复制」按钮已加兜底）。EmulatorJS 不需要跨源隔离
（`EJS_threads=false`），所以不用 COOP/COEP。

## 升级机制

启动器扫 `updates/`、包目录、包目录的上一层，找文件名里版本号更大的 `xgame_v*.zip`，
有就交给 `升级.bat` 并退出。升级脚本（PowerShell）依次：让服务优雅退出
（本地关机口 `POST /api/local/shutdown`，token 在 `runtime/control.token`）→ 解压到旁边的
暂存目录 → 把 `data/` 和 `xgame.ini` 搬进新包 → 整个目录改名交换 → 重新启动。

两个容易踩的点，脚本里都处理了：

- **升级脚本必须先复制到 `%TEMP%` 再执行**：它最后要改名整个 `xgame` 目录，而 Windows
  不允许改名含已打开文件的目录——正在被 PowerShell 读的脚本自己就在里面。
- **不能用子进程 + 硬杀来停服务**：所以启动器是**进程内**跑 uvicorn，收到关机请求时
  走 `should_exit` 优雅退出，SQLite 不会留下半开的事务。

## 构建细节

- **Python 运行时**钉死 release + sha256（`build-win-dist.sh` 顶部三个变量），
  升级时一起改。首次下载会缓存在 `dist-win/cache/`。
- **依赖**用 `pip install --platform win_amd64 --only-binary=:all:` 在 Linux 上直接装 Windows
  轮子；`uvicorn` 不带 `[standard]`（避开 uvloop），`gunicorn` 直接去掉。
- **组装完自动跑一次 `smoke_win.py`**：借 WSL interop 直接执行包里那份 `python.exe`，
  验证 FTS5、依赖 import、没有混进 gunicorn/uvloop、MSVC 运行库在位。
  这几条是「缺了会悄悄坏掉」的地方，所以放进构建流程而不是留给运气。
- **版本号**默认取 `git describe --tags --abbrev=0`（工作区脏则加 `-dirty`），
  同时写进包根 `version.txt` 与前端 `web/version.txt`，前端那套「服务端换了新构建」的
  提示因此照常工作。

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
- 没有代码签名，从网上下载会被 SmartScreen 拦一次；`说明.txt` 第一节写了怎么处理。
- `\\wsl$` 路径不支持作为数据目录（9p 上的 SQLite 又慢又脆）。
