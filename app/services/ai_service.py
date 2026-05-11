from __future__ import annotations

import json

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed

from app.config import Settings
from app.services.classifier_service import ALLOWED_CATEGORIES, ClassifierService
from app.services.exceptions import AIServiceError, ConfigError


class AIService:
    def __init__(self, settings: Settings, classifier_service: ClassifierService) -> None:
        self.settings = settings
        self.classifier_service = classifier_service

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
    def summarize_and_classify(self, source_url: str, title: str, text: str) -> dict[str, object]:
        if not self.settings.openai_api_key:
            raise ConfigError("OPENAI_API_KEY is not configured")

        client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None)
        excerpt = text[:8000]
        prompt = (
            "你是个人知识库整理助手。请根据输入内容输出 JSON，字段必须只有："
            "one_sentence_summary, core_points, use_case, category, tags, raw_excerpt。"
            f"category 只能从以下分类中选择一个：{', '.join(ALLOWED_CATEGORIES)}。"
            "tags 最多 5 个。raw_excerpt 需要是原文摘要，不超过 200 字。"
        )
        user_message = (
            f"标题：{title}\n"
            f"原链接：{source_url}\n"
            f"正文：\n{excerpt}\n"
        )

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
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
        except Exception as exc:
            raise AIServiceError(f"Failed to summarize content: {exc}") from exc

        category = self.classifier_service.normalize_category(str(parsed.get("category", "")))
        tags = self.classifier_service.normalize_tags(self._coerce_tags(parsed.get("tags")))
        summary = self._format_summary(
            source_url=source_url,
            one_sentence_summary=str(parsed.get("one_sentence_summary", "")).strip(),
            core_points=parsed.get("core_points") or [],
            use_case=str(parsed.get("use_case", "")).strip(),
            category=category,
            tags=tags,
        )
        return {
            "summary": summary,
            "category": category,
            "tags": tags,
            "raw_excerpt": str(parsed.get("raw_excerpt", "")).strip(),
        }

    def _coerce_tags(self, raw_tags: object) -> list[str]:
        if raw_tags is None:
            return []
        if isinstance(raw_tags, str):
            return [part.strip() for part in raw_tags.replace("，", ",").split(",") if part.strip()]
        if isinstance(raw_tags, list):
            return [str(part) for part in raw_tags]
        return [str(raw_tags)]

    def _format_summary(
        self,
        source_url: str,
        one_sentence_summary: str,
        core_points: list[object],
        use_case: str,
        category: str,
        tags: list[str],
    ) -> str:
        lines = [
            "原链接：",
            source_url,
            "",
            "一句话总结：",
            one_sentence_summary or "暂无",
            "",
            "核心内容：",
        ]
        cleaned_points = [str(point).strip() for point in core_points if str(point).strip()]
        if cleaned_points:
            for idx, point in enumerate(cleaned_points[:3], start=1):
                lines.append(f"{idx}. {point}")
        else:
            lines.append("1. 暂无")
        lines.extend(
            [
                "",
                "适合用途：",
                use_case or "待补充",
                "",
                "分类：",
                category,
                "",
                "标签：",
                "、".join(tags) if tags else "待整理",
            ]
        )
        return "\n".join(lines)
