# 数据库结构升级

## 职责

`app.db` 的结构版本只有一个来源：`system_config.db_version`。

- 运行代码只描述**最新**结构，不写任何兼容旧库的分支。
- 历史兼容只在根目录 `upgrade/versions/vN.py`，由用户停服后手动执行 `make upgrade`。
- 服务启动只校验版本；不匹配就记录中文错误并永久阻塞，不监听端口。

## 关键接口

| 位置 | 作用 |
|---|---|
| `backend/system_config.py` | `SystemConfig` 模型、`DB_VERSION_KEY`、`LATEST_DB_VERSION` |
| `backend/database.py` | 全新库建表并写版本；已有库只读版本；不匹配抛 `DatabaseVersionError` |
| `backend/startup_guard.py` | `block_forever()`：版本不匹配时永久阻塞 |
| `upgrade/runner.py` | 读版本、逐版本执行、事务、备份 |
| `upgrade/cli.py` | `main(argv)`：解析路径、调用运行器、返回 0/1 |
| `upgrade/versions/v1.py` | 无版本号时代 → 版本 1 的冻结迁移 |
| `packaging/windows/launcher.py` | `--upgrade-db`：Windows 包内的升级动作 |
| `make upgrade` | 宿主机/Docker 路线的升级命令 |

## 版本规则

- 版本是正整数，从 1 连续递增；不允许跳版本。
- `LATEST_DB_VERSION` 是当前代码要求的版本，必须等于 `upgrade/versions` 注册表的最大键。
- 是否执行某个版本**只取决于当前 `db_version`**；版本已经达到就不再执行该版本模块。
- 旧版本模块是冻结快照，不得随当前模型修改；结构变化新增 `vN.py`。
- 别和另外两个版本概念混淆：`APP_VERSION` 是发版号；
  `game.db` 的 `SCHEMA_VERSION` / `RANKING_SCHEMA_VERSION` 是派生索引库自己的版本。

## 新增一个版本

1. 新建 `upgrade/versions/vN.py`：

   ```python
   VERSION = N
   DESCRIPTION = "一句话说明"

   def upgrade(conn):
       conn.execute("ALTER TABLE ...")
   ```

2. 在 `upgrade/versions/__init__.py` 的 `VERSION_MODULES` 末尾登记。
3. 把 `backend/system_config.py::LATEST_DB_VERSION` 改成 N。
4. 补测试：从 N-1 升级到 N、失败回滚、schema 对齐。
5. 更新本文件与 `docs/data_dict.md`。

版本模块的硬约束：

- 只依赖标准库 `sqlite3` 与显式 SQL；不 import `backend` / SQLModel / SQLAlchemy。
- 假定运行器已经开启写事务；禁止 commit / rollback / `executescript`。
- 不要依赖当前 ORM 模型；需要结构就直接写冻结 DDL。

## 执行与事务

`make upgrade` 在宿主机运行 `python3 -m upgrade`，数据路径规则与 compose 一致：

```text
RUNTIME_ROOT → STORAGE_ROOT → ./data/storage
最终库：<根>/db/app.db
```

执行步骤：

1. 库不存在或没有业务表：提示「数据库尚未初始化，无需升级」，不创建文件。
2. 读当前版本；高于代码版本直接报错，不能降级。
3. 已是最新：输出 `当前已是最新版本，无需升级`。
4. 默认先备份为 `<db>.bak-v<旧版本>-<UTC 时间戳>`；备份失败则不做任何迁移。
5. 对每个待升级版本：
   - `BEGIN IMMEDIATE`
   - 执行版本模块
   - upsert `system_config.db_version`
   - `COMMIT`
6. 任一版本失败：回滚该版本，输出中文错误，返回非零码；之前已成功的版本保留。

命令行参数：

```bash
python -m upgrade --db /path/to/app.db
python -m upgrade --runtime-root /path/to/runtime
python -m upgrade --no-backup
```

## 启动行为

- 全新库（不存在或除 `system_config` 外没有表）：`create_all` 建最新结构，并在同一事务里
  写入 `LATEST_DB_VERSION`。
- 已有库：只读版本，不建表、不补列。
- 低于代码版本：日志提示执行 `make upgrade`（Windows 包：关闭启动窗口后双击
  「升级数据库.cmd」），随后 `block_forever()` 永久阻塞。
- 高于代码版本：日志提示使用匹配的程序版本，同样阻塞。
- 版本值不是合法整数：记错误并阻塞。

## 入口与交付

- Docker（库在宿主 bind mount 上）：停 api 后，在宿主机仓库执行 `make upgrade`。
- Windows「解压即用」包：关闭启动窗口后双击「升级数据库.cmd」。
  - 脚本读取 `xgame.ini` 的 `data_dir` / `runtime_dir`，调用 `launcher.py --upgrade-db`。
  - 先查单实例互斥体，再查端口；服务运行中或因版本不匹配阻塞时拒绝执行。
  - 升级前默认备份；退出码原样透传给 `.cmd`，窗口会停住让用户看清结果。
  - 手动兜底：在包根执行
    `python\python.exe -m upgrade --storage-root data --runtime-root data\runtime`。
- 不允许热升级；升级前必须停止服务，避免 SQLite 写锁。

## 边界与错误

- 不允许并发执行 `make upgrade`；`BEGIN IMMEDIATE` + 事务内二次读版本只做兜底。
- 版本模块的 DDL 与 `db_version` 在同一事务里，失败不会出现「表改了一半、版本却前进」。
- 备份文件与 `app.db` 同目录，确认升级成功后可自行清理。
- `system_config.key` 唯一，长度上限 255；`value` 长度上限 1024（应用层校验）。

## 测试要点

- 逐版本执行，不能跳版本。
- 某个版本失败后回滚该版本，`db_version` 停在上一版本。
- 二次运行提示 `当前已是最新版本，无需升级`。
- v0 老库升级后的表、列、索引与全新库一致。
- 版本不匹配启动时阻塞且日志含 `make upgrade` 与「升级数据库.cmd」。
- 版本模块不 import 运行时模型，不自行提交事务。
- Windows 升级入口：参数解析、互斥体/端口拒绝、路径传参、退出码透传、`.cmd` 编码。

## 相关文档

- [数据字典](../data_dict.md)
- [架构说明](../architecture.md)
- [开发与排障](../../DEVELOP.md)
