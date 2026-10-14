# 游戏检索的 CSV 名录

这里的 37 个 CSV 是「游戏检索」页的数据源：3 列、无表头、`机种,中文,英文`，UTF-8 带 BOM、CRLF。

- **只被 `make index` 读**（`backend/cli.py` 的 `index` 命令 → `backend/games/search_index.py`），
  代码不 `import` 这个目录，运行期的检索接口只读构建好的 `<数据根>/db/game.db`。
- 这个目录刻意**不进 Docker 镜像**（根目录 `.dockerignore` 里排除了 `backend/search/csv`），
  所以 `make index` 只能在宿主机跑。
- 目录里只放数据：不要加 `.py`（没有 `__init__.py` 时 Python 会把它当 namespace package）。
- 数据来自外部整理的中英文对照表，行数/机种数变了不用改代码，重跑 `make index` 即可。
