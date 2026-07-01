# Knowledge Console 可视化控制台

## 目标与访问方式

Knowledge Console 是 MemFlow 的本机单用户操作界面，使用 React、Vite 和 TypeScript。开发模式运行 `cd frontend && npm run dev`，生产构建运行 `npm run build`，随后由 FastAPI 在 `http://127.0.0.1:8000/console` 托管。

Vite 将 `/api` 代理到后端；生产模式同源访问，不需要 CORS。控制接口验证客户端为 loopback，绑定到非本机地址时远程请求返回 403。

## 页面模块

- 小红书配置：保存 Cookie、可选用户名/密码，显式检测收藏登录态；Cookie 使用密码输入框，保存后清空，只显示长度。
- Notion 配置：保存 Token 和数据库 ID，显式测试数据库并提供打开链接；Token 不回显。
- inbox：追加单/多链接或含链接段落，查看失败说明、待处理数量，使用版本号安全删除单项。普通文字按一次粘贴整体压为一个整理单位；纯链接列表按每条链接之间一个空行写入。
- 后台任务：显示 idle/processing/success/failed、当前 URL、处理/成功/重复/失败统计和最近错误。
- 最近结果：从 SQLite 展示标题、原始链接、normalized_url、Notion 页面、归档时间和状态。
- hot.md：安全渲染 Markdown，不启用原始 HTML。

## 公共 API

配置：`GET /api/config/status`、`POST|DELETE /api/config/xhs`、`POST|DELETE /api/config/notion`、`POST /api/xiaohongshu/test`、`POST /api/notion/test`。

操作：`GET|POST /api/inbox`、`DELETE /api/inbox/item`、`POST /api/processor/start`、`GET /api/processor/status`、`GET /api/notion/recent`、`GET /api/hot`。现有同步 `/api/inbox/archive-links` 和 CLI 保持兼容。

配置保存仅允许 XHS_COOKIE、XHS_USERNAME、XHS_PASSWORD、NOTION_API_KEY、NOTION_DATABASE_ID。空输入保持原值；清除必须调用 DELETE。`.env` 使用同目录临时文件和 `os.replace` 原子更新，运行任务期间配置写入返回 409，保存后服务立即重载。

## 文件与状态

inbox 返回 `version`、`pending_url_count` 和 items。item_id 由位置与内容摘要生成；删除时版本不一致返回 409，避免误删并发修改。

ProcessorManager 一次只允许一个后台线程，使用独立数据库 Session。状态保存在内存，重启后恢复 idle；输入、SQLite 和 Notion 状态保证任务可重新执行。任务完成后前端自动刷新 inbox、最近结果和 hot.md。

normalized_url 增加 fbclid/gclid 过滤并去除非根路径末尾斜杠。启动迁移重新计算历史 URL，语义重复时最早记录保留 canonical identity，其他内容不删除。

## 安全与失败行为

- 前端不使用 localStorage/sessionStorage 保存密钥，不向控制台打印请求体。
- 配置响应只包含布尔值、长度、脱敏用户名、数据库 ID 和主动测试结果。
- 小红书账号密码只保存，不用于自动账号密码登录；Cookie/profile 优先。
- 外部服务测试由用户显式触发；保存配置不会访问 Notion 或小红书。
- API、队列冲突、外部网络及归档失败均显示明确错误，原有“不成功不删除 inbox”规则不变。

## 测试覆盖

后端覆盖配置原子更新与脱敏、loopback 限制、队列追加/冲突删除、任务并发与进度、只读 API、静态页面、URL 新规则及全部归档回归。前端覆盖六个区域、安全 Markdown、保存后清空秘密输入和后台任务轮询。验收命令为 pytest、compileall、`npm test -- --run`、`npm run build` 和 `start.ps1 -Check`。
## 验收结果（2026-07-01）

- 后端完整测试：75 passed。
- 前端 Vitest：1 test file、3 tests passed，覆盖区域渲染、安全 Markdown、秘密输入清空和任务轮询。
- `npm run build`：通过；194 modules，JS 270.35 kB、CSS 5.16 kB。
- `python -m compileall -q app skills scripts tests`：通过。
- `start.ps1 -Check` 与 `git diff --check`：通过。
- FastAPI `/console` 和构建后的 JS asset：HTTP 200。
- 隐藏本地 Uvicorn + Chromium 真实渲染冒烟：页面标题正确，六个模块标题全部可见，截图生成成功后已清理。
- 安全验证：配置状态响应不含 Cookie、Token 或对应字段名；远程 IP 被 403 拒绝。
## inbox 粘贴单位规则（2026-07-01）

- 如果本次粘贴的所有非空行都是 URL，则每个 URL 单独成为一个队列项，文件中用一个空行分隔。
- 只要本次粘贴包含普通文字，整次粘贴就是一个整理单位；内部换行与空行压为单个空格，避免被 Markdown 段落规则拆开。
- 该规则只影响新追加内容。已有 inbox 项目不自动合并，防止无法确认原始粘贴边界时误改用户内容。
