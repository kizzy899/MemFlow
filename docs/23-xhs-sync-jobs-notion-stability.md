# 小红书后台同步与 Notion 连接稳定性

## 目标

修复 Console 中收藏数量输入后任务长时间没有反馈的问题，并减少批量整理期间重复建立 Notion 连接、重复读取数据库结构造成的抖动。

## 公共 API

- `POST /api/xhs/sync`：请求体为 `{ "limit": 1..100 }`，成功返回 HTTP 202 和任务快照，不再等待整批收藏完成。
- `GET /api/xhs/sync/status`：返回当前任务快照，供 Console 每秒轮询。
- `POST /api/xhs/sync/cancel`：请求协作式取消当前任务；无运行任务时幂等返回当前状态。

任务快照字段：`task_id`、`status`、`phase`、`step`、`message`、`requested`、`discovered`、`fetched`、`processed`、`success`、`failed`、`current_index`、`current_title`、`page_url`、`last_error`、`started_at`、`updated_at`、`last_progress_at`、`heartbeat_at`、`finished_at`。

状态流转：`idle -> fetching -> processing -> success|failed`，取消分支为 `fetching|processing -> cancelling -> cancelled`。同一时刻只允许一个收藏任务；重复启动返回 409。抓取异常或页面超时进入 `failed`；单条整理失败累计到 `failed`，批次结束状态也为 `failed`，本地条目继续保留其原有失败信息。

## 前端行为

已连接 Chrome 时，按钮立即启动后台任务并显示“读取收藏”或“正在整理 processed/fetched”；未连接时不显示无反馈的禁用按钮，而是显示进入 Chrome 授权页的链接。任务完成后显示成功数量，失败时显示后台的 `last_error`。

Console 会在进入页面时恢复当前进程内任务状态，运行期间每秒轮询。进度区展示“读取收藏列表 → 分析与同步 → 完成”三阶段、读取阶段动态条、整理阶段确定进度、当前条目、成功/失败计数、耗时和任务短 ID。读取阶段无法从小红书页面获得可靠的逐条回调，因此使用不确定进度动画，不伪造百分比。

抓取阶段进一步显示 `connecting`、`opening_page`、`opening_home`、`locating_profile`、`opening_profile`、`opening_favorites`、`locating_items`、`reading_item`、`opening_detail`、`video_ocr`。后台每 2 秒更新心跳，步骤变化更新 `last_progress_at`；同一步超过 45 秒时前端提示正在等待超时。CDP/新标签页上限 10 秒，页面导航 35 秒，单条详情 75 秒，视频 OCR 60 秒，关闭临时页面 5 秒。

取消为协作式：接口立即设置取消信号，浏览器操作会在当前受限等待结束后检查信号，关闭 MemFlow 创建的临时标签，并进入 `cancelled`。不会强制关闭用户的 Chrome 或原有标签页。

浏览器控制台中的 `The message port closed before a response was received` 若来源显示为 `contentScript.js`、`injected.js` 或扩展 URL，属于浏览器扩展消息通道，不是 MemFlow API。可用无痕窗口或逐个停用扩展确认；MemFlow 自身的状态轮询失败会直接在收藏卡片显示“状态刷新失败”。

## Notion 连接策略

`NotionService` 按连接模式复用 HTTP/Notion Client。首次成功读取的数据库 properties 在当前服务生命周期内缓存，后续条目仍执行字段校验，但不再为每条内容请求一次数据库 schema。代理传输失败后建立的 direct client 也会复用；配置重载或应用关闭时统一关闭客户端。

未新增数据库字段或磁盘持久化数据。任务状态仅保存在进程内，服务重启后回到 `idle`。Notion 页面创建仍不在不确定的传输错误后盲目重放，避免生成重复页面。

## 测试覆盖

- 收藏 `limit` 边界、后台任务 202 响应和状态 API。
- 取消 API、抓取步骤回报、心跳与协作式取消状态。
- Notion 代理失败后的 direct 降级、客户端生命周期和 schema 单次读取。
- Console 参数提交、授权入口、任务轮询相关现有回归。
- Console 阶段文字和可访问的 `progressbar` 渲染。
- TypeScript/Vite 生产构建。
