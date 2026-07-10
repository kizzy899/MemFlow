# 视频知识提取流水线

## 用途

`app/video/` 提供通用视频知识提取能力，面向小红书、抖音、B站和 YouTube 等视频 URL。URL 收集时，`ContentPipelineService` 会先识别视频平台；视频 URL 不再走网页正文解析，而是生成结构化文件后再交给 AI 总结和 Notion 同步。

## 模块

- `downloader.py`：基于 `yt-dlp` 下载视频，统一保存为 `videos/video.mp4`，并生成 `metadata.json`。
- `metadata.py`：识别平台、判断视频 URL、补齐 title、author、duration、platform、url 等元数据。
- `audio.py`：通过 ffmpeg 抽取 16kHz 单声道 `audio/audio.wav`。
- `whisper.py`：基于 `faster-whisper` 输出 `subtitle.srt`、`subtitle.txt`、`subtitle.json`。
- `frames.py`：按 `VIDEO_FRAME_INTERVAL_SECONDS` 抽帧到 `frames/`，并写入 `frames/frames.json`。
- `ocr.py`：优先使用 PaddleOCR，缺失时降级 RapidOCR，输出逐帧 `ocr.json`。
- `vision.py`：可选调用 OpenAI 兼容多模态模型，输出逐帧 `vision.json`。默认关闭，避免无意产生高额调用。
- `timeline.py`：融合字幕、OCR 和 Vision，生成统一 `timeline.json`。
- `summarize.py`：只基于 metadata、timeline、subtitle、ocr 生成 `summary.md`，不重新分析原始视频。
- `pipeline.py`：编排下载、音频、字幕、抽帧、OCR、Vision、时间轴、总结、缓存与失败恢复。

## 产物与缓存

每个视频 URL 使用 SHA-256 URL hash 建立工作区：`data/video/<url_hash>/`。主要产物包括：

- `videos/video.mp4`
- `metadata.json`
- `audio/audio.wav`
- `audio/subtitle.srt`
- `audio/subtitle.txt`
- `audio/subtitle.json`
- `frames/*.jpg`
- `frames/frames.json`
- `ocr.json`
- `vision.json`
- `timeline.json`
- `summary.md`
- `status.json`

缓存位于 `cache/video/<url_hash>/`。当缓存里存在 `summary.md` 和 `timeline.json` 时，后续同一 URL 直接恢复结构化产物，不重复执行视频解析。下载成功后 metadata 内也记录 `video_hash`，用于后续比对真实视频文件是否变化。

## 配置

新增环境变量：

- `VIDEO_DOWNLOAD_TIMEOUT_SECONDS`：视频下载超时，默认 600 秒。
- `VIDEO_FRAME_INTERVAL_SECONDS`：抽帧间隔，默认 1 秒。
- `VIDEO_VISION_ENABLED`：是否启用逐帧视觉理解，默认 false。
- `VIDEO_VISION_MODEL`：Vision 使用的 OpenAI 兼容模型，默认 `gpt-4.1-mini`。
- `VIDEO_VISION_SAMPLE_EVERY`：Vision 每隔多少帧采样一次，默认 1。
- `VIDEO_SUMMARY_TIMELINE_LIMIT`：传入总结模型的 timeline/subtitle/OCR 行数上限，默认 800。

沿用既有 Whisper 配置：`WHISPER_MODEL`、`WHISPER_DEVICE`、`WHISPER_COMPUTE_TYPE`、`VIDEO_STEP_TIMEOUT_SECONDS`。

## 持久化字段

`content_items` 新增：

- `subtitle_path`
- `ocr_path`
- `timeline_path`
- `summary_path`
- `video_duration`
- `video_platform`
- `has_video`
- `has_subtitle`

视频处理状态继续复用 `media_fetch_status`、`ocr_status`、`transcription_status`、`content_completeness`、`media_error_message`。状态值包括 `success`、`empty`、`failed`、`skipped`、`processing`。

## Notion 同步

如果 Notion 数据库存在以下可选字段，会自动写入：

- `subtitle_path`
- `ocr_path`
- `timeline_path`
- `summary_path`
- `video_duration`
- `video_platform`
- `has_video`
- `has_subtitle`
- `AI Summary`
- `Timeline`
- `Commands`
- `Tools`

页面正文的 `MemFlow 视频内容` Toggle 会包含 AI Summary、Timeline 摘要、产物路径和视频提取状态，方便之后搜索与人工复核。

## 失败行为

任何单步失败都不会中断整个视频 Pipeline：

- 下载失败：仍生成失败说明并进入 AI 总结阶段。
- 音频或 Whisper 失败：继续抽帧、OCR、Vision、timeline 和 summary。
- OCR 失败：继续字幕与 Vision。
- Vision 失败或未启用：继续字幕与 OCR，并在 summary 中标记 `Vision unavailable`。
- Timeline 为空：仍生成 `summary.md`，注明可用结构化信息不足。

AI 后续分析只读取结构化产物和 `timeline.json`，不重新解析原始视频。

## 测试覆盖

`tests/test_video_content_pipeline.py` 覆盖：

- 视频 URL 不进入普通文章 parser，而是调用结构化视频 pipeline。
- ContentItem 写入平台、时长、字幕/时间轴/summary 路径和可用性字段。
- SQLite 旧库自动迁移新增视频字段。