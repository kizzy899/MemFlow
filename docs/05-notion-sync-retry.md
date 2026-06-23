# Notion 手动同步重试

`POST /api/items/{item_id}/sync-notion` 只使用 SQLite 已保存的结构化笔记，不重新抓取网页或调用 AI。

```bash
curl -X POST http://127.0.0.1:8000/api/items/<UUID>/sync-notion
```

状态流转为 `pending → synced/failed`、`failed → synced/failed`、`synced → synced`。已经 synced 且有页面 URL 时直接返回；未配置返回 503；Notion 校验或写入失败返回 502，并保存 `notion_error_message`。

成功响应和错误响应都采用 `{success, message, data}`。同步成功会同时更新页面 ID、URL、同步状态、清空旧错误并刷新 `updated_at`。配置缺失不会覆盖原有状态；实际调用失败会写入 `failed` 和中文可读错误。
