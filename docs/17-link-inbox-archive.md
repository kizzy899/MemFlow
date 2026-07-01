# 自动链接阅读与知识库归档

## 用途与入口

该模块读取固定文件 `inbox/links.md`，从独立 URL 行或普通段落中提取链接，抓取并生成结构化知识笔记，写入 SQLite 与已绑定的 Notion 数据库。

- HTTP：`POST /api/inbox/archive-links`
- CLI：`python -m app.tasks.archive_links`
- 输入：`inbox/links.md`
- 热点摘要：`hot.md` 的 `MEMFLOW:HOT` 托管区块
- 运行日志：`logs/link-archive.jsonl`（已忽略，不提交）

## 输入、循环与文件安全

空行分隔普通段落；只包含 URL 的行单独作为处理单元。同段多个 URL 必须全部归档成功或判定重复后才删除整段。每个 URL 每次运行只尝试一次，失败项留待下次调用，防止无限循环。

任务取得 `inbox/.links.lock` 后，将输入覆盖备份到 `inbox/.links.md.bak`。修改通过同目录临时文件和 `os.replace` 原子提交。抓取、解析、AI 或 Notion 失败均保留原文，并将已有失败说明替换为最新一条：

```text
> 处理失败：失败原因，时间：YYYY-MM-DD HH:mm:ss
```

## 抓取与知识整理

- HTML：复用网页正文解析器。
- PDF：直链 `.pdf` 使用 `pypdf` 提取文本。
- GitHub：公开仓库根链接优先读取 README。
- 视频：仅页面存在可读文字时处理，不下载字幕。

第一阶段生成标题、3–5 句摘要、核心观点、行动建议、分类和关键词；随后按分类和关键词从 SQLite 选择最多 10 条已有笔记，生成关键概念、人物/机构/项目/工具实体以及补充、冲突等知识关联。

## Notion 与去重

`normalized_url` 去除 fragment、默认端口和追踪参数并规范协议、host、查询参数及路径。任务先查 SQLite，再查询 Notion 的“规范链接”URL 属性。缺少该属性时自动创建；类型错误或创建失败会终止整轮且不修改 inbox。

归档页面必须同时写入属性和完整正文 blocks，不执行 properties-only 降级。正文包含原文链接、规范链接、摘要、核心观点、关键概念、关联实体、行动建议、已有知识关联和来源信息。Notion 失败时本地条目状态为 failed，下次运行复用结构化结果重试。

## 持久化字段与状态

新增字段：`key_concepts`、`related_entities`、`knowledge_relations`、`archive_markdown`、`source_type`、`archived_at`，由 SQLite 自动迁移补列。继续使用 `source_url`、`normalized_url`、fetch/AI/process/Notion 状态字段。

日志状态固定为 `processed`、`skipped_duplicate`、`failed_fetch`、`failed_parse`、`failed_notion`。CLI 全部成功/重复返回 0，部分失败返回 2，整轮配置、文件或锁错误返回 1。

## 测试覆盖

覆盖段落解析、失败说明替换、多 URL 原子处理、SQLite/Notion 重复、失败保留、备份与原子写、hot.md 托管区、PDF/GitHub 判断、Notion schema 与完整 blocks、API 和迁移回归。
## 全流程规范验收记录（2026-06-30 23:42:39 +08:00）

### 验收环境与边界

- Windows PowerShell，项目 `.venv`，SQLite 实际数据库，Notion 使用 `.env` 中已绑定数据库。
- 真实 CLI 使用空 `inbox/links.md`，因此验证了 Notion schema、备份、锁和退出码，但没有创建测试知识页面，也没有修改 hot.md 托管内容。
- 页面创建、抓取成功/失败、解析失败、Notion 失败、重复跳过和段落删除由隔离集成测试覆盖，避免向真实知识库写入测试垃圾。

### 执行结果

| 检查项 | 命令或场景 | 结果 |
| --- | --- | --- |
| 启动脚本 | `start.ps1 -Check` | 通过 |
| Python 编译 | `python -m compileall -q app skills tests` | 通过 |
| 完整测试 | `python -m pytest -q -p no:cacheprovider` | 69 passed |
| 健康检查 | TestClient `GET /health` | HTTP 200，`{"status":"ok"}` |
| OpenAPI | 检查 collect/items/export/notion/inbox 路由 | 通过 |
| SQLite 实库 | 六个归档字段及 normalized_url 唯一索引 | 通过 |
| 依赖 | FastAPI/SQLAlchemy/Notion/OpenAI/Trafilatura/pypdf 导入 | 通过，pypdf 5.6.1 |
| 真实 CLI | `python -m app.tasks.archive_links` | 退出码 0；0 remaining；无失败 |
| 文件安全 | backup 与 inbox 字节一致、无残留 lock/tmp | 通过 |
| hot.md | 空 inbox 不更新托管区 | 通过 |
| 差异检查 | `git diff --check` | 通过，仅 Windows 行尾提示 |
| 安全检查 | backup/log ignore 与密钥模式扫描 | 通过；仅命中测试占位 Token |

### Notion 在线诊断

真实 CLI 在一次连接成功时完成了 `ensure_archive_schema` 并正常退出。随后独立读取数据库验证“规范链接”字段时，3 次均出现 `[SSL: UNEXPECTED_EOF_WHILE_READING]`。该错误来自当前代理/TLS 链路，与业务断言、数据库字段或 inbox 文件事务无关。

安全结论：Notion 网络失败时任务不会删除原文；失败链接会保留并记录 `failed_notion`。网络恢复后重新执行 API 或 CLI 即可复测。建议将 `api.notion.com` 设为代理直连或修复 Python/httpx 的代理 TLS 转发后，再执行一次非空测试链接验收。
