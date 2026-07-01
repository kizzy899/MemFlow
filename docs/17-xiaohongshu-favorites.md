# 小红书收藏同步

## 公共 API
`POST /api/xiaohongshu/sync` 接收 `limit`（默认 20），返回 `status` 和 `synced_count`，使用 `XHS_COOKIE` 或 `XHS_BROWSER_PROFILE_PATH` 登录态。

## 流程与状态
服务打开首页，定位当前账号“我”的 `/user/profile/` 地址，进入个人主页并点击“收藏”后解析卡片。条目继续进入既有采集、处理、翻译及 Notion 同步状态流。

## 持久化字段
无新增字段。沿用 `title`、`source_url`、`source_platform=xiaohongshu`、`content_type=post`、`raw_text`、`raw_excerpt`、`external_id`。Cookie 和账号信息不入库。

## 失败行为
缺少或失效登录态、个人主页地址非法、找不到收藏入口、收藏为空时抛出 `XiaohongshuLoginError`，API 返回 HTTP 400；推荐流不再被当作收藏。

## 测试覆盖
覆盖个人主页 URL 白名单、收藏标签点击和入口缺失失败，并执行真实登录态只读冒烟测试。
