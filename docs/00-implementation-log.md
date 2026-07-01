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

## 第三阶段增强（2026-06-30）

### 实施顺序
1. 建立稳定词表与别名规范化，并接入采集及 API 输出。
2. 构建 Notion children，新增安全截断和属性降级写入。
3. 复用单条同步实现批量同步；新增 JSON/Markdown 导出。
4. 补充测试、README、模块文档和验收。

### 决策、文件与状态
- 新增 `app/taxonomy.py`、taxonomy/notion_page/notion_sync/export services、export router，以及四份第三阶段文档和专项测试。
- 修改 pipeline、Notion service、items router、container、main、README 和文档索引。
- 保留既有 SQLite 字段与英文枚举，未新增迁移、taxonomy_version、export_count 或 last_exported_at。
- 新增 pending/failed → synced、异常 → failed 的批量状态路径；单条失败不终止批次。正文失败降级属性写入；导出不修改状态。
- 文档编号使用 13–16，避免覆盖第二阶段已存在的 08–11 文档。

### 公共 API 与验证
- 新增 `POST /api/items/sync-notion/batch`、`GET /api/export/json`、`GET /api/export/markdown`。
- 专项与其余回归共 45 passed；完整套件另有 2 个既有 tmp_path 用例因当前 Windows 受限令牌无法访问临时目录而在 setup 阶段报权限错误（无断言失败）。compileall、OpenAPI 路由检查和 git diff --check 均通过。
## 文本来源链接与 Agent 面试标签（2026-06-30）

### 实施顺序与决策
1. 在内容身份工具新增首个 HTTP(S) URL 提取及句末标点清理。
2. 文本 pipeline 保存既有 source_url/normalized_url，并优先按 URL 域名识别小红书。
3. 标准二级分类新增 Agent面试；结合 AI 结果和原文上下文判断，并写入同名关键词供 Notion multi-select 使用。
4. 重复历史文本缺少链接时原地回填，不创建重复条目；Notion 状态 synced/failed → pending 后复用既有同步流程更新页面。

### 文件、公共 API 与持久化
- 修改 `app/taxonomy.py`、`app/services/taxonomy_service.py`、`app/utils/content_identity.py`、`app/services/content_pipeline_service.py`。
- 修改 taxonomy、内容身份与采集 pipeline 测试，并更新 README 和模块文档。
- `POST /api/collect` 请求结构不变；text 输入现在可能返回非空 source_url 和小红书 platform。
- 未新增 SQLite 字段或迁移，继续使用 source_url、normalized_url、source_platform、category_level_2、tags 和 notion_sync_status。

### 失败行为与验证
- 无 URL 时保持手动输入；链接与已有条目冲突时不覆盖；Notion 失败继续保留本地记录。
- 回归测试（排除两个受 Windows 临时目录权限影响的既有 tmp_path 用例）：49 passed；compileall 与 git diff --check 通过。
## 自动链接阅读与知识库归档（2026-06-30）

### 实施顺序
1. 扩展结构化归档字段和 SQLite 自动迁移，增加 PDF 依赖。
2. 新增 HTML/PDF/GitHub 阅读器、两阶段 AI 整理和本地相关知识检索。
3. 新增 Notion“规范链接”自动建字段、双端去重和严格完整正文写入。
4. 实现 inbox 文件锁、备份、段落事务、原子替换、失败说明、JSONL 日志与 hot.md 托管区。
5. 注册同步 API 与 CLI，补充测试、README 和模块文档。

### 关键决策
- 同段多 URL 整段原子删除；任一失败保留原段。
- 每个 URL 每次运行只尝试一次；下次调用再重试。
- Notion blocks 失败不降级，避免属性成功但正文缺失后误删 inbox。
- SQLite failed/pending 条目不视为重复；复用已生成 Markdown 重试 Notion。
- hot.md 仅替换标记区，日志、备份和锁文件均不提交。

### 文件、公共 API 与持久化
- 新增链接读取、关联 AI、Markdown/blocks 构建、归档编排、inbox router 和 CLI task。
- 新增 `POST /api/inbox/archive-links`，CLI 为 `python -m app.tasks.archive_links`。
- 新增 `key_concepts`、`related_entities`、`knowledge_relations`、`archive_markdown`、`source_type`、`archived_at` 并自动迁移。
- 新增 `inbox/links.md`、`hot.md`、模块文档和专项测试；增加 `pypdf==5.6.1`。

### 状态、失败与验证
- 状态：processed、skipped_duplicate、failed_fetch、failed_parse、failed_notion。
- 所有单条失败保留原文并更新单个失败说明；schema、锁或文件错误整轮失败且不改输入。
- 专项测试覆盖 parser、文件事务、Notion schema/blocks、PDF、API 和失败恢复。
- 完整测试：67 passed、2 skipped（并发加入的小红书 async 测试因环境未安装 pytest-asyncio 而跳过）；`python -m compileall -q app skills tests`、OpenAPI 路由检查和 `git diff --check` 均通过。
- 测试临时目录改为工作区 `data/` 下的隔离目录并自动清理，以兼容 Windows 受限令牌。

## 2026-06-30：修正小红书收藏同步

实施顺序：检查现有抓取器与登录态；探测个人主页入口；改为首页 → 当前用户主页 → 收藏标签；增加测试和真实登录态验证。

关键决策：不硬编码用户 ID；仅接受小红书个人主页路径；找不到收藏入口时失败，不回退推荐流；不新增持久化字段。

变更文件：`app/services/xiaohongshu_service.py`、`tests/test_xiaohongshu_service.py`、`docs/17-xiaohongshu-favorites.md`、`docs/README.md`、`docs/00-implementation-log.md`。

验证：Python 编译通过；单元测试及真实登录态只读冒烟测试通过。
## 自动链接归档全流程验收（2026-06-30 23:42:39 +08:00）

### 执行顺序
1. 启动检查、compileall 和依赖导入。
2. 运行完整 pytest、健康检查、OpenAPI 和 SQLite 实库断言。
3. 使用空 inbox 执行真实 CLI，验证 Notion schema 入口和文件事务。
4. 校验 backup、lock、tmp、hot.md 和 git diff。
5. 独立重试 Notion 在线读取并记录外部网络限制。

### 结果与决策
- 完整测试 69 passed；启动、编译、健康、OpenAPI、迁移字段、唯一索引、依赖和 diff 全部通过。
- 真实 CLI 退出码 0，processed/skipped/failed 均为 0，remaining=0，hot_updated=false。
- `inbox/.links.md.bak` 与输入完全一致，无 lock/tmp 残留，未创建真实测试页面。
- backup/log 均被 `.gitignore` 命中；密钥模式扫描只命中测试占位值，未读取或记录 `.env`。
- Notion 独立数据库读取连续 3 次出现代理 TLS EOF；记录为环境性未稳定项，不改变“不成功不删除”的验收结论。
- 详细命令、矩阵和复测建议见 `docs/17-link-inbox-archive.md`。
## Knowledge Console 可视化控制台（2026-07-01）

### 实施顺序
1. 新增 allowlist `.env` 原子配置、脱敏状态、loopback 安全依赖和服务热重载。
2. 新增 inbox 控制、后台 ProcessorManager、最近归档与 hot.md API，并为归档循环加入进度回调。
3. 更新 normalized_url 追踪参数与尾斜杠规则，启动迁移重新计算历史 identity。
4. 创建 React/Vite/TypeScript 单页控制台及 FastAPI `/console` 生产托管。
5. 补充 Python/React 测试、Notion schema 脚本、README、模块文档和验收。

### 关键决策
- 第一版仅本机单用户，不增加账号系统；配置和控制接口拒绝非 loopback 请求。
- 空配置输入保持原值，DELETE 才清除；任务运行期间拒绝配置变更。
- 小红书用户名/密码只保存，实际检测显式触发且仍优先使用 Cookie/profile。
- 后台任务单例、内存状态、独立 DB Session；应用重启后回到 idle，可依据持久化状态重跑。
- 前端不保存密钥，不启用 Markdown 原始 HTML；生产构建不提交，启动前执行 npm run build。

### 公共 API、持久化与失败行为
- 新增 config、XHS/Notion test、inbox CRUD、processor、recent、hot 共十三个控制端点以及 `/console` 页面。
- 未新增业务表；配置写入 gitignored `.env`，任务状态仅内存，inbox/SQLite/Notion 持久化不变。
- normalized_url 新增 fbclid/gclid 过滤和非根路径尾斜杠清理；迁移冲突不删除内容。
- 403 表示非本机访问，409 表示任务/文件版本冲突，外部测试失败返回清晰诊断且不泄露密钥。

### 变更区域与测试
- 后端：配置、队列、任务管理、安全依赖、console router、静态托管及 URL 迁移。
- 前端：`frontend/` React 应用、API 客户端、蓝白响应式样式、Vitest 测试与 Vite 构建。
- 文档：README、docs 索引、本模块文档和实施日志。
- 后端完整测试 75 passed；前端 Vitest 3 passed；Vite 生产构建、compileall、start.ps1 -Check、OpenAPI/静态资源和 git diff 检查通过。
- 使用隐藏 Uvicorn 与 headless Chromium 完成真实 `/console` 渲染冒烟，六个模块标题均存在，临时截图已清理。
## Knowledge Console inbox 粘贴单位调整（2026-07-01）

- 普通文字改为“一次粘贴一个整理单位”，所有内部换行压为单个空格。
- 纯 URL 列表改为每条 URL 之间写入一个空行，继续形成独立队列项。
- 已有 inbox 不自动合并；新增定向测试覆盖混合文字与多链接列表。
- 同步更新控制台输入提示、模块文档和实施日志，未改变归档失败保留与原子写入规则。
