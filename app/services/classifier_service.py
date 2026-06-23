from __future__ import annotations

from typing import Iterable


ALLOWED_CATEGORIES = [
    "AI",
    "编程开发",
    "英语学习",
    "金融财务",
    "论文写作",
    "工具效率",
    "项目灵感",
    "生活经验",
    "职业发展",
    "其他",
]


class ClassifierService:
    def normalize_category(self, category: str | None) -> str:
        if not category:
            return "其他"

        cleaned = category.strip()
        for allowed in ALLOWED_CATEGORIES:
            if cleaned.lower() == allowed.lower():
                return allowed
        return "其他"

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

