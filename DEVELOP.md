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
  mount_guard.py          # 数据根目录的 .mounted 哨兵文件
  backup.py               # SQLite 月度备份
  database.py             # 引擎、建表、_ensure_columns() 补列（无迁移框架）
  storage/                # types（协议）/ local（LocalStorage）/ access（流式下载响应）
  auth/ games/ tools/     # 一块功能一个包，各含 router.py（只 HTTP）+ service.py（领域逻辑）
  games/paths.py          # 所有磁盘相对路径规则的唯一出处
  games/importer.py       # 搬运（7k7k / 4399 / flash.homes）
  games/remote.py         # 网络上传（http/https 直链）
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

## 配置

绝大部分配置**写死在代码里**，只有两个键留在 `.env`，而且**后端进程一个都不读**：

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `STORAGE_HOST_DIR` | `./data/storage` | **宿主侧**数据目录，compose 挂到容器的 `/data` |
| `WEB_HTTPS_PORT` | `443` | 对外发布的 HTTPS 端口（容器内 nginx 固定听 443） |

写死的东西（要改就改代码，改完重新构建）：

| 配置 | 位置 | 值 |
| --- | --- | --- |
| `SECRET_KEY` | `backend/config.py` | session cookie 的签名密钥，跟仓库一起走；改它会让所有已登录会话失效 |
| `STORAGE_ROOT` | `backend/Dockerfile` 的 `ENV`（容器）/ `backend/config.py`（本机） | 容器里固定 `/data`；本机是 `<仓库>/data/storage` |
| SQLite 路径 | `backend/config.py` 的 `DB_SUBDIR` / `DB_FILENAME` | `<STORAGE_ROOT>/db/app.db`，**没有 `DATABASE_URL` 可配** |
| 证书 | `docker-compose.yml` + `frontend/nginx.conf.template` | `certs/cert.pem` 与 `certs/cert.key` |
| Session cookie | `backend/config.py` | HttpOnly、SameSite=Lax、HTTPS 下 Secure（测试自动关） |
| `TESTING` | `backend/config.py` | 只给测试用 |

> **这是有意的取舍**：平台只给自己用，不打算部署到别人的机器上，所以不做「可配置化」。
> 密钥、证书都随仓库提交，安全性不是考虑项。别把 `SECRET_KEY` 之类的再挪回环境变量。

### 启动时发生什么

`create_app()`（`backend/__init__.py`）按顺序做四件事：

1. `ensure_mounted()` — 数据根目录没有 `.mounted` 哨兵文件就建一个；
2. `ensure_data_dir()` — 建出 `<STORAGE_ROOT>/db`；
3. `init_db()` — `create_all` 建缺失的表，再 `_ensure_columns()` 给老表 `ALTER TABLE ADD COLUMN` 补列；
4. `backup_database()` — 当月还没有备份就往 `<STORAGE_ROOT>/db/<YYYY-MM>.db` 备一份。

第 4 步失败只记 warning，**绝不拦住启动**；不做还原功能，回滚靠手工替换 `app.db`。

### `.mounted` 哨兵文件

数据根目录里有一个空的 `.mounted`，服务启动时检查一次：**没有就新建**。它只是「这个目录就是
数据根」的标记。

**它不拦启动**：数据目录挂在 WSL 的 Windows 盘上（`/mnt/…`）而 docker 先于盘起来时，bind 会把
宿主空目录挂进容器，服务会在空目录里建一个新库。规避办法是把 `STORAGE_HOST_DIR` 指向 docker
启动前就可达的稳定路径，见下面「排障」。

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
.mounted                                     哨兵文件（启动时自动创建）
db/app.db                                    SQLite 库（SQLModel 表）
db/2026-10.db                                月度备份
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

## 提交约定

分支名 `<类型>/<描述>`（小写、`-` 连接），如 `feat/cartridge-id`。
提交标题 `<类型>: <中文短语>`，类型用 `feat` / `fix` / `docs` / `refactor` / `test` / `chore`，
一个提交只做一件事。

## 排障

**数据目录在 WSL 的 Windows 盘上（`/mnt/…`），开机后数据像是空的。**
Docker 守护进程可能先于 WSL 发行版起来，bind 把宿主的空目录挂进了容器，服务就在那儿建了新库
（写入落在 tmpfs 内存里，重启即丢）。发行版起来后 `docker compose restart api` 即可恢复。
治本的办法是把 `STORAGE_HOST_DIR` 指向 docker 启动前就稳定的路径，并且别放在会被 `git pull`
覆盖的仓库目录里。

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
