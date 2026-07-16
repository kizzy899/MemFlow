# 首页文章翻译后台任务

## Purpose

首页“文章翻译”卡片把公开文章 URL 交给仓库内 `skills/global-tech-translation` 完整流水线处理，生成可追溯稿件包，并把最终 `translation.md` 记录为 MemFlow 条目的译文路径。

## Public APIs

- `POST /api/translate/tasks`
  - Request: `{ "url": "https://example.com/article" }`
  - Response: `TranslationTaskStatus`
  - 行为：先按规范化 URL 查找已有 `translated_text_path`，命中时直接返回 `success`；未命中且没有运行中的翻译任务时启动后台任务；已有任务运行中时返回当前任务状态。
- `GET /api/translate/tasks/status`
  - Response: `TranslationTaskStatus`
  - 用于首页轮询当前内存任务状态。

`TranslationTaskStatus` 字段：`task_id`、`status`、`source_url`、`title`、`translated_file_path`、`item_id`、`notion_page_id`、`notion_page_url`、`last_error`、`started_at`、`finished_at`。

## Persisted Fields And Outputs

- 译文产物保存到 `TRANSLATION_OUTPUT_DIR`，默认 `files/translated/<article-dir>/translation.md`。
- 同目录保留 `00-source.md`、`qa.json`、分析文件、分块文件、图片资源等流水线稿件包内容。
- `ContentItem` 更新字段包括：`source_url`、`normalized_url`、`source_platform=translation`、`content_type=translation`、`raw_text`、`clean_content`、`translated_text_path`、`translation_status=translated`、`process_status=completed`、`fetch_status=success`、`ai_status=success`、`is_translated=true`。
- 翻译完成后调用既有 Notion 同步链路；Notion 未配置时条目保持本地保存并记录 pending/错误信息。

## State And Failure Behavior

任务状态保存在进程内存中，服务重启后不恢复正在运行的翻译任务。同一时刻只允许一个后台翻译任务运行。

失败行为：

- 请求 URL 非法时由 Pydantic 返回 422。
- 缺少 `GEMINI_API_KEY` 时任务失败，不进入 Codex 占位稿交付路径。
- 流水线返回非零退出、超时、缺少 `translation.md` 或 `qa.json` 时任务失败。
- `qa.json.verdict` 不是 `ready`、`requires_agent_completion=true` 或 `resolved_translator=codex` 时任务失败，不把待接管稿视作完成稿。
- 同一 URL 已有 `translated_text_path` 时直接返回已有结果，不重复运行流水线。

## Test Coverage And Verification

测试覆盖：

- 翻译任务接口拒绝非法 URL。
- 已有译文路径的重复 URL 直接返回 success。
- 缺少 Gemini key 时失败。
- QA 未 ready 时失败。
- ready 产物保存 `translated_text_path` 并尝试 Notion 同步。
- 首页卡片渲染、提交 URL、processing 状态和完成结果展示。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_translate_tasks.py -q
node node_modules\vitest\vitest.mjs run src\App.test.tsx
```
