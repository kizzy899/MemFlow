# SQLite 数据结构与迁移

`content_items` 在第一阶段字段基础上新增：

| 字段 | 用途 |
| --- | --- |
| `input_type` | `url` 或 `text` |
| `normalized_url` | 去除追踪参数后的 URL 去重键 |
| `content_hash` | 标准化文本的 SHA256 去重键 |
| `clean_content` | 网页提取或空白标准化后的内容 |
| `fetch_status` | `success/failed/skipped` |
| `ai_status` | `success/failed/skipped` |

现有 `raw_text`、`core_points`、`tags`、`source_platform`、`original_language` 和 `notion_error_message` 继续作为唯一数据源，并分别在 API 中表示 raw content、key points、keywords、platform、language 和 notion error。

应用启动时先运行 SQLAlchemy `create_all`，随后检查 SQLite 表结构。缺列通过 `ALTER TABLE ADD COLUMN` 增量添加，历史记录会回填身份和状态字段。迁移不删除字段或记录，并使用 `IF NOT EXISTS` 创建 `normalized_url` 与 `content_hash` 的唯一部分索引，因此可以重复执行。
