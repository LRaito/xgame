# 功能规格索引

本目录放各功能的实现规格：数据、路径、行为、边界与测试要点。

- 核心文档只留结论与链接。
- 每个事实只有一个权威出处。
- 代码与文档冲突时以代码为准，并回来更新本文。

## 阅读路径

1. 先读 [`../architecture.md`](../architecture.md) 了解整体设计。
2. 读 [`../../AGENTS.md`](../../AGENTS.md) 了解编码约定。
3. 按功能查下面的规格。

## 规格清单

| 规格 | 管什么 |
|---|---|
| [`api.md`](api.md) | HTTP 端点总表 |
| [`auth.md`](auth.md) | 注册、登录、锁定、session、CSRF |
| [`platforms.md`](platforms.md) | 机种词表、别名、扩展名、显示名 |
| [`game-storage.md`](game-storage.md) | 两个根、路径、卡带 ID、封面类型、导入 |
| [`game-center-playback.md`](game-center-playback.md) | 三类播放器、标题栏、机壳、NDS、快捷键 |
| [`game-assets.md`](game-assets.md) | 截图、图集、封面美化、素材几何 |
| [`game-saves-stats.md`](game-saves-stats.md) | 云端存档、设置同步、最近游玩、统计 |
| [`guide-and-h5.md`](guide-and-h5.md) | H5 与攻略包的校验、解包、读取 |
| [`game-discover.md`](game-discover.md) | 检索索引、FTS、SQL、榜单、库存关联 |
| [`frontend.md`](frontend.md) | 路由、api 层、组件、界面交互 |
| [`delivery-docker.md`](delivery-docker.md) | 镜像、compose、bind、备份、哨兵 |
| [`delivery-windows.md`](delivery-windows.md) | Windows 包构建、启动器、编码、升级 |

## 统一结构

每份规格按需使用这些二级标题：

- `## 范围与权威`
- `## 数据与路径`
- `## 行为与规则`
- `## 边界与错误`
- `## 测试要点`
- `## 相关文档`

## 写作约定

- 中文；一行一个事实，正文尽量 ≤80 汉字。
- 枚举用无序列表或表格；表格单元格尽量 ≤40 汉字。
- 不写机器相关绝对路径。
- 相对链接，不链接中文锚点。
- 详细数值、算法、字段表只出现在权威文件。

## 其他文档

- [`../data_dict.md`](../data_dict.md)：表结构与磁盘路径。
- [`../architecture.md`](../architecture.md)：设计决策。
- [`../../README.md`](../../README.md)：用户操作。
- [`../../DEVELOP.md`](../../DEVELOP.md)：开发与部署。
