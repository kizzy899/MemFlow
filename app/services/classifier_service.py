from __future__ import annotations

from typing import Iterable


ALLOWED_CATEGORIES = [
    "AI Agent",
    "编程开发",
    "产品设计",
    "运营增长",
    "商业模式",
    "英语学习",
    "论文资料",
    "工具教程",
    "生活灵感",
    "待整理",
]


class ClassifierService:
    def normalize_category(self, category: str | None) -> str:
        if not category:
            return "待整理"

        cleaned = category.strip()
        for allowed in ALLOWED_CATEGORIES:
            if cleaned.lower() == allowed.lower():
                return allowed
        return "待整理"

    def normalize_tags(self, tags: Iterable[str] | None) -> list[str]:
        if not tags:
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            cleaned = str(tag).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned[:50])
            if len(normalized) >= 5:
                break
        return normalized

