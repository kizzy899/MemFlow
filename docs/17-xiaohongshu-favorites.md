# 小红书收藏同步

## 公共 API
`POST /api/xiaohongshu/sync` 接收 `limit`（默认 20），返回 `status` 和 `synced_count`，使用 `XHS_COOKIE` 或 `XHS_BROWSER_PROFILE_PATH` 登录态。

## 流程与状态
服务打开首页，定位当前账号“我”的 `/user/profile/` 地址，进入个人主页并点击“收藏”后解析卡片。条目继续进入既有采集、处理、翻译及 Notion 同步状态流。

## 持久化字段
无新增字段。沿用 `title`、`source_url`、`source_platform=xiaohongshu`、`content_type=post`、`raw_text`、`raw_excerpt`、`external_id`。Cookie 和账号信息不入库。

## 失败行为
缺少或失效登录态、个人主页入口不可识别时抛出 `XiaohongshuLoginError`；已经进入个人主页但找不到收藏入口，或已经进入收藏页但没有解析到内容时抛出 `XiaohongshuFavoritesError`。同步 API 对两类失败均返回 HTTP 400；控制台检测 API 使用 `login_failed` 与 `favorites_unavailable` 明确区分。推荐流不再被当作收藏。

## 测试覆盖
覆盖个人主页 URL 白名单、收藏标签点击、登录失败和登录成功但收藏入口不可读，并执行真实登录态只读冒烟测试。
## 登录后自动读取

Knowledge Console 的 POST /api/config/xhs 在保存并热重载 Cookie/profile 登录态后，立即调用 fetch_favorites(limit=1)。手动 POST /api/xiaohongshu/test 复用同一读取流程。读取样本只用于确认已进入收藏页，不新增持久化内容字段，也不写入原始或翻译后的用户内容。

保存接口的 data.check 状态转换为：成功读取时 configured；登录态无效时 login_failed；已登录但收藏入口或内容不可用时 favorites_unavailable；浏览器、网络等其他异常时 failed。外部读取失败不回滚已保存的本机配置，错误信息会显示在控制台且不包含 Cookie。
## Windows 登录稳定性（2026-07-02）

Windows 下 Uvicorn `--reload` 使用的事件循环不支持 Playwright 启动浏览器子进程时，旧实现会抛出无详细信息的 `NotImplementedError`。`fetch_favorites(limit)` 公共 API、返回条目和异常状态不变；服务现在把整段 Playwright 生命周期放入独立工作线程，并显式使用 `ProactorEventLoop`，保证浏览器创建、页面操作和关闭位于同一事件循环。

未新增持久化字段或登录状态。缺少/失效 Cookie 仍进入 `login_failed`，收藏入口不可用仍进入 `favorites_unavailable`，浏览器或系统权限异常进入 `failed` 并写入本机 traceback；不会记录 Cookie。测试覆盖 Windows 工作线程分派和既有登录/收藏状态转换。
