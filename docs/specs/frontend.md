# 前端框架与交互

## 范围与权威

- 前端是 Vue 3 SPA，UI 底座用 Element Plus。
- 只用 JavaScript，不加 TypeScript。
- 界面文案全中文，不加 i18n / 多语言切换。
- FastAPI 只返回 JSON，HTML 由 Vue 路由负责。
- 路由表是 `frontend/src/router/index.js`。
- 登录守卫是 `frontend/src/permission.js`。
- 唯一 axios 实例是 `frontend/src/utils/request.js`。
- 接口封装在 `frontend/src/api/`，按业务域导出 `xxxAPI`。
- 设计背景见 `../architecture.md` 的「分层规则」与「项目结构」。
- 编码约定以根目录 `AGENTS.md` 为准。

## 数据与路径

- 分层固定为：页面 `views/` → `api/*` → `utils/request.js` → FastAPI。
- 新增接口只改 api 层与后端 router，不碰 `request.js`。
- 响应信封：成功 `{ok:true,data:…}`，失败 `{ok:false,message:"中文"}`。
- 跨模块 UI 组件放 `src/components/common/`。
- 游戏专用组件放 `src/components/games/`。
- 页面组件放 `src/views/`，按业务分目录。
- 样式 token 在 `src/styles/index.css` 的 `--app-*` 变量。
- 同一份样式文件覆盖 Element Plus 的主色、危险色、圆角与按钮尺寸变量。
- Vite 别名 `@components` 指向 `src/components`。
- 开发时 Vite 的 `/api` 与 `/health` 代理到 `:8910`。
- 小件组件在 `main.js` 全局注册；弹窗按需引入。

## 行为与规则

**请求与登录态。**

- `request.js` 是唯一 axios 实例，`withCredentials: true`，超时 60 秒。
- 请求拦截器注入 `X-CSRFToken`。
- 普通对象请求体自动补 `Content-Type: application/json`；`FormData` 不补。
- CSRF token 由 `GET /api/csrf` 取，`ensureCsrf()` 负责写入。
- 响应拦截器拆信封：`ok` 为真返回 `data`，否则弹中文错误并 reject。
- 失败统一 reject 一个带 `reported` 标记的 `Error`。
- `reported=true` 表示拦截器已经弹过提示。
- 页面 catch 要补提示时写成 `if (!err.reported) ElMessage.error(...)`。
- `notShowError: true` 可关掉拦截器的自动弹窗。
- 401 单飞跳登录，带上 `redirect` 查询参数。
- 401 跳转有 1.5 秒重入保护，避免并发请求反复跳。
- `skipAuthRedirect: true` 可跳过 401 跳转，供 best-effort 上报使用。
- 不把 token 写进 `localStorage`；登录态靠 HttpOnly session cookie。
- `permission.js` 白名单只有 `/login`。
- 未登录时先 `fetchMe()`；会话 cookie 还在就直接进入。
- 取不到会话就跳 `/login` 并带 `redirect`。
- 已登录访问 `/login` 回 `/`。

**路由与导航。**

- `/login` 不带 Layout，页内切换登录与注册。
- `/` 挂 Layout，默认子路由重定向到 `/games`。
- 首页即游戏中心，没有单独的导航中心页。
- 侧栏菜单项与顺序由子路由声明顺序 + `meta.title` 生成。
- `buildMenuFromRoutes()` 过滤掉没有 `title` 或带 `hiddenInMenu` 的路由。
- 菜单当前顺序：游戏中心、游戏管理、游戏发现、按键管理。
- `/games/manage` 是游戏管理页。
- `/games/discover` 是游戏发现页，详见 `./game-discover.md`。
- `/shortcuts` 是纯前端静态的按键管理页。
- `/games/search` 重定向到 `/games/discover`，并保留 query。
- `/games/flash|play|h5/:gameId` 三个播放页都 `hiddenInMenu`。
- 新增页面 = 加一条带 `meta` 的子路由。

**浮层与全屏。**

- 左侧侧栏是浮层：常驻收起，鼠标靠近屏幕左边缘时滑出。
- 侧栏展开时盖在页面之上，不占位、不挤压内容。
- 播放页的 `GameShell` 标题栏也是浮层，规则相同。
- 游玩页全屏时鼠标静止 3 秒隐藏光标并收起标题栏。
- 原生全屏与 F11 都算全屏。
- 任何鼠标活动立即恢复光标与标题栏。
- 模拟器把 iframe 内的指针活动转进来，并给宿主 `<html>` 挂 `x-cursor-hidden`。
- H5 是沙箱不透明源，画面内光标无法隐藏。

**通用组件。**

- `components/common/` 必有：`AppDialog`、`AppButton`、`AppSegmented`。
- 还有 `AppPagination`、`AppEmpty`、`CopyButton`、`AppUpdateBanner`。
- 按钮统一走 `AppButton`。
- 只有两种类型：`secondary` 白底蓝框、`danger` 白底红框。
- `text` 是去掉背景与边框的形态，不算第三种类型。
- `pressed` 是开关的选中态（浅蓝底 + 深蓝边），也不算第三种类型。
- 尺寸 `size`：sm 28 / md 32 / lg 40。
- `tone`：light / dark / image / overlay，只换配色。
- 另有 `block` / `iconOnly` / `round`。
- 播放器标题栏与存档管理用 `tone="dark"`，不再手写深色按钮 CSS。
- 禁用态背景/边框 `#EEEEEE`、文字 `#AAAAAA`，不用透明度。
- 焦点只变边框色，不加外环。
- 分段/标签统一走 `AppSegmented`，tone / size 用同一套 token。
- 页面里不再手写原生 `<button>` 或按钮 CSS，唯一例外是 `AppSegmented` 自身。
- 需要新外观先扩 `AppButton` 的 `text` 或 `tone`。
- `CopyButton` 的 20px 卡带 ID 药丸是可复制数据 chip，不是第三种按钮类型。
- `AppDialog` 的 `footer-mode` 四值：default/confirm-only/custom/none。
- 右上角关闭按钮始终存在：只读弹框用 `none`，不再放多余的「关闭」底栏按钮。
- 确认框走 `confirmAction` / `dangerConfirm` / `dangerPrompt`（`utils/confirm.js`）。
- 页面里不再直接调 `ElMessageBox`。
- `AppPagination`：父级给 `page` / `total` / `pageSize`。
- 翻页时先发 `update:page` 再发 `change`。
- 父级的 `change` 要读自己的 page ref，顺序反了会拿旧页码去请求。
- 只有一页时整块不渲染。
- 左右方向键翻页在组件内部，挂在 window 冒泡阶段。
- 带修饰键的按键放行：`Alt+←` 是后退，`Ctrl/Shift+←` 是选词。
- 按住连发、输入法组字、焦点在输入框或下拉里都放行。
- `body.el-popup-parent--hidden`（弹框/抽屉打开）时放行。
- 空状态统一用 `AppEmpty`，覆盖加载失败与暂无内容。

**按键管理页。**

- `/shortcuts` 是纯前端静态页，没有接口。
- 版式是博客式单栏文档。
- 左侧大纲按页面滚动高亮，并支持平滑跳转。
- 一个页面一张表，第一列「功能」按相同功能合并单元格。
- 后两列是按键与说明。
- 键帽样式，同一页内按键帽从短到长排列。
- 相同功能的行保持相邻，便于合并单元格。
- 数据写在 `views/shortcuts/index.vue`。
- 改键位时同步更新那张表。

**游戏管理页。**

- 添加与编辑共用同一弹框：新建要等填完，编辑改完即存。
- 编辑态没有「取消 / 保存」底栏，只留右上角关闭。
- 名称、描述失焦即存，封面类型切换即存；关弹框时补存未失焦的改动。
- 本体、封面、攻略都是选完立即上传，失败不保留选择。
- 上传在途时禁用同一行的按钮，避免并发提交。
- 卡带 ID、图集、美化封面、删除攻略原本就是立即生效。

**交互约定。**

- 一律不做鼠标悬浮提示。
- 图片、按钮、文案都不要 `title`，也不要 `el-tooltip`。
- 需要说明就写常驻小字，或用「点开才看到」的展开层。
- 唯一例外是模拟器/引擎自己渲染的按钮。
- 两个保留项不是悬浮提示：`AppDialog` 的 `title` prop 与 `<iframe title="…">`。
- 检索/榜单的标签栏是一对普通按钮，不用 `el-radio-group`。
- 原因是原生 radio 的左右键会抢走分页条的键，详见 `./game-discover.md`。
- 不用 React、TypeScript、i18n、Bootstrap、Tailwind。
- 不把 Fernet 密钥放 Pinia store；不做全表列配置。
- 不上 WebSocket，除非以后某个工具明确需要实时。

## 边界与错误

- 401 跳转有重入保护；并发请求不会连续触发多次跳转。
- `notShowError` 与 `reported` 一起用，避免同一条错误弹两次。
- 分页事件顺序反了会请求旧页码，这是已知坑。
- 原生 radio 在焦点内时左右键换选项，这是不用它的原因。
- 全屏 3 秒规则由 `GameShell` 计时，任何鼠标活动都会重置。
- H5 沙箱内光标无法由父页隐藏。
- 没有悬浮提示，别把 `title` 当作说明手段。
- 空状态、列表加载失败、暂无游戏都要有 `AppEmpty` 兜底。
- 未登录由路由守卫处理。

## 测试要点

- 前端目前没有单元测试。
- `make test` 里的前端部分是 `cd frontend && npm run lint`。
- 单独跑 lint：`cd frontend && npm run lint`。
- 开发预览：`cd frontend && npm run dev`，Vite 默认 `:5173`。
- 只改文档时不用跑测试。
- 平时只跑改动涉及的用例，全量由用户定期执行。

## 相关文档

- [游戏发现（检索与榜单）](./game-discover.md)
- [H5 与攻略包](./guide-and-h5.md)
- [架构设计](../architecture.md)
- [编码约定](../../AGENTS.md)
