# AGENTS.md

本仓库中编码 Agent 必须遵守的约定。写代码、改代码前先读本文件。

## 本文件管什么

| 文档 | 管什么 |
|---|---|
| 本文件 | 编码约定：语言、技术栈、目录、分层、风格、Git、测试原则 |
| [`docs/architecture.md`](docs/architecture.md) | 设计取舍与宏观架构 |
| [`docs/data_dict.md`](docs/data_dict.md) | SQLite 表结构与磁盘路径 |
| [`docs/specs/`](docs/specs/README.md) | 各功能的实现规格 |
| [`CLAUDE.md`](CLAUDE.md) | 会话入口与硬规则索引 |

## 当前状态

前后端分离已落地：Vue 3 SPA + FastAPI JSON API。

两条交付路线并存：

- Docker：nginx + gunicorn + HTTPS，正式运行。
- Windows「解压即用」包：后端托管前端、单进程 uvicorn、http。

若用户请求会违反本文件（不做 Docker、用 React 替换 Vue、把游戏文件整读进内存），
先停下来说明冲突，再写代码。

## 语言

默认中文。

必须用中文：

- 界面文案（导航、按钮、表单、占位符、空状态、错误提示）
- Markdown 文档
- `.env.example` 注释
- 用户可见的校验失败信息（含 API `message`）
- CLI 帮助与提示

可以保留英文：

- 代码标识符、路由 path、环境变量名、表名、列名
- 第三方库名与官方术语
- 日志里的稳定机器字段名（`message` 本身仍用中文）

不做 i18n / gettext / 多语言切换。

## 产品边界与明确不做

产品是个人自托管游戏平台，只给本人与受邀访客使用。

功能边界：

- 游戏中心：Flash、HTML5、8/16/32-bit 主机 ROM。
- 游戏管理：上传 / 直链 / 搬运、卡带 ID 与元数据、攻略。
- 游戏发现：外部名录的只读检索与按机种榜单。
- 账号：开放注册，只隔离模拟器配置与存档。

明确不做：

- React、TypeScript
- PostgreSQL、Redis、Celery
- OAuth、邮箱验证码、找回密码
- 对象存储（MinIO / S3）
- JWT、把 token 写进 `localStorage`
- 把整个文件读进内存再中转
- 把密钥写进 git、前端源码或日志
- 自动创建 `.mounted`
- Windows 包自动升级、安装向导

## 技术栈（锁定）

后端：

- Python 3.12
- FastAPI + 应用工厂 `create_app()`
- SQLModel + SQLite
- Starlette SessionMiddleware + CSRF
- Docker 内 Gunicorn + uvicorn worker
- Pydantic Settings
- 标准库文件 I/O
- pytest

前端：

- Vue 3 + Vite
- vue-router 4
- Pinia
- Element Plus
- axios（唯一实例在 `frontend/src/utils/request.js`）
- JavaScript（不加 TypeScript）

## 目录约定

只建这些目录，不要多加。宏观分区与分层见
[`docs/architecture.md`](docs/architecture.md) 的「项目结构」与「分层规则」。

```
frontend/                    # Vue 3 SPA
  src/main.js                # 入口：Pinia、router、Element Plus、permission
  src/permission.js          # 路由守卫（登录态）
  src/router/index.js        # 唯一路由表；菜单由 meta 驱动
  src/layout/                # 侧栏 + 顶栏 + 内容区
  src/store/                 # Pinia：app / auth
  src/api/                   # 按业务域导出 xxxAPI
  src/utils/request.js       # axios 实例 + 拦截器
  src/views/                 # login / games / shortcuts
  src/components/common/     # 跨模块 UI 组件
  src/components/games/      # 游戏专用组件
  src/constants/             # 展示层镜像
  src/utils/                 # 前端工具
  src/styles/                # 样式 token
  scripts/                   # 构建期资产脚本
  public/                    # SW、播放宿主、引擎资产
backend/
  __init__.py                # create_app()
  asgi.py                    # 生产 ASGI 入口
  config.py                  # 配置（全部写死）
  database.py                # 引擎、建表、补列
  backup.py                  # SQLite 滚动备份
  mount_guard.py             # 根目录哨兵检查
  static_site.py             # 可选：后端托管前端 dist
  request_limit.py           # 请求体上限
  entrypoint.sh              # api 容器入口
  auth/                      # 账号
  games/                     # 游戏中心与管理
    paths.py                 # 磁盘路径规则
    save_*                   # 云端存档
    screenshot_* / gallery_* # 截图 / 图集
    settings_* / stats_*     # 模拟器设置 / 游玩统计
    search_* / ranking_*     # 检索 / 榜单
    importer.py / remote.py  # 搬运 / 网络上传
  tools/                     # 工具注册表
  storage/                   # 跨模块存储
    types.py / local.py      # 协议 / LocalStorage
    access.py                # 流式下载响应
  search/csv/                # 检索名录 CSV
  search/ranking/            # 榜单 CSV
tests/                       # pytest
packaging/windows/           # Windows 解压即用包
docs/                        # architecture / data_dict / specs
scripts/version.sh           # 版本号唯一出处
certs/                       # 自签名证书
```

- `data/` 只放本地运行时数据，加入 gitignore。
- 不使用 docker 具名卷。
- 数据 schema 见 [`docs/data_dict.md`](docs/data_dict.md)。

## 架构规则（必须遵守）

1. **应用工厂。** 唯一入口是 `create_app()`；生产 ASGI 入口是 `backend/asgi.py` 的 `app`。
2. **一个功能一个包。** `router.py` 只管 HTTP、只返回 JSON；`service.py` 管领域逻辑。
3. **service 是拆微服务的边界。** 禁止在 `service.py` 里使用 FastAPI `Request` / `session`；
   存储后端等依赖由构造函数传入。
4. **前端分层。** 页面 → `api/*`（`xxxAPI`）→ `request.js` → FastAPI。
   新增接口只改 api 层与后端 router，不碰 `request.js`。
5. **通用组件。** 自定义弹窗、按钮、筛选、空状态放 `components/common/`；
   只被一个工具用的放 `components/<tool>/`；带路由的页面只放 `views/`。
6. **导航由路由表驱动。** 侧栏菜单由子路由声明顺序 + `meta.title` 生成，不要在页面里写死链接。
7. **配置写死。** 全部配置在 `backend/config.py`。
   - `.env` 只有 `STORAGE_HOST_DIR` / `RUNTIME_HOST_DIR` / `WEB_HTTPS_PORT` 三个键。
   - `.env` **只给 docker compose 读**，后端不读这个文件。
   - 两个 `*_HOST_DIR` 由 compose 作为环境变量传进容器，仅供哨兵前缀判断。
   - 根目录不存在会自动创建，storage 永远可用，没有「未配置」开关。
8. **SQLite 路径。** 写死为 `<运行时根>/db/app.db`，没有 `DATABASE_URL` 可配；
   备份写在数据根的 `db/` 里。
9. **Gunicorn。** 必须 `--workers 1 --threads 8`；单进程避免 SQLite 写冲突。

## 代码风格

- Python 3.12；service 对外方法写类型标注；4 空格缩进。
- 拆模块，不要把 SQL 写进 router。
- service 抛领域异常；router 转成 JSON 4xx（`message` 用中文）。
- 不留大段注释掉的代码；功能路径里不留「TODO: 以后再实现」。
- 日志：请求/操作用 INFO；禁止记录密码、`SECRET_KEY`。
- 注释只在需要解释「为什么」时使用，用中文。
- 前端 4 空格；api 函数命名 `xxxAPI`。

## 前端约定

- 页面在 `views/`；api 在 `api/*`；唯一 axios 实例是 `utils/request.js`。
- 按钮统一走 `AppButton`：`secondary` / `danger` 两种类型，`text` 是无框形态，size × tone。
- 分段/标签统一走 `AppSegmented`；分页、空状态、复制等走 `components/common/`。
- 样式 token 在 `styles/index.css`，页面里不手写原生 `<button>` 或按钮 CSS。
- 侧栏与播放页标题栏是浮层：常驻收起、鼠标靠近边缘滑出，不占位、不引起内容缩放。
- 详细路由、组件与交互约定见 [`docs/specs/frontend.md`](docs/specs/frontend.md)。

## Git 分支与提交

分支名 `<类型>/<描述>`，小写、`-` 连接，描述两三词内。

- 好：`feat/cartridge-id`、`fix/h5-upload`
- 坏：`feature_eye`、`fix/login_timeout_issue`、`FEAT/x`

提交标题 `<类型>: <中文短语>`，冒号后一个空格。

- 好：`feat: 游戏增加卡带ID`、`fix: 修复 H5 重传后资源 404`
- 坏：`feat`、`feat:xx`、`fix: 修 bug`

类型用 `feat` / `fix` / `docs` / `refactor` / `test` / `chore`。
一个提交只做一件事。

## 测试原则

```bash
make test        # = python -m pytest + cd frontend && npm run lint
python -m pytest # 只跑后端
```

- 用 `python -m pytest`，不要用裸 `pytest`（后者加不进仓库根目录）。
- 实现过程中只跑本次改动涉及的用例，全量测试由用户定期执行。
- **只改文档（含本文件、`CLAUDE.md`、`docs/`、技能说明）不跑测试。**
- 测试用临时 SQLite + 临时 `STORAGE_ROOT`，直接打真实文件系统，不 mock 存储层。
- 最低覆盖范围：账号与锁定、存储读写与越界、游戏入库与卡带 ID、H5/攻略、
  云端存档、截图与图集、模拟器设置、最近游玩、游玩统计、检索与榜单、
  静态站、请求上限、Windows 启动器。
- 每个功能的详细测试要点见对应 `docs/specs/*.md` 的「测试要点」。

## 新增功能 / 工具

1. 建 `backend/<name>/`，含 `router.py` + `service.py`。
2. 在 `create_app()` 注册 router。
3. 写入 `backend/tools/registry.py`（名称、描述用中文）。
4. 建 `frontend/src/api/<name>.js`、`views/<name>/` 与路由 `meta`。
5. 工具专用组件放 `components/<name>/`；跨工具 UI 只改 `components/common/`。
6. 补测试；除导航与注册表外，不要改其它工具。

若工具变重，保持同一套 service 接口，以便以后迁到微服务。

## 功能域规格索引

| 功能域 | 规格 |
|---|---|
| 账号、登录、CSRF | [`auth.md`](docs/specs/auth.md) |
| 存储、卡带 ID、封面类型、导入 | [`game-storage.md`](docs/specs/game-storage.md) |
| 机种词表 | [`platforms.md`](docs/specs/platforms.md) |
| 播放器、标题栏、机壳、NDS | [`game-center-playback.md`](docs/specs/game-center-playback.md) |
| 截图、图集、封面美化 | [`game-assets.md`](docs/specs/game-assets.md) |
| 存档、设置、最近、统计 | [`game-saves-stats.md`](docs/specs/game-saves-stats.md) |
| H5 与攻略 | [`guide-and-h5.md`](docs/specs/guide-and-h5.md) |
| 游戏发现 | [`game-discover.md`](docs/specs/game-discover.md) |
| 前端框架与交互 | [`frontend.md`](docs/specs/frontend.md) |
| HTTP 端点 | [`api.md`](docs/specs/api.md) |
| Docker | [`delivery-docker.md`](docs/specs/delivery-docker.md) |
| Windows 包 | [`delivery-windows.md`](docs/specs/delivery-windows.md) |

## 用户意图

- 用户要求写代码时：直接实现，不要只复述文档。
- 用户只要文档时：不要加应用代码。
- 默认不做截图 / 浏览器验证；除非用户当次明确要求。
