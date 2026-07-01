# 批量 Notion 同步

`POST /api/items/sync-notion/batch` 接受 `status`（pending/failed/all_unsynced）、`item_ids`、`limit`（默认 20，服务最大 100）和 `force`。item_ids 优先；两者均缺失返回统一 422。Notion 未配置返回 503。

每条记录独立调用既有单条同步，成功/失败均持久化；单条异常只写入该结果，批次继续。默认跳过 synced；force 会重新处理，可能创建重复页面（已有 page_id 时为更新）。返回 total/synced/skipped/failed/results，部分失败仍 HTTP 200。

未新增字段。状态为 pending/failed → synced，写入异常 → failed；测试和回归验证覆盖统计与不中断语义。
