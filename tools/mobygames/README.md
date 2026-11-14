# MobyGames 排行榜平台支持确认

确认日期：2026-11-10。

## 结论

- 本项目的 **34 个可玩机种全部**在 MobyGames 有平台页，并且都能按 Moby Score 排行。
- 对应 **37 个平台页**：`gb`、`ngp`、`ws` 三个机种在 MobyGames 被拆成两个平台，需要合并两页。
- `sega`、`mame` 是 EmulatorJS 的兜底键，不可玩，MobyGames 没有对应平台页，不参与排行榜。
- 直接访问 `https://www.mobygames.com/game` 是「Game Browser」，可以跨平台筛选；**按机种取排行榜用平台页更直接**。

## 排行榜从哪来

### 1. 平台页（推荐）

```
https://www.mobygames.com/platform/<slug>/sort:-moby_score/
```

- 默认就是 Moby Score 降序，`sort:-moby_score` 可省略。
- 每页 50 条。
- 其他排序：`sort:date`、`sort:title`。
- 分页段 `page:N` 是 **0 开始**：首屏没有分页段，第 2 页是 `page:1`，第 3 页是 `page:2`。
- 页面显示 `[ Page 1 of 34 ]` 这种 1 开始的名次，与 URL 的 N 差 1。
- 没有足够评分的游戏显示 `n/a`，排在已评分条目之后；小平台的榜单会被这类条目占掉大半。

组合形式示例：

```
https://www.mobygames.com/platform/nes/sort:-moby_score/page:1/
```

### 2. 全站 Game Browser

```
https://www.mobygames.com/game/?platform=<id>&order_by=moby_score
https://www.mobygames.com/game/?format=json&platform=<id>&order_by=moby_score
```

- 默认按 Moby Score 降序。
- 默认门槛：`min_critic_votes=5`、`min_user_votes=25`；平台页没有这个门槛。
- 每页 18 条，`perPage` 可调。
- `platform` 可重复传多个 id；平台 id 见下表。
- 这是 Vue 单页应用，`initial-values` 里带首屏数据；`format=json` 走同一套接口。

## 抓取脚本（用户脚本）

`mobygames-ranking.user.js` 是实际可用的抓取工具。它运行在**你自己的浏览器**里，
由页面同源请求游戏浏览器的 JSON 接口，不经过服务端，因此不会再触发自动化检测。

### 为什么不用服务端 / 无头浏览器

2026-11-10 实测：

- `curl` 与第三方 reader 直接 403。
- Playwright 无头、带头、patchright 都被 Cloudflare 拦在 “Just a moment...”。
- 带界面的自动化浏览器手动点 “Verify you are human” 后仍会立刻再次要求验证，形成循环。

所以本项目不提供服务端抓取脚本；浏览器用户脚本是唯一稳定的路线。

### 安装与使用

1. 在 Tampermonkey 里新建脚本，粘贴 `mobygames-ranking.user.js` 全部内容，保存。
   不想装 Tampermonkey 也可以：在已通过验证的 `https://www.mobygames.com/game/` 页面
   按 F12 打开控制台，粘贴整个文件内容回车，面板会直接出现。
2. 在浏览器里正常登录 MobyGames。脚本不保存账号密码。
3. 打开任意 `https://www.mobygames.com/` 页面（必须先通过 Cloudflare 验证），
   右上角出现「MobyGames 榜单抓取」面板。
4. 列表默认全选 34 个机种；可多选，或点「全选」「全不选」。
5. 点「选择目录」指定 CSV 保存位置（推荐，用 File System Access API）。
   不选目录时逐个触发下载，浏览器可能询问是否允许下载多个文件。
6. 点「开始」。脚本按机种逐个请求：
   - `POST /game/?format=json`
   - `platform=[MobyGames 平台 id]`
   - `sort=moby_score`（降序）
   - `perpage=50`
   - `min_critic_votes=5`、`min_user_votes=25`（与站点默认值一致）
7. 每个机种完成立即写 `<项目机种键>.csv`，列为：

   ```
   中文名,英文名,评分,卡带ID
   ```

   - `中文名`、`卡带ID`：脚本留空，由建索引前的人工整理流程补充。
   - `英文名`：MobyGames 标题原文；同一机种内唯一，重复标题保留评分最高的一条。
   - `评分`：接口返回的原始 double，如 `8.345679012345679`，不四舍五入。
   - 编码 UTF-8 带 BOM，CRLF，方便 Excel 直接打开。

### 停止规则

- 按 Moby Score 降序翻页。
- 某页出现第一条 `platforms[].moby_score` 为 `null` 的游戏时，当前 MobyGames 平台页立即停止。
- 合并型机种（`gb`、`ngp`、`ws`）两个平台页分别按上述规则拉取，最后合并、按 `game_id` 去重、
  按评分重排。

### 异常处理

- 请求失败（网络错误或 HTTP 错误）固定等 5 秒重试，最多 10 次。
- 每次失败都会把 HTTP 状态、状态文本和响应体前 400 字符打到日志里。
- 脚本会依次尝试四种请求方式：JSON POST、FormData POST、GET、带 `X-CSRF-TOKEN` 头的 JSON POST。
  某一种成功后，后续优先用它。
- POST 全部返回 503 时，GET 方式会改从榜单 HTML 的 `initial-values` 解析；
  日志会打印服务端实际返回的 `perPage`，如果被改成 18，说明 `perpage=50` 没有生效。
- 面板上的「诊断」按钮会对 NES 第 1 页逐个测试四种方式，并打印结果，用来定位 503 之类的问题。
- 遇到 Cloudflare 验证时脚本暂停，完成验证后点「继续」。
- 每个机种完成即落盘；中断后只勾选未完成的机种再跑即可。

## 平台对照表

按项目机种词表顺序。游戏数来自 MobyGames 平台总表的 2026-09-12 快照，只用于估算规模。

| 项目 id | 显示名 | MobyGames 平台 | 平台 id | 游戏数 |
|---|---|---|---:|---:|
| `nes` | 任天堂 FC | [NES](https://www.mobygames.com/platform/nes/) | 22 | 1,658 |
| `snes` | 任天堂 SFC | [SNES](https://www.mobygames.com/platform/snes/) | 15 | 1,335 |
| `n64` | 任天堂 N64 | [Nintendo 64](https://www.mobygames.com/platform/n64/) | 9 | 393 |
| `gb` | 任天堂 GB/GBC | [Game Boy](https://www.mobygames.com/platform/gameboy/)、[Game Boy Color](https://www.mobygames.com/platform/gameboy-color/) | 10 / 11 | 889 + 766 |
| `gba` | 任天堂 GBA | [Game Boy Advance](https://www.mobygames.com/platform/gameboy-advance/) | 12 | 1,283 |
| `nds` | 任天堂 NDS | [Nintendo DS](https://www.mobygames.com/platform/nintendo-ds/) | 44 | 2,404 |
| `vb` | 任天堂 VB | [Virtual Boy](https://www.mobygames.com/platform/virtual-boy/) | 38 | 28 |
| `segaMD` | 世嘉 MD | [Genesis](https://www.mobygames.com/platform/genesis/) | 16 | 1,074 |
| `segaGG` | 世嘉 GG | [Game Gear](https://www.mobygames.com/platform/game-gear/) | 25 | 369 |
| `segaMS` | 世嘉 SMS | [SEGA Master System](https://www.mobygames.com/platform/sega-master-system/) | 26 | 360 |
| `segaCD` | 世嘉 CD | [SEGA CD](https://www.mobygames.com/platform/sega-cd/) | 20 | 216 |
| `sega32x` | 世嘉 32X | [SEGA 32X](https://www.mobygames.com/platform/sega-32x/) | 21 | 41 |
| `segaSaturn` | 世嘉 土星 | [SEGA Saturn](https://www.mobygames.com/platform/sega-saturn/) | 23 | 1,161 |
| `psx` | 索尼 PS1 | [PlayStation](https://www.mobygames.com/platform/playstation/) | 6 | 3,251 |
| `psp` | 索尼 PSP | [PSP](https://www.mobygames.com/platform/psp/) | 46 | 2,323 |
| `pce` | 日电 PCE | [TurboGrafx-16](https://www.mobygames.com/platform/turbo-grafx/) | 40 | 308 |
| `pcfx` | 日电 PC-FX | [PC-FX](https://www.mobygames.com/platform/pc-fx/) | 59 | 62 |
| `ngp` | SNK NGPC | [Neo Geo Pocket](https://www.mobygames.com/platform/neo-geo-pocket/)、[Neo Geo Pocket Color](https://www.mobygames.com/platform/neo-geo-pocket-color/) | 52 / 53 | 10 + 76 |
| `ws` | 万代 WS | [WonderSwan](https://www.mobygames.com/platform/wonderswan/)、[WonderSwan Color](https://www.mobygames.com/platform/wonderswan-color/) | 48 / 49 | 108 + 50 |
| `atari2600` | 雅达利 2600 | [Atari 2600](https://www.mobygames.com/platform/atari-2600/) | 28 | 666 |
| `atari5200` | 雅达利 5200 | [Atari 5200](https://www.mobygames.com/platform/atari-5200/) | 33 | 95 |
| `atari7800` | 雅达利 7800 | [Atari 7800](https://www.mobygames.com/platform/atari-7800/) | 34 | 83 |
| `jaguar` | 雅达利 Jaguar | [Jaguar](https://www.mobygames.com/platform/jaguar/) | 17 | 111 |
| `lynx` | 雅达利 Lynx | [Lynx](https://www.mobygames.com/platform/lynx/) | 18 | 100 |
| `coleco` | ColecoVision | [ColecoVision](https://www.mobygames.com/platform/colecovision/) | 29 | 168 |
| `3do` | 松下 3DO | [3DO](https://www.mobygames.com/platform/3do/) | 35 | 256 |
| `c64` | 康懋达 64 | [Commodore 64](https://www.mobygames.com/platform/c64/) | 27 | 5,750 |
| `c128` | 康懋达 128 | [Commodore 128](https://www.mobygames.com/platform/c128/) | 61 | 30 |
| `pet` | 康懋达 PET | [Commodore PET/CBM](https://www.mobygames.com/platform/pet/) | 77 | 834 |
| `plus4` | 康懋达 Plus/4 | [Commodore 16, Plus/4](https://www.mobygames.com/platform/commodore-16-plus4/) | 115 | 514 |
| `vic20` | 康懋达 VIC-20 | [VIC-20](https://www.mobygames.com/platform/vic-20/) | 43 | 968 |
| `amiga` | Amiga | [Amiga](https://www.mobygames.com/platform/amiga/) | 19 | 3,993 |
| `dos` | DOS | [DOS](https://www.mobygames.com/platform/dos/) | 2 | 8,462 |
| `arcade` | 街机 | [Arcade](https://www.mobygames.com/platform/arcade/) | 143 | 3,651 |

机种页的 `sort:-moby_score` 排行页就是把上表链接改成：

```
https://www.mobygames.com/platform/<slug>/sort:-moby_score/
```

## 需要合并或特别注意的机种

- `gb` → Game Boy + Game Boy Color。两页各自排行，合并后要重新排序；同名游戏按 MobyGames game id 去重。
- `ngp` → Neo Geo Pocket + Neo Geo Pocket Color。两页合计约 86 款，NGP 侧只有 10 款。
- `ws` → WonderSwan + WonderSwan Color。两页合计约 158 款。
- `pce` → MobyGames 只有 TurboGrafx-16 一页；`SuperGrafx`（id 127，7 款）是独立平台。项目把 `.sgx` 归入 `pce`，如需覆盖，要额外并入 SuperGrafx。
- `segaMD` → MobyGames 平台名是 `Genesis`；页面正文明确写 “known as the Mega Drive outside North America”，日版 MD 不会另开平台。
- `arcade` → MobyGames 只有一个 `Arcade` 平台，没有 CPS1/CPS2/NEOGEO 子板区分。
- `dos`、`amiga`、`c64` 的条目远多于卡带机，榜单规模大，抓取时要靠名次区间截断。

## 访问限制

- 2026-11-10 实测：`curl` 与第三方 reader 都拿到 Cloudflare 的 403 `Just a moment...`。
- 因此**服务端直接抓取不可行**；要抓只有两条路：
  1. 浏览器端用户脚本，做法同 `tools/vimm-grab.user.js`（在页面上下文里取 DOM / 同源请求）。
  2. 带真实浏览器指纹的抓取环境，过 Cloudflare 校验后再取。
- 本文件的平台清单与计数来自 Wayback Machine 的快照：
  - 平台总表：2026-09-12。
  - NES 平台页：2026-11-01；Genesis：2026-06-19；PC-FX：2026-04-11；Virtual Boy：2026-05-01。
  - `/game/` Game Browser：2026-11-01。

## 与榜单 CSV 的关系

MobyGames 的排行行只提供：MobyGames game id、标题、发行年份、类型、Moby Score。**没有卡带 ID**。

- 脚本输出的文件名就是项目机种 id（`nes.csv`、`segaMD.csv`…），与
  `backend/search/rankings/README.md` 的契约一致，建索引时直接按文件名识别机种。
- 中文名与卡带 ID 由脚本写成空列，需另找来源（中文名可按英文名整理，卡带 ID 如 Vimm's Lair）
  后人工补入。
- **重新跑脚本会覆盖已有中文名与卡带 ID**，重抓后需要重新回填。
- MobyGames 的平台名不再写入 CSV；平台对应关系只用于请求接口，见上面的平台对照表。

