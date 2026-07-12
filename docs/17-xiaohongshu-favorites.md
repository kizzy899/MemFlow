# 小红书收藏同步

## 公共 API
`POST /api/xhs/sync` 接收 `limit`（默认 20，范围 1–100），返回 202 后台任务；`GET /api/xhs/sync/status` 查询进度。抓取统一复用认证中心维护的 Chrome/CDP 会话，不读取环境变量 Cookie、用户名或密码。

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
## 内容优先的视频与推荐笔记规范（2026-07-03）

收藏卡片取得详情链接后，抓取器会打开独立详情页读取正文并检测 `video`。视频存在可下载的 HTTP(S) 源时，调用本地 Agent Search，以 1 秒间隔、最多 1800 帧执行画面 OCR；去重后的全部有效片段追加到 `raw_text` 的 `[视频 OCR 全文]` 区域，识别到的网页资源追加到 `[视频中识别到的资源链接]`；图文详情正文中的显式 `<a href>` 也以“名称｜完整链接”加入上下文。同步期间不持久化视频文件或帧图片，临时下载沿用 Agent Search 的自动清理规则。

视频提取状态写入既有 `source_type` 与 `raw_text`，不新增数据库字段：成功为 `小红书视频（视频文字提取成功…）`；画面无清晰文字写入 `[视频文字提取为空：…]`；视频地址、下载或 OCR 异常写入 `[视频文字提取失败：…]`。视频条目强制保持 `content_type=video`。详情页本身无法读取时写入 `[详情内容提取失败：…]`，不会错误宣称完成视频 OCR。

AI 对小红书使用内容优先规则：忽略作者/账号和点赞、收藏、评论、粉丝、关注数据；视频基于全部已提取 OCR 文字分点总结；提取为空或失败时必须在摘要中明确标记。工具、网站、应用、项目或资源推荐类内容使用一句概括加资源清单，清单格式为 `名称｜完整网页链接｜一句极简介绍`，链接缺失时明确写“链接未提供”，不得编造。推荐清单允许超过 5 条，以保留全部确认到的资源。

再次同步已有小红书条目时，会用本次详情正文/OCR 覆盖旧抓取文本并重新执行 AI，然后将既有 Notion 页面置为待同步并更新；`author` 被清空。状态仍沿用 `processing → completed|failed`、`fetch_status=success` 与 `ai_status=success|failed`。OCR 失败属于可归档的内容缺失标记，不会伪造文字；AI 或 Notion 失败继续使用既有失败状态与重试行为。

测试覆盖 OCR 全文和资源传递、空结果/异常标记、社交指标与作者标签过滤、超过 5 项的推荐清单、规范提示词，以及已有笔记使用新 OCR 内容重新分析。公共 `POST /api/xhs/sync` 请求和响应不变。

## 视频媒体、OCR 与语音转写（2026-07-05）

仅画面 OCR 已升级为 Provider 流水线：详情视频源优先，失败时由 OpenCLI 复用 CDP 9223 降级下载；本地视频并行进入 Agent Search OCR 与 faster-whisper。完整结果写入 `raw_text`，Notion 使用 `MemFlow 视频内容` Toggle。新增六个媒体状态字段，旧记录默认 `skipped/unknown` 且不自动回填。完整 API、字段、失败行为和 PoC 见 [视频流水线](24-xhs-video-content-pipeline.md)。

## ???????????2026-07-12?

??????? `POST /api/xhs/sync` ??????????????? API??????? Notion ???????????????????????????? `/user/profile/` ?????????????????????????????? DOM ???????????????????????????????????????????????????????????????????????????????????? tab DOM ??????????????

????????????????????????? `XiaohongshuLoginError`????? failed ?????????????????????????? `XiaohongshuFavoritesError`????????????????????????? DOM ??????????????????????
