# 存档、设置、最近游玩与统计

## 范围与权威

- 本规格覆盖云端存档快照、本地存档、存档管理弹框、模拟器设置同步、最近游玩与游玩统计。
- 后端权威在 `backend/games/save_service.py`、`save_router.py`、`sort_order.py`。
- 设置与统计权威在 `settings_service.py`、`settings_router.py`、`stats_service.py`、`stats_router.py`。
- 最近游玩权威在 `backend/games/service.py` 的 `mark_played()` 与 `list_recent()`。
- 前端权威在 `frontend/src/components/games/SaveManager.vue`、`SaveTreeView.vue`。
- 本地档与计时权威在 `frontend/src/utils/emulatorSaves.js`、`gamePlaytime.js`、`recentGames.js`。
- 播放页入口与快捷键见 [`./game-center-playback.md`](./game-center-playback.md)。

## 数据与路径

| 表 | 粒度 | 关键列 |
|---|---|---|
| `game_cloud_snapshots` | 每 (用户, 游戏) 一快照 | `parent_id`、`sort_order`、`remark` |
| `game_cloud_snapshot_files` | 快照内每个文件 | `local_key`、`name`、`file_path` |
| `game_emulator_settings` | 每 (用户, 平台) 一份 | `payload` JSON |
| `game_recent_plays` | 每 (用户, 游戏) 一行 | `played_at` |
| `game_user_stats` | 每 (用户, 游戏) 一行 | `play_seconds`、`progress` |

- 云端存档内容路径：`save/{用户名}/{game_type}/{卡带ID}/{uuid}.state`。
- 文件名不体现原名；原名只用于下载时的 `Content-Disposition`。
- 下载名规则：`name` 含点则原样，否则补 `.sol`，空名回退「存档」。
- 快照行有 `remark`（上限 100 字）与 `created_at`；前者超长报错，后者只判定「最新一条」。
- `game_cloud_snapshot_files.sort_order` 是快照内文件序号，不是展示分数。
- 模拟器设置只覆盖 8 个主机平台，不含 flash/h5；只存 SQLite，不落文件。
- 设置 payload 必须是 `{controlSettings, settings, cheats}` 且 ≤64KB，否则 400。
- 最近游玩一行只记最后一次 `played_at`，重玩只刷新时间。
- 统计行与游戏类型无关；Flash、H5、主机 ROM 共用同一张表。
- 模拟器本地档内容存 IndexedDB，键为 `x_emusave:{gameId}:state1`。
- 本地档索引在 localStorage 的 `x_emusave_index_v1`；内容键指向 `{gameId,id,name,size,updatedAt}`。
- 模拟器本地档固定叫 `save.state`；本地展示、下载与云端快照文件名都用它。
- Flash 本地档是 Ruffle 写进 localStorage 的 `.sol`，一个游戏可以有多份。
- H5 没有本地存档，也不接入云存档。

## 行为与规则

### 云端快照语义

- 一次「同步至云端」= 把该 (用户, 游戏) 此刻**全部本地存档文件**上传成一个不可变的整体快照。
- Flash 一个快照可含多条 `.sol`；模拟器恒为 1 个文件。
- 上传用 multipart：`game_id`、`remark`、`manifest`、`sols`。
- `manifest` 是 `[{local_key, name}]`，与 `sols` 顺序一一对应。
- `local_key` 是还原时要写回浏览器本地存储的键。
- 先逐个写文件，再落快照与文件行；中途失败回滚已提交行并删已写文件。
- 快照按 `(user_id, game_id)` 隔离；别人的快照一律 404，不区分「不存在」。
- 列表接口为 `GET /api/games/saves?game_id=…`，按 `(sort_order, id)` 升序。
- 详情接口为 `GET /api/games/saves/{id}`。
- 单文件下载为 `GET /api/games/saves/{id}/files/{file_id}/download`。
- 改描述为 `PUT /api/games/saves/{id}`。
- 删除为 `DELETE /api/games/saves/{id}`。

### 父子层级与排序

- 快照之间是同一 `(用户, 游戏)` 内的森林；允许多个顶层。
- 每个节点最多一个父级、可有多个子级；`parent_id` 可空，NULL = 顶层。
- `parent_id` **无物理外键**；归属、同游戏与防环由 service 校验。
- 父级必须同属一个 `(user_id, game_id)`，不能指向自己，沿祖先链不能成环。
- `PUT /api/games/saves/{id}/parent` 设置或清除父级，body 为 `{parent_id}`。
- `parent_id: null` 表示设为顶层。
- 新建快照自动指向同组最新一条；最新按 `created_at DESC, id DESC` 判定。
- 第一条快照为顶层；之后每条接在上一条后面。
- 删除快照时，**直接子级改回顶层**；不级联删除、不接续祖父。
- 展示顺序由 `sort_order` 分数决定，升序，越新越靠下。
- 新快照取「最大分 + 1000」追加到末尾。
- 同级调序走 `POST /api/games/saves/{id}/move`，body 为 `{to_index}`。
- `to_index` 是同级兄弟内的下标，0 起。
- 移动只改被移动那一行的分数，取相邻两分数的中值。
- 相邻间隔用尽时，才把整份按步长重新铺开。
- `created_at` 只决定自动父级是谁，不再决定列表顺序。
- 树形视图只是前端自动布局，**不存节点坐标**。

### 存档管理弹框

- 两个播放页共用 `SaveManager.vue`：一个弹框，上半本地、下半云端。
- `platform="flash"` 与 `"emulator"` 只区分本地存档差异。
- 本地工具条有「捕捉」「同步至云端」「从本地上传」；Flash 另有「刷新」。
- 本地项可载入（仅模拟器）、下载、删除。
- 云端是 `CloudSavePanel` + `SaveTreeView`。
- 云端左列默认展示全部节点，顶部是「搜索存档详情」输入框。
- 左列不提供按顶层过滤的开关；要看父子层级时看右侧画布。
- 右侧画布按 `parent_id` 自动布局；节点尺寸、层距与根间距由布局常量决定。
- 拖动节点到另一节点下即建立父子关系。
- 拖到空白处、或右键「设为顶层」即脱离父级。
- 拖到自己的子级下面会被拒绝并提示。
- 滚轮缩放，范围 0.2–2.5；空白处拖动平移。
- 工具条有「适应视图」与「全屏 / 退出全屏」。
- 选中节点后 `Shift + ↑/↓` 调整同级顺序；连按会防抖到停手后再落库。
- 节点正文直接显示描述，换行折成空格；CSS 截成最多两行、每行约 5 个汉字。
- 空描述就是空节点，不显示时间戳。
- 右键节点弹详情：描述、创建时间、文件列表。
- 详情底部有「同步至本地」「设为顶层」「删除」。
- 左列项与画布节点双击都在原地改描述，不弹详情。
- 详情弹框里的描述也可双击改。
- 描述内联编辑上限 100 字；回车保存、ESC 取消、失焦保存。
- 删除云端快照前会确认，并提示有多少子存档会变为顶层。
- ESC 按层级由内到外收：先结束描述编辑，再收上传描述面板，最后才关存档弹框。
- 监听挂在 `window` 冒泡阶段，避免 Element Plus 确认框吃掉 ESC 时连带关掉弹框。

### 本地存档

- 模拟器每个游戏固定只有一份本地档，覆盖式，不做多槽位。
- 捕捉、导入 `.state`、云端还原都是覆盖这一份。
- 进入播放页或存档面板时，`ensureSingleSlotModel()` 会清掉旧版多槽位档。
- 捕捉与放回走宿主页 `__ejsRpc.capture` / `__ejsRpc.load`，底层用引擎 `storage.states`。
- 捕捉不暂停引擎。
- Flash 的本地档来自 Ruffle SharedObject；Ruffle 只在播放器卸载时才落盘。
- 因此 Flash 的「同步至云端」必须先重启游戏，捕捉前也要先在游戏里存过档。
- 本地档只在这台浏览器里；换设备、换浏览器、清站点数据都会丢。
- 云端还原按快照逐文件取回：Flash 写 localStorage，模拟器覆盖本地唯一档。

### 快捷键与同步

- `·`（Backquote）在三个播放页都支持：捕捉当前进度 → 上传云端。
- 模拟器直接复用 `onUploadCloud()`，它内部已含 `capture` 与成功提示。
- 两步顺次跑完只弹一句「已同步至云端」；模块级 `syncingCloud` 挡连发。
- Flash 的 `·` 先弹二次确认，提醒游戏会重启；取消则不重启、不提示。
- Flash 的 `onUploadCloud()` 返回布尔值，只有真的传上去才弹成功提示。
- H5 按 `·` 只提示「HTML5 游戏不支持云存档。」
- ``Alt + ` ``（Backquote）打开存档管理，只对 Flash 与模拟器有效。
- 存档管理已开、截图确认框开着、游戏未加载或正在同步时不响应。
- 快捷键用 `event.code` 匹配；焦点在输入框、文本域、下拉或可编辑区时不抢。

### 模拟器设置同步

- 设置按**平台**（`game_type`）一份，随账号跨设备同步。
- 内容就是引擎 localStorage 那块的 `{controlSettings, settings, cheats}`。
- 引擎设置键为 `ejs-{gameId}-{core}-{gameName}-settings`。
- 引擎只在启动流程里读一次设置键。
- 播放页在设 iframe `src` 之前把云端值写回 localStorage，这就是「自动加载」。
- 保存是手动的：标题栏「保存配置」把当前整块配置 PUT 上去。
- 不做自动侦测：引擎不发设置变更事件，也没有保存按钮。
- NDS 写回前会剔除双屏布局与 gap 选项，保证窗口选择器是布局的唯一入口。
- 接口为 `GET /api/games/emulator-settings?game_type=…` 与 `PUT /api/games/emulator-settings`。

### 最近游玩

- 数据源是游戏中心顶部的「最近游玩」rail；只占一行、不滚动。
- rail 下面是完整「全部游戏」，重复资源不剔除。
- 记录按账号存 SQLite，唯一 `(user_id, game_id)`；一个游戏只留一行。
- 列表按 `played_at DESC, id DESC` 排序。
- 只返回 `game_path != ''` 的游戏，与中心列表同口径。
- 默认 20 条、上限 50；`limit` 越界在 service 收敛，不走 422。
- 上报只能由播放页发起：在真正拉起播放器的那一刻调 `reportGamePlayed()`。
- 上报是 best-effort，失败只丢一条记录，不影响游玩。
- 没有登录态的播放资源接口不负责记 user，所以不在后端资源接口上记。

### 游玩时长与进度

- 统计按账号存 SQLite，唯一 `(user_id, game_id)`；一行含 `play_seconds` 与 `progress`。
- 计时器 `gamePlaytime.js` 是模块级单例，三个播放页共用。
- 在与 `reportGamePlayed()` **完全相同的时机**起表，离开播放页时停表。
- 每 30 秒发一次心跳，`POST /api/games/stats/playtime` 累加。
- service 把单次秒数收敛到 0..300，防时钟跳变与刷量。
- `document.hidden` 期间不累计；回到前台重新起算。
- 离开播放页时把剩余时长一次性发出，不足 1 秒丢弃。
- 手动设置时长走 `PUT /api/games/stats/{id}/playtime`，单位小时，**覆盖**不累加。
- 手动上限 100000 小时；非数字或越界返回 400。
- 之后继续游玩仍从该值往上加。
- 进度走 `PUT /api/games/stats/{id}/progress`，只认 `not_started`、`in_progress`、`completed`。
- 进度**只由用户手动设置**，不会因游玩自动变更。
- 因此会出现「时长 > 0 但进度仍是未开始」的组合。
- `GET /api/games` 与 `/recent` 载荷都带 `play_seconds` 与 `progress`。
- 无记录时返回 `0` 与 `not_started`。
- 游戏中心只在游戏卡上接管右键；菜单有详情、攻略、设置进度、设置时长。
- 设置进度是右滑子菜单，三选一点完即存；设置时长是弹框，清空输入时拒绝。
- 保存后本地 patch 两个列表；工具栏类型下拉左边是进度下拉，三者纯前端联合筛选。
- 卡片封面下方是居中的「进度标签 + 总时长」；时长 <10 小时留 1 位小数，≥10 取整。
- 进度还是 `not_started` 时不画内容，但状态行容器仍占一行（`min-height: 14px`）。

### 删除游戏与改卡带 ID

- 删游戏时清理该游戏所有账号的存档快照行、文件与存档目录。
- 同时清理截图行/文件/目录、图集行、最近游玩行与统计行。
- 存档与截图目录名带的是**写入当时**的游戏类型。
- 所以目录只能从 `file_path` 反推，绝不用游戏当前类型拼。
- 改卡带 ID 时同样按 `file_path` 反推父目录，只换最后一段。
- 运行时根下的 H5/攻略解包产物随游戏目录一起作废。

## 边界与错误

- 云端存档、设置、最近与统计接口都需要登录。
- 别人的快照一律 404「云端存档不存在。」。
- 父级自指返回 400；跨游戏返回 400；成环或层级数据异常也返回 400。
- `move` 的 `to_index < 0` 或 ≥ 同级数量返回 400「目标位置不合法。」。
- 快照描述超过 100 字返回 400。
- 无可同步文件、文件数超过 64、缺 `local_key`、单文件超过 64MB 均返回 400。
- `manifest` 与文件数量不一致返回 400；游戏不存在返回 404。
- 统计的非法进度、非数字或越界时长返回 400；游戏不存在或无本体返回 404。
- 最近游玩 `limit` 不报 422，收敛到 1..50。
- 设置非主机平台返回 400；payload 缺字段或超过 64KB 返回 400。
- H5 没有云存档；Flash 没有 `.sol` 时提示「本地没有可同步的存档。」。
- 本地档只存在浏览器里；换设备或清站点数据就会丢。

## 测试要点

- 后端：`python -m pytest tests/test_game_saves.py`。
- 覆盖路径、登录、往返、描述上限、隔离、manifest 不一致、游戏不存在与自动父级。
- 还覆盖父级自指/跨游戏/成环/缺失、删除改顶层、排序、移动与删游戏清理。
- 后端：`python -m pytest tests/test_game_recent.py`。
- 覆盖登录、首玩为空、按时间倒序、单行刷新、账号隔离、limit 收敛、无本体与删游戏。
- 后端：`python -m pytest tests/test_game_stats.py`。
- 覆盖累加、0..300 收敛、手动覆盖后继续累加、越界拒绝、进度校验与删游戏。
- 后端：`python -m pytest tests/test_game_emulator_settings.py`。
- 覆盖登录、首次为空、往返、整块覆盖、按平台/账号隔离、非主机平台与非法/超大 payload。
- 手工：两播放页存档管理上下半区、本地操作与云端树视图都可用。
- 手工：拖动建树、拖空白脱离、右键设顶层、Shift+↑/↓ 调序、滚轮缩放与全屏。
- 手工：双击改描述、回车保存、ESC 取消、失焦保存；删除后子级变顶层。
- 手工：`·` 在模拟器只弹一句、Flash 先确认、H5 提示不支持；``Alt+` `` 打开存档管理。
- 手工：保存配置后换设备自动恢复设置；最近游玩顺序与卡片时长格式正确。

## 相关文档

- [`../architecture.md`](../architecture.md)
- [`../data_dict.md`](../data_dict.md)
- [`./game-center-playback.md`](./game-center-playback.md)
- [`./game-assets.md`](./game-assets.md)
- [`../../AGENTS.md`](../../AGENTS.md)
