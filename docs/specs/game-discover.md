# 游戏发现（检索与榜单）

## 范围与权威

- 页面是侧栏第 3 项「游戏发现」，路由 `/games/discover`。
- 旧路径 `/games/search` 重定向到这里，并保留 query。
- 页内是单选栏「游戏检索 / 游戏榜单」，标签写在 URL。
- 默认是检索；`?tab=ranking` 是榜单。
- 数据来自与平台游戏库无关的外部名录，页面与接口全只读。
- 索引写入方只有 `backend/games/search_index.py`。
- 检索读取方是 `search_service.py::GameSearchService`。
- 榜单读取方是 `ranking_service.py::GameRankingService`。
- 机种命名的唯一权威是 `backend/games/platforms.py` 的机种词表。
- 数据契约的权威是 `docs/data_dict.md` 的「游戏发现索引」。
- 榜单 CSV 的格式契约见 `backend/search/ranking/README.md`。
- 检索 CSV 的目录约定见 `backend/search/csv/README.md`。
- 前端页面是 `frontend/src/views/games/discover/index.vue`。

## 数据与路径

- 检索数据源是 `backend/search/csv/` 下的 37 个 CSV。
- 每行三列：`机种,中文,英文`；UTF-8 带 BOM、CRLF、无表头。
- 规模约 5 万余行、36 个机种。
- 按 `(机种,中文,英文)` 三元组去重：52,611 → 51,359 行。
- 只中文或只英文相同的行保留，那是不同地区版本。
- 检索侧同一机种的多个原始写法合并成一行 console。
- 合并结果：36 个原始机种 → 32 项（23 统一 + 9 未收录）。
- 榜单数据源是 `backend/search/ranking/ranking.csv`，四列。
- 榜单放单独目录；混进 `csv/` 会被当成坏行。
- 索引库路径是 `<STORAGE_ROOT>/db/game.db`（`GAME_INDEX_FILENAME`）。
- 索引在数据根里，与 `app.db` 无外键关系，是独立派生只读库。
- 索引刻意不参与备份，因为它可从 CSV 完整重建。
- 检索与榜单 CSV 随 `backend/` 进 api 镜像与 Windows 包；换数据要重建镜像。
- 表：`console`（统一机种）、`game`（名录行）、`game_fts`（FTS5）与 `ranking`。
- 另有 `meta` 存版本/指纹，`idx_game_console` / `idx_console_platform` 两个索引。
- 完整字段见 `../data_dict.md` 的「游戏发现索引」。

## 行为与规则

**写入路径与运行期只读。**

- 写入方只有 `search_index.py`，共两条写路径。
- 第一条是 `build_index()` 整库重建，`make index` 与服务启动共用。
- 服务启动入口是 `ensure_game_index()`：文件不存在就整库建一次。
- 文件存在但 `meta.schema_version` 与代码不符时也会整库重建一次。
- `TESTING` 下直接跳过；全程 best-effort，失败只记 warning、不拦启动。
- 手动入口：`make index` → `python -m backend.cli index` → `build_index()`。
- `--skip-ranking` 可以只重建检索。
- 第二条是 `ensure_ranking_loaded()`，启动时把榜单就地补进已存在的库。
- 构建一律整库重建 + 原子替换。
- 步骤：写同目录 `game.db.tmp` → `chmod 0644` → `os.replace()`。
- 可重复执行；**不开 WAL**，避免残留 `-wal`/`-shm` 与新主库错配。
- 重建后不用重启 api：旧连接读旧 inode，新请求自动拿新库。
- 宿主机与容器写同一个 bind 数据目录，宿主机 `make index` 容器立刻能读到。
- 运行期读经 `GameSearchService` 与 `GameRankingService`。
- 打开方式是 `Path.as_uri()` + `?mode=ro` + `PRAGMA query_only=1`。
- 每请求一条短连接，用完即关；运行期绝不写它。
- 索引缺失时返回 `indexed:false` + 空列表，不报错；接口永不建索引。

**机种归一与分词。**

- 两份 CSV 的机种列都是自由文本，建库时经词表解析成统一机种。
- 统一机种 id 就是 EmulatorJS 的 system key。
- 例：`任天堂GB` 与 `任天堂GBC` 都落到 `gb`；`SEGA CD` 与 `世嘉cd游戏` 都落到 `segaCD`。
- 认不出机种时保留原文，`platform_id` 留空，归为「未收录」。
- 检索侧合并 console，下拉不会出现两个同名项。
- 选「任天堂 GB/GBC」一次覆盖 GB 与 GBC 的全部条目。
- `tests/test_platforms.py` 拿真实 CSV 钉住解析；加机种只改词表别名。
- FTS5 用 `unicode61 remove_diacritics 2`，汉字逐字拆成独立 token。
- 裸 `unicode61` 会把整串中文当一个 token；`trigram` 少于 3 字全废。
- `search_text.py` 的 `index_text()` 是索引期与查询期共用的唯一实现。
- 任一处漏调中文归一化，中文就静默搜不到。
- 查询把词包成短语、词间用 AND，顺带做 NFKC。
- 英文按整词索引，缩写 `ff vii` 搜不到；不做拼音、错别字或中英互搜。
- 中文为空的约 2,632 行只能靠英文搜到。

**结尾标签与去重。**

- `(Japan)`、`(En,Ja)`、`(Rev A)`、`[a1]`、`（日版）`、`[PS2]` 等结尾标签不进索引。
- 建库时由 `strip_tags()` 剥掉；落库与展示仍是原文。
- 名录里 76% 的英文名、38% 的中文名带这种后缀。
- 不剥的话搜 `japan` 会命中一万多条。
- 整串都是标签的行回退成保留原串。
- 去重只在三元组完全一致时发生，跨源文件生效。

**检索 SQL 硬约束。**

- FTS 表不能起别名：`FROM game_fts f … WHERE f MATCH ?` 报 `no such column: f`。
- `MATCH` 与 `bm25()` 只认真表名。
- `bm25()` 权重顺序等于 FTS 列顺序：`zh_uni` 8.0，`en_uni` 1.0。
- `ORDER BY bm25(...)` 是升序（返回负值，越小越相关）。
- 不能用 `COUNT(*) OVER ()` 配 bm25 排序；total 单独走第二条 `count(*)`。
- `ORDER BY` 末尾必须有 `g.id` 兜排序，否则翻页会重复或丢行。
- 机种过滤按有无拼 `AND g.console_id = :cid` 片段。
- 不写 `:cid IS NULL OR …`，OR 会让 SQLite 放弃 `idx_game_console`。
- 无关键词时不做 MATCH，走 `ORDER BY g.console_id, g.en, g.id` 全量分页。
- `game_fts` 是 contentless 表，`snippet()`/`highlight()` 返回 NULL。
- 高亮只能在前端做：把命中片段切成数组渲染 `<mark>`，不用 `v-html`。

**榜单 CSV 与落库。**

- 四列固定：`序号,机种名称,游戏名称,游戏卡带ID`。
- 表头可有可无；首行第一格是 `序号` 或 `排名` 就跳过。
- 序号是正整数，同一机种内唯一；重复报错。
- 页面按序号升序展示并原样显示，不重排。
- 机种名称非空，建库时经词表归一成机种键，`GBA` 与 `gba` 自然合并。
- 卡带 ID 每行 0~2 个，用 `;` 分隔，也兼容 `、` `,` `，` `/` `；`。
- 空格、连字符、下划线不是分隔符，因为卡带 ID 里常有空格。
- 卡带 ID 可以为空，第 4 列可整列省掉；超过 2 个被拒绝。
- 空行跳过，Excel 行尾多余空列裁掉；空文件或只有表头算错误。
- 解析错误消息必须带文件名与行号。
- 落库单表 `ranking(platform, console, rank, title, cartridge_ids)`。
- 主键 `(platform, rank)` 且 `WITHOUT ROWID`。
- `platform` 是归一机种键，认不出时写 `raw:{归一后的原文}`。
- `console` 留 CSV 原文供溯源；`cartridge_ids` 存 JSON 数组文本。
- 机种存文本而非外键，因为榜单机种未必出现在检索名录里。
- meta 记 `ranking_schema_version`，独立于检索 `SCHEMA_VERSION`，不 bump 它。
- 加榜单表是纯新增，老库要继续能检索；补载失败也不能让检索 503。
- meta 还记 `ranking_fingerprint`、`ranking_source`、`ranking_rows` 等。
- 指纹是 CSV 原始字节 SHA-256，只有成功加载后才写。
- 用指纹而非 size+mtime，因为 `touch`/`git checkout` 会改 mtime 但内容不变。

**榜单就地补载。**

- `ensure_ranking_loaded()` 先用只读连接比对指纹。
- 一致就直接返回，连读写连接都不打开。
- 需要更新时先 `PRAGMA journal_mode = DELETE`，再 `BEGIN IMMEDIATE`。
- 事务内二次比对指纹，然后 DROP 旧表、建表、全量插入、upsert meta。
- 成功后 commit；异常 rollback，旧榜单原封不动。
- CSV 缺失时保留库里已有榜单，不删不改。
- 启动加载是 best-effort，失败只记 warning。

**榜单与平台库存的关联。**

- 关联只在请求期做，只读；不落库、不进索引、不缓存。
- 榜单行任意一个卡带 ID 命中库存即算关联。
- 一行最多 2 个 ID，命中多个时取该行第一个命中的。
- 比对是 `normalize_cartridge_id()`：去首尾空白 + 转大写。
- 绝不能复用会抛错的 `validate_cartridge_id()`。
- 后者遇到 `Part No. 7004 0894` 这类原文会抛错，把只读接口打挂。
- 只认 `game_path != ""` 的条目，与中心列表、最近游玩同口径。
- 不校验机种；卡带 ID 是「同一盘卡带」的全局身份。
- 榜单的 `platform` 还有 `raw:3ds` 这类永远等不上 `game_type` 的值。
- 命中行多 `game_id` 与 `path`；`path` 由 `service.play_path()` 按类型给。
- `path` 与 `GameItem.path` 同一实现；没命中时两个字段都是 `null`。
- `GameRankingService` 构造函数注入窄回调 `cartridge_lookup`。
- 整份榜单的卡带 ID 一次性交给它，不是逐行查。
- 一个机种最多 100 行 × 2 个 ID = ≤200 个宿主参数，所以不分块。
- 命中结果用 `dataclasses.replace` 附到 `RankingItem` 上。
- 增删游戏立刻生效，不需要 `make index`，也不用重启。
- 代价是每次打开/切换榜单多一条走 `uq_games_cartridge_id` 的小查询。
- 榜单页内翻页不查，因为榜单是一次全取的。

**接口。**

- `GET /api/games/search`：`q` / `console_id` / `page` / `page_size`，需登录、服务端分页。
- 参数越界在 service 收敛，不放 `Query(ge=,le=)`（422 会绕开统一错误信封）。
- `GET /api/games/search/consoles`：每项 `{id, name, platform_id}`。
- `name` 是统一显示名；`platform_id` 是机种键；未收录为 `null`。
- `GET /api/games/search/ranking?console=`：需登录，不分页。
- `console` 传机种键，回显也是机种键。
- `GET /api/games/search/ranking/consoles`：返回机种清单与 `default_console`。
- 榜单机种项是 `{platform, label, playable}`。
- 路由挂在 `/api/games/search/` 下，避免与未来单段 `/{game_id}` 撞车。

**前端交互。**

- 一个组件装两个标签；检索区状态在切标签时保留。
- 榜单区第一次切到榜单标签才请求，用 `rankingLoaded` 标记。
- 标签栏是一对普通按钮，只能点；不用 `el-radio-group` / `el-segmented`。
- 原因是原生 radio 焦点在里面时，左右键会换选中项，抢走分页条的键。
- 检索区：关键词 300ms 防抖 + 回车即搜、机种下拉、三列表格、服务端分页。
- 用请求序号丢弃过期响应。
- 榜单工具栏 = 机种下拉 + 搜索框 + 紧挨其右的「已入库比例」按钮。
- 按钮不推到最右，不用 `margin-left: auto`。
- 榜单搜索与分页全在前端，因为一个机种整份取回。
- 搜索是对游戏名称做不区分大小写的裸子串匹配，逐字即时、无防抖无高亮。
- 不认 FTS 语法，`mario*` 的星号是普通字符；不做 NFKC，也不剥尾部标签。
- 榜单关键词与检索区 `keyword` 是两个独立 ref，语义不同、别合并。
- 「已入库 N / M」由前端按整份 `rankingItems` 现算。
- 分子是 `path` 非空的行数，分母是该机种榜单总行数。
- 按钮单击即按下：实心主色 + `aria-pressed`，再点恢复全部。
- 它同时是「只看已入库」的开关；榜单只展示已入库的行。
- 按钮上的比例恒按整份榜单算，不随搜索与过滤变。
- 两个条件的关系是 AND：`rankingKeywordMatches` → `rankingVisibleItems`。
- 表格与分页条按过滤后的行数算；任一条件变化页码回第一页。
- 命中库存的行，游戏名渲染成真 `<a href>`：`<router-link :to="item.path">`。
- 不加 `@click`，也不加 `custom`，否则 Ctrl/中键开新标签页就废了。
- 卡带 ID 是并排可点按钮，点击复制。
- 复制复用 `utils/clipboard.js` 的 `writeClipboard()`；不用 `title` / `el-tooltip`。
- 榜单默认机种是 FC（`nes`）；没有就取词表最靠前，未收录排最后。
- 空态按「谁清空的」分流：关键词、关键词+已入库、只有已入库。

## 边界与错误

- 索引缺失：`indexed:false` + 空列表，HTTP 200，不是错误。
- 页面给「执行 make index」的中文引导。
- 文件在但打不开或版本不符：503 + 中文提示（`IndexUnavailableError`）。
- 榜单未加载：`has_ranking:false` + 空列表，HTTP 200，不是错误。
- 只有 `meta.ranking_schema_version` 存在但不匹配才 503。
- `ranking` 表、版本、指纹三者都在才算 `has_ranking:true`。
- 请求的机种不在榜单里：回显请求值 + 空列表。
- 接口永不建索引；只有 `search_index.py` 的两条写路径会建。
- 自动补建失败只记 warning，页面显示「尚未构建索引」。
- 数据根被 Docker 以 root 建过时，宿主机用户写不进去。
- 此时自动补建失败、`make index` 也失败。
- `make index` 先 `test -w` 预检并提示 `sudo chown -R "$USER" "$STORAGE_HOST_DIR"`。
- 容器里跑的是 root，不受这个权限问题影响。
- 坏库不会自愈，要重跑 `make index`。
- 服务端只提供 `/api/` 与 `/health`，没有服务端渲染页面。

## 测试要点

- `tests/test_platforms.py`：用真实 CSV 钉住机种解析与未收录名单。
- `tests/test_game_search.py`：分词、查询边界、去重、分页稳定性。
- 还覆盖版本过旧 503、坏库 503、运行期不写索引、只读权限。
- `tests/test_game_ranking.py`：榜单 CSV 解析与坏行报错。
- 还覆盖缺省表头、空卡带 ID、非 UTF-8、榜单目录必须独立。
- 还覆盖整库重建、指纹幂等、内容变化重载、CSV 缺失保留旧榜。
- 还覆盖启动加载、榜单未加载、版本过旧 503、运行期不写索引。
- 库存关联覆盖：命中、按类型给 path、第二个 ID 命中、大小写不敏感。
- 关联还覆盖：非法 ID 不抛错、无本体不关联、删游戏后立刻断开。

## 相关文档

- [前端框架与交互](./frontend.md)
- [架构设计](../architecture.md)
- [数据字典](../data_dict.md)
- [检索名录说明](../../backend/search/csv/README.md)
- [榜单 CSV 说明](../../backend/search/ranking/README.md)
