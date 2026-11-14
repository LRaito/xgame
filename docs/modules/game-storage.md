# 游戏存储与入库

本文件回答：游戏文件放在哪、如何入库，以及卡带 ID 如何迁移。

## 范围与权威

- 本文说明游戏文件放在哪、怎么读写，以及新建 / 换本体 / 搬运 / 删除的规则。
- 路径权威是 `backend/games/paths.py`；入库逻辑权威是 `backend/games/service.py`。
- 两个包的校验与解包原语在 `backend/games/archive.py`。
- 数据库表结构见 `../data_dict.md`，本文不重复列字段。

## 职责

- 把游戏本体收进数据根：本地上传、网络直链、站点搬运。
- 维护卡带 ID、封面类型、游戏目录与显式迁移。
- 删除游戏时清理本体、封面、攻略与各账号的关联目录。

## 关键接口

- `GET|POST /api/games/manage`、`POST /api/games/manage/import`。
- `PUT /api/games/manage/{id}/cartridge-id`、`PUT /api/games/manage/{id}/game-type`。
- 领域实现：`backend/games/service.py`、`importer.py`、`remote.py`、`uploads.py`、`paths.py`。

## 依赖

- `backend/storage/` 的 `StorageBackend` 协议与 `LocalStorage` 实现。
- SQLModel 表 `games`。
- `backend/games/platforms.py` 提供机种、扩展名与候选顺序。
- `backend/games/archive.py` 与 `runtime_assets.py` 处理 ZIP 与解包。

## 数据与路径

- 存储分两个根：数据根 `STORAGE_ROOT` 与运行时根 `RUNTIME_ROOT`。
- 数据根放原始素材，会被整体拷走备份；没有对象存储，全是宿主机普通文件。
- 运行时根放 SQLite 库（`db/app.db`）与 H5 / 攻略的解包产物。
- `RUNTIME_ROOT` 不配置时等于数据根，两个 `LocalStorage` 实例指向同一棵树。
- SQLite 只存相对路径；两个根下的相对路径逐字一致，只换拼接的根。
- 数据根的游戏目录是 `game/{game_type}/{卡带ID}/`，类型那层用键值而不是显示名。
- 该目录下：本体 `game.{后缀}`、封面 `cover.{后缀}`、攻略 `guide.zip` 或 `guide.pdf`、图集 `image/{uuid}.{后缀}`。
- 多文件本体在该目录下另建 `body/`：各文件用原文件名，入口统一 `game.{后缀}`，
  清单固定 `body/manifest.json`。
- 按账号分：存档 `save/{用户名}/{game_type}/{卡带ID}/{uuid}.state`。
- 按账号分：截图 `image/{用户名}/{game_type}/{卡带ID}/{uuid}.{后缀}`。
- 分片暂存：`upload/{upload_id}/`（可丢弃，提交后即删，见「本体分片上传」）。
- 运行时根下：H5 资源 `game/{类型}/{卡带ID}/h5/{包内路径}`。
- 运行时根下：攻略资源 `game/{类型}/{卡带ID}/guide/{包内路径}`。
- 完整路径表与生成函数见 `../data_dict.md` 的「文件存储结构 / 路径规则」。
- 目录名不随游戏名变化，改游戏名不会挪动任何文件。
- 读写一律经 `backend/storage/local.py` 的 `LocalStorage`，别在别处手拼绝对路径。
- `create_app()` 建两个实例：`app.state.storage` 与 `app.state.runtime_storage`。
- 单文件原语：`upload` / `delete` / `stat` / `open_download`，上传下载都分块流式。
- 目录级原语：`remove_tree` / `replace_tree` / `move` / `move_tree` / `dir_exists`。
- 分片原语：`open_writer`（按偏移写）、`exists`、`list_dir`、`mtime`。
- 写入先落同目录临时文件 `.{文件名}.tmp-{随机}`，再 `os.replace` 改名。
- `LocalStorage` 拒绝空路径、反斜杠、绝对路径与任何一段 `..`；根目录不存在时自动创建。
- 存储协议在 `backend/storage/types.py`，跨模块下载响应在 `backend/storage/access.py`。

## 行为与规则

### 游戏类型

- 游戏类型由「本体后缀 + 用户选择」判定，唯一入口是 `resolve_game_type()`。
- `flash` ← `.swf`；`h5` ← `.zip`；其余 34 个主机类型见 [机种词表](../common/platforms.md)。
- `.zip` 同时是 H5 静态包、DOS 的 jsdos 包与街机 romset：候选是
  `h5` / `dos` / `arcade`。用户不传类型时保持历史默认 `h5`；DOS 与街机必须显式选择。
  `.jsdos` 唯一对应 `dos`，`.cso` 唯一对应 `psp`。
- `.iso` 候选是 `psx` / `psp` / `3do`，默认仍是 PS1。
- 扩展名白名单 `_GAME_TYPE_EXTENSIONS` 从机种词表派生，未收录后缀中文 400。
- 后缀唯一对应一个机种时自动确定，类型不可选；后缀有多个候选时（Commodore 的
  `.d64` / `.prg`，CD 镜像的 `.chd` / `.iso`）必须由用户选择。
- 多候选的默认项取词表顺序第 1 个；`.chd` 由覆盖表指定为 PS1（实际镜像最多）。
- 本地文件与网络直链都接受 `body_game_type`；后端始终按候选集重新校验。
- 游戏类型可以在编辑弹框里修改，走独立接口 `PUT /manage/{id}/game-type`。
  目标类型必须在当前本体后缀的候选集内，因此唯一后缀不能改类型。
- 改类型会搬游戏目录与各账号的存档/截图目录，并改写所有路径列（见「改类型」）。
- 换本体仍只接受与当前类型相同的本体；多候选后缀只要当前类型在候选内即可。
- 同类型内允许换后缀：`.gb ↔ .gbc`、`.sfc ↔ .smc`、`.md ↔ .gen`。
- 跨类型换本体中文 400，旧本体、封面、图集、攻略都不动；需要跨类型时先改类型再换本体。
- 类型目录用 `flash` / `h5` / `nes` 等键值，不是中文显示名。

### 改类型

- `change_game_type()` 与改卡带 ID 同一套「先规划、再搬目录、提交、失败回滚」流程。
- 搬三类目录：游戏目录整棵树、各账号的存档目录、各账号的截图目录。
- 存档/截图目录的类型层按 `file_path` 反推，绝不用当前 `game_type` 拼（历史数据可能
  已经换过类型）。
- 改写五处路径列：`games.game_path`、`games.cover_path`、`game_gallery_images.file_path`、
  `game_cloud_snapshot_files.file_path`、`game_screenshots.file_path`。
- 目标类型下已有同名游戏：中文 400，磁盘与库都不动。
- `.zip` 本体（H5 / DOS / 街机）不支持改类型：同一个 ZIP 在三种类型里含义不同，
  迁移只会得到打不开的游戏；显式中文 400，请删除后重新上传。
- 新类型不支持美化封面时清空 `cover_type`，封面文件随目录搬走。
- 旧运行时解包产物作废，下次访问按新类型重新解包。

### 卡带 ID

- `games.cartridge_id` 创建时必填，搬运是唯一例外（服务端自动生成）。
- 全局唯一，跨类型也唯一，唯一索引是 `uq_games_cartridge_id`。
- 只允许数字、字母、中划线、下划线，最长 64 字符。
- 落库前去首尾空白并统一转大写（`validate_cartridge_id()`）。
- 它同时是磁盘目录名与「同一盘卡带」的身份标识。
- 普通编辑 `PUT /manage/{id}` 不接受该字段；改 ID 走独立接口。
- 改名由 `rename_cartridge_id()` 执行，搬三类目录并改写所有路径列。
- 三类目录：游戏目录、各账号的存档目录、各账号的截图目录。
- 存档与截图目录里的类型是写入当时的，只能从 `file_path` 反推，绝不用当前类型拼。
- 同一事务改写 `cartridge_id`、`game_path`、`cover_path` 与图集 / 截图 / 快照文件三张子表。
- 先搬磁盘、后提交数据库；中途失败按相反顺序搬回，库一个字节不动。
- 源目录不在照常成功；源不在而目标在则 400；新旧相同是空操作。
- 改名后运行时旧解包产物作废；没有行引用的孤儿目录不会跟着改名。

### 封面类型

- `games.cover_type` 记录封面被「美化」成哪种外观，值就是封面样式 id。
- 可空：空表示没有封面类型，不是「始终有值」。
- `flash` → `flash`；`gb` → `gb` / `gbc`；`gba` → `gba`；`nds` → `nds`；
  `nes` → `fc` / `nes`；`snes` → `sfc`。
- `h5` / `sega*` 等未登记类型返回空元组，永远没有封面类型。
- 校验入口 `validate_cover_type()`：先判空，空值合法并返回 `None`。
- 不支持美化的类型收到非空值、或值不在集合内，都是中文 400。
- 新建（手动上传 / 网络上传 / 搬运）一律留空，建好后才能设置。
- 写入路径共两条：管理页编辑弹框，与「美化封面」的同一次 assets 调用。
- 编辑弹框里 `None` = 不改、空串 = 清空；前端用文字单选。
- 前端镜像 `frontend/src/constants/coverStyles.js` 的 `coverTypesFor()`，顺序必须一致。
- 老库的 `cover_type` 列由 `upgrade/versions/v1.py` 补齐；运行代码不写兼容分支。

### 游戏名、描述与 CRC32

- 同类型下游戏名唯一（`uq_games_game_type_name`），不同类型之间可以重名。
- 游戏名须同时是合法的 Windows 文件名与百度网盘文件名。
- 非法字符：`\ / : * ? " < > |`；全角版本不受影响。
- 不能含控制字符、不能以点结尾、不能是 Windows 保留设备名（带扩展名也算）。
- 游戏名最长 255 字符，首尾空白自动去掉，校验入口 `validate_game_name()`。
- 搬运标题走 `sanitize_game_name()`：非法字符换 `_`、去结尾点、截断，空则回退「未命名游戏」。
- 描述上限 200 字，新建与编辑超长中文 400；搬运抓到的简介按上限截断后入库。
- 上传本体时算 CRC32 落 `games.crc32`，8 位大写十六进制，分块计算不整读内存。
- CRC32 只是当前本体摘要，不是锁定凭据；换同类型本体时重算，空串表示尚未算出。

### 入库与搬运

- 新建走 `POST /api/games/manage`（multipart），建条目并写本体；本体可省略。
- 表单：`name` / `cartridge_id` / `description` / `file`，可选 `cover`。
- 无本体时不传 `file` / `upload_id` / `upload_ids` / `body_url`，但必须用 `body_game_type`
  指定类型；`size` / `crc32` / `game_path` 保持空值，条目照常进入游戏中心。
- 无本体卡片在中心只提示「请先上传游戏本体」，不进播放页；详情的大小 / CRC32 显示「—」。
- 补传本体走编辑的 `POST /manage/{id}/assets`，类型必须与建条目时选的类型一致。
- 本体与封面也可给直链：`body_url` + `body_game_type` / `cover_url`，来源可混用。
- 超过 30MB 的本地本体改走分片：同一个接口接受 `upload_id`，与 `file` / `body_url` 三选一。
- 多文件本体用 `upload_ids`（每个物理文件一个现有分片会话），与 `file` / `body_url` /
  `upload_id` 互斥；单文件本体仍写 `game.{ext}`，多文件写 `body/`。
- 任一步失败整体回滚，不留半成品条目与文件。
- 换本体 / 换封面走 `POST /manage/{id}/assets`，`kind=game|cover`。
- 分片暂存本体也只能用于 `kind=game`；封面与攻略不分片。
- 换本体成功后更新 `crc32` / `size` / `game_path`，落库成功后才删旧后缀文件。
- 网络上传由服务端下载，单文件上限 512MB（`remote.MAX_REMOTE_BYTES`）。
- 本体直链类型以用户所选 `game_type` 为准：地址能认出就必须一致，否则 400。
- 地址认不出类型时，用该类型的 `default_extension` 补后缀。
- 封面直链只接受 jpg / jpeg / png / gif / webp；直链原始文件名不落盘也不入库。
- 搬运走 `POST /api/games/manage/import`，body 只有 `{url}`。
- 只接受 7k7k.com / 4399.com / flash.homes 的游戏页地址，避免被当作任意 URL 代理。
- 搬运由 `backend/games/importer.py` 解析下载，再走普通上传管线；结果是 Flash 或 H5。
- 搬运的卡带 ID 自动生成为 `F-{CRC32}`；同一文件重复搬运会撞唯一索引。

### 本体分片上传

- 本地上传 ≤30MB 仍走单文件 multipart；>30MB 由前端切 16MB 分片，5 路并发。
- 阈值与分片大小由 `/api/games/status.upload` 下发，后端常量在 `backend/games/uploads.py`。
- 分片会话绑定当前账号；`upload_id` 是 32 位小写十六进制，别人拿到也一律 404。
- 会话暂存在**数据根**的 `upload/{upload_id}/`，与最终素材同一文件系统：
  - `meta.json`：用户、文件名、总大小、分片大小、分片数、所选类型与状态；
  - `body.part`：唯一目标文件，分片按偏移直接写入；
  - `chunks/{index}`：空标记，写完并 `fsync` 后才创建。
- 分片请求是原始字节流（`application/octet-stream`），不经过 `UploadFile`，
  nginx 关闭 `proxy_request_buffering`，后端用 `request.stream()` 边收边写。
- 每个分片必须正好是约定长度；有 `Content-Length` 先比对，实际字节数再校验一次。
- 所有分片到齐后 `complete` 只检查标记与 `body.part` 大小，不读整包、不算 CRC。
- 提交（新建或换本体）时才读一遍暂存文件算 CRC32，然后 `os.replace` 到
  `game/{类型}/{卡带ID}/game.{后缀}`；H5 仍是 `game.zip`，并作废运行时解包产物。
- 提交成功后删除整个暂存目录；失败保留，前端 DELETE 或 24 小时 TTL 兜底。
- 服务启动时清理超过 24 小时的暂存会话。
- 分片本体不设总大小上限，只受磁盘限制；H5 `.zip` 仍受 `archive.MAX_ZIP_SIZE` 128MB 限制。
- 前端对失败分片等待 5 秒重试，最多 5 次；某片仍失败就取消其余分片、
  删除服务端会话，整次上传标记失败。新建失败不会留下没有本体的条目。
- nginx `client_max_body_size` 为 130m（128MB 内容 + multipart 余量）；
  攻略 ZIP/PDF 上限仍为 128MB。
- 播放 URL 末段带真实落盘名（`/api/games/{id}/play/game.<ext>`），
  EmulatorJS 用它当 ROM 文件名并识别 `.pbp` 等格式；原名段必须与落盘名一致。

### 多文件本体

- 适用机种由 `Platform.bundle_extensions` 决定，当前是 `segaCD` 与 `amiga`。
- 每个物理文件各开一个现有分片会话（小文件也是一片），提交时 `upload_ids` 一次给全；
  服务端在提交点统一校验，不新增打包会话。
- 单文件后缀仍走 `game.{ext}`：世嘉 CD 的 `.chd`、Amiga 的 `.adf` / `.hdf`。
- 多文件落 `body/{原文件名}`；入口统一改名 `game.{后缀}`（EJS 取 URL 末段当 MEMFS 文件名
  且不做 URL 解码，原名带空格/中文会对不上 cue 内引用）。
- 入口选择：唯一 `.m3u` > `.cue` > `.chd` / `.adf` / `.hdf`；多个分盘且没有 m3u 时，
  按文件名自然排序自动生成 `game.m3u`。`.bin` 永远不能当入口。
- cue 的 `FILE` 与 m3u 的每行只能引用同一层的 basename；拒绝子目录、绝对路径、远程 URL、
  大小写不一致与重复引用。`.cue` / `.m3u` / `.bin` 单独上传会被中文 400 拒绝；
  `.bin` 直链仍按旧规则补所选类型的默认后缀。
- `manifest.json` 记录 `{version, entry, files:[{name,size,crc32}]}`；`files` 含入口与自动
  m3u，不含清单自身，按 `name` 排序。
- `games.game_path` 指向入口；`size` 是 `files` 大小之和；`crc32` 是
  `name\tsize\tcrc32\n`（按 name 排序）文本的 CRC32。
- 文件数上限 64；总大小不设应用层上限，只受磁盘限制；前端对 >1GB 给内存提示。
- 文件名必须是安全 basename（无 `/`、`\`、`..`、控制字符、Windows 非法字符、`? # %`；
  不以点或空格结尾；不是 Windows 保留设备名），大小写不敏感去重，≤120 字符。
- 提交在同层 `.body-{token}` 组装，旧 `body/` 改名备份 → 新目录就位 → 数据库提交；
  失败按相反顺序还原。成功后删旧 `body/` 或旧 `game.{ext}` 与全部上传会话。
- 多文件本体不支持改游戏类型（中文 400）；改卡带 ID 仍整目录搬家，删游戏删整棵目录。
- 多文件游戏不提供「下载本体为单个文件」，管理详情提示从数据目录整体备份。

### 线程核与街机本体

- PSP 与 DOS 的核只有线程变体（`Platform.threads=True`），宿主页只对它们打开
  `EJS_threads`；页面必须带 COOP/COEP，否则播放前给中文提示。
- PSP 收 `.iso` / `.cso`，分别存 `game.iso` / `game.cso`；无 BIOS。
- DOS 收 `.jsdos` / `.zip`，分别存 `game.jsdos` / `game.zip`；包内结构由 DOSBox 解析。
  DOS 的 `.zip` 不走 H5 的 ZIP 清单校验，128MB 上限也只约束 H5。
- 街机收 romset `.zip`，存 `game/{arcade}/{卡带ID}/{romset}.zip`，保留集合名
  （如 `mslug.zip`）；`EJS_gameUrl` 末段必须就是集合名，FBNeo 靠它找集合。
- 街机文件名：安全 basename，只含字母、数字、点、下划线与短横线，以 `.zip` 结尾，
  且不能占用 `guide.zip`；非法名中文 400。
- 街机只接受本地上传；网络直链的临时名 `remote.zip` 无法满足集合名要求，中文 400。
- 街机可选 `arcade.zip` BIOS 包（内含 `neogeo.zip`、`pgm.zip` 等）；缺包不拦启动，
  只影响需要该 BIOS 的集合。
- 街机的 `size` / `crc32` 仍是 zip 本身的；`body_kind` 为 `file`，可正常下载单文件。
- 只打包默认 FBNeo；设置菜单切到未打包的 CPS1/CPS2 会缺资产，与 NDS 只打包
  melonds 的现状一致。

### H5 与攻略包

- H5 上传只校验、不解压：zip 原样存数据根的 `game.zip`，就是 `game_path`。
- H5 不落清单表；真实解包推迟到播放时。
- 两个包共同校验：只读中央目录，检查路径、重名、条目数、单条、总量、压缩比、加密条目。
- 上限：zip ≤128MB、条目 ≤2000、单条 ≤64MB、解压后 ≤256MB、压缩比 ≤200。
- 入口固定在包内根目录；H5 接受 `index.html` / `index.htm`，攻略只认 `index.html`。
- 整包套单层目录会自动剥前缀；入口大小写不敏感，落盘统一小写。
- 攻略可以是 ZIP 静态站包或单个 PDF，二者互斥；上传走 `POST /manage/{id}/guide`。
- PDF 校验后缀、大小（≤128MB）与前 1024 字节含 `%PDF-`，原样存数据根、不解包。
- 上传一种形态会删掉另一种；删旧失败时把新文件也删掉再报错。
- 攻略写入不动 `game_path` / `size` / `crc32`，只写 `games.guide_kind`。
- 删除攻略走 `DELETE /manage/{id}/guide`，文件、解包产物与 `guide_kind` 一起清；幂等，删文件失败返回 500 且不清列。

### 删除与运行时产物

- 删游戏时先删数据根的游戏目录（本体、封面、攻略、图集都在里面）。
- 再删运行时根的同名游戏目录，清掉 H5 / 攻略解包产物。
- 云端存档：删该游戏所有账号的快照行、文件行、文件与存档目录。
- 截图：删该游戏所有账号的截图行、文件与截图目录。
- 图集行、最近游玩行、游玩统计行与 `games` 行一并删除。
- 存档与截图目录按 `file_path` 反推，因为目录里的类型可能是写入当时的旧类型。
- H5 / 攻略首次播放或查看时才解包：入口文件在就直接复用，不再解。
- 解包先写同层暂存目录，再用 `replace_tree` 原子替换目标目录。
- 同一 `(类别, 类型, 卡带 ID)` 用进程内锁串行，因此 gunicorn 必须 `--workers 1`。
- 重传 zip / 改卡带 ID / 删游戏由写路径显式作废运行时根产物。

## 边界与错误

- 卡带 ID 为空、超长、含非法字符：中文 400。
- 卡带 ID 已被占用：中文 400；搬运重复时提示「这个游戏已经搬运过了」。
- 未收录本体后缀、跨类型换本体、游戏名非法或重复、描述超长：中文 400，旧档不动。
- 多候选后缀未选类型、改类型目标不在候选集：中文 400，不搬任何目录。
- 单文件本地本体超过 30MB：中文 400，提示改用分片上传。
- 分片长度不符、序号越界、缺片、总大小不符：中文 400；别人的 `upload_id`：404。
- 多文件本体缺入口、缺引用、引用子目录/远程地址/大小写不一致、重名、超过 64 个文件：
  中文 400，旧本体不动。
- 街机 romset 文件名非法、不是 `.zip`、占用保留名：中文 400；街机网络直链：中文 400。
- `.zip` 本体改类型（H5 / DOS / 街机互转）：中文 400，旧档不动。
- 分片上传的 chunks 与 complete 路由允许没有 `Content-Length`（HTTP/2），其它写方法仍返回 411。
- 封面后缀或封面类型非法、上传文件为空、网络直链不合法或超 512MB：中文 400。
- H5 / 攻略 ZIP 缺入口、路径越界、重名、超限、加密条目：中文 400。
- PDF 后缀不符、超过 128MB、文件头没有 `%PDF-`：中文 400。
- 游戏、攻略或 H5 资源不存在、形态不符：404。
- 解包写运行时根失败（磁盘满 / 只读）：500，并提示检查运行时目录。
- 删除攻略时文件删不掉：500，`guide_kind` 保持不变，方便重试。
- 改名时源目录不在而目标目录已在：400；路径超过 Windows 总长预算：中文 400。

## 测试要点

- `LocalStorage` 读写、覆盖、删除、目录替换，以及 `..`、绝对路径被拒。
- 新建必填卡带 ID、自动转大写、全局唯一；普通编辑改不动它。
- 本体可选：无本体新建必须给类型；中心可见但不可游玩，补传后恢复正常。
- 封面类型：新建一律留空；编辑弹框与「美化封面」写入后能读回，非法值 400 且原值不变。
- 上传后文件按 `game/{类型}/{卡带ID}/…` 真实落盘。
- 换同类型本体更新 `crc32` / `size` / `game_path`，保留封面 / 图集 / 攻略；跨类型返回 400 且旧档不动。
- 多候选后缀（`.d64` / `.prg`）不选类型被拒；选 c128 / pet 等按所选落库。
- 分片上传：乱序分片、缺片、长度不符、上传会话归属、DELETE 幂等与 TTL 清理。
- 多文件本体：cue+bin、m3u 多碟、多 adf、自动 m3u、引用校验、单文件/多文件互转与旧文件清理。
- 后端：`python -m pytest tests/test_game_bundles.py tests/test_game_uploads.py tests/test_local_storage.py`。
- 改类型搬三类目录（含历史类型目录）、改五处路径列、多账号都搬；失败分支全测。
- 改卡带 ID 搬三类目录（含换过类型的历史目录）、改五处路径列、多账号都搬；失败分支全测。
- 两个根下都不留旧 ID 的残迹；运行时旧解包产物作废。
- H5 / 攻略 ZIP 上传后运行时根仍然干净，首次访问才解包，二次访问不重解；重传后旧产物作废。
- 缺 `index.html` 与超限时两个根零残留。
- PDF 攻略只落 `guide.pdf`；ZIP 与 PDF 上传一种会替换另一种。
- 删游戏后素材、存档、截图、图集、最近游玩与统计都不留孤儿。

## 相关文档

- [机种词表](../common/platforms.md)
- [数据字典](../data_dict.md)
- [架构说明](../architecture.md)
- [编码约定](../../AGENTS.md)
