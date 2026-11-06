# 机型简史

本文件回答：36 个游戏类型的图文介绍页如何组织、内容与图片从哪来。

## 职责

- 提供「机型简史」页面：6×6 网格按年份展示 36 个游戏类型。
- 提供每个类型的详情页：概览、参数、历史、游戏机图、卡带/载体图。
- 维护一份只读的静态介绍数据，不涉及数据库、上传与播放。

## 关键接口

- 页面：`frontend/src/views/platforms/index.vue`、`detail.vue`。
- 图片区组件：`frontend/src/components/platforms/IntroGallery.vue`。
- 数据：`frontend/src/constants/platformIntros/index.js`。
- 图片索引：`frontend/src/constants/platformIntros/images.js`（生成文件）。
- 抓取脚本：`scripts/build-platform-intros.py`。
- 路由：`/platforms`、`/platforms/:id`。

## 依赖

- 后端 `/api/games/status` 的 36 个类型，经 `store/gameTypes` 提供 id / label / kind。
- 中文维基百科与英文维基百科的正文（CC BY-SA 4.0）。
- Wikimedia Commons 的图片，优先 Evan-Amos（Vanamo）公有领域图库。
- 构建期不需要联网；抓取脚本只在人工维护内容时运行。

## 数据与路径

- 数据按年份升序写死在 `constants/platformIntros/index.js`，不属于后端词表。
- 36 个 id 必须与 `backend/games/service.py::GAME_TYPES` 完全一致：
  `flash`、`h5` 加 34 个可玩机种。
- 图片在 `frontend/src/assets/platforms/<id>/console-N.webp` 与 `media-N.webp`。
- `images.js` 显式 import 每张图，导出 key → URL 的 `PLATFORM_IMAGES`。
- 图片统一宽 900px、WebP 质量 80；只保留自由许可（PD / CC0 / CC BY / CC BY-SA）。
- 原始抓取文本与署名缓存写在 `/tmp/platform-intros-raw/`，不进仓库。

## 行为与规则

**首页。**

- 网格固定 6 列；≤1200px 四列、≤900px 三列、≤600px 两列。
- 每格一张游戏机图，下方一行「年份 + 机种名」。
- 机种名从 `store/gameTypes` 取，页面不手写 label。
- 整卡是 `router-link`，点击进入 `/platforms/:id`。
- `flash` 用仓库现有的 `assets/flash-logo.png`；`h5` 用 Commons 的 HTML5 标志。

**详情页。**

- 固定顺序：概览 → 参数速览 → 历史 → 游戏机图 → 卡带/载体图。
- 历史按段落渲染，不使用 `v-html`，也不引入 Markdown 依赖。
- `flash` / `h5` 不是实体机：图片区标题改为「平台形象」「载体形式」。
- 图片缺失时整块不渲染；不拿非自由许可图片凑数。
- 点击图片打开大图预览：Escape 关闭，左右键切换，遮罩点击关闭。

**内容维护。**

- 文案按「诞生背景 → 硬件与市场 → 影响与遗产」整理，数字以维基为准。
- 英文维基只用于中文条目缺失或过短的类型。
- 新增机种时改三处：`platforms.py`、`MANIFEST`、`platformIntros/index.js`。
- 重跑：`python scripts/build-platform-intros.py`；
  断点续跑加 `--skip-done`；只重建索引加 `--write-images-js`。

## 边界与错误

- 未知 id 进详情页显示 `AppEmpty`，不抛错。
- 维基标题必须用规范标题；重定向标题会返回错误页。
- 接口限流 429 时脚本按 `Retry-After` 退避，仍失败就中断整批。
- 页面只做展示，不影响机种词表、上传判定与播放。

## 测试要点

- 前端没有单元测试，验证靠 `cd frontend && npm run lint` 与 `npm run build`。
- 生成脚本自带断言：36 个 id 必须与 `GAME_TYPES` 一致。
- 手工验收：首页 36 格、窄屏两列、任选机型看图片、未知 id 显示空状态。

## 相关文档

- [机种词表](../common/platforms.md)
- [前端框架与交互](./frontend.md)
