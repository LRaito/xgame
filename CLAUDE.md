# CLAUDE.md

> 给 Claude Code 的会话入口：只放结论与硬规则。
> 实现细节在 `docs/specs/`，写代码前读 [`AGENTS.md`](AGENTS.md)。

## 一分钟了解本仓库

- 个人自托管游戏平台：Vue 3 SPA（`frontend/`）+ FastAPI JSON API（`backend/`）。
- ORM 用 SQLModel + SQLite。
- 两条交付路线：Docker（正式运行）与 Windows「解压即用」包。
- 两条路数据格式一致，但**不能同时打开同一份数据目录**。
- 三块功能：游戏中心、游戏管理、游戏发现。
- 账号开放注册，只用于隔离各人的模拟器配置与存档。

## 先读哪份文档

| 你要做的事 | 先读 |
|---|---|
| 写代码、改代码 | [`AGENTS.md`](AGENTS.md) |
| 理解设计取舍 | [`docs/architecture.md`](docs/architecture.md) |
| 查表结构、磁盘路径 | [`docs/data_dict.md`](docs/data_dict.md) |
| 查某个功能的实现细节 | [`docs/specs/README.md`](docs/specs/README.md) |
| 用户怎么操作 | [`README.md`](README.md) |
| 开发、部署、排障 | [`DEVELOP.md`](DEVELOP.md) |

## 语言约定

- 界面文案、Markdown 文档、注释、提交说明、API 错误 `message` 一律中文。
- 代码标识符、路由 path、环境变量名保持英文。
- 不加 i18n / 多语言切换。

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
npm run dev
```

测试与构建：

```bash
make test        # pytest + 前端 lint
make win         # Windows 解压即用包
make index       # 重建游戏发现索引
```

- 平时只跑改动涉及的用例，全量 `make test` 由用户定期执行。
- **只改文档（含本文件、`AGENTS.md`、`docs/`、技能说明）不跑测试。**

## 架构速览

- 应用工厂：`backend/__init__.py::create_app()` 是唯一入口。
- 一个功能一块：`router.py` 只管 HTTP，`service.py` 管领域逻辑。
- 前端分层：`views/` → `api/*` → `utils/request.js` → FastAPI。
- 响应信封：成功 `{ok:true,data}`；失败 `{ok:false,message:"中文"}`。
- 配置写死在 `backend/config.py`；`.env` 只有三个键且只给 compose 读。
- 数据分两个根：数据根放原始素材，运行时根放 SQLite 与解包产物。
- 全站需登录，唯一业务例外是 H5 资源接口。
- 详细设计见 [`docs/architecture.md`](docs/architecture.md)。

## 必须遵守的硬规则

1. **应用工厂。** 唯一入口是 `create_app()`，不要另起入口。
2. **功能模块 = router + service。**
   `service.py` 里禁止使用 FastAPI `Request` / `session`。
3. **前端分层。** 新增接口只改 `api/` 与后端 router，不碰 `request.js`。
4. **两个根。** 数据根放会被备份的原始素材；运行时根放 SQLite 与解包产物。
   没有对象存储，没有 docker 具名卷。
5. **路径只经 `paths.py` / `LocalStorage`。** 不要在别处手拼磁盘路径。
6. **卡带 ID。** 手动新建与网络上传时必填、全局唯一、落库前转大写；
   搬运由服务端按 CRC32 自动生成；它同时是目录名，改名走显式迁移。
7. **封面类型。** 可空，只有编辑弹框与「美化封面」两条写入路径。
8. **机种词表。** `backend/games/platforms.py` 是唯一权威；
   加机种只改这张表。
9. **H5 / 攻略 ZIP 只校验不解压。** 播放或查看时才解到运行时根。
10. **云端存档是整体快照。** 快照之间是同一 (用户, 游戏) 内的父子森林。
11. **登录。** 除注册/登录/CSRF/健康检查与 H5 资源外，所有接口都要登录。
12. **配置写死。** `.env` 只有 `STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR` / `WEB_HTTPS_PORT`；
    后端不读 `.env` 文件。
13. **`.mounted` 哨兵。** 只拦启动、绝不代建；
    只在 Windows 盘挂载前缀下要求。
14. **Gunicorn 必须 `--workers 1`。** SQLite 单写者，多进程会冲突。
15. **明确不做。** React、TypeScript、i18n、OAuth、对象存储、JWT、
    Redis/PostgreSQL/Celery；Windows 包不做自动升级。

细节链接：

- 文件存储 / 卡带 ID / 封面类型 → [`game-storage.md`](docs/specs/game-storage.md)
- 机种词表 → [`platforms.md`](docs/specs/platforms.md)
- 播放器 / 机壳 / NDS → [`game-center-playback.md`](docs/specs/game-center-playback.md)
- 截图 / 图集 / 封面美化 → [`game-assets.md`](docs/specs/game-assets.md)
- 存档 / 设置 / 统计 → [`game-saves-stats.md`](docs/specs/game-saves-stats.md)
- H5 / 攻略 → [`guide-and-h5.md`](docs/specs/guide-and-h5.md)
- 游戏发现 → [`game-discover.md`](docs/specs/game-discover.md)
- 账号与会话 → [`auth.md`](docs/specs/auth.md)
- Docker → [`delivery-docker.md`](docs/specs/delivery-docker.md)
- Windows 包 → [`delivery-windows.md`](docs/specs/delivery-windows.md)

## 目录速查

```
frontend/        Vue 3 SPA
backend/         FastAPI API（auth / games / tools / storage）
docs/            architecture.md / data_dict.md / specs/
packaging/       windows/
tests/           pytest
```

完整目录树与新增目录规则见 [`AGENTS.md`](AGENTS.md) 的「目录约定」。

## Git 约定

- 分支名 `<类型>/<描述>`，小写、`-` 连接，如 `feat/cartridge-id`。
- 提交标题 `<类型>: <中文短语>`，类型 `feat` / `fix` / `docs` /
  `refactor` / `test` / `chore`。
- 一个提交只做一件事。
