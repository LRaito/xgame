# 开发指南

面向改这个仓库的人。只想玩的话看 [`README.md`](README.md)。

- **代码约定**（写代码前先读）：[`AGENTS.md`](AGENTS.md)
- **设计文档**：[`docs/architecture.md`](docs/architecture.md)
- **数据结构**：[`docs/data_dict.md`](docs/data_dict.md)
- **功能规格**：[`docs/specs/`](docs/specs/README.md)

项目默认**中文**：界面文案、文档、注释、提交说明、API 错误 `message` 全用中文；
代码标识符、路由 path、环境变量名保持英文。**不做 i18n。**

## 这是什么

Vue 3 SPA（`frontend/`）+ FastAPI JSON API（`backend/`），ORM 是 SQLModel，库是 SQLite。

三块功能：

- **游戏中心**：Flash 用 Ruffle、HTML5 走沙箱 iframe、主机 ROM 用 EmulatorJS。
- **游戏管理**：上传 / 直链 / 搬运、卡带 ID 与元数据、攻略。
- **游戏发现**：外部名录的只读检索与榜单。

账号开放注册，只用于隔离各人的模拟器配置与存档 / 截图。

## 环境要求

- Python 3.10+（镜像里是 3.12）
- Node.js 22（镜像里是 `node:22.23.3-alpine3.24`）
- 正式运行只需要 Docker

## 本机开发

后端：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.asgi:app --reload --port 8910
```

后端启动时自动建表，不需要手动跑 `init-db`。

前端（另开终端）：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 Vite 给出的地址（默认 `http://localhost:5173`），点「注册一个」建号。
`npm run dev` 会先拉引擎资产到 `frontend/public/`（首次联网，之后走缓存）。

本机数据根默认是仓库下的 `data/storage`，不在 `/mnt` 下，**不需要**哨兵文件。
把根指到 WSL 挂载的 Windows 盘时，见下面「根目录哨兵」。

## Docker 运行

```bash
make all            # = docker compose build && up -d
```

站点在 **https://localhost**。只支持 HTTPS，不发布 80，也没有 http→https 跳转。
证书随仓库提供，不建 `.env` 也能直接跑——数据落在 `./data/storage`，端口 443。

要改数据目录、运行时目录或端口：

```bash
cp .env.example .env
# 改 STORAGE_HOST_DIR / RUNTIME_HOST_DIR / WEB_HTTPS_PORT
```

### 根目录哨兵（操作）

只有根目录的**宿主路径**落在 Windows 盘挂载前缀（默认 `/mnt`）下时才需要 `.mounted`。

- 数据根与运行时根各查一份；两个根相同时就是同一个文件。
- 缺文件时 api 拒绝启动，并被 compose 反复重启。
- 先建目录，再手工建空文件：

```bash
mkdir -p "$STORAGE_HOST_DIR" && touch "$STORAGE_HOST_DIR/.mounted"
mkdir -p "$RUNTIME_HOST_DIR" && touch "$RUNTIME_HOST_DIR/.mounted"
```

- 哨兵要建在**真实目录**里；换目录要重新建。
- 代码只检查、绝不代建。
- 机制与运行行为见 [`docs/specs/delivery-docker.md`](docs/specs/delivery-docker.md)。

## 配置

绝大部分配置**写死在代码里**。`.env` 只有三个键，且**后端不读这个文件**。

| 键 | 默认 | 作用 |
|---|---|---|
| `STORAGE_HOST_DIR` | `./data/storage` | 宿主侧数据目录，挂到 `/data` |
| `RUNTIME_HOST_DIR` | `./data/runtime` | 宿主侧运行时目录，挂到 `/runtime`；留空则同数据根 |
| `WEB_HTTPS_PORT` | `443` | 对外发布的 HTTPS 端口 |

不建 `.env` 时 compose 把两个根都退回 `./data/storage`；
`.env.example` 才给出分开的默认值（`./data/runtime`）。

写死的东西（要改就改代码，改完重新构建）：

| 配置 | 位置 | 值 |
|---|---|---|
| `SECRET_KEY` | `backend/config.py` | session cookie 签名密钥 |
| `STORAGE_ROOT` | Dockerfile ENV / config.py | 容器 `/data`；本机 `<仓库>/data/storage` |
| `RUNTIME_ROOT` | Dockerfile ENV / config.py | 容器 `/runtime`；本机不设 = 数据根 |
| `WINDOWS_MOUNT_PREFIX` | `backend/config.py` | 默认 `/mnt`；设 `/` = 所有路径都要求 |
| SQLite 路径 | `backend/config.py` | `<运行时根>/db/app.db` |
| 备份间隔 | `backend/backup.py` | 3600 秒 |
| 证书 | compose + nginx | `certs/cert.pem` / `certs/cert.key` |
| Session cookie | `backend/config.py` | HttpOnly、SameSite=Lax、HTTPS 下 Secure |

> 这是有意的取舍：平台只给自己用，不做「可配置化」。
> 密钥、证书随仓库提交，安全性不是考虑项。别把 `SECRET_KEY` 挪回环境变量。

### 启动时发生什么

`create_app()` 按顺序：

1. `require_mounted()`：按前缀检查哨兵；缺了就拒绝启动。
2. `ensure_data_dir()`：建 `<运行时根>/db`。
3. `init_db()`：建缺失的表，并给老表补列。
4. `backup_database()`：立刻备份一份。
5. `start_backup_loop()`：起守护线程，每小时再备一次。
6. `ensure_game_index()`：索引不存在就补建。

哨兵缺失**一定拦住启动**；备份与补建失败只记 warning，不拦启动。

## 证书

`certs/cert.pem` 与 `certs/cert.key` 随仓库提交（自签名，`CN=localhost`）。
浏览器会提示不受信任，点「继续访问」即可。

要用 IP / 域名访问，或换受信任证书：

```bash
FORCE=1 make certs ARGS="192.168.1.10"
FORCE=1 make certs ARGS="my.host.com"
docker compose restart web
```

## Windows 解压即用包

```bash
make win          # 组装 dist-win/xgame_v<版本>.zip
make win-image    # 只构建/更新构建环境镜像
```

- 整个组装在容器里跑，宿主机只要有 Docker。
- 构建环境镜像预置运行时、轮子、前端依赖与引擎资产，出包那一步不联网。
- 包内是后端托管前端 dist + 单进程 uvicorn + http。
- 升级 = 关窗口 → 解压新包到新目录 → 搬 `data`；没有自动升级。

构建命令、文件清单与换图标见
[`packaging/windows/README.md`](packaging/windows/README.md)。
与 Docker 的差异、编码规则与升级细节见
[`docs/specs/delivery-windows.md`](docs/specs/delivery-windows.md)。

本机直跑一份「生产形态」（排查用）：

```bash
STORAGE_ROOT=/tmp/x STATIC_DIR=frontend/dist python -m backend.cli serve --port 8910
```

不设 `STATIC_DIR` 时后端不注册静态路由，Docker 路线行为不变。

## 测试与 lint

```bash
make test                              # pytest + 前端 lint
python -m pytest                       # 只跑后端
python -m pytest tests/test_games.py   # 只跑某个文件
cd frontend && npm run lint
```

- 后端测试用临时 SQLite + 临时 `STORAGE_ROOT`，直接打真实文件系统，不 mock 存储层。
- 开发时按改动范围挑相关用例跑即可；全量测试由用户定期执行。
- **只改文档不跑测试。**

## 构建游戏发现索引

「游戏发现」的数据源：

- `backend/search/csv/` 下 37 个中英文名录 CSV（检索）。
- `backend/search/ranking/ranking.csv`（榜单，四列）。

它们构建成一个只读库 `<数据根>/db/game.db`：

```bash
make index
# CLI 还可加 --skip-ranking（只重建检索）或 --ranking-csv PATH
```

- 只有一个写入模块：`backend/games/search_index.py`。
- 两条写路径：
  - `build_index()` 整库重建，`make index` 与启动自动补建都走它。
  - `ensure_ranking_loaded()` 启动时就地补榜单。
- 运行期只读：`mode=ro` + `PRAGMA query_only=1`，每请求一条短连接。
- 不参与备份，可从 CSV 重建。
- 重建后不用重启 api。

实现细节见 [`docs/specs/game-discover.md`](docs/specs/game-discover.md)。

### 自动补建失败（PermissionError）

数据目录若被 Docker 以 root 建过，宿主用户可能写不了。
服务照常启动，页面提示「尚未构建索引」/「榜单尚未加载」。

```bash
sudo chown -R "$USER" "$STORAGE_HOST_DIR"
```

也可以换一个宿主用户自有的 `STORAGE_HOST_DIR`。

### 改了名录、榜单或分词规则之后

- 改 `backend/games/search_text.py` 后必须重跑 `make index`，否则中文可能静默搜不到。
- 改检索表结构要加 `SCHEMA_VERSION`。
- 改榜单表结构改 `RANKING_SCHEMA_VERSION`，不要动 `SCHEMA_VERSION`。
- 榜单 CSV 换内容不用改版本号：重跑 `make index`，或重启让服务按指纹补载。

## 提交约定

- 分支名 `<类型>/<描述>`，小写、`-` 连接，如 `feat/cartridge-id`。
- 提交标题 `<类型>: <中文短语>`。
- 类型用 `feat` / `fix` / `docs` / `refactor` / `test` / `chore`。
- 一个提交只做一件事。

## 排障

**数据目录在 WSL 的 Windows 盘上，开机后数据像是空的。**
Docker 可能先于 WSL 发行版起来，bind 把空目录挂进了容器。
哨兵会拦住启动；盘挂上后容器下一次重启自愈（急的话 `docker compose restart api`）。
前提是哨兵当初建在真实目录里。

**api 容器一直重启，日志出现「根目录 … 里没有哨兵文件」。**
确认盘已挂上（`mountpoint -q /mnt/d`），在宿主侧那个目录里 `touch .mounted`。
日志里写明了是哪个宿主路径。

**页面还是旧版。**
前端按构建版本号探测更新；nginx 对 HTML 与 `/version.txt` 不缓存。
经 `make all` 构建才会带上版本号，直接 `docker compose build` 会退化成时间戳。

**api 起不来，日志里一串「Booting worker」。**
看 worker 抛的异常（常见是数据目录不可写）。
注意 `--workers 1` 是必须的，多进程会撞 SQLite 写锁。

**端口被占用，web 容器起不来。**
改 `.env` 的 `WEB_HTTPS_PORT`（如 `8443`），用 `https://localhost:8443` 访问。

**浏览器证书警告。**
自签名证书的正常表现，见「证书」。

**网盘备份报「文件被占用」。**
库还在数据目录里。把 `RUNTIME_HOST_DIR` 指到网盘之外；
数据目录里就只剩普通文件，运行时目录不用备份。

**备份文件每小时都被重写。**
这是有意的：启动一次、之后每小时整份重写当月文件；快照最多落后一小时。

## 文档索引

| 文档 | 读者 | 内容 |
|---|---|---|
| [`README.md`](README.md) | 玩游戏的人 | 功能使用指南 |
| `DEVELOP.md` | 改代码的人 | 本文：环境、配置、部署、排障 |
| [`AGENTS.md`](AGENTS.md) | 改代码的人 / AI 助手 | 编码约定，写代码前必读 |
| [`docs/architecture.md`](docs/architecture.md) | 改代码的人 | 设计决策与宏观架构 |
| [`docs/data_dict.md`](docs/data_dict.md) | 改代码的人 | 表结构与磁盘路径 |
| [`docs/specs/`](docs/specs/README.md) | 改代码的人 / AI 助手 | 各功能的实现规格 |
| [`packaging/windows/README.md`](packaging/windows/README.md) | 打包的人 | Windows 包构建 |
| [`backend/search/csv/README.md`](backend/search/csv/README.md) | 维护数据的人 | 检索 CSV 格式 |
| [`backend/search/ranking/README.md`](backend/search/ranking/README.md) | 维护数据的人 | 榜单 CSV 格式 |
