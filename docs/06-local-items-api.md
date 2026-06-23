# 本地条目 API

## 接口

- `GET /api/items`：分页列表，支持 `notion_sync_status`、`input_type`、`platform`、`keyword`。
- `GET /api/items/failed`：分页返回抓取、AI、pipeline 或 Notion 失败记录。
- `GET /api/items/{item_id}`：返回完整结构化笔记、阶段状态和错误信息。
- `POST /api/items/{item_id}/sync-notion`：手动重试 Notion。

`page` 默认 1，`page_size` 默认 20，允许范围 1–100。平台响应使用英文机器值，筛选兼容英文值和中文别名。列表按创建时间倒序。

详情使用 `key_points`、`keywords`、`language` 和 `notion_error` 作为 API 字段，同时保留 `id` 与 `item_id`。失败列表匹配 `process_status`、`fetch_status`、`ai_status` 或 `notion_sync_status` 中任一失败状态。

关键词搜索覆盖标题、摘要、关键词、原始 URL 和规范化 URL。
