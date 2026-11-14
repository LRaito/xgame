# Docker 交付

本文件回答：Docker 路线如何构建、部署与备份。

## 范围与权威

- Docker 是正式运行方式，由根目录 `docker-compose.yml` 编排。
- 只有两个服务：`web` 与 `api`，没有对象存储。
- api 镜像来自 `backend/Dockerfile`，web 镜像来自 `frontend/Dockerfile`。
- 容器入口是 `backend/entrypoint.sh`。
- 配置在 `backend/config.py`；`.env` 由 compose 与 Makefile 读取。
- 哨兵检查见 `backend/mount_guard.py`，备份见 `backend/backup.py`。
- 索引构建见 `backend/games/search_index.py`。
- 设计背景见 `../architecture.md` 的「运行架构」与「配置」。

## 职责

- 用 Docker Compose 交付 web 与 api 两个容器。
- 把两个宿主目录 bind 进容器，并做启动哨兵检查。
- 维护 HTTPS、反向代理、上传闸门与 SQLite 备份。

## 关键接口

- 部署入口：`docker-compose.yml`、`Makefile`。
- 镜像：`backend/Dockerfile`、`frontend/Dockerfile`。
- 网关：`frontend/nginx.conf.template`；启动检查：`backend/entrypoint.sh`、`mount_guard.py`。

## 依赖

- Docker Compose、nginx、Gunicorn + uvicorn。
- `STORAGE_HOST_DIR`、`RUNTIME_HOST_DIR`、`WEB_HTTPS_PORT` 三个 `.env` 键。
- 仓库内 `certs/` 的自签名证书。

## 数据与路径

- 数据落两个宿主目录，**不使用任何 docker 具名卷**。
- `STORAGE_HOST_DIR` 是数据根，bind 到容器 `/data`。
- `RUNTIME_HOST_DIR` 是运行时根，bind 到容器 `/runtime`。
- 数据根放游戏文件与月度备份。
- 运行时根放 SQLite 业务库、游戏发现索引与 H5/攻略解包产物。
- 不建 `.env` 时两个根都退回 `./data/storage`。
- `.env.example` 的默认值是 `./data/storage` 与 `./data/runtime`。
- SQLite 固定为 `<运行时根>/db/app.db`，没有 `DATABASE_URL`。
- 游戏发现索引（游戏名录与游戏榜单）在 `<运行时根>/db/game.db`。
- 月度备份在 `<数据根>/db/app.db.<YYYY-MM>`。
- 证书随仓库提交在 `certs/`，只读挂到 `/etc/nginx/certs`。
- `.env` 只有三个键：`STORAGE_HOST_DIR`、`RUNTIME_HOST_DIR`、`WEB_HTTPS_PORT`。
- 后端不读 `.env`；两个 `*_HOST_DIR` 由 compose 传进容器，只给哨兵判断。

## 行为与规则

**镜像。**

- 基础镜像按 digest 固定（`FROM <image>@sha256:<digest>`），Dockerfile 注释里记录原 tag 与取值日期。
- 构建统一带 `--pull=false`（`make build` 与 Windows 包构建脚本），不在构建前拉取更新的基础镜像。
  本地缺基础镜像时 Docker 仍会联网拉取；要完全离线运行构建，先手动 `docker pull` 好一次。
- api：`python:3.12.15-slim-trixie`。
- web 构建阶段：`node:22.23.3-alpine3.24`。
- web 运行阶段：`nginx:1.27.5-alpine3.21`。
- Windows 包构建环境：`node:22.23.3-bookworm-slim`。

**web 服务。**

- nginx 托管前端 `dist`，把 `/api/` 与 `/health` 反代到 `api:8910`。
- 只开一个 443 server，只支持 HTTPS。
- 不发布 80，也没有 http→https 跳转。
- 宿主端口由 `WEB_HTTPS_PORT` 决定，容器内固定听 443。
- `client_max_body_size 130m` 是上传网关（128MB 内容 + multipart 余量）。
- `/api/` 关闭 `proxy_request_buffering`：请求体边收边转发，不再落 nginx 临时文件。
- `/api/` 同时用 `proxy_http_version 1.1`，没有长度的流式请求可用 chunked 转给后端。
- 本体超过 30MB 由前端切 16MB 分片；攻略 ZIP/PDF 仍限 128MB。
- 多文件本体（cue+bin / m3u / 多盘）每个物理文件各开一个分片会话，单请求仍受 130m 网关限制。
- `/assets/`、`/ruffle/`、`/emulatorjs/` 是 immutable 长缓存；
  更具体的 `/emulatorjs/bios/` 例外，改为 `no-cache`。
- 这些前缀未命中就 404，不回落 `index.html`。
- `index.html` 与 `emulator-host.html` 是 no-cache。
- 这两个 HTML 响应另带 `Cross-Origin-Opener-Policy: same-origin` 与
  `Cross-Origin-Embedder-Policy: require-corp`，供 PSP / DOS 的线程核使用
  `SharedArrayBuffer`；SPA 深链经 `try_files` 内部跳转后同样命中这组头。
- H5 资源由后端单独发 `Cross-Origin-Embedder-Policy: unsafe-none` 与
  `Cross-Origin-Resource-Policy: cross-origin`，沙箱页里的外链资源不受隔离策略影响。
- 静态核心资产与 ROM 都是同源请求，不需要额外 CORP。

**api 服务。**

- api 不对外发端口，只在 compose 网络内听 8910。
- Gunicorn 参数：`--workers 1 --threads 8 --timeout 300`。
- 必须 `--workers 1`：单进程避免 SQLite 写冲突。
- 单进程也保证 `RuntimeAssets` 的进程内锁有效。
- 多进程下并发 `os.replace` 覆盖非空目录会报 `ENOTEMPTY`。
- 入口脚本先过哨兵检查，再 `exec "$@"` 跑 CMD 里的 gunicorn。

**时区与时间。**

- api 与 web 两个服务镜像都固定 `TZ=Asia/Shanghai`。
- 日志时间与月度备份文件名按北京时间。
- 库里的 `created_at` 等时间戳仍存 UTC。
- 接口返回的时间没有时区后缀；前端经 `parseApiDate()` 按 UTC 解析再按本地展示。

**根目录哨兵。**

- `create_app()` 在 `ensure_data_dir()` 之前调 `require_mounted()`。
- 只当某个根的宿主路径落在 `WINDOWS_MOUNT_PREFIX` 下才检查。
- 默认前缀是 `/mnt`，可改；设成 `/` 表示所有路径都要求。
- 数据根与运行时根逐个查；两个根相同时按挂载点去重只查一次。
- 缺 `.mounted` 时只 stat 一下，不建目录、不建库。
- 然后打一条中文日志，等 5 秒，`sys.exit(3)`。
- 退出码 3 = gunicorn 的 `WORKER_BOOT_ERROR`；绕过入口脚本时 master 也会退出。
- 退的是容器主进程，compose 的 `restart: unless-stopped` 随即重新拉起。
- 如此循环直到哨兵出现，服务自己恢复。
- 哨兵必须人工创建，代码只检查、绝不代建。
- 普通 Linux 目录不检查，直接启动。

**bind 时序。**

- bind 源路径必须在 docker 启动之前就可达。
- WSL 里 Docker Desktop 可能先于发行版启动，bind 会挂一个空 tmpfs。
- 空挂载天然没有 `.mounted`，于是被哨兵拦住。
- 两个根应指向 docker 启动前就稳定的路径，别放仓库内。

**SQLite 滚动备份。**

- `create_app()` 启动时立刻调一次 `backup_database()`。
- 之后每 `BACKUP_INTERVAL_SECONDS`（1 小时）由守护线程再备一次。
- 当月只有一份 `app.db.<YYYY-MM>`，写在数据根 `db/` 里。
- 每次整份重写：先写 `.tmp` 再 `os.replace()`。
- 读的人永远看到完整文件，快照最多落后一小时。
- 用 `sqlite3` 的 backup API，不拷文件；服务一直在写，裸拷会撕裂。
- 失败只记 warning，绝不拦住启动；不做还原功能。

**索引与命令。**

- 服务启动只建空的 game.db 结构，不写游戏名录/榜单数据、不重载、不改已有结构。
- 游戏名录/游戏榜单数据只能人工执行 `make index`：整库重写 + `os.replace()`，不开 WAL；
  执行前要求 game.db 已是当前结构，缺失/过旧会提示先 `make upgrade`。
  同时全量同步两个库的库存/榜单标记，建议先停 api。
- 数据库结构升级入口是宿主机 `make upgrade`：先 `docker compose down`，升级完再 `make all`。
  它迁移 app.db 与 game.db 结构，但不构建游戏名录/榜单数据；之后还需 `make index`。
  服务启动只校验 `system_config.db_version`，不会自动改表；版本不匹配会永久阻塞。
- `cp .env.example .env` 可选，只放三个键；`make all` 等于 build + up，
  `up` 在 `compose up -d` 之后还会重启 api 与 web 各一次。
- 浏览器打开 `https://localhost`，点「注册一个」建号。

## 边界与错误

- 缺哨兵：api 容器反复重启，日志里有中文提示与要 `touch` 的宿主路径。
- 运行时根被 Docker 以 root 建过时，宿主机用户可能没有写权限。
- 此时 `make index` 会提示 `sudo chown -R "$USER" "$RUNTIME_HOST_DIR"`。
- `TESTING` 下跳过哨兵检查与备份线程。
- 宿主端口被占用时 web 容器直接起不来。
- 没有对象存储、没有具名卷、没有服务端渲染页面。
- Docker 与 Windows 包不能同时打开同一份数据目录，否则会写坏库。
- 更细的排障步骤见 `../../DEVELOP.md`。

## 测试要点

- `tests/test_mount_guard.py` 覆盖前缀判断、两个根、去重与缺哨兵退出。
- `tests/test_backup.py` 覆盖月度文件名、整份重写、新月份、失败不留残留文件。
- `make test` 在本机跑 pytest + 前端 lint，不动 Docker。

## 相关文档

- [Windows 解压即用包](./delivery-windows.md)
- [架构设计](../architecture.md)
- [数据字典](../data_dict.md)
- [开发与排障](../../DEVELOP.md)
- [项目说明](../../README.md)
