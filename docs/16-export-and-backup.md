# JSON 与 Markdown 导出备份

`GET /api/export/json` 和 `/api/export/markdown` 按创建时间倒序导出，支持 notion_sync_status、category_level_1、platform、keyword、limit；JSON 另支持 include_raw_content。limit 在服务层限制为 1–1000。

JSON 输出 format、exported_at、total、items，条目含身份、来源、分类、摘要、列表字段、语言、Notion 状态和时间。raw_content 默认省略，降低隐私泄露与响应体积。Markdown 包含标题、元数据、摘要、核心观点、行动建议、关键词，空值转为“无”。可将 JSON 导入其他系统，后续也可作为 RAG 分块源。

未记录导出次数，未新增 SQLite 字段或迁移。非法枚举筛选返回统一 422；测试覆盖原文开关、Markdown 内容、筛选和 limit 截断。
