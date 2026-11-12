# 游戏发现（游戏名录与游戏榜单）

本文件回答：游戏名录与游戏榜单的数据从哪来、如何查询。

## 范围与权威

- 页面是侧栏第 3 项「游戏发现」，路由 `/games/discover`。
- 旧路径 `/games/search` 重定向到这里，并保留 query。
- 页内是单选栏「游戏名录 / 游戏榜单」，标签写在 URL。
- 默认是游戏名录；`?tab=ranking` 是游戏榜单。
- 数据来自与平台游戏库无关的外部名录，页面与接口全只读。
- 索引写入方只有 `backend/games/search_index.py`。
- 游戏名录读取方是 `search_service.py::GameSearchService`。
- 游戏榜单读取方是 `ranking_service.py::GameRankingService`。
- 机种命名的唯一权威是 `backend/games/platforms.py` 的机种词表。
- 数据契约的权威是 `docs/data_dict.md` 的「游戏发现索引」。
- 游戏榜单 CSV 的格式契约见 `backend/search/rankings/README.md`。
- 游戏名录 CSV 的目录约定见 `backend/search/catalog/README.md`。
- 前端页面是 `frontend/src/views/games/discover/index.vue`。

## 职责

- 从外部名录 CSV 与榜单 CSV 构建只读索引库。
- 提供游戏名录的中英文全文检索与机种筛选。
- 提供按机种或跨机种的游戏榜单，并把榜单条目关联到库存卡带。

## 关键接口

- `GET /api/games/search`、`GET /api/games/search/consoles`。
- `GET /api/games/search/ranking`、`GET /api/games/search/ranking/consoles`。
- 构建入口：`backend/games/search_index.py`；查询：`search_service.py`、`ranking_service.py`。

## 依赖

- `<运行时根>/db/game.db` 与 SQLite FTS5。
- `backend/search/catalog/` 的 37 个名录 CSV 与 `backend/search/rankings/` 的 34 个机种榜单 CSV。
- `make index`；服务启动只建空结构，不写数据。

## 数据与路径

- 游戏名录数据源是 `backend/search/catalog/` 下的 37 个 CSV。
- 每行两列：`中文名,英文名`；首行是表头，UTF-8 带 BOM、CRLF。
- 机种由文件名决定，经 `platforms.SEARCH_CSV_CONSOLE_NAMES` 映射回机种名。
- 规模约 5 万余行、36 个机种。
- 按 `(机种原始名,中文,英文)` 三元组去重：52,611 → 51,359 行。
- 只中文或只英文相同的行保留，那是不同地区版本。
- 名录侧同一机种的多个原始写法合并成一行 console。
- 合并结果：36 个原始机种 → 32 项（23 统一 + 9 未收录）。
- 游戏榜单数据源是 `backend/search/rankings/`，每个机种一个四列 CSV
  （`中文名,英文名,评分,卡带ID`），机种由文件名（机种 id）决定。
- 榜单放单独目录；混进 `catalog/` 会被当成坏行。
- 索引库路径是 `<RUNTIME_ROOT>/db/game.db`（`GAME_INDEX_FILENAME`）。
- 索引在运行时根里，与 `app.db` 无外键关系，是独立派生只读库。
- 索引刻意不参与备份，因为它可从 CSV 完整重建。
- 游戏名录与游戏榜单 CSV 随 `backend/` 进 api 镜像与 Windows 包；换数据要重建镜像。
- 表：`console`（统一机种）、`game`（名录行）、`game_fts`（FTS5）、`ranking` 与
  `ranking_cartridges`（卡带 ID → 榜单行）。
- 另有 `meta` 存版本/指纹，`idx_game_console` / `idx_console_platform` 两个索引。
- 完整字段见 `../data_dict.md` 的「游戏发现索引」。

## 行为与规则

**写入路径与运行期只读。**

- 游戏名录与游戏榜单数据**只能由人工执行 `make index` 写入**；服务启动只建空的 game.db 结构，
  不写数据、不重载、不重建。已有表的 game.db 启动时一律不碰。
- game.db 的**结构**只由启动初始化（仅限新项目）或 `make upgrade` 改变。
- `make index` 执行前校验结构版本与索引；缺失/过旧直接报错并提示 `make upgrade`，
  它不建表、不改索引、不迁移结构。
- 写入方是 `search_index.py` 的 `build_index()`：每次全量构建游戏名录、游戏榜单与映射表。
- 运行期只读：`GameSearchService` / `GameRankingService` 一律 `mode=ro`。
- 例外是 `ranking_flags.py`：只对 `ranking.in_library` 做短事务 UPDATE，不重建榜单。
- 手动入口：`make index` → `python -m backend.cli index` → `build_index()`。
- 没有 `--skip-ranking`；每次都会同时构建游戏名录与游戏榜单，并在成功后全量同步两边标记。
- 构建一律整库重写数据 + 原子替换；结构由启动/升级保证，构建函数不负责迁移。
- 步骤：写同目录 `game.db.tmp` → `chmod 0644` → `os.replace()`。
- 可重复执行；**不开 WAL**，避免残留 `-wal`/`-shm` 与新主库错配。
- 重建后不用重启 api：旧连接读旧 inode，新请求自动拿新库。
- 宿主机与容器写同一个 bind 运行时目录，宿主机 `make index` 容器立刻能读到。
- 运行期读经 `GameSearchService` 与 `GameRankingService`。
- 打开方式是 `Path.as_uri()` + `?mode=ro` + `PRAGMA query_only=1`。
- 每请求一条短连接，用完即关；运行期除标记外不写它。
- 索引缺失时返回 `indexed:false` + 空列表，不报错；接口永不建索引。
**机种归一与分词。**

- 两份 CSV 的机种列都是自由文本，建库时经词表解析成统一机种。
- 统一机种 id 就是 EmulatorJS 的 system key。
- 例：`任天堂GB` 与 `任天堂GBC` 都落到 `gb`；`SEGA CD` 与 `世嘉cd游戏` 都落到 `segaCD`。
- 认不出机种时保留原文，`platform_id` 留空，归为「未收录」。
- 未收录机种的显示名同样补厂商名后的空格，如 `任天堂3DS` → `任天堂 3DS`；
  名字里没有厂商的（`3DS`、`CD-I`）在词表的未收录显示名表里统一为 `任天堂 3DS`、`飞利浦 CD-i`。
- 名录侧合并 console，下拉不会出现两个同名项。
- 选「任天堂 GB/GBC」一次覆盖 GB 与 GBC 的全部条目。
- `tests/test_platforms.py` 拿真实 CSV 钉住解析；加机种只改词表别名。
- FTS5 用 `unicode61 remove_diacritics 2`，汉字逐字拆成独立 token。
- 裸 `unicode61` 会把整串中文当一个 token；`trigram` 少于 3 字全废。
- `search_text.py` 的 `index_text()` 是索引期与查询期共用的唯一实现。
- 任一处漏调中文归一化，中文就静默搜不到。
- 查询把词包成短语、词间用 AND，顺带做 NFKC。
- 英文按整词索引，缩写 `ff vii` 搜不到；不做拼音、错别字或中英互搜。
- 去重后共 51,359 行，其中中文为空的 2,623 行只能靠英文搜到。

**结尾标签与去重。**

- `(Japan)`、`(En,Ja)`、`(Rev A)`、`[a1]`、`（日版）`、`[PS2]` 等结尾标签不进索引。
- 建库时由 `strip_tags()` 剥掉；落库与展示仍是原文。
- 名录里 76% 的英文名、38% 的中文名带这种后缀。
- 不剥的话搜 `japan` 会命中一万多条。
- 整串都是标签的行回退成保留原串。
- 去重只在三元组完全一致时发生，跨源文件生效。

**游戏名录 SQL 硬约束。**

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

- 每个机种一个四列 CSV，文件名 stem 就是机种 id（`nes.csv`、`segaMD.csv`…）。
- 四列固定：`中文名,英文名,评分,卡带ID`。
- 中文名可空（查不到译名就留空，页面显示 `—`）；英文名非空，**同一机种内唯一**。
  两者都去掉地区/修订/语言标注（区分版本的标题括号保留）。
- 评分非空，是普通十进制数字（MobyGames 原始 double），落库为 `REAL`；
  页面固定显示两位小数并四舍五入，后端不做格式化。
- 表头可有可无；首行恰好是四列表头时跳过。
- 卡带 ID 每行 0~2 个，用 `;` 分隔，也兼容 `、` `,` `，` `/` `；`。
- 空格、连字符、下划线不是分隔符，因为卡带 ID 里常有空格。
- 卡带 ID 可以为空，第 4 列可整列省掉；超过 2 个被拒绝。
- 空行跳过，Excel 行尾多余空列裁掉；只有表头的文件跳过，所有文件都没有数据行才算错误。
- 同一机种内英文名重复时，解析会收集全部冲突行（文件名、行号、标题）并报错。
- 解析错误消息必须带文件名与行号。
- 落库 `ranking(id, platform, console, score, zh, en, cartridge_ids, in_library)`。
- `id` 是自增主键，只用于数据库身份与同分稳定排序，不展示。
- `platform` 是机种 id；`console` 留文件名 stem 供溯源；`cartridge_ids` 存 JSON 数组文本。
- 机种存文本而非外键，因为榜单机种未必出现在游戏名录里。
- 另建 `ranking_cartridges(cartridge_id 主键, ranking_id 外键)`：
  - 卡带 ID 归一（去空白 + 转大写）后写入；
  - 同一行内重复的卡带 ID 去重；
  - 同一卡带 ID 出现在多行时，`make index` 直接报错并列出冲突 ID。
- 索引：
  - `uq_ranking_platform_en(platform, en)` 唯一索引：同一机种内英文名唯一。
  - `idx_ranking_score(score DESC)`：跨机种 `ORDER BY score DESC, id`；主键 id 自动附带。
  - `idx_ranking_platform_score(platform, score DESC)`：单机种
    `WHERE platform = ? ORDER BY score DESC, id`。
  - `idx_ranking_in_library_score(in_library, score DESC)`、
    `idx_ranking_platform_in_library_score(platform, in_library, score DESC)`：
    库存三态筛选后的排序。
  - `idx_ranking_cartridges_ranking(ranking_id)`：反向查一行榜单的卡带 ID。
- meta 记 `ranking_schema_version`，独立于游戏名录的 `SCHEMA_VERSION`，不 bump 它。
- meta 还记 `ranking_fingerprint`、`ranking_source`、`ranking_rows` 等。
- 指纹覆盖目录里所有 CSV 的「文件名 + 原始字节」SHA-256，只有成功加载后才写。
- 用指纹而非 size+mtime，因为 `touch`/`git checkout` 会改 mtime 但内容不变。

**榜单与平台库存的标记。**

- `ranking.in_library` 表示该行是否命中库存；`games.in_ranking` 表示库存行是否命中榜单。
- 判定只看 `games` 行是否存在，不检查本体：无本体条目也算库存之内。
- 一行榜单最多 2 个卡带 ID，任意一个命中即 `in_library=1`。
- 更新时机：
  1. `make index`：全量对账两个标记；
  2. 添加游戏：按卡带 ID 查映射，设置 `games.in_ranking` 并重算对应榜单行；
  3. 编辑卡带 ID：同时重算旧 ID 与新 ID 对应的榜单行；
  4. 删除游戏：重算旧 ID 对应的榜单行。
- 增量更新只做短事务 UPDATE；game.db 缺失/过旧/写锁时只记 warning，不阻断游戏操作。
- 查询只对当前页做库存关联：用 `map_for_cartridge_ids()` 给每盘卡带补
  `game_id` / `path` / `has_body`，再用 `map_for_games()` 按**当前登录用户**批量取进度；
  标记本身负责筛选与计数，不再全量关联。
- 每行最多 2 个卡带，逐盘独立关联：同一行可以一个在库、一个不在库。
- 在库但没有统计行按 `not_started`；不在库的卡带 `progress` 为 `null`。
- `path` 与 `GameItem.path` 同一实现；没命中时 `game_id` / `path` / `progress` 都是 `null`。

**接口。**

- `GET /api/games/search`：`q` / `console_id` / `page` / `page_size`，需登录、服务端分页。
- 参数越界在 service 收敛，不放 `Query(ge=,le=)`（422 会绕开统一错误信封）。
- `GET /api/games/search/consoles`：每项 `{id, name, platform_id}`。
- `name` 是统一显示名；`platform_id` 是机种键；未收录为 `null`。
- `GET /api/games/search/ranking`：需登录、服务端分页。
  - 参数：`console`、`keyword`、`in_library`、`page`、`page_size`。
  - `in_library` 是三态：省略 = 全部；`true` = 库存之内；`false` = 库存之外。
  - `page_size` 默认 10、上限 100；`page` 越界钳到最后一页。
- item 是 `{score, zh, en, platform, cartridges}`；**没有 rank**，也没有行级
  `in_library` / `cartridge_ids` / `game_id` / `path` / `has_body`。
- `cartridges` 每项是 `{game_id, cartridge_id, in_library, progress, path, has_body}`：
  一行最多两个，逐盘给出是否在库、播放路径、有无本体与当前用户进度。
- `progress` 取 `not_started` / `in_progress` / `completed`；不在库为 `null`。
- `score` 是原始 double；前端固定两位小数展示，四舍五入。
- `console` 传机种键，回显也是机种键；**不传则跨机种**，回显 `null`。
- 跨机种按评分全局降序；单机种按该类型内评分降序；同分按自增 id 稳定排序。
- 响应计数：
  - `total`：应用 `keyword` + `in_library` 后、分页用的总数。
  - `matched_total`：应用 `keyword`、未应用 `in_library` 的总数。
  - 不再返回 `ranking_total` / `linked_total`。
- `GET /api/games/search/ranking/consoles`：返回机种清单。
- 榜单机种项是 `{platform, label, playable}`。
- 路由挂在 `/api/games/search/` 下，避免与未来单段 `/{game_id}` 撞车。

**前端交互。**

- 一个组件装两个标签；名录区状态在切标签时保留。
- 榜单区第一次切到榜单标签才请求，用 `rankingLoaded` 标记。
- 标签栏是一对普通按钮，只能点；不用 `el-radio-group` / `el-segmented`。
- 原因是原生 radio 焦点在里面时，左右键会换选中项，抢走分页条的键。
- 名录区：关键词 300ms 防抖 + 回车即搜、机种下拉、三列表格、服务端分页。
- 榜单区同样是服务端分页：只保存当前页 items 与后端计数。
- 用请求序号丢弃过期响应。
- 榜单工具栏 = 机种下拉 + 搜索框 + 紧挨其右的「库存类型」下拉。
- 「库存类型」选项：库存之内 / 库存之外，默认不选（全部）；用通用 `AppSelect`。
- 下拉不推到最右，不用 `margin-left: auto`。
- 机种下拉**可清空**：清空即跨机种，表格多一列「游戏类型」；选中机种时不显示该列。
- 排名不落库：`rank = (page - 1) × page_size + 页内序号 + 1`。
- 榜单列顺序：序号、评分、[游戏类型]、中文名、英文名、卡带 ID。
- 评分由 `formatRankingScore()` 用 `toFixed(2)` 四舍五入；中文名为空时显示 `—`。
- 榜单搜索走后端：输入 300ms 防抖，回车立即请求；清空、换机种、改库存类型都回第 1 页。
- 搜索是对中文名/英文名做 SQL `LIKE` 子串匹配，无高亮；`%` / `_` / `\` 按字面处理。
- 不认 FTS 语法，`mario*` 的星号是普通字符；不做 NFKC，也不剥尾部标签。
- 榜单关键词与名录区 `keyword` 是两个独立 ref，语义不同、别合并。
- 库存类型不再显示「已入库 N / M」按钮，也不请求任何比例计数。
- 分页条 `:total` 用 `total`；翻页触发 `loadRanking()`。
- 空态用 `matched_total` / `total` / 库存类型区分「没有匹配」与「所选库存范围为空」。
- 命中库存的榜单行，中英文名保持纯文本，只保留截断展开；不再做跳转链接。
- 卡带 ID 是按钮列：固定列宽、每个按钮固定占整列 1/2（用 grid 两等分），
  白底描边，文字与边框按进度着色。
- 配色与游戏中心一致：未开始蓝（`--brand-accent`）、进行中紫
  （`--app-color-in-progress`）、已通关绿（`--app-color-success`）、不在库灰（`--text-muted`）。
- 卡带按钮点击：
  - 在库且有本体：直接进播放页（用后端返回的 `path`）；
  - 在库但无本体：提示「请先上传游戏本体」；
  - 不在库：打开与游戏管理页共用的添加游戏弹框，预填名称（中文名，空则英文名）、
    被点卡带的 ID、以及该机种可玩时的游戏类型；保存后留在榜单页并刷新当前页。
- 卡带按钮行高仍与其它行一致（40px）：按钮 28px，卡带格上下内边距各 6px。
- 卡带 ID 最长 15 字符（见 `backend/search/rankings/`），窄屏超出时省略显示，完整值在 `title` 里。
- 页面默认不选类型，首次请求就不传 `console`，直接看跨机种榜单；选中类型后只取该类型。
- 行 key 用 `platform + rank`；rank 由当前页位置计算，单页内唯一。

## 边界与错误

- 索引缺失：`indexed:false` + 空列表，HTTP 200，不是错误。
- 页面给「执行 make index」的中文引导。
- 文件在但打不开或版本不符：503 + 中文提示（`IndexUnavailableError`）。
- 榜单未加载：`has_ranking:false` + 空列表，HTTP 200，不是错误。
- 只有 `meta.ranking_schema_version` 存在但不匹配才 503。
- `ranking` 表、版本、指纹三者都在才算 `has_ranking:true`。
- 请求的机种不在榜单里：回显请求值 + 空列表。
- 接口永不建索引；服务启动只建空结构，数据只有人工 `make index` 会写。
- 榜单结构版本过旧：`make upgrade` 做 game.db 结构迁移；数据/标记仍要 `make index`。
- 重复卡带 ID 会让 `make upgrade` 的映射迁移和 `make index` 都报错，需先修 CSV。
- 运行时根被 Docker 以 root 建过时，宿主机用户写不进去。
- 此时 `make index` 失败；命令会提示 `sudo chown -R "$USER" "$RUNTIME_HOST_DIR"`。
- 容器里跑的是 root，不受这个权限问题影响。
- 坏库不会自愈，要重跑 `make index`。
- Docker/API 路线服务端只提供 `/api/` 与 `/health`，没有服务端渲染页面；
  Windows 包设 `STATIC_DIR` 时由 `static_site.py` 额外托管前端。

## 测试要点

- `tests/test_platforms.py`：用真实 CSV 钉住机种解析与未收录名单。
- `tests/test_game_search.py`：分词、查询边界、去重、分页稳定性。
- 还覆盖版本过旧 503、坏库 503、运行期不写索引、只读权限。
- 还覆盖「启动建空 game.db 但不写数据」。
- `tests/test_game_ranking.py`：榜单目录解析与坏行报错。
- 还覆盖缺省表头、空卡带 ID、非 UTF-8、榜单目录必须独立。
- 还覆盖 v7 结构、映射表、重复卡带 ID 报错、库存/榜单三态筛选与 SQL 分页。
- 还覆盖只对当前页做库存关联、关键词 `%` / `_` 转义。
- 还覆盖逐卡带库存/进度：无统计行按未开始、按用户隔离、进度查询只调一次。
- `tests/test_ranking_flags.py`：全量双向对账、双 ID 行重算、API 增删改标记、缺列报错。
- 库存关联覆盖：命中、按类型给 path、第二个 ID 命中、大小写不敏感、无本体也算库存之内。

## 相关文档

- [前端框架与交互](./frontend.md)
- [架构设计](../architecture.md)
- [数据字典](../data_dict.md)
- [游戏名录说明](../../backend/search/catalog/README.md)
- [榜单 CSV 说明](../../backend/search/rankings/README.md)
