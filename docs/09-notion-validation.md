# Notion 配置验证

`GET /api/notion/validate` 检查 API Key、Database ID、数据库访问权限以及全部字段名称和类型。诊断完成时始终返回 HTTP 200，通过 `success` 表示配置是否有效。

返回数据包含 `configured`、`database_accessible`、`missing_config`、逐字段 `fields`、`missing_fields`、`type_mismatches` 和可读错误。已知的权限、数据库 ID、字段及请求校验错误会转换为中文说明。

Notion rich text 单段最多保留 2000 字符，超长内容在末尾加入 `...（内容过长已截断）`。
## 连接重试与代理降级（2026-07-02）

Notion 客户端使用 10 秒连接超时、20 秒总超时和最多 2 次连接级重试。优先使用 `PROXY_URL`；未显式配置时沿用进程的 HTTP(S) 代理。数据库读取若发生 `httpx.TransportError`（TLS EOF、连接中断或连接超时），会只读地绕过环境代理再试一次，并缓存成功通道供后续页面查询和写入使用。

401/403/404、字段类型及请求校验错误不触发通道切换，继续按原有中文错误和状态返回。写页面本身不做操作级自动重放，避免响应丢失时产生重复页面。无新增配置或数据库字段；`configured`、`database_accessible`、`missing_fields` 和 `type_mismatches` 状态不变。测试覆盖传输错误后的直连降级及原有配置、权限、字段诊断。
