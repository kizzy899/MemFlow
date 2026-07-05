# 小红书视频完整内容流水线

## 目标与边界

收藏列表继续由已授权的 Chrome/CDP 9223 读取。视频优先使用详情页暴露的媒体地址；失败时才调用固定版本 OpenCLI，并通过 `OPENCLI_CDP_ENDPOINT` 复用同一 Chrome 登录态。系统不复制 Cookie、不安装 Browser Bridge，也不提交媒体或模型。

下载成功后并行执行 Agent Search 画面 OCR 与 faster-whisper `small / CPU INT8` 语音转写，再合并正文、资源链接、OCR、转录和警告。任务目录 `data/xhs-media-tmp/<task-id>/` 在 `finally` 中删除；模型缓存位于 `data/models/whisper/`，两者均被 Git 忽略。

## Provider 与状态流

`fetching_media → opencli_download（按需）→ video_ocr / audio_transcription → assembling_content → ai_analysis → notion_sync`

- `BrowserMediaProvider` 下载详情页现有视频源。
- `OpenCliMediaProvider` 只接受小红书 HTTPS 笔记 URL，以参数数组启动并限定输出目录。CDP、认证或超时失败会在当前实例熔断后续调用。
- `AudioTranscriptionService` 懒加载并复用 Whisper；同一实例最多一个转录任务。
- `VideoContentAssembler` 让本地 `raw_text` 保存未截断全文；AI 输入最多 60,000 字符，截断时追加警告。

视频超过 1,800 秒时保留正文，跳过 OCR 与转录并记录 `VIDEO_TOO_LONG`。OpenCLI 下载上限 90 秒，OCR/转录默认上限 180 秒。取消会终止 OpenCLI 子进程；OCR/Whisper 在检查点退出。

## 公共 API

- `GET /api/xhs/providers`：Browser、OpenCLI、Whisper 的安装、版本、可用性及脱敏信息。
- `POST /api/xhs/providers/opencli/check`：重新读取 OpenCLI 安装/版本及验证状态；不接受命令、URL或路径。
- `GET /api/xhs/media/candidates`：最多 100 条失败、空结果、跳过或完整度不足的小红书视频。
- `POST /api/xhs/media/reprocess`：请求 `{ item_ids: [...] }`，去重后必须为 1–20 条已存在的小红书视频。成功返回 202；已有任务时返回 409。
- 既有同步 API 保持契约，并增加媒体处理步骤。

Provider API 不返回 Cookie、任意命令或本地媒体路径。Console 只允许用户勾选候选项手动重处理，不自动回填旧数据。

## 持久化字段

`content_items` 新增 `media_fetch_status`、`media_provider`、`ocr_status`、`transcription_status`、`content_completeness`、`media_error_message`。

媒体/OCR/转录状态使用 `pending|processing|success|empty|failed|skipped|cancelled`。旧记录迁移默认 `skipped`；完整度默认 `unknown`，处理后为 `complete|partial`。完整正文、OCR、转录及警告写入 `raw_text`。Notion 新增顶层 Toggle `MemFlow 视频内容`，每段 1,800 字符；重处理时只归档同名旧 Toggle，不改人工区块。

## 失败行为

稳定错误包括 `INVALID_NOTE_URL`、`BROWSER_MEDIA_EMPTY`、`MEDIA_DOWNLOAD_BLOCKED`、`MEDIA_DOWNLOAD_TIMEOUT`、`OPENCLI_NOT_INSTALLED`、`OPENCLI_AUTH_REQUIRED`、`OPENCLI_BRIDGE_UNAVAILABLE`、`OPENCLI_EMPTY_RESULT`、`OPENCLI_CIRCUIT_OPEN`、`MEDIA_PATH_ESCAPE`、`VIDEO_TOO_LONG` 和 `TASK_CANCELLED`。

媒体失败不伪造 OCR 或转录；正文仍可以部分内容继续整理，并以 `partial` 和警告呈现。stderr、URL 查询参数和本地路径不进入 API、日志或 DOM。AI/Notion 失败沿用既有失败与重试机制。

## 配置与验证

`.env.example` 提供非敏感的 OpenCLI、OCR、Whisper、超时和最大时长配置；登录态仍仅来自 Chrome/CDP 或认证存储。

测试覆盖 Provider 降级/全失败、URL/路径约束、内容合并和字符预算、数据库字段、Notion Toggle、Provider/候选/重处理 API、CDP WebSocket 解析及 Console 展示。

2026-07-05 真实 PoC 确认 CDP 9223 可连接，Agent Reach 1.5.0、OpenCLI 1.8.6、faster-whisper 1.2.1 已安装；但收藏首条详情返回小红书 `300031`，OpenCLI 未完成可验证媒体下载，因此真实媒体闸门为 **No-Go**。系统未复制 Cookie或安装 Browser Bridge。因没有可用视频输入，Whisper `small` 模型尚未下载，也不声称真实转录已验证；获得可访问视频后可从 Console 手动复验。
