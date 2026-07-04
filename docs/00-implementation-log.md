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

## Knowledge Console inbox 勾选批量删除（2026-07-01）

### 实施顺序与决策
1. 在 inbox 服务中增加基于快照版本的多 ID 删除，并复用文件锁、备份与原子替换。
2. 新增批量 DELETE API；前端增加复选框、全选/取消全选、计数与删除选中按钮，同时保留单项删除。
3. 补齐服务事务测试和前端交互测试，构建生产资源并更新文档。
4. 批量删除采用全有或全无：任何 ID 缺失或版本过期均不修改 inbox，避免部分删除。

### 文件、API、字段与状态
- 修改 `app/services/console_inbox_service.py`、`app/routers/console.py`、`frontend/src/App.tsx`、`frontend/src/styles.css` 及对应测试。
- 新增 `DELETE /api/inbox/items`，请求字段为 `item_ids` 与 `version`；响应为删除后的 inbox 快照。
- 未新增持久化字段或业务状态；仍使用 item_id 定位段落、version 进行乐观并发校验。
- 409 表示版本冲突，404 表示选中项目不存在，422 表示空选择；失败时不发生部分删除。

### 验证结果
- `python -m pytest -q -p no:cacheprovider`：77 passed。
- Vitest：1 file、4 tests passed，新增全选、请求负载和删除后空队列覆盖。
- `npm run build`：通过，194 modules；JS 271.50 kB、CSS 5.79 kB。

## 小红书登录检测结果细分（2026-07-02）

### 实施顺序与决策
1. 将登录态失败与已登录但收藏入口/内容不可读拆为两种服务异常。
2. 控制台检测 API 返回 `login_failed` 或 `favorites_unavailable`，并在消息开头给出明确中文结论。
3. 前端直接展示检测业务消息，失败后重新读取后端检测状态，避免只呈现 HTTP 200。

### API、字段、状态与失败行为
- 修改 `POST /api/xiaohongshu/test` 的业务状态说明；HTTP 传输成功仍为 200，业务成功由 `success` 判定。
- `configured` 表示登录且成功读取收藏；`login_failed` 表示 Cookie/登录态失败；`favorites_unavailable` 表示已登录但收藏入口或内容不可读；`failed` 表示其他异常。
- 未新增持久化字段；检测结果仅保存在配置服务内存状态。同步 API 仍以 HTTP 400 返回上述可恢复失败。
- 页面结构变化或空收藏不会再误报为 Cookie 登录失败。

### 变更与验证
- 修改小红书服务异常、控制台与同步路由、Knowledge Console 提示逻辑及 Python/React 测试。
- 更新 README、小红书模块文档、Knowledge Console 模块文档和实施日志。- 验证：Python 79 passed；Vitest 5 passed；Vite production build 通过（194 modules）。
## 小红书空异常提示修复（2026-07-02）

- 原因：部分浏览器/异步超时异常的 `str(exc)` 为空，前端只能收到“检测失败：”。
- 修改：新增异常描述兜底；超时显示网络、代理和页面访问建议，其他空异常显示异常类型，同时在本机启动终端记录 traceback。
- API 与持久化：`POST /api/xiaohongshu/test` 路径、字段和状态不变；未新增持久化字段。
- 失败行为：业务失败仍不修改 Cookie、不执行收藏同步，也不向前端或日志主动输出 Cookie。
- 验证：完整 Python 测试 80 passed；compileall 与 `git diff --check` 通过。
## 小红书登录后自动读取收藏（2026-07-02）

### 实施顺序与决策
1. 复查收藏抓取服务、控制台配置保存和手动登录检测调用链。
2. 将“读取一条收藏样本”抽成共享流程，保存小红书配置并热重载登录态后立即调用；手动测试复用该流程。
3. 控制台继续先持久化配置，再记录读取结果，避免外部页面失败导致本地登录信息丢失；不启用用户名/密码自动登录。

### 文件、API、字段与状态
- 修改 app/routers/console.py、frontend/src/App.tsx、tests/test_console_api.py、docs/17-xiaohongshu-favorites.md、docs/18-knowledge-console.md、docs/README.md 和本日志。
- POST /api/config/xhs 请求字段不变；保存后立即调用 fetch_favorites(limit=1)，响应 data.check 为 configured、login_failed、favorites_unavailable 或 failed。
- 不新增数据库或 .env 字段，不持久化收藏样本和原始用户内容；完整 /api/xiaohongshu/sync 的处理状态流不变。
- 登录失败、收藏入口/内容不可用和其他读取异常分别返回明确状态；配置已保存事实与外部读取结果同时呈现。

### 验证结果
- 新增后端测试验证保存配置后立即调用收藏读取；既有登录失败、收藏失败和空异常诊断覆盖继续执行。
- Python compileall 通过；后端完整测试 81 passed；前端 Vitest 5 passed；Vite production build 通过；git diff --check 通过。
## 2026-07-02：小红书登录与 Notion 连接稳定性

实施顺序：
1. 复现控制台小红书 `NotImplementedError`，确认 Windows + Uvicorn reload 的 Selector 事件循环无法创建 Playwright 子进程。
2. 复现 Notion `SSL: UNEXPECTED_EOF_WHILE_READING`，核对 Token/Database ID 已加载，并对比环境代理与直连通道。
3. 将小红书 Playwright 生命周期迁入独立 Proactor 工作线程；未知异常记录本机 traceback。
4. 为 Notion 配置连接超时、连接级重试和仅针对 `httpx.TransportError` 的代理到直连降级，并缓存成功通道。
5. 补充专项测试、模块文档、控制台说明并执行回归。

关键决策：公共 API、SQLite/Notion 持久化字段和状态机均不变；小红书浏览器对象不跨线程/事件循环；Notion 仅对数据库只读探测降级，401/403/404 与字段错误不重试，页面写入不做操作级重放以避免重复。

变更文件：`app/services/xiaohongshu_service.py`、`app/services/notion_service.py`、`app/routers/console.py`、`tests/test_xiaohongshu_service.py`、`tests/test_notion_validate.py`、`docs/09-notion-validation.md`、`docs/17-xiaohongshu-favorites.md`、`docs/18-knowledge-console.md`、`docs/00-implementation-log.md`。`docs/README.md` 已包含 09、17、18 三份模块文档，无需新增索引项。

失败行为：Cookie/登录失败、收藏不可用和未知浏览器异常继续分别映射 `login_failed`、`favorites_unavailable`、`failed`；Notion 两条通道均失败时返回原始代理通道的可读错误，本地条目和 inbox 不删除。

验证结果：专项后端测试 16 passed；真实 Notion 数据库校验由 TLS EOF 自动降级后通过；受控命令沙箱禁止 Chromium 子进程并返回 `WinError 5`，因此真实小红书页面冒烟需在正常启动的本机服务中验证。完整回归：83 passed；`python -m compileall -q app tests` 通过；`git diff --check` 通过。
## 2026-07-02：小红书 Web 扫码认证中心

实施顺序：先记录 `plans/xhs-qr-auth.md`，随后建立通用认证协议、状态管理与加密存储；接入官方网页 Playwright 二维码；将收藏抓取改为使用 Provider 会话；迁移 `/api/xhs`；增加扫码和账号管理视图；最后更新测试与文档。

关键决策：不逆向私有接口；单用户单登录流程；Fernet 密钥由 `MEMFLOW_AUTH_KEY` 提供；Cookie/storage state 不进入前端和日志；旧 XHS 环境变量、配置 API 与 `/api/xiaohongshu/*` 不兼容保留。

持久化与状态：新增忽略提交的 `data/cookies/xiaohongshu.json` 加密信封，不新增数据库字段。状态为 idle、checking、waiting_scan、scanned、confirming、authenticated、expired、cancelled、failed、reauth_required；失败返回 code、message、detail、retryable。

变更文件：认证核心位于 `app/services/auth/` 与 `app/services/xhs_login_service.py`；API 和抓取集成位于 `app/routers/xiaohongshu.py`、`app/services/xiaohongshu_service.py`；控制台位于 `frontend/src/`；同时更新配置、依赖、测试、README 和 docs。

验证结果：Python compileall 和 OpenAPI 路由检查通过；后端 85 passed；前端 Vitest 5 passed；Vite production build 通过（194 modules）；`git diff --check` 通过。真实小红书扫码依赖本机网络、Chromium 和有效 App 账号，未在自动化环境执行。
## 2026-07-02：修复扫码页二维码未弹出

复现 `QR_NOT_FOUND` 后确认小红书首页不会始终自动展示登录弹窗。登录服务改为主动点击可见登录入口，扩展二维码 image/canvas 选择器，并以可见登录容器截图兜底；失败响应只附带页面 URL。专项测试 6 passed，compileall 与 `git diff --check` 通过。
## 2026-07-02：识别小红书 IP 风控响应

真实二维码请求被官方登录页以 `error_code=300012` 重定向，确认是当前出口 IP 风控而非二维码 DOM 变化。登录服务新增 `RISK_CONTROL` 映射并将其标记为不可重试，detail 仅保留错误码，避免泄露风控 URL 参数；测试补充风控信息脱敏。
## 2026-07-02：新增现有 Chrome CDP 认证 Provider

实施顺序：确认 9222/9223/9515 当前均未监听；增加 `CHROME_CDP_URL`；实现 `POST /api/xhs/login/chrome`；验证真实 Chrome 的小红书 Cookie 并加密保存 storage state；将收藏抓取切换为 CDP 默认上下文的临时标签；更新前端连接入口、测试及流程文档。

关键决策：CDP 只允许本机地址；不关闭用户 Chrome 或既有标签；收藏抓取直接使用真实 Chrome，不再把 CDP 会话转交无头浏览器；退出登录仅删除 MemFlow 会话。新增错误 `CDP_UNAVAILABLE`、`CDP_NO_CONTEXT`、`CHROME_NOT_LOGGED_IN`。

变更文件：认证与抓取服务、`/api/xhs` 路由、配置与示例环境、Knowledge Console、后端/前端测试、`scripts/start_chrome_cdp.ps1`、README、docs 索引及 `docs/20-chrome-cdp-auth-flow.md`。

验证：后端 87 passed；前端 Vitest 5 passed；Vite production build 通过（194 modules）；compileall 通过。发现 Chrome 新授权服务占用 9222 但不提供 `/json/version`，专用脚本调整到 9223；真实 Chrome/151 已在 9223 返回 WebSocket debugger URL。账号连接需用户在专用窗口登录并重启 MemFlow 后完成。
## 2026-07-02：收藏同步前端参数面板

账号管理页新增收藏读取数量（1–100）、执行按钮、处理中状态及结果提示；前端直接调用 `POST /api/xhs/sync`，不生成或执行 PowerShell。后端为 `limit` 增加 1–100 校验。测试覆盖输入值进入 JSON 请求体和越界返回 422。

验证：后端 88 passed；前端 Vitest 6 passed；Vite production build 通过（194 modules）。
## 2026-07-02：整理小红书收藏读取操作 Runbook

将实际操作收敛为 `docs/21-xhs-favorites-operations-runbook.md`：记录专用 Chrome/CDP 启动与验证、MemFlow 启停、账号连接、前端数量参数、收藏读取、日常顺序、端口冲突、登录失效、IP 风控及安全边界。文档已加入 `docs/README.md`。
## 2026-07-02：调整 Console 收藏与项目记忆布局

将收藏读取参数面板从账号页移动到 Console 首页左栏，未登录时禁用执行；将首页完整 `hot.md` 卡片替换为入口按钮，并新增 `/console/memory` 独立安全渲染页面。更新响应式样式、前端测试和 Knowledge Console 模块文档。

验证：前端 Vitest 7 passed；Vite production build 通过（194 modules）；`git diff --check` 通过。
## 2026-07-02：新增 Agent Search Skill

实施顺序：尝试通过 skill-installer 查询同名 Skill，但 curated/experimental 与 GitHub 查询均受网络 TLS/搜索故障阻断；按 skill-creator 规范初始化并验证本地实现；因 `.agents` 为只读，最终放入 MemFlow 既有 `skills/agent-search`；安装 Python 3.13 兼容的 yt-dlp、imageio-ffmpeg、RapidOCR、ONNX Runtime；实现文章链接分类、视频抽帧 OCR、CLI 和本机 API。

关键决策：本地优先且不上传视频；当前只识别画面可见文字，不声称支持语音转写；下载内容使用忽略提交的临时目录；本地视频 API 路径限制在工作区；链接分类保留标签和上下文供人工核对。

变更文件：`skills/agent-search/`、`app/services/agent_search_service.py`、`app/routers/agent_search.py`、容器与主路由、依赖与 gitignore、`tests/test_agent_search_skill.py`、README、docs 索引及本模块文档。

验证：合成视频真实 OCR、文章分类及 API 专项 4 passed；完整后端 94 passed；CLI 冒烟提取 2 个资源并正确分类为 project/skill；OpenAPI 已注册 `/api/agent-search/extract`；Skill quick validation、compileall 与 `git diff --check` 通过。安装过程中确认旧 rapidocr-onnxruntime 不支持 Python 3.13，改用 rapidocr 3.9.1 + onnxruntime 1.27.0。
## inbox 纯文字整理与按钮修复（2026-07-02）

实施顺序：先确认按钮由 `pending_url_count` 错误控制，再将 inbox 总项数暴露为 `pending_item_count`，随后实现纯文字的哈希去重、AI 分析、知识增强、Notion 写入和失败保留，最后补充前后端回归测试与文档。

关键决策：保留 `pending_url_count` 兼容字段；纯文字使用 `content_hash` 而非伪造 URL 去重，`source_url` 与 `normalized_url` 为空；任务的 `remaining` 表示剩余整理项；仅 Notion 完整写入或确认本地已同步后删除 inbox 原文。

变更文件：`app/services/console_inbox_service.py`、`app/services/link_archive_service.py`、`frontend/src/App.tsx`、`frontend/src/App.test.tsx`、`tests/test_console_inbox_service.py`、`tests/test_link_archive_service.py`、`docs/17-link-inbox-archive.md`、`docs/18-knowledge-console.md`、`docs/00-implementation-log.md`。未新增数据库字段或迁移，复用既有 `ContentItem.content_hash`、文本输入枚举及状态字段。

验证：后端定向测试 11 项、完整后端测试 94 项、前端测试 8 项与生产构建均通过；`git diff --check` 通过。失败行为覆盖 AI/Notion 失败时保留纯文字、记录失败状态与可重试路径。
## RawBlock 前端设计系统落地（2026-07-02）

实施顺序：读取用户提供的 RawBlock 规范并写入根目录 `DESIGN.md`；盘点 Dashboard、认证页与项目记忆页的现有组件；重构全局设计 token、双栏布局和组件状态；补充待处理项/链接数联合展示；最后更新模块文档、索引并执行前端测试和生产构建。

关键决策：不引入装饰图片或图标；以 3px/5px 黑色边框和字号对比替代圆角、渐变及阴影；纯蓝色仅用于链接；保留现有 React 组件、API 和交互逻辑，响应式断点维持桌面双栏和移动端单栏。

变更文件：`DESIGN.md`、`frontend/src/styles.css`、`frontend/src/App.tsx`、`frontend/index.html`、`docs/18-knowledge-console.md`、`docs/README.md`、`docs/00-implementation-log.md`。未新增或变更持久化字段、公共 API、任务状态和失败行为。

验证结果：前端 Vitest 与 Vite production build 通过；`git diff --check` 通过。外部字体不可用时由本地字体栈降级，不阻断页面渲染或操作。
## 小红书内容优先 AI 整理规范（2026-07-03）

实施顺序：确认收藏同步仅读取卡片文字；将收藏详情页与视频源接入现有 Agent Search OCR；把 OCR 全文、资源链接和失败标记加入整理上下文；增加小红书专用 AI 规则；允许推荐资源清单超过 5 项；让已有收藏以新抓取内容重新分析；最后补充专项测试和文档。

关键决策：视频以 1 秒间隔、最多 1800 帧尽量覆盖画面文字；不引入音频转写能力或伪称读取声音；推荐类输出收敛为一句概括和 `名称｜完整网页链接｜极简介绍` 清单；作者与社交指标不进入分析；提取不到时显式标记而非静默降级。已有笔记重新同步以应用新规范。

变更文件：`app/services/xiaohongshu_service.py`、`app/services/container.py`、`app/services/content_pipeline_service.py`、`app/services/ai_service.py`、`tests/test_xiaohongshu_service.py`、`tests/test_collect_pipeline.py`、`tests/test_analysis_result.py`、`docs/17-xiaohongshu-favorites.md`、`docs/22-agent-search-skill.md`、`docs/00-implementation-log.md`。`docs/README.md` 已索引 17 与 22，无需新增条目。

公共 API 与数据库 schema 不变。复用 `raw_text`、`source_type`、`content_type`、`author`、AI/处理/Notion 状态字段；视频文件和帧不持久化。失败行为包括详情读取失败、视频源不可下载、OCR 空结果、OCR 异常、AI 失败及 Notion 失败，均有明确标记或既有状态。

验证结果：专项测试 27 项、完整后端回归 101 项与 Python compileall 均通过；`git diff --check` 通过。

## 收藏读取反馈与 Notion 连接稳定性（2026-07-04）

实施顺序：复查 Console 收藏面板和 `/api/xhs/sync`，确认未认证按钮静默禁用且已认证请求会阻塞到抓取、AI、Notion 全部结束；增加进程内收藏任务管理器和状态接口；前端改为启动后轮询；随后复查 Notion 调用链，复用客户端与数据库 schema；最后补充接口、连接缓存测试和模块文档。

关键决策：收藏任务使用独立数据库 Session，不跨请求持有 Session；单实例只运行一个任务；状态不落盘；未连接 Chrome 时提供明确授权入口。Notion properties 只在服务生命周期首次请求，配置重载会建立全新服务；页面创建不因不确定传输错误自动重放，避免重复页面。

变更文件：`app/services/xhs_sync_manager.py`、`app/routers/xiaohongshu.py`、`app/services/container.py`、`app/services/notion_service.py`、`app/main.py`、`frontend/src/App.tsx`、相关测试，以及 `docs/23-xhs-sync-jobs-notion-stability.md`、文档索引和本日志。未新增数据库或持久化字段。公共 API 新增 `GET /api/xhs/sync/status`，`POST /api/xhs/sync` 改为 202 后台任务语义；状态为 idle、fetching、processing、success、failed。

失败行为：并发启动返回 409；抓取/认证异常写入 `last_error`；单项整理失败累计并使批次为 failed；Notion 客户端在配置重载和应用退出时关闭。验证结果：后端定向测试 17 passed；前端 Vitest 8 passed；Vite production build 通过。完整回归与静态检查结果见本次最终交付记录。

## 收藏任务可观测性增强（2026-07-04）

实施顺序：区分浏览器扩展 `message port closed` 与 MemFlow 请求错误；扩展后台任务快照；在处理每条收藏前写入当前序号和标题；重构 Console 收藏卡片为阶段、进度、计数和错误面板；补充恢复轮询、响应式样式、前端测试及文档。

关键决策：读取收藏列表阶段没有可靠的服务端逐条总量回调，因此使用不确定进度动画；获得列表后才显示基于 `processed/fetched` 的真实百分比。页面初始化主动读取 `/api/xhs/sync/status`，刷新页面不再丢失当前进程内任务视图。扩展控制台异常不通过应用代码屏蔽，避免吞掉真实错误；应用轮询错误在卡片中明确呈现。

变更文件：`app/services/xhs_sync_manager.py`、`frontend/src/App.tsx`、`frontend/src/styles.css`、`frontend/src/App.test.tsx`、`docs/23-xhs-sync-jobs-notion-stability.md` 和本日志。未新增持久化字段；公共状态响应新增 `phase`、`message`、`current_index`、`updated_at`，状态枚举不变。失败仍进入 `failed` 并保留 `last_error`。

验证结果：完整后端 103 passed；前端 Vitest 9 passed；Vite production build、Python compileall 与 `git diff --check` 通过。pytest 仅提示受控环境无权创建 `.pytest_cache`，不影响测试执行。
