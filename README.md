# MemFlow

MemFlow is a FastAPI-based personal knowledge agent that collects web links, Xiaohongshu favorites, and translation tasks into a single Notion database.

## Features

- Submit a normal web article and automatically:
  - parse the source page
  - summarize it with AI
  - classify it and generate tags
  - store it locally and sync it to Notion
- Submit a translation task from either a URL or raw foreign text
- Save translated Markdown files under `files/translated/`
- Sync Xiaohongshu favorites through Playwright using browser profile or cookie-based login state
- Deduplicate by `source_url`

## Project Layout

```text
knowledge-agent/
  app/
    main.py
    config.py
    db.py
    models/
    routers/
    schemas/
    services/
  data/
  files/
    raw/
    translated/
  skills/
    translation_skill.py
  tests/
```

## Quick Start

1. Create a virtual environment and install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

2. Copy `.env.example` to `.env` and fill in your config.

3. Start the API:

```bash
uvicorn app.main:app --reload
```

## Notion Database Requirements

Database name suggestion: `Personal Knowledge Inbox`

Required properties:

- `标题`: Title
- `原链接`: URL
- `来源平台`: Select
- `内容类型`: Select
- `AI总结`: Rich text
- `分类`: Select
- `标签`: Multi-select
- `作者`: Rich text
- `发布时间`: Date
- `译文路径`: Rich text
- `翻译状态`: Status
- `处理状态`: Status
- `创建时间`: Date
- `更新时间`: Date

The service validates these properties when Notion credentials are configured.

## API

- `POST /api/web-links/submit`
- `POST /api/translate`
- `POST /api/xiaohongshu/sync`
- `GET /api/items/{item_id}`

## Translation Skill Contract

`skills/translation_skill.py` must expose:

```python
def translate_text(text: str, source_lang: str = "auto", target_lang: str = "zh-CN") -> str:
    ...
```

The default implementation intentionally raises a clear error so you can replace it with your own translation skill later.

## Notes

- Sensitive data is only loaded from environment variables.
- Xiaohongshu automation is intentionally conservative and uses browser automation rather than a hardcoded crawler.
- Raw fetched pages and translated Markdown files are stored locally for debugging and review.

