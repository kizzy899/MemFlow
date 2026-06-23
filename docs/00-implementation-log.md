# 第二阶段实施日志

## 执行顺序

1. 建立 `docs/` 文档索引、模块文档和仓库级文档维护规则。
2. 已完成：SQLite 增量迁移与内容身份字段。
3. 已完成：条目服务、去重和 Notion 重试。
4. 已完成：条目查询 API 与 Notion 详细验证。
5. 已完成：测试、README 和最终验收。

## 已完成操作

- 创建 `AGENTS.md`，要求后续功能与文档同步变更。
- 创建本目录及第二阶段模块文档入口。
- 新增 URL 规范化、文本标准化和 SHA256 内容哈希工具。
- 为条目模型增加输入类型、规范化 URL、内容哈希、清洗内容、抓取状态和 AI 状态。
- 新增启动迁移：自动补列、回填历史数据并创建唯一部分索引；迁移异常会记录日志并中止启动。
- 新增集中式条目服务，统一保存、身份查询、分页筛选、失败查询和 Notion 状态更新。
- 采集 pipeline 改为 URL/text 双重去重，并分别持久化 fetch/AI 阶段状态。
- 新增手动 Notion 重试、条目列表、失败列表，并增强条目详情。
- Notion 校验改为结构化诊断；写入使用默认值、长文本截断提示和中文错误转换。
- 更新翻译入口以复用新的身份索引和同步服务，避免旧接口触发唯一索引冲突。
- 将文件时间戳改为时区感知 UTC，消除 Python 弃用警告。

## 关键决策

- 保留现有 UUID 条目 ID。
- API 枚举继续返回英文机器值，查询参数兼容中文别名。
- Notion 验证是诊断接口，完成诊断时固定返回 HTTP 200。
- 失败记录使用分页，默认 20 条、最大 100 条。

## 文件与模块

- 数据层：`app/models/content_item.py`、`app/db_migrations.py`、`app/utils/content_identity.py`。
- 业务层：`app/services/item_service.py`、采集 pipeline、Notion 服务和翻译兼容逻辑。
- API：条目列表、失败列表、详情、手动同步以及 Notion 诊断路由和响应模型。
- 文档：根 README、仓库规则以及 `docs/` 中的索引和六份模块/验收文档。
- 测试：新增迁移、身份计算、列表筛选、同步重试、Notion 校验和文档清单测试。

## 最终验证

- `python -m pytest -q`：38 passed。
- `python -m compileall -q app skills tests`：通过。
- OpenAPI：确认 `/api/items`、`/api/items/failed`、`/api/items/{item_id}`、`sync-notion` 和 Notion validate 路由存在。
- 健康检查：应用路由包含 `/health`，端点回归测试通过。
- SQLite：实际数据库包含六个新增字段及 `normalized_url`、`content_hash` 唯一索引。
- `git diff --check`：通过，仅有 Windows 行尾提示。

## 项目启动脚本（2026-06-23）

### 实施顺序

1. 确认项目入口为 `app.main:app`，运行时依赖为根目录 `.env`、`.venv` 和相对数据目录。
2. 新增 `start.ps1`，实现环境检查、参数化监听、开发热重载及 `-Check` 验证模式。
3. 新增模块文档并登记到文档索引。
4. 执行脚本检查、测试和健康检查后启动项目。

### 关键决策

- 脚本使用自身目录作为工作目录，因此可以从任意目录调用。
- 默认保留开发体验所需的 `--reload`，生产式运行可传 `-NoReload`。
- `.env` 缺失只警告；`.venv` 或 `uvicorn` 缺失会立即失败并给出修复命令。

### 变更文件

- `start.ps1`
- `docs/11-project-startup.md`
- `docs/README.md`
- `docs/00-implementation-log.md`

### 公共接口、持久化与状态

- 新增脚本参数 `BindAddress`、`Port`、`NoReload`、`Check`；未新增 HTTP API。
- 未新增持久化字段或业务状态流转，应用启动流程保持不变。
- 失败行为和测试覆盖详见 `docs/11-project-startup.md`。

### 验证结果

- `powershell -ExecutionPolicy Bypass -File .\start.ps1 -Check`：通过。
- `.venv\Scripts\python.exe -m pytest -q --basetemp <writable-dir> -p no:cacheprovider`：38 passed。
- 后台启动后请求 `GET /health`：HTTP 200，返回 `{"status":"ok"}`。
## 简短标题生成（2026-06-23）

### 实施顺序

1. 追踪 URL 标题从网页解析、AI 分析到条目持久化的调用链。
2. 修正采集 pipeline 的标题优先级，统一保存 AI 概括标题。
3. 收紧 AI 提示词并在结构化结果模型增加空白清洗和 40 字符长度兜底。
4. 增加单元测试、模块文档并执行完整回归测试。

### 关键决策

- 网页原标题只作为 AI 分析上下文，不再覆盖 AI 生成标题。
- 提示词以最多 20 个汉字为目标；代码以最多 40 个字符做确定性兜底。
- 已去重的历史条目不自动重新分析，避免重复消耗 AI 和意外改写用户数据。

### 变更文件

- `app/services/ai_service.py`
- `app/services/content_pipeline_service.py`
- `tests/test_analysis_result.py`
- `tests/test_collect_pipeline.py`
- `docs/12-concise-title-generation.md`
- `docs/README.md`
- `docs/10-testing-and-verification.md`
- `docs/00-implementation-log.md`

### 公共 API、持久化、状态与失败行为

- `POST /api/collect` 契约不变，`data.title` 改为返回规范化后的 AI 概括标题。
- 数据库结构不变，现有 `content_items.title` 字段保存短标题。
- AI 成功、失败及 Notion 同步状态流转不变；空标题进入现有 AI 校验失败和重试流程。
- 历史重复条目按原去重逻辑直接返回，不自动改写标题。

### 验证结果

- 标题与采集定向测试：13 passed。
- 完整测试：40 passed。
- `python -m compileall -q app tests`：通过。
- `git diff --check`：通过，仅有既有 Windows 行尾提示。
