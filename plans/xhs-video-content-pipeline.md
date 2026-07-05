# Task：小红书视频完整内容提取（CDP + OpenCLI + OCR + Whisper）

## 一、目标

在不替换现有收藏夹读取能力的前提下，建立可插拔的小红书视频内容流水线：

```text
Chrome/CDP 获取收藏笔记链接
        ↓
现有详情页读取尝试获取正文和视频源
        ↓
OpenCLI 下载笔记媒体（备用 Provider）
        ↓
Agent Search 对视频抽帧 OCR
        ↓
Whisper 对视频音频转写
        ↓
正文 + OCR + 语音转录 + 资源链接合并
        ↓
AI 分类、摘要、知识提取
        ↓
本地数据库 + Notion
```

最终应能区分并展示“笔记正文读取成功”“视频下载成功”“OCR 成功”“语音转写成功”“部分降级”与“完全失败”，不能再用一个模糊的“视频读取失败”覆盖所有环节。

## 二、边界与关键决策

- 收藏列表继续由现有 Chrome/CDP Provider 获取；Agent Reach/OpenCLI 不负责“我的收藏夹”枚举。
- Agent Reach 仅用于安装、诊断和选择上游能力；运行时优先直接调用 OpenCLI 的稳定 CLI/JSON 输出，不把 Agent Reach 当作业务代理服务。
- OpenCLI 是媒体获取备用 Provider：现有浏览器详情页成功得到视频源时不重复调用；缺少视频 URL、下载被拒或页面结构变化时才降级调用。
- OCR 只负责画面可见文字；Whisper 只负责音轨语音。两者结果分别保存和标记，不互相冒充。
- 单个环节失败不丢弃已成功内容；正文、OCR、转录任一有效即可继续 AI 整理，并标记内容完整度。
- 不在 `.env`、日志、数据库或前端保存/显示完整 Cookie。OpenCLI/Agent Reach 凭据使用其本机安全存储，不复制进 MemFlow。
- 下载的视频、音频、帧和临时字幕默认仅存在忽略提交的临时目录，任务完成后清理。

## 三、准备与可行性验证

### Agent Reach / OpenCLI 安装

- 先阅读并固定 Agent Reach 与 OpenCLI 的版本、许可证和安装清单。
- 先执行 Agent Reach `--dry-run`，记录将安装的 Python、Node、OpenCLI、Browser Bridge、MCP 与 Skill 组件。
- 默认采用安全模式安装，不允许安装脚本静默修改项目 `.env` 或提交 Agent 全局配置。
- Windows 环境确认 Node.js 20+、Python、ffmpeg、OpenCLI CLI 与 Browser Bridge 可用。
- 执行 `agent-reach doctor`、`opencli doctor`，把诊断结果记录到实施文档，但不记录 Cookie、Token、浏览器 Profile 路径或账号信息。
- 用一个本人有权访问的小红书视频笔记验证：
  - OpenCLI 能读取笔记元数据；
  - `opencli xiaohongshu download <url> --output <temp>` 能下载视频；
  - JSON/退出码可稳定区分成功、空结果、超时、未登录和配置错误。

### Go / No-Go 条件

- 若 OpenCLI 无法在当前 Windows + Chrome 环境下载测试视频，不接入生产流水线，只保留诊断报告。
- 若只能通过导出明文 Cookie 使用，则停止集成，改为 Browser Bridge/CDP 登录态方案。
- 若测试账号触发风控，停止自动重试并要求用户在真实浏览器确认状态。

## 四、Provider 架构

新增媒体获取协议，业务流水线只依赖协议：

```python
class XhsMediaProvider(Protocol):
    name: str
    def can_handle(note_url: str) -> bool: ...
    def fetch(note_url: str, workspace: Path, progress, cancel_event) -> MediaFetchResult: ...
```

实现：

- `BrowserMediaProvider`：复用当前详情页得到的正文、显式链接、视频 URL。
- `OpenCliMediaProvider`：调用 OpenCLI 下载小红书图片/视频并读取结构化输出。
- `MediaProviderChain`：按 Browser → OpenCLI 顺序执行；记录每次尝试、耗时和失败类别。

`MediaFetchResult` 至少包含：

- `provider`
- `note_url`
- `text`
- `video_paths`
- `image_paths`
- `resource_links`
- `status`
- `warnings`
- `started_at` / `finished_at`

禁止使用 `shell=True` 或字符串拼接命令；使用参数数组执行 OpenCLI，校验可执行文件路径、笔记 URL、输出目录和返回文件均位于允许范围。

## 五、Whisper 语音转写

- 新增 `AudioTranscriptionService` 接口，默认实现采用本地 `faster-whisper`；模型通过配置选择，默认使用适合本机资源的中文多语言模型。
- 使用 ffmpeg 从视频提取单声道 16 kHz 音频；提取与转写均有独立超时、取消检查和资源限制。
- 自动语言检测，但允许中文优先提示；保留分段的开始时间、结束时间和文本。
- 对无音轨、纯音乐、低置信度、模型缺失、内存不足和超时返回稳定错误，不把它们当作空白成功。
- 不默认保存音频；若开启调试保留，必须位于忽略提交的任务目录并在 UI 明示。

转写结果：

```json
{
  "status": "success|empty|failed|cancelled",
  "language": "zh",
  "text": "...",
  "segments": [{"start": 0.0, "end": 4.2, "text": "..."}],
  "model": "...",
  "durationSeconds": 0,
  "error": null
}
```

## 六、OCR 与内容合并

- 复用现有 Agent Search 视频抽帧 OCR，不建立第二套 OCR 实现。
- OCR 和 Whisper 可并行执行，但必须分别限制并发，避免 20 条视频同时占满 CPU/内存。
- 新增 `VideoContentAssembler`，按以下区块构造 AI 输入：
  - `[笔记正文]`
  - `[正文显式链接]`
  - `[视频画面 OCR]`
  - `[视频语音转录]`
  - `[视频中识别到的资源链接]`
  - `[提取警告]`
- 合并时按规范化文本去重，不删除时间顺序不同但内容相近的关键片段。
- 限制送入模型的总字符数；优先保留正文、资源链接、OCR/转录的高信息片段，并记录截断信息。
- AI 提示词明确区分来源，禁止把 OCR 错字或低置信度语音当作确定事实。

## 七、任务状态与前端

扩展收藏任务步骤：

```text
reading_item
fetching_media
opencli_download
extracting_audio
video_ocr
audio_transcription
assembling_content
ai_analysis
notion_sync
```

每一步返回：当前收藏序号、标题、Provider、步骤、开始时间、最后进展时间、心跳、耗时和可选警告。

Console 增加单条视频处理详情：

- 媒体获取：Browser / OpenCLI / 失败
- 画面文字：成功 / 空 / 失败 / 跳过
- 语音转写：成功 / 无音轨 / 失败 / 跳过
- AI 与 Notion：等待 / 成功 / 失败
- 当前视频耗时和批次总进度
- 取消任务按钮继续可用

前端不得获取本地媒体绝对路径、Cookie 或 OpenCLI 凭据；只显示文件类型、数量、状态和脱敏错误。

## 八、配置与持久化

新增非敏感配置建议：

```env
XHS_MEDIA_PROVIDER_CHAIN=browser,opencli
OPENCLI_COMMAND=opencli
VIDEO_OCR_ENABLED=true
VIDEO_TRANSCRIPTION_ENABLED=true
WHISPER_MODEL=small
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
VIDEO_STEP_TIMEOUT_SECONDS=180
VIDEO_MAX_DURATION_SECONDS=3600
```

- 不新增 Cookie 配置。
- 数据库需要保存可查询的处理摘要，而不是原始媒体：`media_fetch_status`、`media_provider`、`ocr_status`、`transcription_status`、`content_completeness`、`media_error_message`。
- 如新增字段，必须提供 SQLite 迁移和旧记录默认值。
- 原始视频、音频、帧、完整转录是否长期保存必须由独立配置控制，默认不保存。

## 九、错误合同

统一错误结构：

```json
{
  "code": "OPENCLI_AUTH_REQUIRED",
  "message": "OpenCLI 无法使用当前 Chrome 登录态",
  "detail": "脱敏诊断",
  "retryable": false,
  "stage": "opencli_download",
  "provider": "opencli"
}
```

至少覆盖：

- `OPENCLI_NOT_INSTALLED`
- `OPENCLI_BRIDGE_UNAVAILABLE`
- `OPENCLI_AUTH_REQUIRED`
- `OPENCLI_EMPTY_RESULT`
- `MEDIA_DOWNLOAD_TIMEOUT`
- `MEDIA_DOWNLOAD_BLOCKED`
- `VIDEO_TOO_LONG`
- `AUDIO_TRACK_MISSING`
- `FFMPEG_FAILED`
- `WHISPER_MODEL_MISSING`
- `TRANSCRIPTION_TIMEOUT`
- `OCR_FAILED`
- `TASK_CANCELLED`

任何日志不得包含 Cookie、签名参数、完整本地路径或完整下载 URL；URL 查询参数需要删除或脱敏。

## 十、公共 API

保持现有：

- `POST /api/xhs/sync`
- `GET /api/xhs/sync/status`
- `POST /api/xhs/sync/cancel`

扩展状态响应中的单条媒体阶段；如需要单独诊断，新增只读接口：

- `GET /api/xhs/providers`：返回 Provider 是否安装、是否可用、版本和脱敏诊断。
- `POST /api/xhs/providers/opencli/check`：执行一次无凭据回显的健康检查，不返回 Cookie。

不要提供任意命令、任意 URL 或任意本地路径执行接口。

## 十一、测试计划

### 单元测试

- Provider Chain 首选成功、首选失败降级、全部失败和取消。
- OpenCLI 参数数组、退出码映射、JSON 解析、路径逃逸和超时终止。
- ffmpeg 无音轨、损坏视频、超长视频、取消和超时。
- Whisper 成功、空转录、语言检测、模型缺失、低置信度和异常。
- OCR/转录并行限制、内容合并、去重、截断和资源链接提取。
- 任务状态、心跳、最后进展、单条失败继续与批次结果。

### API 与前端测试

- Provider 健康接口不泄漏敏感信息。
- 同步状态完整展示媒体、OCR、转录、AI、Notion 阶段。
- 取消可终止下载、OCR、转录并清理任务目录。
- 前端显示部分成功和具体失败阶段，不显示本地绝对路径。

### 集成与手工验收

- 图文笔记：不调用 Whisper，既有能力不回归。
- 有画面文字、无语音视频：OCR 有结果，转录标记无音轨/空。
- 有语音、无画面文字视频：转录有结果，OCR 标记空。
- 同时有画面文字和语音视频：两者合并并进入 AI/Notion。
- OpenCLI 降级下载：Browser 获取视频源失败后成功下载并处理。
- 风控、登录失效、网络断开、超时和用户取消均有明确结果。

执行完整 `pytest`、Vitest、Vite build、Python compileall、OpenAPI 检查、敏感信息扫描和 `git diff --check`。真实账号测试仅使用本人授权账号和内容，测试结果不得提交原始媒体或转录正文。

## 十二、文档要求

按照仓库 `AGENTS.md` 同步完成：

1. 新建或更新 `docs/` 下视频提取模块文档。
2. 加入 `docs/README.md`。
3. 在 `docs/00-implementation-log.md` 记录安装、决策、变更文件、迁移和验证结果。
4. 更新小红书收藏、Agent Search、启动与故障排查文档。
5. 记录公共 API、Provider、持久化字段、状态转换、失败行为和测试覆盖。

文档不得包含真实 Cookie、Token、账号、原始视频、OCR 全文、语音转录全文或用户收藏内容。

## 十三、实施顺序

1. Agent Reach/OpenCLI dry-run、安全安装和单笔记下载 PoC。
2. 定义 `XhsMediaProvider`、结果和错误合同。
3. 实现 OpenCLI Provider 与 Provider Chain。
4. 实现 ffmpeg 音轨提取和 Whisper 服务。
5. 并行接入现有 OCR，完成内容合并器。
6. 接入收藏任务状态、取消、超时和清理。
7. 接入 AI、数据库迁移和 Notion 展示。
8. 完成前端状态与 Provider 诊断页。
9. 自动化测试、真实单条视频验收、安全扫描。
10. 更新全部文档和实施日志。

## 十四、验收标准

1. 收藏列表仍由 CDP 可靠读取，不因 OpenCLI 不可用而失效。
2. Browser Provider 无法取得视频时，OpenCLI 可以作为自动降级路径。
3. 视频画面文字和语音分别提取、分别标记并合并进入 AI。
4. 无字幕视频能够通过 Whisper 得到可用语音文本；无语音视频不会误报失败。
5. 单条失败不阻断整个收藏批次，失败阶段和原因在前端清晰可见。
6. 下载、OCR、转录均支持超时、心跳和取消，临时文件可验证地清理。
7. 前端和日志不暴露 Cookie、签名 URL、凭据或本地绝对路径。
8. 不提交原始媒体、音频、帧、OCR/转录用户内容、缓存或模型文件。
9. 所有自动化测试、构建、静态检查和文档要求通过。
10. 至少用一条本人授权的小红书视频完成端到端手工验收并记录脱敏结果。
