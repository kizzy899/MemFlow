from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from app.config import Settings


class Concept(BaseModel):
    name: str
    explanation: str


class EntityGroups(BaseModel):
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class KnowledgeRelation(BaseModel):
    item_id: str = ""
    title: str
    relation: str
    conflict_or_complement: str = ""


class ArchiveEnrichment(BaseModel):
    key_concepts: list[Concept] = Field(default_factory=list, max_length=8)
    entities: EntityGroups = Field(default_factory=EntityGroups)
    knowledge_relations: list[KnowledgeRelation] = Field(default_factory=list, max_length=10)

    @field_validator("key_concepts", "knowledge_relations", mode="before")
    @classmethod
    def ensure_list(cls, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []


class LinkArchiveAIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enrich(self, title: str, content: str, candidates: list[dict[str, str]]) -> ArchiveEnrichment:
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None)
        candidate_text = json.dumps(candidates, ensure_ascii=False)
        prompt = (
            "你是知识库关联分析助手。只输出 JSON，字段为 key_concepts、entities、knowledge_relations。"
            "key_concepts 是 name/explanation 对象数组；entities 含 people、organizations、projects、tools 字符串数组；"
            "knowledge_relations 只允许引用候选笔记，字段 item_id、title、relation、conflict_or_complement。"
            "没有证据时返回空数组，不得编造实体或关联。"
        )
        user = f"标题：{title}\n正文：{content[:8000]}\n候选已有笔记：{candidate_text[:6000]}"
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}],
            temperature=0.1,
        )
        try:
            return ArchiveEnrichment.model_validate_json(response.choices[0].message.content or "{}")
        except Exception as exc:
            raise ValueError(f"关联分析结果无效：{exc}") from exc