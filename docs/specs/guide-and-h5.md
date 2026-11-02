# H5 与攻略包

## 范围与权威

- H5 游戏与 ZIP 形态的攻略共用一套压缩包校验与解包原语。
- 原语在 `backend/games/archive.py`，按需解包在 `runtime_assets.py`。
- H5 播放页是 `frontend/src/views/games/h5-player.vue`。
- 攻略入口在游戏中心卡片的右键菜单。
- 设计取舍见 `../architecture.md` 的「决策 6」与「决策 14」。
- 制作攻略的流程见 `.claude/skills/make-guide`。

## 数据与路径

- H5 本体是 zip，原样存数据根 `game/{game_type}/{卡带ID}/game.zip`。
- 该路径就是 `games.game_path`。
- H5 解包产物在运行时根 `game/{game_type}/{卡带ID}/h5/{包内相对路径}`。
- ZIP 攻略存数据根 `game/{game_type}/{卡带ID}/guide.zip`。
- PDF 攻略存数据根 `game/{game_type}/{卡带ID}/guide.pdf`。
- 攻略 ZIP 的解包产物在运行时根 `game/{game_type}/{卡带ID}/guide/{包内相对路径}`。
- 路径里的 `{game_type}` 用键值（如 `h5` / `gba`），不是中文显示名。
- 两个根下相对路径逐字一致，只换拼的根。
- 所有读写经 `LocalStorage`，路径拼接集中在 `games/paths.py`。

| 内容 | 数据根 | 运行时根 |
|------|--------|----------|
| H5 本体 | `.../game.zip` | 无 |
| H5 资源 | 无 | `.../h5/…` |
| ZIP 攻略 | `.../guide.zip` | `.../guide/…` |
| PDF 攻略 | `.../guide.pdf` | 无 |

## 行为与规则

**H5 上传与校验。**

- H5 只接受 `.zip`；上传时只校验、不解压。
- 包内根目录必须含 `index.html`。
- H5 也接受 `index.htm`，落盘统一成小写 `index.html`。
- 整包套一层唯一顶层目录时会自动剥掉前缀。
- ZIP 本体上限 128MB。
- 条目数上限 2000；单条解压后上限 64MB。
- 总解压量上限 256MB。
- 压缩比上限 200；只在解压后体积超过 1MB 时才看比例。
- 加密条目直接拒绝。
- 包内路径要归一化：禁反斜杠与控制字符。
- 路径还禁 `?` `#` `%` 与 `\ / : * ? " < > |` 里的非法字符。
- 路径禁绝对路径、`.`/`..` 段、以点或空格结尾的段。
- 路径禁 Windows 保留设备名，如 `CON` / `NUL` / `COM1`。
- 相对路径上限 512 字符、32 段。
- 校验只读 zip 中央目录，一个字节都不解。
- 入库没有清单表；早期 `game_h5_files` 表已删除。

**H5 按需解包。**

- 播放时 `RuntimeAssets.ensure()` 才把整包解到运行时根。
- 判据是运行时根里的入口文件在不在；在就直接返回。
- 不在才解到同层暂存目录 `.h5-{随机}`。
- 全部写完再用 `replace_tree` 整体替换，磁盘上要么没有、要么完整。
- 同一 `(类别, 游戏类型, 卡带ID)` 用进程内 `threading.Lock` 串行。
- 因此 gunicorn 必须保持 `--workers 1`。
- 多进程下锁不跨进程，并发 `os.replace` 覆盖非空目录会报 `ENOTEMPTY`。
- 解压前会再跑一次 `read_manifest()`。
- 数据根是宿主可写的普通目录，zip 可能在上传后被换掉。
- 解包失败会清掉暂存目录，再抛领域错误。
- 重传 zip / 改卡带ID / 删游戏时，由写路径显式 `drop_tree` 作废产物。
- 两个根相同时，这些清理退化成一次 `exists()` 检查。
- 运行时写失败（磁盘满、只读）返回 500，并提示检查运行时目录。
- zip 不在数据根（宿主手删）返回 404。
- 包损坏或不合规返回 400。

**H5 资源接口。**

- 读取走 `GET|HEAD /api/games/{id}/h5/{资源路径}`。
- 入口固定 `index.html`。
- 路径归一化后从运行时根直接取，没有清单表。
- MIME 由 `archive.guess_asset_mime()` 的显式表按后缀给。
- 这是唯一免登录的业务接口。
- 原因是沙箱 iframe 是不透明源，请求被浏览器按跨站处理。
- `SameSite=Lax` 的 session cookie 不会随这些请求带上。
- 加登录依赖只会让游戏加载不了 JS 与图片。
- 播放页本身仍要登录；未登录拿不到游戏 id 与入口地址。
- 响应强制 CSP `sandbox`，且不含 `allow-same-origin`。
- sandbox 还带 `allow-scripts allow-forms allow-modals allow-popups`。
- 另加 `nosniff`、`Referrer-Policy: no-referrer`、`ACAO: *`、`no-cache`。
- `no-cache` 避免重传后仍取到旧资源。
- 首次访问会触发解包写盘，代价上界是一份已上传内容的解压副本。
- 前端用嵌套 sandbox iframe 呈现，同样不带 `allow-same-origin`。
- 沙箱下没有 `localStorage` / `IndexedDB` / Web Worker。
- 所以 H5 不接入云存档。
- 在 H5 播放页按 `·` 只弹「HTML5 游戏不支持云存档。」。

**攻略的上传与形态。**

- 一个游戏可挂一份攻略，ZIP 静态站包或单个 PDF，二者互斥。
- ZIP 的入口固定包内根目录 `index.html`。
- 攻略不认 `index.htm`，与 H5 不同。
- 整包套单层目录会自动剥掉。
- PDF 只查后缀 `.pdf`、大小与文件头。
- PDF 大小上限 128MB。
- PDF 只认前 1024 字节内出现 `%PDF-`，不信任文件名与 Content-Type。
- PDF 原样存数据根，不做任何解包。
- 形态记在 `games.guide_kind`，取值 `""` / `"zip"` / `"pdf"`。
- 列表载荷的 `has_guide` 由 `guide_kind` 派生。
- 上传接口是 `POST /api/games/manage/{id}/guide`。
- multipart 里只有一个 `file`。
- 入口只在管理页编辑弹框的「上传封面」下方，新建弹框没有。
- ZIP 与 H5 共用同一套校验，同样只校验、不解压。
- ZIP 上限同 H5：128MB、2000 条、单条 64MB、总量 256MB、压缩比 200。
- 两种形态都在写任何字节之前全量校验。
- 上传一种会删掉另一种。
- 删旧形态失败时会把新文件也删掉再报错，避免两种攻略并存。
- 上传还会作废运行时根的旧解包产物。
- 上传攻略不动 `game_path` / `size` / `crc32`。
- 删除接口是 `DELETE /api/games/manage/{id}/guide`。
- 删除会一起清掉 ZIP/PDF 文件、运行时解包目录与 `guide_kind`。
- 删除是幂等的，没有攻略也返回 200。
- 删文件失败返回 500，且不清空 `guide_kind`，方便重试。

**攻略的读取与入口。**

- ZIP 攻略走 `GET|HEAD /api/games/{id}/guide/{资源路径}`。
- ZIP 攻略需登录，与 H5 的免登录不同。
- 首次查看时才解到运行时根 `.../guide/`，入口在就不再解。
- 读取时按后缀给 MIME，用同一张显式表。
- PDF 攻略走 `GET|HEAD /api/games/{id}/guide.pdf`。
- PDF 也从数据根流式返回，content-type 是 `application/pdf`。
- `Content-Disposition` 是 `inline`，交给浏览器内置查看器。
- 两条读取接口都需登录。
- 两条都只加 `nosniff` + `no-cache`，重传后立刻生效。
- 两条都不加 CSP `sandbox`。
- 原因是攻略是新标签页顶层导航打开的同源页面，照常带 cookie。
- 文件不存在或形态不符即 404。
- 入口在游戏中心卡片右键菜单「详情」下方的「攻略」。
- 没有攻略就不显示这一项。
- 用 `window.open(..., "_blank", "noopener")` 在新标签页顶层打开。
- `guide_kind=pdf` 打开 PDF 地址，否则打开 `index.html`。
- 重传 / 改卡带ID / 删游戏都随整个游戏目录处理。
- 攻略包里的链接一律写相对路径，绝对路径会指到站点根而 404。

**做攻略技能。**

- `make-guide` 的输入有两类：静态 HTML 攻略站，或 PDF/扫描件/MinerU 产物。
- 流程：镜像原站 → 剥站点外壳 → 转中文 → 自检 → 打成 zip 上传。
- 专有名词只在标题/词条位置写 `中文（原文）`。
- 自检脚本是 `python3 .claude/skills/make-guide/check_guide.py <目录>`。

## 边界与错误

- 宿主手动往数据根增删攻略文件不会自动反映到列表。
- 依据是库里的 `guide_kind`，不是磁盘扫描。
- 手动删掉攻略文件后，打开会 404。
- `guide_kind` 是 `zip` 但文件不在：404。
- `guide_kind` 是 `pdf` 但打开 ZIP 地址：404，反之亦然。
- ZIP 缺入口、含加密条目、路径越界、重名、超限都是 400。
- 解包时 zip 被换坏：400；zip 被删：404。
- 解包写运行时根失败：500，提示检查运行时目录是否可写、空间是否足够。
- Windows 下解包前会按运行时根算完整路径，超过 240 字符就 400。
- H5 资源免登录不表示 H5 播放页公开；播放页仍要登录。
- 攻略不是免登录例外，所有攻略读取与上传都要登录。

## 测试要点

- `tests/test_games.py` 覆盖 H5 上传、读取、二次访问不重解。
- 还覆盖并发只解一次、损坏/缺失 zip、缺入口、zip slip。
- 还覆盖 Windows 非法条目名、GBK 条目名、路径过长。
- 还覆盖大小写不敏感重名、单层目录剥离、重传整包替换。
- 还覆盖删游戏清理解包产物、各项上限。
- 攻略侧覆盖上传读取、二次查看不重解、单层目录剥离。
- 还覆盖缺入口、只认 `index.html`、坏路径、重名。
- 还覆盖 ZIP/PDF 互斥替换、PDF 头校验、PDF 需登录。
- 还覆盖删除 ZIP/PDF、无攻略时幂等删除、删文件失败保留状态。
- 还覆盖 `guide_kind` 在改卡带ID 后仍正确、列表不 stat 攻略文件。
- 还覆盖两个根分开时的删除，以及删游戏时一并清掉攻略。

## 相关文档

- [前端框架与交互](./frontend.md)
- [Windows 解压即用包](./delivery-windows.md)
- [架构设计](../architecture.md)
- [数据字典](../data_dict.md)
- [make-guide 技能](../../.claude/skills/make-guide/SKILL.md)
