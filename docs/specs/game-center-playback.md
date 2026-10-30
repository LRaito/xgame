# 游戏中心播放

## 范围与权威

- 本规格覆盖 Flash、HTML5、主机 ROM 三类播放器与播放页交互。
- 内容包括入口分派、播放接口、标题栏、加速模式、窗口倍率、机壳、NDS 布局与快捷键。
- 播放页代码权威：`frontend/src/views/games/flash-player.vue`、`h5-player.vue`、`emulator-player.vue`。
- 机壳几何权威在 `emulator-player.vue` 的 `SHELLS` 表与 `frontend/src/assets/shells/` 的素材。
- 帧缓冲基准权威在 `frontend/src/constants/emulatorScreens.js` 的 `EMU_NATIVE`、`NDS_NATIVE`。
- 引擎侧 RPC 权威在 `frontend/public/emulator-host.html` 的 `window.__ejsRpc`。
- 截图与图集的完整规则见 [`./game-assets.md`](./game-assets.md)。
- 存档、设置、最近游玩与统计的完整规则见 [`./game-saves-stats.md`](./game-saves-stats.md)。

## 数据与路径

| 播放类型 | 前端路由 | 实现 |
|---|---|---|
| Flash | `/games/flash/{id}` | Ruffle |
| HTML5 | `/games/h5/{id}` | 嵌套 sandbox iframe |
| 主机 ROM | `/games/play/{id}` | 宿主 iframe + EmulatorJS |

- 播放路径只有一份实现：`play_path(game_type, id)`，列表载荷的 `path` 也用它。
- 主机播放页外层是 SPA 壳，内嵌 `/emulator-host.html`，EmulatorJS 官方要求 iframe 隔离。
- 引擎资产由 `frontend/scripts/fetch-emulatorjs.mjs` 在构建期拉到 `frontend/public/emulatorjs/`。
- 引擎资产以固定版本随镜像发布，nginx 与 `static_site.py` 按 immutable 缓存，运行时不依赖外网。
- NDS 使用 melonDS 核，BIOS 是用户自备的 `frontend/public/emulatorjs/bios/nds.zip`，不进 git。
- BIOS 包根目录需含 `bios7.bin`、`bios9.bin`、`firmware.bin`。
- `emulatorjs/bios/` 前缀在 nginx 与 `static_site.py` 里单独 no-cache。
- 宿主页启动前对 BIOS 做 HEAD 预检；缺失时给中文提示，不静默黑屏。
- H5 解包产物在运行时根的 `game/{类型}/{卡带ID}/h5/`，首次访问资源接口时按需生成。
- 攻略解包产物在运行时根的 `game/{类型}/{卡带ID}/guide/`，首次访问攻略资源时按需生成。

| 接口 | 用途 | 登录 | 内容类型 |
|---|---|---|---|
| `GET/HEAD /api/games/{id}/play` | 本体下载 | 需要 | `.swf` 用 Flash 值，其余 `octet-stream` |
| `GET /api/games/{id}/cover` | 封面预览 | 需要 | inline；`?download=1` 附件 |
| `GET/HEAD /api/games/{id}/h5/{路径}` | H5 资源 | **不需要** | 按后缀现算 |
| `GET/HEAD /api/games/{id}/guide/{路径}` | ZIP 攻略资源 | 需要 | 按后缀现算 |
| `GET/HEAD /api/games/{id}/guide.pdf` | PDF 攻略 | 需要 | `application/pdf` inline |

- 本体文件名取落盘名 `game.{后缀}`；文件不存在或本体未上传时返回中文 400/404。
- 主机播放页会先对本体的 URL 发 HEAD 探测，所以 play 接口同时提供 HEAD。
- H5 资源接口是唯一免登录的业务接口，原因是沙箱 iframe 带不上 SameSite=Lax 的 cookie。
- H5 响应强制 CSP `sandbox`，不含 `allow-same-origin`；另加 `nosniff`、`no-referrer`、`ACAO: *`、`no-cache`。
- 攻略资源在新标签页顶层导航打开，cookie 正常带上，所以**必须登录**。
- 攻略响应只加 `nosniff` 与 `no-cache`，**不加** CSP sandbox。
- PDF 攻略直接从数据根流式返回，交给浏览器内置查看器就地渲染。

## 行为与规则

- **三类播放。**
  - Flash 用 Ruffle 播放 `.swf`。
  - H5 用不带 `allow-same-origin` 的 sandbox iframe。
  - 主机 ROM 用 EmulatorJS。
- 播放页会核对游戏类型，误入其它类型时重定向到对应播放路由。
- H5 iframe 的 sandbox 值：
  `allow-scripts allow-forms allow-modals allow-popups allow-pointer-lock allow-downloads`。
- H5 iframe 还设置 `allow="autoplay; fullscreen; gamepad"` 与 `referrerpolicy="no-referrer"`。
- **开始手势。** 刷新或直链进入没有用户手势时，三个播放页都先显示「开始游戏」。
- 点击「开始游戏」后才挂载播放器；这样音频能正常启动。
- 「真正拉起播放器」的那一刻，三个播放页都上报最近游玩并开始计时。
- 最近游玩与计时的细节见 [`./game-saves-stats.md`](./game-saves-stats.md)。

- **模拟器标题栏。** 按钮自左向右固定为：加速模式、截图、保存配置、窗口倍率、显示机壳、存档管理。
- 「显示机壳」只对 GBA、FC、GBC、NDS 出现。
- 加速模式与显示机壳使用固定文案 + 点亮高亮，不随状态改文案。
- 「保存配置」把键位、选项与金手指整块上传到账号；引擎只在启动时读一次设置。
- 模拟器设置的完整规则见 [`./game-saves-stats.md`](./game-saves-stats.md)。

- **加速模式。** 按一次持续加速，再按恢复；开关的是引擎自己的 Fast Forward 设置项。
- 调用链为 `__ejsRpc.setFastForward` → `changeSettingOption("fastForward", …)`。
- `changeSettingOption` 经设置行监听触发 `menuOptionChanged` → `handleSpecialOptions`。
- 该链路会同时改掉 `isFastForward` 与内核的 `toggle_fastforward`，并调用 `saveSettings()`。
- 因此它与引擎设置菜单里的那一项是同一份状态，也会随「保存配置」进账号。
- 设置行被 `EJS_hideSettings` 隐藏时监听不会注册，宿主页会补一次 `menuOptionChanged`。
- 按钮亮灭由每秒轮询读 `__ejsRpc.fastForward` 对齐；用户在引擎菜单里改过也认。
- 加速模式**不碰任何按键**：关着时用户绑的快进键按住即加速、松手恢复。
- 开着时按住该快进键临时回到正常速度，这是引擎自身语义。
- 倍率用引擎默认的 3.0×；要改倍率去引擎设置菜单的 Fast Forward Ratio。

- **窗口倍率。** 选择器是 `frontend/src/components/games/EmuWindowSelect.vue`，不是原生下拉。
- 面板就地渲染在标题栏内；鼠标移进面板仍算在标题栏内，标题栏不会收起。
- 普通机种是两列矩阵：行 = 倍率与「适应窗口」，列 = 显示比例。
- 倍率可选 `1×`、`1.5×`、`2×`、`2.5×`、`3×`、`3.5×`、`4×`。
- 只有 FC 画第二列「4:3」；其它机种只有「像素完美」一列。
- 取值格式为 `<倍率>|<显示比例>`，如 `2|pp`、`1.5|wide`、`fit|pp`。
- 普通机种的值存 localStorage 的 `games.emu.window`；老值只有倍率时按像素完美读。
- NDS 例外为三列 = 双屏、单屏、左右三种屏幕布局。
- NDS 每列独立记住自己的倍率或「适应窗口」，存 `games.emu.nds.window`。
- 点 NDS 某列的格子，除了记倍率，还会顺便切到那个屏幕布局。
- 面板尺寸按帧缓冲**高度**乘倍率换算，宽度再按舞台宽高比推出。
- 面板里括号中的尺寸是真实窗口像素尺寸，不是帧缓冲像素数。
- 基准分辨率为：NES 256×224、SNES 256×224、GB/GBC 160×144、GBA 240×160。
- 基准还含：NDS 默认 256×438、MD 320×224、GG 160×144、SMS 256×192。
- NDS 的 `NDS_NATIVE` 另给 `top` 256×192、`side` 585×192。
- **舞台长宽比取引擎上报的显示宽高比**，即 `__ejsRpc.videoInfo().aspect`。
- 不能用帧缓冲比例代替：引擎按内核上报的 aspect 等比摆放画面，画布填不满处即黑边。
- 引擎就绪前或取不到 aspect 时，用当前模式的帧缓冲比例兜底。
- 就绪后每秒跟随一次；用户改内核 aspect 选项时舞台也会跟着变。
- 引擎就绪后播放页会按选中模式纠正一次显示比例；窗口选择器是显示比例的唯一入口。
- 「适应窗口」模式下，要塞进可用空间的是画面；开着机壳时改为整张机壳。
- NDS `top`、`side` 的适应窗口按合成后的 `canvas` 尺寸计算。

- **FC 两套显示比例。** 左列「像素完美」是 8:7，1× 窗口为 256×224。
- 像素完美模式设 `fceumm_aspect = "PP"`，并保留内核默认的上下各裁 8 行过扫描。
- 其帧缓冲为 256×224；显示比例为 256:224。
- 右列「4:3」设 `fceumm_aspect = "4:3"`，并关掉过扫描裁切。
- 4:3 模式必须使用完整 240 行帧，帧缓冲为 256×240。
- 4:3 的 1× 窗口为 320×240，显示比例为 4:3。
- 显示比例模式经 iframe 的 `?ratio=` 传入；运行中切换走 `__ejsRpc.setDisplayMode`。

- **显示机壳。** 把机壳图盖在画面上，只从透明屏幕洞露出游戏画面。
- 对齐规则：按「洞（多洞取外接矩形）宽 = 画面宽」放大并偏移。
- 画面尺寸一变（换倍率、缩窗口、全屏），机壳自动跟着缩放。
- `SHELLS` 表每项统一用 `holes` 数组：单洞机种一个元素，NDS 两个。
- 渲染走 `parts`：每块一个固定定位外层 + 负偏移 `img` 裁出 crop 区域。
- 没有 `parts` 的机种整图一块，输出与旧版逐像素一致。
- 机壳层 `pointer-events: none`，不会挡住引擎操作。
- 机壳定位必须用 `position: fixed`，坐标从 `getBoundingClientRect` 读取并随滚动/缩放/全屏重算。
- 用 absolute 会被 `.game-shell__body` 的 `overflow: auto` 裁掉并顶出滚动条。
- 倍率调大后超出浏览器视口的部分看不见即可；不裁剪、不隐藏、不提示。
- 机壳偏好存 localStorage 的 `games.emu.shell`；换到没有机壳的机种时不生效。

| 机种 | 素材 | 整图尺寸 | 洞或部件几何 |
|---|---|---|---|
| GBA | `gba-shell.png` | 3840×2160 | 洞 (960,440) 1920×1280 |
| GB/GBC | `gbc-shell.png` | 2131×1996 | 洞 (423,338) 1285×1156.5 |
| FC 像素完美 | `nes-shell.png` | 1326×1237 | 洞 (121,146.3333) 1084×948.5 |
| FC 4:3 | `nes-shell-43.png` | 1326×1077 | 洞 (121,125) 1084×813 |
| NDS 双屏 | `nds-shell.png` | 1080×1920 | 两洞 (120,177)、(120,984) 各 840×630 |
| NDS 单屏 | `nds-shell.png` | 1080×1920 | 画布 1080×807；洞 (120,177) |
| NDS 左右 | `nds-shell.png` | 1080×1920 | 画布 2160×1113；两洞 x=120、1200 |

- GBA 洞 1920×1280 = 精确 3:2，正是 GBA 原生 240×160，且居整图正中。
- GBC 洞 1285×1156.5 = 10:9，正是 GB/GBC 的 160×144。
- GBC 原素材左右留白差 17px，入项目前从左边裁掉 17px 让屏幕左右对称。
- GBC 剩下半个像素差按小数声明，不拉伸图画。
- FC 像素完美素材是把原素材屏幕段纵向拉长 7/6 得到的。
- 拉长后洞从 1084×813 变为 1084×948.5 = 256:224。
- 下方 121 行控制条（扬声器、按键、指示灯）保持等比，不被压扁。
- 最后裁掉四周透明留白；只有顶部 10 行是空的，所以洞的 y 是原坐标 × 7/6 再减 10。
- FC 4:3 素材就是原素材本身，只裁掉顶部 9 行透明留白。
- NDS 两个洞各 840×630 = 精确 4:3，256×192 的屏幕完整铺满、不被机壳遮挡。
- NDS 两洞之间是 177px 铰链带，外接矩形 840×1437 = 256:438。
- 外接矩形对应双屏帧缓冲 192 + 54 gap + 192；gap 54 由几何反推。
- NDS 原素材每块屏幕左右各 8px 被补成机身色，洞才从 856 宽收到 840。
- NDS `top` 只取上图 crop y=0..807，不显示铰链。
- NDS `side` 上半取 crop(0,0,1080,807)，下半取 crop(0,984,1080,936)。
- `side` 的下半 offset 为 x=1080、下移 177，使两洞顶部对齐；铰链带不出现在任何一块。
- `side` 合成画布 2160×1113，对应 585×192 帧缓冲的 gap 73。
- 换机壳图必须同步改 `SHELLS` 几何；NDS 还要同步改 `EMU_NATIVE.nds` 与 `NDS_NATIVE`。
- 机壳图必须 `import` 取值，让 Vite 生成带内容哈希的 URL；放 public 会缓存旧图。

- **NDS 屏幕布局。** 布局固定为 `dual`、`top`、`side`，循环顺序也是这个。
- `dual` = 上下双屏，`Top/Bottom` + gap 54。
- `top` = 只显示上屏，`Top Only`，帧缓冲 256×192。
- `side` = 左右双屏，`Left/Right` + gap 73，帧缓冲 585×192。
- 模式经 iframe 的 `?nds=` 传入；运行中切换走 `__ejsRpc.setNdsLayout`。
- 切换时先本地重排舞台与机壳，再由宿主页改内核变量并等引擎上报新几何。
- 失败会回滚到原布局并给中文提示。
- 不自动重启内核：宿主页返回 `needsRestart` 时只提示，不重建 iframe，以免丢进度。
- `melonds_screen_layout` 与 `melonds_screen_gap` 已从引擎设置菜单隐藏。
- 布局偏好存 localStorage 的 `games.emu.nds.screen`。

- **NDS iframe 例外。** NDS 的 iframe 抬到机壳之上：`z-index: 6` > 机壳的 `5`。
- iframe 文档与引擎容器透明，引擎主画布用 `mask-image` 只保留两块屏幕区域。
- 宿主页在 `EJS_onGameStart` 后给 `<html>` 挂 `x-nds-passthrough`。
- 这样引擎设置弹框跨过铰链时显示在机壳上面。
- 其它机种的 iframe 仍不透明，机壳照旧盖在画面上。

- **快捷键。** 模拟器播放页在父页面与宿主 iframe 的 `window` 各挂一份 `keydown`。
- iframe 那份用捕获阶段，避免被引擎自己的按键处理吞掉。
- 快捷键在输入框、引擎菜单/设置面板、弹框开着或引擎未就绪时不响应。

| 快捷键 | 作用 | 适用 |
|---|---|---|
| `Ctrl+Shift+S` | 截图 | 模拟器 |
| `·`（Backquote） | 捕捉当前进度并同步云端 | 三个播放页 |
| ``Alt + ` ``（Backquote） | 打开存档管理 | Flash、模拟器 |
| `-` / `=` | NDS 屏幕布局上一个/下一个 | 模拟器 |
| `回车` | 载入本地存档并交出键盘焦点 | 模拟器 |

- `Ctrl+Shift+S` 与标题栏「截图」按钮同效；F12 是浏览器开发者工具保留键，页面拦不住。
- 截图截下后不直接下载，先走确认框；完整流程见 [`./game-assets.md`](./game-assets.md)。
- `·` 用 `event.code === "Backquote"` 匹配，且不带任何修饰键。
- `·` 命中后先捕捉当前进度，再上传云端，成功只弹一句「已同步至云端」。
- Flash 的 `·` 会先弹二次确认，因为落盘必须先重启游戏；细节见 [`./game-saves-stats.md`](./game-saves-stats.md)。
- H5 的 `·` 只弹「HTML5 游戏不支持云存档。」
- ``Alt + ` `` 必须按住 Alt；存档管理已开或截图确认框开着时不响应。
- `-` / `=` 认 `event.code` 的 `Minus` / `Equal`，即 Backspace 左边两个物理键。
- 小键盘的 `-` / `+` 不生效；`+` 就是 `Shift + =`，按不按 Shift 都算下一个。
- `-` / `=` 带 Ctrl/Alt/Meta 时不生效；焦点在输入框或引擎菜单/设置面板里时不抢。
- 回车优先载入最近一份本地存档；没有本地存档时不拦键，回车照常传给引擎。
- 无论有没有存档，回车后都会把焦点交给模拟器（已选中时不动）。
- 焦点在按钮、链接、下拉、输入框或弹框里时，回车不抢。
- H5 没有存档管理，也没有 ``Alt + ` `` 与 `-` / `=`。

- **全屏与光标。** 三个播放页全屏时（原生全屏或 F11），鼠标静止 3 秒隐藏光标并收起标题栏。
- 任何鼠标活动立即恢复光标并重新计时；只认鼠标，键盘操作不算活动。
- 模拟器把 iframe 内的指针活动转给 `GameShell`，并给宿主 `<html>` 挂 `x-cursor-hidden`。
- 因此模拟器全屏时 iframe 内的光标也会一起隐藏。
- H5 是沙箱不透明源，父页拿不到 iframe 文档，画面内光标无法隐藏。

## 边界与错误

- 引擎未就绪时，加速、截图、窗口与存档管理按钮不可用或返回中文提示。
- 加速切换失败返回「切换加速模式失败。」；引擎未开始时提示「请先开始游戏再切换加速模式。」。
- 截图失败返回「截图失败，请重试。」；没有可截画面时宿主页返回中文错误。
- NDS 布局切换失败回滚并提示「切换屏幕布局失败。」。
- NDS BIOS 缺失时播放页给中文安装提示，不会只留黑屏。
- H5 资源解包或读取写盘失败返回 500，并提示检查运行时目录是否可写、空间是否充足。
- 攻略资源与 PDF 文件不存在、形态不符时返回 404。
- 本体未上传时 play 接口返回 400「游戏文件尚未上传。」。
- H5 沙箱下没有 localStorage 与 Web Worker，因此 H5 不接入云存档。
- H5 画面内光标无法隐藏；H5 焦点在游戏里时父页也收不到 `·`。
- 机壳超出视口不裁剪、不隐藏、不产生滚动条；这是刻意的观感。
- 快捷键不会在输入框、引擎设置面板、确认框或存档弹框里抢键。

## 测试要点

- 后端：`python -m pytest tests/test_games.py -k "emulator_types_upload_and_play or play_path"`。
- 上述用例覆盖各主机类型按扩展名入库、列表 `path` 与播放路由一致、本体 `octet-stream` 下发。
- 后端：`python -m pytest tests/test_static_site.py -k "emulatorjs or bios"`。
- 上述用例覆盖引擎资产 immutable、BIOS 前缀 no-cache、BIOS 缺失时 404。
- 后端：`python -m pytest tests/test_platforms.py`，确认机种 id 与 EmulatorJS system key 一致。
- 手工：三种播放页都能从游戏中心进入，误入其它类型会跳到正确路由。
- 手工：H5 首次播放触发解包，重复播放不再解包；沙箱内拿不到本站 cookie。
- 手工：模拟器标题栏按钮顺序与文案正确，显示机壳只在 GBA/FC/GBC/NDS 出现。
- 手工：加速模式点亮后持续加速，重进游戏保持；用户自绑的快进键仍按引擎语义工作。
- 手工：窗口选择器每种倍率/比例显示真实尺寸；FC 两列切换时画面、机壳、窗口同时变。
- 手工：NDS 三种布局用 `-` / `=` 循环，舞台、机壳、窗口选择器三列同步。
- 手工：每种机种的机壳洞与画面四边对齐，换倍率/全屏后仍对齐。
- 手工：截图、`·`、``Alt + ` ``、回车、NDS 布局快捷键在焦点位于输入框/弹框时不响应。
- 手工：全屏静止 3 秒光标与标题栏一起消失，动一下鼠标立即恢复；F11 同样成立。

## 相关文档

- [`../architecture.md`](../architecture.md)
- [`./game-assets.md`](./game-assets.md)
- [`./game-saves-stats.md`](./game-saves-stats.md)
- [`../../AGENTS.md`](../../AGENTS.md)
