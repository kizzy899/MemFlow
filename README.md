# MemFlow

MemFlow 是基于 FastAPI、SQLite、OpenAI 兼容接口和 Notion API 的个人知识整理 Agent。它可以采集网页或粘贴文本，生成中文结构化笔记，本地持久化，并在 Notion 可用时同步。

完整设计和实施记录见 [docs/README.md](docs/README.md)。仓库要求每个新功能或模块在同一次变更中更新模块文档和实施日志。

## 安装与启动

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

`.env` 至少配置 `OPENAI_API_KEY`。Notion 同步还需要 `NOTION_API_KEY` 和 `NOTION_DATABASE_ID`。模型和兼容服务地址分别使用 `OPENAI_MODEL`、`OPENAI_BASE_URL`。

```bash
curl http://127.0.0.1:8000/health
```

## 采集内容

```bash
curl -X POST http://127.0.0.1:8000/api/collect \
  -H "Content-Type: application/json" \
  -d '{"input_type":"url","content":"https://example.com/article"}'
```

文本输入把 `input_type` 改为 `text`。URL 会移除常见追踪参数后去重；文本合并空白后计算 SHA256。重复内容不会重新调用 AI，未同步内容会再次尝试 Notion。

## Notion 配置检查

```bash
curl http://127.0.0.1:8000/api/notion/validate
```

诊断结果包含：

- `configured`：必要环境变量是否完整。
- `database_accessible`：Integration 是否能访问数据库。
- `fields`：每个字段的预期类型、实际类型和有效性。
- `missing_fields`：缺失字段。
- `type_mismatches`：类型不匹配字段。

诊断接口固定返回 HTTP 200，通过响应中的 `success` 表示配置是否有效。

## 手动重试 Notion

```bash
curl -X POST http://127.0.0.1:8000/api/items/<UUID>/sync-notion
```

适用于首次未配置 Notion、修复字段后重试或网络失败后重试。该接口只读取本地结果，不重新抓取或调用 AI。已同步条目会幂等返回。

## 查询本地记录

```bash
curl "http://127.0.0.1:8000/api/items?page=1&page_size=20"
curl "http://127.0.0.1:8000/api/items?notion_sync_status=failed"
curl "http://127.0.0.1:8000/api/items?keyword=AI"
curl "http://127.0.0.1:8000/api/items?platform=GitHub&input_type=url"
curl http://127.0.0.1:8000/api/items/failed
curl http://127.0.0.1:8000/api/items/<UUID>
```

列表和失败列表均分页，默认 20、最大 100。平台筛选支持英文机器值和中文别名，响应统一返回英文机器值。

## Notion 数据库字段

| 字段 | 类型 |
| --- | --- |
| 标题 | Title |
| 原始链接 | URL |
| 来源平台、内容类型、一级分类、二级分类 | Select |
| 摘要、核心观点、行动建议 | Rich text |
| 关键词 | Multi-select |
| 原文语言、阅读状态、重要程度、AI处理状态 | Select |
| 是否翻译 | Checkbox |
| 创建时间、更新时间 | Date |

## 常见问题

### Notion 未配置

补齐 `.env` 中的 `NOTION_API_KEY` 和 `NOTION_DATABASE_ID` 后重启。已有本地条目不会丢失，可使用手动同步接口重试。

### 数据库无法访问

打开 Notion 数据库，在 `... → Connections` 中添加对应 Integration，并检查 Database ID。

### 字段类型不匹配

运行 `/api/notion/validate`，按照 `missing_fields` 和 `type_mismatches` 修正数据库。

### 重复提交没有重新整理

这是去重后的预期行为。如只需重新同步 Notion，请调用 `/api/items/{item_id}/sync-notion`。

## 其他兼容接口

- `POST /api/web-links/submit`
- `POST /api/translate`
- `POST /api/xiaohongshu/sync`

## 测试

```bash
python -m pytest -q
python -m compileall -q app skills tests
```
