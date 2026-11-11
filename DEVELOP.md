# 开发指南

面向改这个仓库的人。只想玩的话看 [`README.md`](README.md)。

- **代码约定**（写代码前先读）：[`AGENTS.md`](AGENTS.md)
- **设计文档**：[`docs/architecture.md`](docs/architecture.md)
- **数据结构**：[`docs/data_dict.md`](docs/data_dict.md)
- **功能规格**：[`docs/`](docs/README.md)

项目默认**中文**：界面文案、文档、注释、提交说明、API 错误 `message` 全用中文；
代码标识符、路由 path、环境变量名保持英文。**不做 i18n。**

## 这是什么

Vue 3 SPA（`frontend/`）+ FastAPI JSON API（`backend/`），ORM 是 SQLModel，库是 SQLite。

主要功能：

- **游戏中心**：Flash 用 Ruffle、HTML5 走沙箱 iframe、主机 ROM 用 EmulatorJS。
- **库存管理**：上传 / 直链 / 搬运、卡带 ID 与元数据、攻略。
- **游戏发现**：外部游戏名录与按机种榜单。
- **按键管理**：按账号保存自定义快捷键。
- **机型简史**：静态展示各机种的介绍与代表机型。

账号开放注册，只用于隔离各人的模拟器配置、存档、截图与统计。

## 环境要求

- Python 3.12（与 api 镜像、Windows 包一致）
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

后端启动时：全新的 app.db 会按最新结构自动建表；已有的库只校验结构版本，不自动升级。
`game.db` 不存在或为空文件时建最新的空结构，已有表不碰；数据只由 `make index` 写入。
拉取到包含表结构变化的代码后，先停服务，再执行 `make upgrade`。

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
- 机制与运行行为见 [`docs/modules/delivery-docker.md`](docs/modules/delivery-docker.md)。

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
3. `init_db()`：
   - 全新库：按当前模型建全部表，并写入 `system_config.db_version = 最新版本`。
   - 已有库：只读 `db_version`，不建表、不补列。
4. 版本不匹配：记录中文错误并永久阻塞，服务不会监听端口。
5. `ensure_empty_game_db()`：game.db 不存在或没有表时，建一份最新的空结构；
   已有表的 game.db 不碰。它只建结构，不写游戏名录/榜单数据。
6. `backup_database()`：立刻备份一份。
7. `start_backup_loop()`：起守护线程，每小时再备一次。

游戏名录、游戏榜单数据不在这里构建：启动只建空结构，数据只由人工 `make index` 写入。

哨兵缺失与 `app.db` 版本不匹配**一定拦住启动**；`game.db` 结构不符只让发现页返回 503；
备份失败只记 warning，不拦启动。

### 数据库结构升级

`app.db` 的结构版本记录在 `system_config.db_version`；`game.db` 另有
`meta.ranking_schema_version`。运行代码只认最新结构，历史兼容全部在根目录 `upgrade/`
（app.db 用 `versions/`，game.db 用 `game_versions/`），由用户手动执行。

Docker / 仓库路线：

```bash
docker compose down
make upgrade      # app.db + game.db 结构迁移；不读 CSV
make index        # 构建游戏名录、游戏榜单并同步两个标记
make all
```

Windows「解压即用」包：

```text
关闭启动窗口 → 双击「升级数据库.cmd」→ 重新双击「启动游戏平台.cmd」
```

- 升级脚本读取 `xgame.ini` 的 `data_dir` / `runtime_dir`，调用 `launcher.py --upgrade-db`。
- 服务运行中，或因版本不匹配正在阻塞时，脚本拒绝执行并提示先关窗口。
- 升级前会默认把库备份成 `<运行时根>/db/app.db.bak-v<旧版本>-<时间戳>`。
- 已是最新时输出 `当前已是最新版本，无需升级`。
- 失败会回滚当前版本并返回非零码；之前已成功的版本保留，修好后可重跑。
- 升级时服务必须停止，SQLite 不允许一边写一边重建表。
- 改过 `xgame.ini` 的用户要把旧配置一起复制到新包，否则脚本会看默认的 `data`。

- `make upgrade` 会迁移 app.db 与 game.db 结构；game.db 迁移只补列/映射/索引，不读 CSV。
  game.db 不存在时顺手建空结构。
- `make index` 只接受当前结构：缺失或过旧会直接报错并提示 `make upgrade`。
  它只构建游戏名录、游戏榜单与刷新标记，不建表、不改索引。
- Windows 包没有 make index；需要时在仓库/WSL 执行 `make index`，或在包根先设
  `STORAGE_ROOT` / `RUNTIME_ROOT` 再执行 `python\python.exe -m backend.cli index`。
- 榜单 CSV 里同一卡带 ID 出现在多行时，`make upgrade` 的映射迁移与 `make index` 都会报错，
  需先修 CSV。

Docker 路线的 `make upgrade` 在宿主机仓库执行，读取 `.env` 里的
`RUNTIME_HOST_DIR`（缺失时退回 `STORAGE_HOST_DIR`）。Windows 包的手动兜底：

```bash
RUNTIME_ROOT=/mnt/d/xgame/data/runtime STORAGE_ROOT=/mnt/d/xgame/data \
  python3 -m upgrade
```

#### 增加一个 app.db 结构版本

1. 新建 `upgrade/versions/vN.py`，定义 `VERSION = N` 与 `upgrade(conn)`。
2. 在 `upgrade/versions/__init__.py` 的 `VERSION_MODULES` 末尾登记。
3. 把 `backend/system_config.py::LATEST_DB_VERSION` 改成 N。
4. 补升级测试，并更新 [`docs/modules/database-upgrade.md`](docs/modules/database-upgrade.md)。

版本模块只写显式 SQL，不 import 当前模型，也不自行 commit / rollback。
详细规则见 [`docs/modules/database-upgrade.md`](docs/modules/database-upgrade.md)。

#### 增加一个 game.db 榜单结构版本

1. 新建 `upgrade/game_versions/vN.py`，定义 `VERSION = N` 与 `migrate(conn)`；只补结构/映射，不读 CSV。
2. 在 `upgrade/game_versions/__init__.py` 的 `MIGRATIONS` 末尾登记。
3. 同步递增 `backend/games/search_index.py::RANKING_SCHEMA_VERSION`。
4. 补迁移测试，并更新 [`docs/modules/database-upgrade.md`](docs/modules/database-upgrade.md)。

游戏名录结构（`SCHEMA_VERSION`）不做原地迁移：版本变化时停服务、删除 `game.db`，
重新启动会建空结构，再执行 `make index` 重建数据。

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
[`docs/modules/delivery-windows.md`](docs/modules/delivery-windows.md)。

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

- `backend/search/catalog/` 下 37 个中英文名录 CSV（游戏名录）。
- `backend/search/rankings/` 下 34 个机种榜单 CSV（每个机种一个文件，四列：`中文名,英文名,评分,卡带ID`）。

它们构建成一个只读库 `<运行时根>/db/game.db`：

```bash
make index
# CLI 还可加 --ranking-dir PATH 临时换一份榜单目录
```

- 每次运行都全量构建游戏名录、游戏榜单与卡带映射，并同步 app.db / game.db 的标记。
- 没有 `--skip-ranking`，也不做增量。
- 只有 `build_index()` 构建；启动只建空结构，不写数据。
- 执行前先确认 game.db 已是当前结构（`make upgrade`）；缺失或过旧会直接报错，不会自动建表/改索引。
- 构建前建议停 api：`make index` 会写 app.db 的 `in_ranking` 标记。
- 运行期只读：`mode=ro` + `PRAGMA query_only=1`，每请求一条短连接。
- 唯一例外是 `ranking_flags.py` 对 `ranking.in_library` 的短事务更新。
- 不参与备份，可从 CSV 重建。
- 重建后不用重启 api。

实现细节见 [`docs/modules/game-discover.md`](docs/modules/game-discover.md)。

### 索引构建失败（PermissionError）

运行时目录若被 Docker 以 root 建过，宿主用户可能写不了。
服务照常启动，页面提示「尚未构建游戏名录」/「榜单尚未加载」；`make index` 会失败并提示。

```bash
sudo chown -R "$USER" "$RUNTIME_HOST_DIR"
```

也可以换一个宿主用户自有的 `RUNTIME_HOST_DIR`。

### 改了名录、榜单或分词规则之后

- 改 `backend/games/search_text.py` 后必须重跑 `make index`，否则中文可能静默搜不到。
- 改游戏名录表结构要加 `SCHEMA_VERSION`；它不能原地迁移，删 `game.db` 后重启再 `make index`。
- 改游戏榜单表结构改 `RANKING_SCHEMA_VERSION`，不要动 `SCHEMA_VERSION`；同时补 `upgrade/game_versions/vN.py`。
- 榜单目录换内容不用改版本号：重跑 `make index`；服务启动不会补载。

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

**服务不监听端口，日志提示「数据库结构版本 … 低于/高于当前程序需要的 …」。**
`app.db` 结构与代码不匹配，服务已按设计永久阻塞。Docker 停服务后执行 `make upgrade`，
再启动；Windows 包关闭启动窗口后双击「升级数据库.cmd」。不要尝试让服务自动改表。
注意 `--workers 1` 是必须的，多进程会撞 SQLite 写锁。

**游戏发现页返回 503，提示索引版本过旧或无法打开。**
`game.db` 结构或文件有问题。停服务执行 `make upgrade`；若提示游戏名录结构不能原地升级，
删除 `game.db` 后重启建空结构，再执行 `make index`。

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
| [`docs/`](docs/README.md) | 改代码的人 / AI 助手 | 各功能的实现规格 |
| [`packaging/windows/README.md`](packaging/windows/README.md) | 打包的人 | Windows 包构建 |
| [`backend/search/catalog/README.md`](backend/search/catalog/README.md) | 维护数据的人 | 游戏名录 CSV 格式 |
| [`backend/search/rankings/README.md`](backend/search/rankings/README.md) | 维护数据的人 | 榜单 CSV 格式 |
