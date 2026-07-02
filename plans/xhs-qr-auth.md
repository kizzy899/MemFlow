# Xiaohongshu QR authentication plan

Implement provider-based official web QR login, encrypted session persistence, `/api/xhs` APIs, console login/account views, tests, and required documentation.

Order: backend auth core; Playwright login; API and crawler integration; frontend; verification; documentation.

Decisions: single local account and active login; two-second polling; Fernet encryption with `MEMFLOW_AUTH_KEY`; no cookies in frontend/logs; remove legacy XHS environment fields and routes.

Follow-up implementation: prefer the `chrome_cdp` Provider, connecting an already authenticated local Chrome at `CHROME_CDP_URL`. Favorites run in a temporary tab in that real browser; QR login remains a fallback API only.


# 小红书 Web 扫码认证中心重构

## Summary

- 移除 `.env` 中 `XHS_COOKIE`、`XHS_USERNAME`、`XHS_PASSWORD`、`XHS_BROWSER_PROFILE_PATH` 及对应配置 API/UI。
- 基于 Playwright 官方网页二维码实现扫码登录，登录态加密持久化并在启动时自动恢复、验证。
- 建立可插拔认证 Provider 层；收藏同步只依赖认证会话，不再接触 Cookie 配置。
- 将现有 `/api/xiaohongshu/*` 迁移为 `/api/xhs/*`，不保留旧接口。
- 同步更新模块文档、文档索引、README 和实施日志。

## Implementation Changes

### 后端认证架构

- 在现有 Python/FastAPI 结构下新增通用 `AuthProvider` 协议及小红书实现，不创建任务草案中的 TypeScript `backend/`。
- 小红书 Provider 拆分为登录协调、Playwright 二维码获取、2 秒状态轮询、会话管理、加密存储和脱敏日志模块。
- 同一时间只允许一个登录流程；新建二维码会关闭并替换旧流程。二维码默认按页面倒计时判定，无法读取时采用 60 秒兜底。
- 状态机固定为：
  `idle → waiting_scan → scanned → confirming → authenticated`
  或进入 `expired/cancelled/failed`；登出后回到 `idle`。
- 扫码成功后从浏览器保存完整 `storage_state`，提取昵称、头像及可推导的 Cookie 到期时间；前端永远不接收 Cookie。
- “刷新 Cookie”访问官方页面验证现有会话并重新捕获、续存 storage state；401、403、登录页跳转或关键账号元素缺失均标记失效并要求重新扫码。
- 保留现有 Windows Proactor 专用工作线程约束；Playwright context、page 和轮询任务始终在所属线程/事件循环内创建和销毁。

### 加密持久化与生命周期

- 新增 `MEMFLOW_AUTH_KEY`，要求为安全随机的 base64 32 字节密钥；仅认证功能依赖该变量，缺失或格式错误时服务仍可启动，但认证 API 返回不可重试的配置错误。
- 使用 `cryptography` 的 AES-256-GCM 加密认证负载；`data/cookies/xiaohongshu.json` 仅保存版本、nonce、ciphertext 和更新时间，不保存明文 Cookie。
- 加密负载包含 storage state、账号摘要、`createdAt`、`updatedAt`、`expireAt`；写入采用临时文件加原子替换，解密或结构校验失败时隔离为无效会话，不覆盖证据文件。
- 启动时恢复并异步验证会话；验证期间返回 `checking`，有效则进入 `authenticated`，失效则进入 `reauth_required`。
- 登出关闭活动浏览器上下文、清除内存会话并删除加密认证文件。
- `logs/login.log` 使用轮转日志，记录二维码生成、扫码、确认、刷新、恢复、成功、失败、失效和登出；只记录会话 ID、错误分类和脱敏 Cookie 指纹，不记录 Cookie、storage state、二维码内容或用户原始数据。
- `.gitignore` 覆盖认证文件、临时文件和日志；`.env.example` 删除所有旧 XHS 字段并添加不含真实值的 `MEMFLOW_AUTH_KEY` 说明。

### API 与业务集成

- 新增统一错误结构：`{code, message, detail, retryable}`；网络错误、二维码失效、扫码取消、Cookie 捕获失败、风控、Provider 异常分别使用稳定错误码。
- 提供以下本机受限 API：
  - `GET /api/xhs/login/qrcode`：创建或替换登录流程，返回 `{qrImage, qrId, expireTime}`。
  - `GET /api/xhs/login/status`：返回当前 `qrId`、状态、剩余时间及可选错误；单用户模式无需客户端传 Cookie。
  - `GET /api/xhs/session`：返回登录状态、有效性、账号公开摘要、登录/更新时间、剩余有效期及是否需要重登。
  - `POST /api/xhs/session/refresh`：验证并续存登录态。
  - `POST /api/xhs/logout`：清除会话。
  - `POST /api/xhs/sync`：替代 `/api/xiaohongshu/sync`。
- 删除 `/api/config/xhs`、`/api/xiaohongshu/test`、`/api/xiaohongshu/sync` 及旧 XHS 配置状态字段。
- 收藏抓取服务通过 Provider/SessionManager 获取已认证 Playwright context；无会话、验证中或失效时返回明确认证错误，不再读取 Settings 或 `.env`。
- 启动验证不阻塞 FastAPI 就绪；会话状态变化供前端轮询，不在后台主动向浏览器弹窗。

### 前端

- 保持现有轻量 React SPA，不引入 React Router；根据 `/console` 下路径和 History API 提供：
  - `/console/login/xiaohongshu`
  - `/console/settings/account`
  - `/console` Dashboard
- 导航栏持续显示小红书状态；未登录进入扫码页，已登录可进入账号管理或重新扫码。
- 登录页展示后端返回的二维码图片、倒计时、状态步骤、错误和重试按钮，每 2 秒轮询；成功动画后自动跳转 Dashboard。
- 设置页展示头像、昵称、登录时间、Cookie 更新时间和可用剩余时间，并提供重新扫码、退出登录、刷新 Cookie。
- 启动验证发现失效时显示全局提示并链接扫码页；所有状态提供图标、颜色及文本，不只依赖颜色表达。
- 延续现有蓝白响应式风格；仅在项目现有主题能力存在时复用暗色模式，不额外建立完整主题系统。

## Test Plan

- 单元测试覆盖状态机合法转换、重复登录替换、超时/取消、错误映射、Cookie 脱敏、AES-GCM 加解密、错误密钥、损坏文件、原子写入及登出清理。
- 使用伪 Playwright 页面覆盖二维码截图、扫码、确认、风控、登录跳转、账号信息提取、刷新续存和 Cookie 失效，不依赖真实账号。
- API 测试覆盖所有新路径、响应结构、本机访问限制、并发二维码请求、缺少主密钥、未登录同步及旧路径返回 404。
- 启动生命周期测试覆盖有效恢复、失效恢复、验证异常不阻塞启动，以及业务抓取只通过 Provider 获取认证上下文。
- 前端测试覆盖扫码状态序列、2 秒轮询清理、过期重试、成功跳转、全局失效提示、账号操作和敏感信息不进入 DOM。
- 运行完整 `pytest`、Vitest、Vite production build、Python compileall、OpenAPI 路由检查、敏感字段全文检索和 `git diff --check`；真实扫码仅作为正常本机环境下的手工验收项并记录结果。

## Documentation

- 重写 `docs/17-xiaohongshu-favorites.md`，记录 Provider 架构、公开 API、加密持久化字段、状态转换、失败行为、安全边界和测试覆盖。
- 更新 `docs/18-knowledge-console.md`、`docs/README.md`、根 `README.md` 与 `.env.example`，移除手动 Cookie/账号密码说明，补充扫码、主密钥生成和账号管理流程。
- 在 `docs/00-implementation-log.md` 追加实施顺序、关键决策、全部变更文件和实际验证结果。
- 文档不得包含真实密钥、Cookie、二维码、账号数据或原始/翻译用户内容。

## Assumptions

- 小红书扫码通过官方网页 Playwright 自动化实现，不逆向非公开 API。
- `MEMFLOW_AUTH_KEY` 是唯一新增认证配置；不会由程序写回 `.env`。
- 项目仍是本机单用户控制台，同一时刻只有一个小红书账号和一个活动扫码流程。
- Cookie 无明确到期时间时 API 返回 `expireAt: null`、`remainingSeconds: null`，不会伪造有效期。
- 昵称或头像无法提取不影响登录成功，以空值呈现并在后续刷新时补全。
