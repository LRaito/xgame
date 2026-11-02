# 游戏检索的 CSV 名录

这里的 37 个 CSV 是「游戏检索」页的数据源：3 列、无表头、`机种,中文,英文`，UTF-8 带 BOM、CRLF。

- **只被建索引读**（`backend/games/search_index.py`，两个入口：服务启动时的自动补建与
  `make index`），代码不 `import` 这个目录，运行期的检索接口只读构建好的 `<数据根>/db/game.db`。
- 这个目录**随 `backend/` 一起进 api 镜像**，所以宿主机上的 `make index` 与容器里的
  启动自动补建都能用到它。
- 目录里只放数据：不要加 `.py`（没有 `__init__.py` 时 Python 会把它当 namespace package）。
- **游戏榜单的 CSV 不在这个目录**：它是四列、放在旁边的 `../ranking/ranking.csv`。这个目录会被
  整目录扫成检索索引，四列的榜单混进来会被当成坏行。
- 数据来自外部整理的中英文对照表，行数/机种数变了不用改代码，重跑 `make index` 覆盖索引即可
  （镜像里换数据要重建镜像）。
- **第一列的机种名会被解析成统一机种**（`backend/games/platforms.py` 的词表，机种 id 就是
  EmulatorJS 的 system key）：`任天堂GB` 与 `任天堂GBC` 都落到 `gb`，页面上合并成一项
  「任天堂 GB/GBC」展示。**加了新的机种写法**（改了列里的名字）要去那张表补一条别名，
  否则它会以原文单独出现、并被归为「未收录」——`tests/test_platforms.py` 会拿这份数据提醒你。
- 索引构建、只读连接与分词规则见
  [`docs/specs/game-discover.md`](../../../docs/specs/game-discover.md)。
