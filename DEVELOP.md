# 开发指南

面向改这个仓库的人。只想玩的话看 [`README.md`](README.md)。

- **代码约定**（写代码前先读）：[`AGENTS.md`](AGENTS.md)
- **设计文档**：[`docs/architecture.md`](docs/architecture.md)
- **数据结构**（SQLite 表、磁盘路径规则）：[`docs/data_dict.md`](docs/data_dict.md)

项目默认**中文**：界面文案、文档、注释、提交说明、API 错误 `message` 全用中文；
代码标识符、路由 path、环境变量名保持英文。**不做 i18n。**

## 这是什么

Vue 3 SPA（`frontend/`）+ FastAPI JSON API（`backend/`），ORM 是 SQLModel，库是 SQLite。
两块功能：**游戏中心**（Flash 用 Ruffle、HTML5 解包后走沙箱 iframe、主机 ROM 用 EmulatorJS）
与**游戏管理**（上传 / 直链 / 搬运、卡带 ID 与元数据、整目录上传攻略）。账号开放注册，
只用于隔离各人的模拟器配置与存档 / 截图。

## 目录结构

```
frontend/                 # Vue 3 SPA（main.js / permission.js / router / layout / store / api / utils / views / components）
  src/components/common/  # 跨模块 UI 组件（AppDialog、AppButton、AppFilterBar、AppEmpty、CopyButton）
  src/components/games/   # 游戏专用组件（卡片、详情弹框、截图图库、存档管理、播放器与 GameShell）
backend/
  __init__.py             # create_app() 应用工厂（唯一入口）
  config.py               # 配置：全部写死在这里，见下
  asgi.py                 # 生产 ASGI 入口（gunicorn 用）
  backup.py               # SQLite 月度备份
  mount_guard.py          # 启动前的数据根目录哨兵检查（数据根在 Windows 盘挂载路径下时缺 .mounted 就退出）
  entrypoint.sh           # api 容器的 ENTRYPOINT：先过哨兵检查，再 exec gunicorn
  database.py             # 引擎、建表、_ensure_columns() 补列（无迁移框架）
  storage/                # types（协议）/ local（LocalStorage）/ access（流式下载响应）
  auth/ games/ tools/     # 一块功能一个包，各含 router.py（只 HTTP）+ service.py（领域逻辑）
  games/paths.py          # 所有磁盘相对路径规则的唯一出处
  games/importer.py       # 搬运（7k7k / 4399 / flash.homes）
  games/remote.py         # 网络上传（http/https 直链）
  games/search_*.py       # 游戏检索：text（归一化，索引期与查询期共用）/ index（建库，唯一写入方：启动补建 + make index）/ service（只读查询）/ router
  search/csv/             # 游戏检索的 37 个中英文名录 CSV（纯数据，只被 make index 读；被 .dockerignore 排除、不进镜像）
scripts/gen-certs.sh      # 重新生成自签名证书
certs/                    # 证书，随仓库提交（cert.pem / cert.key）
tests/                    # pytest
docs/                     # architecture.md + data_dict.md
```

## 环境要求

Python 3.10+（镜像里是 3.12）、Node.js 22（镜像里是 `node:22.23.3-alpine3.24`）。
正式运行只需要 Docker。

## 本机开发

后端：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.asgi:app --reload --port 8910
```

本机数据根默认是仓库下的 `data/storage`，它不在 Windows 盘挂载前缀（`/mnt`）下，**不需要**哨兵文件。
只有把数据根指到 WSL 挂载的 Windows 盘上（如 `STORAGE_ROOT=/mnt/x/xgame`）时才要**先手工建一次**
`/mnt/x/xgame/.mounted`，否则后端不会启动：打一条中文日志、等 5 秒、以非零码退出（本机没有容器
重启策略，就是起不来）——这是有意的，见下面「启动时发生什么」。测试不用管（`TESTING` 下跳过检查）。

前端（另开一个终端）：

```bash
cd frontend
npm install
npm run dev        # Vite :5173，/api 与 /health 代理到 :8910
```

浏览器打开 Vite 给出的地址（默认 `http://localhost:5173`），点「注册一个」建号。
`npm run dev` 会先跑 `scripts/copy-ruffle.mjs` 与 `scripts/fetch-emulatorjs.mjs` 把引擎资产
拉到 `frontend/public/`（首次需要联网，之后走缓存）。

建表不用手动做：`create_app()` 启动时就会建。`python -m backend.cli init-db` 是等价的手动命令，
一般用不上。

## Docker 运行

```bash
make all            # = docker compose build && up -d
```

站点在 **https://localhost**（只支持 HTTPS，不发布 80，也没有 http→https 跳转）。
证书随仓库提供，**不建 `.env` 也能直接跑**——数据落在 `./data/storage`，端口 443。
要改数据目录或端口：

```bash
cp .env.example .env        # 改 STORAGE_HOST_DIR / WEB_HTTPS_PORT
```

**数据目录在 Windows 盘上（`/mnt/…`）时，第一次运行平台前要先建 `.mounted` 哨兵**，否则 api 容器
起不来（日志里反复出现「数据根目录 … 里没有哨兵文件」，容器被 `restart: unless-stopped` 反复重启）。
数据目录放在普通 Linux 路径（如 `/srv/xgame`）下不用建、也完全不检查。要建的话先建目录再 `make all`：

```bash
mkdir -p "$STORAGE_HOST_DIR" && touch "$STORAGE_HOST_DIR/.mounted"     # 只建一次
```

## 配置

绝大部分配置**写死在代码里**，只有两个键留在 `.env`，而且**后端进程不读这个文件**（唯一例外见下表：`STORAGE_HOST_DIR` 会被 compose 作为环境变量传进 api 容器，只用于启动时的哨兵判断）：

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `STORAGE_HOST_DIR` | `./data/storage` | **宿主侧**数据目录，compose 挂到容器的 `/data` |
| `WEB_HTTPS_PORT` | `443` | 对外发布的 HTTPS 端口（容器内 nginx 固定听 443） |

写死的东西（要改就改代码，改完重新构建）：

| 配置 | 位置 | 值 |
| --- | --- | --- |
| `SECRET_KEY` | `backend/config.py` | session cookie 的签名密钥，跟仓库一起走；改它会让所有已登录会话失效 |
| `STORAGE_ROOT` | `backend/Dockerfile` 的 `ENV`（容器）/ `backend/config.py`（本机） | 容器里固定 `/data`；本机是 `<仓库>/data/storage` |
| `STORAGE_HOST_DIR` | `.env`（只给 compose） | 宿主侧数据目录。compose 除了拿它做 bind，还把它作为环境变量传进 api 容器，**只**用于启动时的哨兵前缀判断（见 `backend/mount_guard.py`） |
| `WINDOWS_MOUNT_PREFIX` | `backend/config.py` | Windows 盘的挂载路径前缀，默认 `/mnt`；数据根落在这下面才要求 `.mounted` 哨兵（设成 `/` = 所有路径都要求） |
| SQLite 路径 | `backend/config.py` 的 `DB_SUBDIR` / `DB_FILENAME` | `<STORAGE_ROOT>/db/app.db`，**没有 `DATABASE_URL` 可配** |
| 证书 | `docker-compose.yml` + `frontend/nginx.conf.template` | `certs/cert.pem` 与 `certs/cert.key` |
| Session cookie | `backend/config.py` | HttpOnly、SameSite=Lax、HTTPS 下 Secure（测试自动关） |
| `TESTING` | `backend/config.py` | 只给测试用（顺带跳过启动时的 `.mounted` 哨兵检查） |

> **这是有意的取舍**：平台只给自己用，不打算部署到别人的机器上，所以不做「可配置化」。
> 密钥、证书都随仓库提交，安全性不是考虑项。别把 `SECRET_KEY` 之类的再挪回环境变量。

### 启动时发生什么

`create_app()`（`backend/__init__.py`）按顺序做四件事：

1. `require_mounted()` — 数据根落在 Windows 盘挂载前缀下时，没有 `.mounted` 哨兵就**拒绝启动**（见下）；不在那个前缀下直接放行；
2. `ensure_data_dir()` — 建出 `<STORAGE_ROOT>/db`；
3. `init_db()` — `create_all` 建缺失的表，再 `_ensure_columns()` 给老表 `ALTER TABLE ADD COLUMN` 补列；
4. `backup_database()` — 当月还没有备份就往 `<STORAGE_ROOT>/db/<YYYY-MM>.db` 备一份。

第 1 步与第 4 步的失败处理正好相反：哨兵缺了**一定拦住启动**；备份失败只记 warning、绝不拦，
也不做还原功能（回滚就手工把备份文件改名成 `app.db` 替换）。

### `.mounted` 哨兵文件

**只对 Windows 盘挂载路径下的数据根**要求一个空的 `.mounted`：**人工创建，代码只检查、绝不代建**
（`backend/mount_guard.py`）。

它用来识破「bind 把宿主空目录挂进来了」这种情况：数据目录放在 WSL 挂的 Windows 盘（`/mnt/…`）上
时，开机可能 docker 先于盘挂载起来，那时容器里的数据根目录是个**空目录**——可写、`statvfs` 也
正常，服务照常启动就会在里面新建一个空库，看起来就像「数据全没了」。唯一能识破它的判据就是
哨兵文件在不在。

所以判断分两步：

1. **要不要检查**：数据根路径是否落在 Windows 盘挂载前缀下。前缀写死在
   `backend/config.py` 的 `WINDOWS_MOUNT_PREFIX`（**可改，默认 `/mnt`**；设成 `/` 表示对所有路径
   都要求哨兵）。**不在这个前缀下（普通 Linux 目录，比如仓库内的 `data/storage` 或 `/srv/xgame`）
   没有这个竞态，直接启动、不要求任何文件**。这里的「数据根路径」在容器里取 compose 传进来的
   宿主路径 `STORAGE_HOST_DIR`（容器里 `STORAGE_ROOT` 固定是 bind 目标 `/data`，看不出宿主路径），
   本机直跑时退回 `STORAGE_ROOT`。
2. **检查哪一份**：进程能看到的 `<STORAGE_ROOT>/.mounted`（容器里就是挂进来的宿主目录）。

缺哨兵时：打一条中文日志（含该 `touch` 哪个路径）→ 等 5 秒 → 以非零码退出。容器里这一步发生在
`exec gunicorn` **之前**（`backend/entrypoint.sh` 是 api 镜像的 ENTRYPOINT，它调的就是
`create_app()` 里同一个 `require_mounted()`），退出的是容器主进程，compose 的
`api.restart: unless-stopped` 随即把容器重新拉起，如此循环直到哨兵出现、服务自己恢复。
判断与日志只有 `mount_guard.py` 一份，脚本只是把退出码透传出去。

```bash
# 数据根在 Windows 盘上（如 /mnt/x/xgame）时，第一次运行平台前建一次；普通 Linux 目录不用建
touch "$STORAGE_HOST_DIR/.mounted"
```

哨兵要建在**真实的数据目录**里（它会随数据目录一起被备份；空的 bind 挂载天然没有它），
换新的数据目录要重新建一次。

## 证书

`certs/cert.pem` 与 `certs/cert.key` 随仓库提交（自签名，`CN=localhost`，SAN 含
`localhost` 与 `127.0.0.1`），浏览器会提示不受信任，点「继续访问」即可。

要用 IP / 域名访问，或换一张受信任的证书：

```bash
# 重新生成自签名证书（脚本默认跳过已存在的证书，换 CN 必须加 FORCE=1）
FORCE=1 make certs ARGS="192.168.1.10"
FORCE=1 make certs ARGS="my.host.com"

# 或者：把已有的证书改名成 cert.pem / cert.key 放进 certs/，重启 web 容器
docker compose restart web
```

改完证书浏览器仍可能缓存旧的那张，必要时清一下站点数据或换个标签页。

## 数据与磁盘布局

数据根目录（`STORAGE_ROOT`）里的一切都是普通文件，**没有任何对象存储、也没有 docker 具名卷**：

```
.mounted                                     哨兵文件（数据根在 /mnt 这类 Windows 盘路径下时人工创建）
db/app.db                                    SQLite 库（SQLModel 表）
db/2026-10.db                                月度备份
db/game.db                                   游戏检索索引（派生只读库，make index 构建，不备份）
game/{游戏类型}/{卡带ID}/game.{后缀}          本体
game/{游戏类型}/{卡带ID}/cover.{后缀}         封面
game/{游戏类型}/{卡带ID}/h5/{相对路径}        H5 解包资源（清单在 game_h5_files 表）
game/{游戏类型}/{卡带ID}/guide/{相对路径}     攻略（入口固定 index.html，库里不存标记）
game/{游戏类型}/{卡带ID}/image/{uuid}.{后缀}  图集（按游戏共享，随游戏类型迁移）
save/{用户名}/{游戏类型}/{卡带ID}/{uuid}.state  云端存档快照（按账号）
image/{用户名}/{游戏类型}/{卡带ID}/{uuid}.png   游戏截图（按账号）
```

路径规则全部集中在 `backend/games/paths.py`，**别在别处手拼字符串**；读写一律走
`backend/storage/local.py` 的 `LocalStorage`。SQLite 里只存相对根目录的路径，
所以换盘、换目录只改 `STORAGE_HOST_DIR`，库里的数据不用动。

`save/` 与 `image/` 不可重建；`game/` 下的本体、封面、H5、攻略都能重传。

## 测试与 lint

```bash
make test                              # = python -m pytest + cd frontend && npm run lint
python -m pytest                       # 只跑后端
python -m pytest tests/test_games.py   # 只跑某个文件
cd frontend && npm run lint
```

后端测试用临时 SQLite + 临时 `STORAGE_ROOT`（直接打真实文件系统，不 mock 存储层），
不需要 Docker。开发时按改动范围挑相关用例跑即可。

## 构建游戏检索索引

「游戏检索」页的数据源是 `backend/search/csv/` 下 37 个中英文名录 CSV。它不是业务数据，
而是构建成一个**独立的只读索引库** `<数据根>/db/game.db`：

```bash
make index        # = STORAGE_ROOT=${STORAGE_HOST_DIR:-./data/storage} python -m backend.cli index
```

**两个写入口，同一份实现**（`backend/games/search_index.py::build_index()`）：

1. **服务启动自动补建**：`create_app()` 启动时调 `ensure_game_index()`（紧跟 `backup_database()`）
   ——文件不存在就整库建一次，已存在就跳过；`TESTING` 下直接跳过；失败只记一条中文 warning、
   **绝不拦住启动**。所以装好就能用检索，不用先读文档。
2. **`make index`**：手动重建/更新（换了 CSV、改了分词规则、升级了平台之后用它覆盖）。

两者都是：**整库重建**（写同目录临时文件再 `os.replace` 原子替换）、直接覆盖旧文件，约 1 秒、
5 万余行、10MB 左右。

- **运行期只读**。所有读都经 `GameSearchService`，用 `mode=ro` + `PRAGMA query_only=1` 打开，
  每请求一条短连接；没有第三条路径会写它。
- **不参与月度备份**（`backend/backup.py` 只备份 `app.db`）——它随时能从 CSV 重建。
- **重建后不用重启 api**：`os.replace` 之后，已经打开的连接继续读旧 inode，新请求自动拿新库。
- **只能在宿主机跑**：CSV 被根目录 `.dockerignore` 排除了，镜像里没有这份数据，容器里的自动
  补建必然跳过（只记一条 INFO）。数据根取自 `.env` 的 `STORAGE_HOST_DIR`，与容器挂的是同一个
  宿主目录，所以宿主机建完容器立刻能读到。

### 自动补建没成功（PermissionError / 「数据根不可写」）

数据目录若是 Docker 容器以 root 建的（默认的 `./data/storage` 跑过一次 compose 之后就是这样），
宿主用户在里面**建不了临时文件**，启动时的自动补建会失败并记一条 warning（服务照常起来，
检索页提示「尚未构建索引」）。手动 `make index` 会先做一次 `test -w` 预检并打印对策，
照做即可：

```bash
sudo chown -R "$USER" "$STORAGE_HOST_DIR"     # 默认就是 ./data/storage
```

换一个宿主用户自有的 `STORAGE_HOST_DIR` 也可以（推荐放在仓库外，见「配置」）。

### 改了名录或改了分词规则之后

`backend/games/search_text.py` 里是**索引期与查询期共用的唯一一份归一化实现**（NFKC → 剥结尾的
地区/语言/版本标签 → 汉字逐字拆 token）。改它之后必须重跑 `make index`，否则老索引与新查询
对不上，中文会静默搜不到。同理，改了 `search_index.py` 的表结构要把 `SCHEMA_VERSION` 加一——
运行期读到不匹配的版本会明确报「索引版本过旧，请重新构建」，而不是给出莫名其妙的结果。

## 提交约定

分支名 `<类型>/<描述>`（小写、`-` 连接），如 `feat/cartridge-id`。
提交标题 `<类型>: <中文短语>`，类型用 `feat` / `fix` / `docs` / `refactor` / `test` / `chore`，
一个提交只做一件事。

## 排障

**数据目录在 WSL 的 Windows 盘上（`/mnt/…`），开机后数据像是空的。**
Docker 守护进程可能先于 WSL 发行版起来，bind 把宿主的空目录挂进了容器。**这种数据根由哨兵拦住**：
容器里的数据根没有 `.mounted`，api 拒绝启动并被反复重启，窗口期内一个字节都写不进去（不会再
静默建出空库）。盘挂上后不用做别的，容器下一次重启就自己恢复（急的话 `docker compose restart api`）。
前提是哨兵当初已建在**真实的数据目录**里——走的是「数据根在 `/mnt` 前缀下」这条判断，若曾在空
挂载里建过一次 `.mounted`，它反而会把问题掩盖掉。治本的仍是把 `STORAGE_HOST_DIR` 指向 docker
启动前就稳定的路径，别放在会被 `git pull` 覆盖的仓库目录里。

**api 容器一直在重启，日志反复出现「数据根目录 … 里没有哨兵文件」。**
数据根在 Windows 盘挂载前缀（默认 `/mnt`）下、却缺 `.mounted`：从没建过、换过 `STORAGE_HOST_DIR`、
或者盘还没挂上。确认盘已挂上（`mountpoint -q /mnt/d`）之后，在**宿主侧**那个数据目录里
`touch .mounted`，容器下一次重启就起来了。在容器里 `touch /data/.mounted` 也行，但那是建在 bind
进来的宿主目录里，效果一样（盘没挂上时只是白建，掩盖问题）。日志给出的 `touch` 路径就是宿主路径。

**页面还是旧版。** 前端按构建版本号（git 短 sha）探测更新，`nginx` 对 HTML 与 `/version.txt`
都不缓存。经 `make all` 构建才会带上 sha；直接 `docker compose build` 会退化成构建时间戳。
实在不放心就硬刷新。

**api 起不来、日志里一串「Booting worker」。** gunicorn 的 worker 起来又挂掉。看 worker 里抛的
异常（常见是数据目录不可写）；注意 `--workers 1` 是必须的，多进程会撞 SQLite 写锁。

**端口被占用，web 容器起不来。** 宿主 443 被别的服务占了，改 `.env` 的 `WEB_HTTPS_PORT`
（如 `8443`），然后用 `https://localhost:8443` 访问。

**浏览器的证书警告。** 自签名证书的正常表现，见上面「证书」。

## 文档索引

| 文档 | 读者 | 内容 |
| --- | --- | --- |
| [`README.md`](README.md) | 玩游戏的人 | 功能使用指南 |
| `DEVELOP.md` | 改代码的人 | 就是本文：环境、配置、部署、排障 |
| [`AGENTS.md`](AGENTS.md) | 改代码的人 / AI 助手 | 编码约定与关键规则，**最详细，写代码前必读** |
| [`docs/architecture.md`](docs/architecture.md) | 改代码的人 | 设计决策与架构 |
| [`docs/data_dict.md`](docs/data_dict.md) | 改代码的人 | SQLite 表结构、磁盘路径规则 |
