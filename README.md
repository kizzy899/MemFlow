# MemFlow

MemFlow 是基于 FastAPI、SQLite、OpenAI 兼容接口和 Notion API 的个人知识整理 Agent。它可以采集网页或粘贴文本，生成中文结构化笔记，本地持久化，并在 Notion 可用时同步。

项目内置 `agent-search` Skill，可对视频抽帧执行本地 OCR，并从文章或 OCR 文字中提取项目、Agent Skill 与推荐网页地址。详见 `docs/22-agent-search-skill.md`。

小红书视频支持 Browser/OpenCLI 媒体 Provider 降级、本地画面 OCR、faster-whisper 语音转录及手动历史重处理；完整状态、安全边界和真实 PoC 结果见 `docs/24-xhs-video-content-pipeline.md`。

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
- `GET /api/xhs/login/qrcode`
- `POST /api/xhs/login/chrome`
- `GET /api/xhs/login/status`
- `GET /api/xhs/session`
- `POST /api/xhs/session/refresh`
- `POST /api/xhs/logout`
- `POST /api/xhs/sync`

## 测试

```bash
python -m pytest -q
python -m compileall -q app skills tests
```

## 第三阶段：长期知识库增强

MemFlow 会标准化 AI 生成的平台、内容类型、分类、关键词和重要程度，避免 Notion 标签发散。一级分类固定为：AI、编程开发、英语学习、金融财务、论文写作、工具效率、项目灵感、生活经验、职业发展、其他。

同步新 Notion 页面时会写入摘要、核心观点、行动建议、分类信息和原始信息正文；正文格式异常时降级为仅写数据库属性。

```bash
curl -X POST "http://127.0.0.1:8000/api/items/sync-notion/batch" -H "Content-Type: application/json" -d '{"status":"all_unsynced","limit":50}'
curl "http://127.0.0.1:8000/api/export/json?limit=100"
curl "http://127.0.0.1:8000/api/export/markdown?limit=100"
```

PowerShell：
```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/items/sync-notion/batch" `
  -H "Content-Type: application/json" `
  -d "{\"status\":\"all_unsynced\",\"limit\":50}"
```

固定分类是长期可维护的标签治理；无法映射的二级分类为“未分类”，可在 taxonomy aliases 中扩展。Markdown 默认不含原文；需要原文时使用 JSON 导出并传 `include_raw_content=true`。
### 文本中的来源链接与 Agent 面试标签

文本采集会自动提取正文中的首个 HTTP(S) 链接。包含 `xiaohongshu.com` 或 `xhslink.com` 的文本会记录为小红书来源；Agent 面试、求职、岗位和上岸复盘内容会规范为二级分类及关键词标签 `Agent面试`。已有无链接的重复文本再次提交时会回填链接并重新尝试 Notion 同步。
## 自动链接阅读与知识库归档

将链接逐行或按段落写入 `inbox/links.md`，然后使用 API 或 CLI 归档：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/inbox/archive-links"
.\.venv\Scripts\python.exe -m app.tasks.archive_links
```

任务支持网页、直链 PDF 和公开 GitHub 仓库 README。只有 SQLite 与 Notion 完整写入成功后才删除输入原文；失败会保留原文并更新原因。重复链接按 normalized_url 在 SQLite 和 Notion 双重判断。首次运行会自动为 Notion 数据库创建 URL 类型的“规范链接”属性。

每次运行前生成 `inbox/.links.md.bak`，逐条状态写入 `logs/link-archive.jsonl`。成功批次只更新 `hot.md` 的托管区块，不覆盖人工内容。详细字段、状态和恢复行为见 `docs/17-link-inbox-archive.md`。
## Knowledge Console

安装并构建前端：

```powershell
cd frontend
npm install
npm run build
cd ..
.\start.ps1
```

`start.ps1` 会先自动启动或复用本机 `127.0.0.1:9223` 的专用 Chrome CDP，再启动 MemFlow。浏览器打开 `http://127.0.0.1:8000/console`。开发模式可在另一个终端运行 `cd frontend && npm run dev`，访问 `http://127.0.0.1:5173/console/`。

控制台提供连接现有 Chrome 的小红书授权、账号管理、收藏与历史视频重处理、Notion 配置、inbox 队列、后台整理进度、最近 Notion 结果和 hot.md。小红书浏览器状态使用 `MEMFLOW_AUTH_KEY` 加密保存在本机，前端不接触 Cookie；CDP 默认只连接 `127.0.0.1:9223`，配置和控制 API 仅允许本机访问。

前端验证：

```powershell
cd frontend
npm test -- --run
npm run build
```

详细接口、状态和安全行为见 `docs/18-knowledge-console.md`。
