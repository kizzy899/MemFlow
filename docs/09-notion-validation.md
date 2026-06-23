# Notion 配置验证

`GET /api/notion/validate` 检查 API Key、Database ID、数据库访问权限以及全部字段名称和类型。诊断完成时始终返回 HTTP 200，通过 `success` 表示配置是否有效。

返回数据包含 `configured`、`database_accessible`、`missing_config`、逐字段 `fields`、`missing_fields`、`type_mismatches` 和可读错误。已知的权限、数据库 ID、字段及请求校验错误会转换为中文说明。

Notion rich text 单段最多保留 2000 字符，超长内容在末尾加入 `...（内容过长已截断）`。
