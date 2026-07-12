# Notion 手动同步重试

`POST /api/items/{item_id}/sync-notion` 只使用 SQLite 已保存的结构化笔记，不重新抓取网页或调用 AI。

```bash
curl -X POST http://127.0.0.1:8000/api/items/<UUID>/sync-notion
```

状态流转为 `pending → synced/failed`、`failed → synced/failed`、`synced → synced`。已经 synced 且有页面 URL 时直接返回；未配置返回 503；Notion 校验或写入失败返回 502，并保存 `notion_error_message`。

成功响应和错误响应都采用 `{success, message, data}`。同步成功会同时更新页面 ID、URL、同步状态、清空旧错误并刷新 `updated_at`。配置缺失不会覆盖原有状态；实际调用失败会写入 `failed` 和中文可读错误。

当本地条目保留了旧 `notion_page_id`，但 Notion 返回 archived/unarchive/block/page 相关错误（例如页面或正文块已归档，无法编辑）时，服务不再继续更新旧页面，而是清空内存中的旧页面 ID/URL 并在目标数据库创建新页面。创建成功后，既有 `sync_notion` 流程会把新的 `notion_page_id`、`notion_page_url` 持久化到 SQLite，并将状态置为 `synced`。普通网络、权限、字段校验或其他 Notion 写入错误不会触发自动重建，避免不确定失败生成重复页面。

本功能不新增 HTTP API、数据库字段或状态枚举。状态仍为 `pending → synced/failed`、`failed → synced/failed`、`synced → synced`；archived 旧页重建成功属于 `synced`，重建失败仍记录为 `failed` 和 `notion_error_message`。测试覆盖 archived 旧页自动创建新页、非 archived 错误不创建重复页面，以及既有手动重试 API。
