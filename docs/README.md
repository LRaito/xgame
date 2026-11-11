# 文档索引

本文件回答：项目文档有哪些、各自管什么、按什么顺序读。

## 阅读路径

1. 先读 [`../CLAUDE.md`](../CLAUDE.md)，了解项目定位与硬规则。
2. 读 [`../AGENTS.md`](../AGENTS.md)，了解编码约定与测试原则。
3. 读 [`architecture.md`](architecture.md)，理解分层与设计取舍。
4. 查 [`data_dict.md`](data_dict.md)，确认表结构与磁盘路径。
5. 按功能查 [`modules/`](modules/)。
6. 跨模块复用的能力查 [`common/`](common/)。
7. 待办与计划查 [`plans/`](plans/)。

## 核心文档

| 文档 | 管什么 |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | 会话入口：项目是什么、硬规则、常用命令 |
| [`../AGENTS.md`](../AGENTS.md) | 编码约定、目录、分层、Git、测试原则 |
| [`architecture.md`](architecture.md) | 分层、模块关系、数据流、关键设计决策 |
| [`data_dict.md`](data_dict.md) | SQLite 表结构与磁盘路径 |
| [`../README.md`](../README.md) | 用户操作指南 |
| [`../DEVELOP.md`](../DEVELOP.md) | 开发、部署、排障 |

## 功能模块

| 文档 | 管什么 |
|---|---|
| [`modules/auth.md`](modules/auth.md) | 注册、登录、锁定、session、CSRF |
| [`modules/game-storage.md`](modules/game-storage.md) | 两个根、路径、卡带 ID、封面类型、导入 |
| [`modules/game-center-playback.md`](modules/game-center-playback.md) | 三类播放器、标题栏、机壳、NDS、快捷键 |
| [`modules/game-assets.md`](modules/game-assets.md) | 截图、图集、封面美化、素材几何 |
| [`modules/game-saves-stats.md`](modules/game-saves-stats.md) | 云端存档、设置同步、最近游玩、统计 |
| [`modules/guide-and-h5.md`](modules/guide-and-h5.md) | H5 与攻略包的校验、解包、读取 |
| [`modules/game-discover.md`](modules/game-discover.md) | 游戏名录索引、FTS、SQL、游戏榜单、库存/榜单标记 |
| [`modules/frontend.md`](modules/frontend.md) | 路由、api 层、组件、界面交互 |
| [`modules/platform-chronicle.md`](modules/platform-chronicle.md) | 机型简史：36 个类型的介绍页、图片与来源 |
| [`modules/delivery-docker.md`](modules/delivery-docker.md) | 镜像、compose、bind、备份、哨兵 |
| [`modules/delivery-windows.md`](modules/delivery-windows.md) | Windows 包构建、启动器、编码、升级 |
| [`modules/database-upgrade.md`](modules/database-upgrade.md) | 结构版本、upgrade 目录、make upgrade、启动阻塞 |

## 共享能力

| 文档 | 管什么 |
|---|---|
| [`common/platforms.md`](common/platforms.md) | 机种词表、别名、扩展名、显示名 |
| [`common/http-api.md`](common/http-api.md) | HTTP 端点总表与统一错误边界 |

## 计划

| 文档 | 管什么 |
|---|---|
| [`plans/cart-shell-todo.md`](plans/cart-shell-todo.md) | 各机种封面美化与游戏机壳完成清单（计划，非规格） |

## 统一结构

- `docs/modules/*.md` 开头写「职责 / 关键接口 / 依赖」三节。
- 其余小节按需使用：`数据与路径`、`行为与规则`、`边界与错误`、`测试要点`、`相关文档`。
- `docs/common/*.md` 至少写「职责 / 关键接口」。

## 写作约定

- 中文；一行一个事实，正文尽量不超过 80 汉字。
- 枚举用无序列表或表格；表格单元格尽量不超过 40 汉字。
- 不写机器相关绝对路径。
- 跨文件引用一律用相对路径链接。
- 每个事实只有一个权威出处，其他文档链接过去。
- 代码与文档冲突时以代码为准，并回来更新本文。
