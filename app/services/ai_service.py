from __future__ import annotations

import json
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.config import Settings
from app.services.classifier_service import ALLOWED_CATEGORIES, ClassifierService
from app.services.exceptions import AIServiceError, ConfigError


class AnalysisResult(BaseModel):
    title: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=2000)
    core_points: list[str] = Field(min_length=1, max_length=50)
    action_items: list[str] = Field(max_length=5)
    content_type: Literal[
        "article",
        "video",
        "note",
        "tutorial",
        "paper",
        "code_project",
        "inspiration",
        "tool",
        "resource_collection",
    ]
    category_level_1: str
    category_level_2: str = Field(min_length=1, max_length=100)
    keywords: list[str] = Field(min_length=1, max_length=5)
    importance: Literal["low", "medium", "high", "critical"]
    original_language: str = Field(min_length=2, max_length=50)
    is_translated: bool

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, value: object) -> str:
        title = " ".join(str(value).split())
        if not title:
            raise ValueError("title cannot be empty")
        return title if len(title) <= 40 else f"{title[:39]}…"

    @field_validator("core_points", "action_items", "keywords", mode="before")
    @classmethod
    def clean_lists(cls, values: object, info: ValidationInfo) -> list[str]:
        if not isinstance(values, list):
            raise ValueError("value must be a JSON array")
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value).strip()
            if not item or item.lower() in seen:
                continue
            seen.add(item.lower())
            cleaned.append(item[:500])
            limit = 50 if info.field_name == "core_points" else 5
            if len(cleaned) >= limit:
                break
        return cleaned


class AIService:
    XIAOHONGSHU_RULES = (
        "这是小红书内容。完全忽略作者姓名、账号、点赞数、收藏数、评论数、粉丝数和关注数，只分析正文与视频文字。正文含视频文字提取标记时 content_type 必须为 video。"
        "如果正文包含视频 OCR 文字，必须覆盖全部 OCR 内容后再总结，按主题分点，不得只取开头。"
        "如果出现‘视频文字提取为空’或‘视频文字提取失败’标记，必须在 summary 中明确写出该视频文字未能提取，不能假装已看完。"
        "如果属于工具、网站、应用、项目或资源推荐，采用精简资源清单：summary 只写一句概括；"
        "core_points 逐项输出‘名称｜完整网页链接｜一句极简介绍’，不得省略正文或 OCR 中出现的任何资源名称和 HTTP(S) 链接，"
        "没有可确认链接时写‘链接未提供’，不得编造；action_items 返回空数组。推荐清单允许 core_points 超过 5 条。"
    )

    def __init__(self, settings: Settings, classifier_service: ClassifierService) -> None:
        self.settings = settings
        self.classifier_service = classifier_service

    @retry(
        retry=retry_if_exception_type(AIServiceError),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        reraise=True,
    )
    def analyze(self, source_url: str, title: str, text: str) -> AnalysisResult:
        if not self.settings.openai_api_key:
            raise ConfigError("OPENAI_API_KEY is not configured")

        client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None)
        prompt = (
            "你是个人知识库整理助手。根据原始内容生成可直接保存的中文结构化笔记。"
            "只输出 JSON，不要 Markdown 或解释。必须包含字段：title, summary, core_points, "
            "action_items, content_type, category_level_1, category_level_2, keywords, importance, "
            "original_language, is_translated。summary、core_points、action_items、分类和关键词必须使用中文；"
            "不要编造原文没有的信息。summary 必须用 3-5 句话概括核心内容。title 必须重新概括内容主题，使用简洁中文短语，不照抄网页标题，"
            "不添加网站名、作者、仓库路径或副标题，最多 20 个汉字（或 40 个字符）。"
            f"category_level_1 只能是：{', '.join(ALLOWED_CATEGORIES)}。"
            "content_type 只能是 article、video、note、tutorial、paper、code_project、inspiration、tool、"
            "resource_collection。importance 只能是 low、medium、high、critical。"
            "original_language 使用语言代码（如 zh-CN、en），非中文内容的 is_translated 为 true。"
            "普通内容的 core_points 为 1-5 条，action_items 为 0-5 条，keywords 为 1-5 个。"
        )
        is_xiaohongshu = "xiaohongshu.com" in source_url.lower() or "xhslink.com" in source_url.lower()
        if is_xiaohongshu:
            prompt += self.XIAOHONGSHU_RULES
        content_limit = 30000 if is_xiaohongshu else 8000
        user_message = f"已有标题：{title or '无'}\n原始链接：{source_url or '无'}\n正文：\n{text[:content_limit]}"

        try:
            response = client.chat.completions.create(
                model=self.settings.openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
            )
            parsed = json.loads(response.choices[0].message.content or "{}")
            parsed["category_level_1"] = self.classifier_service.normalize_category(
                str(parsed.get("category_level_1", ""))
            )
            result = AnalysisResult.model_validate(parsed)
            result.category_level_1 = self.classifier_service.normalize_category(result.category_level_1)
            result.keywords = self.classifier_service.normalize_tags(result.keywords)
        except (ValidationError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise AIServiceError(f"AI returned invalid structured content: {exc}") from exc
        except Exception as exc:
            raise AIServiceError(f"Failed to analyze content: {exc}") from exc

        result.is_translated = not result.original_language.lower().startswith("zh")
        return result

    def summarize_and_classify(self, source_url: str, title: str, text: str) -> dict[str, object]:
        result = self.analyze(source_url, title, text)
        return {
            "title": result.title,
            "summary": self._format_legacy_summary(source_url, result),
            "category": result.category_level_1,
            "tags": result.keywords,
            "raw_excerpt": result.summary[:200],
            "analysis": result,
        }

    def _format_legacy_summary(self, source_url: str, result: AnalysisResult) -> str:
        lines = [
            "原链接：",
            source_url or "无",
            "",
            "摘要：",
            result.summary,
            "",
            "核心内容：",
        ]
        lines.extend(f"{index}. {point}" for index, point in enumerate(result.core_points, start=1))
        if result.action_items:
            lines.extend(["", "行动建议："])
            lines.extend(f"{index}. {item}" for index, item in enumerate(result.action_items, start=1))
        return "\n".join(lines)
