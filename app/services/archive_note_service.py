from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.models.content_item import ContentItem
from app.services.notion_page_service import safe_rich_text


def parse_json(value: str, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(default)) else default
    except (ValueError, TypeError):
        return default


def build_archive_markdown(item: ContentItem) -> str:
    concepts = parse_json(item.key_concepts, [])
    entities = parse_json(item.related_entities, {})
    relations = parse_json(item.knowledge_relations, [])
    lines = [
        f"# {item.title or '未命名'}", "", "## 原文链接", item.source_url or "无", "",
        "## 规范链接", item.normalized_url or "无", "", "## 摘要", item.summary or "无", "",
        "## 核心观点", *[f"- {point}" for point in item.core_points_list()], "", "## 关键概念",
        *[f"- {entry.get('name', '')}：{entry.get('explanation', '')}" for entry in concepts], "",
        "## 关联实体",
        f"- 人物：{'、'.join(entities.get('people', [])) or '无'}",
        f"- 机构：{'、'.join(entities.get('organizations', [])) or '无'}",
        f"- 项目：{'、'.join(entities.get('projects', [])) or '无'}",
        f"- 工具：{'、'.join(entities.get('tools', [])) or '无'}", "",
        "## 可行动建议", *[f"- {action}" for action in item.action_items_list()], "",
        "## 与已有知识的关联",
        *[f"- {entry.get('title', '')}：{entry.get('relation', '')}；{entry.get('conflict_or_complement', '')}" for entry in relations], "",
        "## 来源信息", f"- 来源类型：{item.source_type or '其他'}",
        f"- 抓取时间：{(item.archived_at or item.updated_at or item.created_at or datetime.now()).isoformat()}",
        "- 处理状态：已归档", "",
    ]
    return "\n".join(line for line in lines if line is not None)


def _block(kind: str, text: object) -> dict[str, Any]:
    return {"object": "block", "type": kind, kind: {"rich_text": [{"type": "text", "text": {"content": safe_rich_text(text)}}]}}


def build_archive_children(item: ContentItem) -> list[dict[str, Any]]:
    concepts = parse_json(item.key_concepts, [])
    entities = parse_json(item.related_entities, {})
    relations = parse_json(item.knowledge_relations, [])
    blocks: list[dict[str, Any]] = []
    def section(title: str) -> None: blocks.append(_block("heading_2", title))
    section("原文链接"); blocks.append(_block("paragraph", item.source_url or "无"))
    section("规范链接"); blocks.append(_block("paragraph", item.normalized_url or "无"))
    section("摘要"); blocks.append(_block("paragraph", item.summary or "无"))
    section("核心观点"); blocks.extend(_block("bulleted_list_item", value) for value in item.core_points_list())
    section("关键概念"); blocks.extend(_block("bulleted_list_item", f"{x.get('name', '')}：{x.get('explanation', '')}") for x in concepts)
    section("关联实体")
    labels = (("人物", "people"), ("机构", "organizations"), ("项目", "projects"), ("工具", "tools"))
    blocks.extend(_block("bulleted_list_item", f"{label}：{'、'.join(entities.get(key, [])) or '无'}") for label, key in labels)
    section("可行动建议"); blocks.extend(_block("bulleted_list_item", value) for value in item.action_items_list())
    section("与已有知识的关联")
    blocks.extend(_block("bulleted_list_item", f"{x.get('title', '')}：{x.get('relation', '')}；{x.get('conflict_or_complement', '')}") for x in relations)
    section("来源信息")
    timestamp = (item.archived_at or item.updated_at or item.created_at or datetime.now()).isoformat()
    blocks.extend([_block("bulleted_list_item", f"来源类型：{item.source_type or '其他'}"), _block("bulleted_list_item", f"抓取时间：{timestamp}"), _block("bulleted_list_item", "处理状态：已归档")])
    return blocks