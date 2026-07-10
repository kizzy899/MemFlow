from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import Settings
from app.video.common import read_json


SUMMARY_TEMPLATE = """# {title}

作者：{author}
发布日期：{publish_time}
平台：{platform}
链接：{url}

---

## 视频摘要

{overview}

---

## 详细内容

{details}

---

## 时间轴

{timeline}

---

## 知识点

{knowledge}

---

## 代码

```text
{code}
```

---

## 命令

```bash
{commands}
```

---

## 配置

```text
{config}
```

---

## 待实践

{practice}

---

## 原视频链接

{url}
"""


class VideoSummarizer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def summarize(self, metadata: dict[str, Any], timeline_path: Path, subtitle_path: Path, ocr_path: Path, warnings: list[str], output_path: Path) -> str:
        timeline = read_json(timeline_path, [])
        subtitles = read_json(subtitle_path, [])
        ocr_rows = read_json(ocr_path, [])
        generated = self._llm_summary(metadata, timeline, subtitles, ocr_rows, warnings)
        if not generated:
            generated = self._fallback_summary(metadata, timeline, warnings)
        output_path.write_text(generated, encoding="utf-8")
        return generated

    def _llm_summary(self, metadata: dict[str, Any], timeline: list[dict[str, Any]], subtitles: list[dict[str, Any]], ocr_rows: list[dict[str, Any]], warnings: list[str]) -> str:
        if not self.settings.openai_api_key:
            return ""
        client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None)
        payload = {
            "metadata": metadata,
            "timeline": timeline[: self.settings.video_summary_timeline_limit],
            "subtitle": subtitles[: self.settings.video_summary_timeline_limit],
            "ocr": ocr_rows[: self.settings.video_summary_timeline_limit],
            "warnings": warnings,
        }
        prompt = (
            "你是视频知识整理助手。只基于 metadata、timeline、subtitle、ocr 生成中文 Markdown，"
            "不要声称重新观看了视频。必须包含：视频简介、核心观点、操作步骤、所有工具、命令、配置项、"
            "注意事项、我的收获、Tags，并使用用户指定的固定 Markdown 模板字段。"
            "如果 OCR/字幕/Vision 不可用，必须明确写出 unavailable。"
        )
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            temperature=0.2,
        )
        return str(response.choices[0].message.content or "").strip()

    def _fallback_summary(self, metadata: dict[str, Any], timeline: list[dict[str, Any]], warnings: list[str]) -> str:
        speech = "\n".join(str(row.get("speech") or "") for row in timeline if row.get("speech"))
        screen = "\n".join(str(row.get("screen") or "") for row in timeline if row.get("screen"))
        vision = "\n".join(str(row.get("vision") or "") for row in timeline if row.get("vision"))
        text = "\n".join([speech, screen, vision])
        commands = "\n".join(dict.fromkeys(re.findall(r"\b(?:npm|git|docker|python|pip|pnpm|yarn|uv|curl)\b[^\n\r]*", text)))
        config = "\n".join(dict.fromkeys(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b|\.env\b|[A-Za-z0-9_.-]+\.ya?ml", text)))
        timeline_lines = [
            f"- {row.get('time')}｜语音：{row.get('speech') or '无'}｜画面：{row.get('screen') or '无'}｜视觉：{row.get('vision') or '无'}"
            for row in timeline[:120]
        ]
        unavailable = "\n".join(f"- {warning}" for warning in warnings) or "- 无"
        title = metadata.get("title") or "未命名视频"
        return SUMMARY_TEMPLATE.format(
            title=title,
            author=metadata.get("author") or "未知",
            publish_time=metadata.get("publish_time") or "未知",
            platform=metadata.get("platform") or "unknown",
            url=metadata.get("url") or "",
            overview=(speech[:300] or screen[:300] or "未提取到可用字幕或画面文字。"),
            details=f"### 核心观点\n\n{_bullets(_first_lines(text, 8))}\n\n### 操作步骤\n\n{_steps(timeline)}\n\n### 所有工具\n\n{_tools(text)}\n\n### 注意事项\n\n{unavailable}\n\n### 我的收获\n\n以后可用于复盘视频教程、提取操作流程，并在无需再次访问原视频时完成知识检索。\n\n### Tags\n\n视频,知识整理,自动化",
            timeline="\n".join(timeline_lines) or "- 暂无",
            knowledge=_bullets(_first_lines(text, 10)),
            code="",
            commands=commands or "# 未识别到命令",
            config=config or "# 未识别到配置项",
            practice="- 根据时间轴复核关键步骤\n- 将命令和配置项加入个人知识库",
        )


def _first_lines(text: str, limit: int) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[:limit] or ["暂无可用结构化内容"]


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _steps(timeline: list[dict[str, Any]]) -> str:
    lines = []
    for row in timeline:
        content = row.get("vision") or row.get("screen") or row.get("speech")
        if content:
            lines.append(f"Step{len(lines) + 1}: {str(content).splitlines()[0]}")
        if len(lines) >= 12:
            break
    return "\n".join(lines) or "Step1: 暂无明确操作步骤"


def _tools(text: str) -> str:
    known = ["Cursor", "Claude Code", "Docker", "Notion", "GitHub", "OpenAI", "Gemini", "Qwen", "B站", "YouTube"]
    found = [tool for tool in known if tool.lower() in text.lower()]
    return "\n".join(f"- {tool}" for tool in found) or "- 未识别到明确工具"
