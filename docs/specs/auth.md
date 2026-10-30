# 账号与会话

## 范围与权威

- 后端实现是 `backend/auth/` 的 `router.py` / `service.py` / `login_lockout.py` / `models.py`。
- 表结构见 `../data_dict.md` 的「auth — 账号」；前端守卫是 `frontend/src/permission.js`。
- 账号只用于隔离各人的模拟器配置与存档，不做更强的安全机制。

## 数据与路径

- `users` 表：`id` / `username` / `password_hash` / `created_at`；username 唯一，哈希永不明文。
- `login_attempts` 表按 `username` 一行；登录成功后该行被删除。
- 用户名会被直接当成存档目录名：`save/{用户名}/…` 与 `image/{用户名}/…`。
- 字符集收窄到数字、字母、中划线、下划线，就是为了不必再考虑路径转义。

## 行为与规则

### 注册与登录

- 开放注册：`POST /api/register`，只收用户名与密码，成功即写 session。
- 没有命令行建号；也不做邮箱、验证码、找回密码、OAuth。
- 登录：`POST /api/login`，校验 `users` 表里的 werkzeug 哈希。
- 退出：`POST /api/logout`；当前用户：`GET /api/me`。
- 没有游客模式；后端没有「可登录可不登录」的依赖。

### 用户名与密码

- 用户名规则：`^[0-9A-Za-z_-]{2,32}$`，校验入口 `validate_username()`。
- 规则本身大小写敏感，但注册查重按小写比较：大小写不同的同名视为已占用。
- 已有账号的落盘路径不改写，避免旧数据「看起来丢了」。
- 密码长度 6–64，校验入口 `validate_password()`；密码**不 strip**。
- 重名注册返回 409，其它格式错误返回 400。

### 失败锁定

- 同一 username 连续失败 ≥3 次：短锁 5 分钟。
- 同一 username 连续失败 ≥6 次：锁到当天 UTC 结束。
- 锁定检查在密码校验之前；锁定期内直接返回 429。
- 短锁到期只清 `locked_until`，`failed_count` 保留，再次失败继续累加。
- 登录成功即删除该 username 的失败行；短锁与日锁文案不同。

### 会话与 CSRF

- 登录态用 Starlette SessionMiddleware 的 session cookie。
- Cookie 是 HttpOnly、`SameSite=Lax`；Docker 走 HTTPS 时 `Secure` 为真。
- Windows 包走 http 时由启动器把 `Secure` 改成假，否则登录静默失效。
- 签名密钥是 `backend/config.py` 里写死的 `SECRET_KEY`，不从环境变量读。
- 换 `SECRET_KEY` 会让所有已登录会话立即失效。
- session 里只存 `user_id`，不存 token；axios 固定 `withCredentials: true`。
- CSRF：先 `GET /api/csrf` 拿 token，之后写操作带 `X-CSRFToken`。
- token 存在 session 里，服务端用 `secrets.compare_digest` 比对；安全方法不校验。
- 白名单是 `/health`、`/api/csrf`、`/api/register`、`/api/login`；写操作缺 token 返回 400。

### 前端登录态

- 登录态**不放进 localStorage 当 token**，只靠 HttpOnly cookie。
- 非敏感用户名可缓存在 sessionStorage，键是 `x_username`。
- `clearSession()` 按约定 key 清单同时清 sessionStorage 与 localStorage。
- 401 拦截器单飞处理：清本地缓存并跳 `/login?redirect=…`。
- 路由守卫白名单只有 `/login`：先 `fetchMe()`，失败则带 `redirect` 去登录页。

### 免登录例外与不做项

- 免登录：`/health`、`/api/csrf`、`/api/register`、`/api/login`。
- 免登录业务接口只有 H5 资源 `GET|HEAD /api/games/{id}/h5/{资源路径}`。
- H5 免登录是浏览器约束：沙箱不透明源带不上 `SameSite=Lax` cookie。
- 播放页本身仍要登录；攻略资源不在此例外里，它在新标签页顶层打开、cookie 照常带上。
- 不做 JWT、Redis、多因子、权限 ID、游客模式。

## 边界与错误

- 用户名或密码为空、长度不符、用户名含非法字符：400；重名（含大小写不同）：409。
- 用户名或密码不正确：401，统一提示「用户名或密码不正确。」
- 锁定期内登录：429；未登录访问业务接口：401；写操作缺 CSRF token：400。

## 测试要点

- 错误密码与不存在用户都返回 401，提示不泄漏用户是否存在。
- 登录成功后可访问 `/api/me`，退出后会话失效。
- 注册成功即登录，密码只以哈希入库。
- 非法用户名、非法密码、重名注册被拒；大小写不同的同名也被拒。
- session cookie 的 `Secure` 标志跟随配置；连续 3 次失败短锁、6 次日锁。
- 成功登录清空失败计数；`/api/csrf` 可取 token，白名单免校验。

## 相关文档

- [HTTP 端点总表](./api.md)
- [数据字典](../data_dict.md)
- [架构说明](../architecture.md) 的「决策 5」与「决策 8」
- [编码约定](../../AGENTS.md)
