# 游戏检索的 CSV 名录

这里的 37 个 CSV 是「游戏检索」页的数据源：2 列、首行表头 `中文名,英文名`，UTF-8 带 BOM、CRLF。
**机种由文件名决定**，不再写在每一行里；表头只占一行，建索引时跳过，不计入游戏。

- **只被建索引读**（`backend/games/search_index.py`，两个入口：服务启动时的自动补建与
  `make index`），代码不 `import` 这个目录，运行期的检索接口只读构建好的 `<数据根>/db/game.db`。
- 这个目录**随 `backend/` 一起进 api 镜像**，所以宿主机上的 `make index` 与容器里的
  启动自动补建都能用到它。
- 目录里只放数据：不要加 `.py`（没有 `__init__.py` 时 Python 会把它当 namespace package）。
- **游戏榜单的 CSV 不在这个目录**：它在旁边的 `../rankings/`，每个机种一个四列 CSV。这个目录会被
  整目录扫成检索索引，榜单行混进来会被当成坏行。
- 数据来自外部整理的中英文对照表，行数/机种数变了不用改代码，重跑 `make index` 覆盖索引即可
  （镜像里换数据要重建镜像）。
- **文件名 stem 经 `backend/games/platforms.py::SEARCH_CSV_CONSOLE_NAMES` 映射回机种名**
  （机种 id 就是 EmulatorJS 的 system key）：`gb.csv` → `任天堂GB`、`gbc.csv` → `任天堂GBC`，
  两者在页面上合并成一项「任天堂 GB/GBC」；`ps2-jp.csv` 与 `ps2-us.csv` 都映射到 `索尼PS2`，
  所以两份文件之间的同款游戏仍会跨文件去重。
- **新增/改名文件必须同步登记映射表**，否则该文件会以文件名 stem 单独出现、并被归为「未收录」；
  `tests/test_platforms.py` 会检查真实目录与映射表一一对应。
- 索引构建、只读连接与分词规则见
  [`docs/modules/game-discover.md`](../../../docs/modules/game-discover.md)。
