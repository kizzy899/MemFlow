# Agent Search Skill

## 功能

项目内 Skill 位于 `skills/agent-search/`，可被 MemFlow 通过 CLI 或本机 API 调用：

- 对本地视频或公开可下载视频按时间间隔抽帧，使用 RapidOCR + ONNX Runtime 识别画面中的中文、英文、字幕、幻灯片和界面文字；
- 对 HTML 文件、公开文章 URL 或直接文本提取显式链接；
- 将链接启发式分类为 `project`、`skill`、`recommended`；
- 保留视频时间戳、OCR 平均置信度、链接标签和局部上下文。

本版本不做音轨语音转写；“视频文字”指视频画面中实际可见的文字。视频下载使用 yt-dlp，临时文件写入已忽略提交的 `data/agent-search-tmp` 并在运行后清理。

## 使用方式

```powershell
.\.venv\Scripts\python.exe skills\agent-search\scripts\agent_search.py video files\demo.mp4 --interval 2 --pretty
.\.venv\Scripts\python.exe skills\agent-search\scripts\agent_search.py video "https://公开的视频地址" --interval 3 --max-frames 200 --pretty
.\.venv\Scripts\python.exe skills\agent-search\scripts\agent_search.py article "https://example.com/article" --pretty
```

API：

```http
POST /api/agent-search/extract
Content-Type: application/json

{
  "source_type": "video",
  "source": "files/demo.mp4",
  "interval": 2,
  "max_frames": 300
}
```

API 仅允许本机访问。视频本地路径必须位于 MemFlow 工作区。文章 `source` 可为工作区文件、HTTP(S) URL 或直接文本。

## 公共字段

请求字段：

- `source_type`：`video | article`；
- `source`：路径、URL 或文章文本，不能为空；
- `interval`：视频抽帧秒数，范围 `(0, 60]`，默认 2；
- `max_frames`：最多处理帧数，范围 1–3000，默认 300。

响应 `data`：

- `source_type/source`：来源类型与安全来源标识；
- `text`：去重后的可见文字；
- `segments`：视频 `timestamp/text/score`；
- `resources`：`url/category/label/context`；
- `metadata`：方法、抽帧数、视频时长和间隔；
- `errors`：稳定错误数组。

## 分类、状态与失败

GitHub/GitLab/Gitee 仓库形状链接归为项目；包含 Skill、plugin、MCP、Agent、marketplace 或 `SKILL.md` 的链接归为 Skill；其他 HTTP(S) 链接归为推荐网页。分类为启发式结果，调用方应保留原始标签与上下文供核对。

一次调用的内存状态为 `requested → processing → success|failed`，不新增数据库字段或迁移。成功 API 返回 `success=true`；参数越界返回 422；下载失败、无效视频、网络或 OCR 异常由 CLI 写入 `AGENT_SEARCH_FAILED`，API 未捕获运行异常时返回 500。空 OCR 结果是成功但 `text/segments` 为空，不伪造文字。

## 安全与持久化

- 不自动保存视频、帧图片、文章正文或 OCR 全文到数据库；
- 下载文件只存在临时目录，目录已加入 `.gitignore`；
- 不将私有 Cookie 注入 yt-dlp；
- 公开 URL 必须由用户有权访问和处理；
- API 的本地视频路径限制在工作区，避免任意文件读取。

## 测试覆盖

- 合成 HTML 验证项目、Skill、推荐网页分类；
- 合成 AVI 帧执行真实 RapidOCR，验证可见文字和时间戳；
- API 验证文章提取及视频参数边界；
- `quick_validate.py` 验证 Skill frontmatter 与目录结构。
## 小红书收藏调用约定（2026-07-03）

小红书收藏同步通过服务层调用视频提取，参数为 `interval=1.0`、`max_frames=1800`，以提高字幕和画面文字覆盖率。返回的 `text`、`segments`、`resources` 进入当前收藏条目的整理上下文；临时视频仍在调用结束后清理。空 `text` 被上游标记为“视频文字提取为空”，下载/OCR 异常被标记为“视频文字提取失败”。该集成不改变 `/api/agent-search/extract` 的公共契约和持久化边界。
