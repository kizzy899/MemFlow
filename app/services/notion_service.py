from __future__ import annotations

from datetime import datetime
from typing import Any

from notion_client import Client

from app.config import Settings
from app.models.content_item import ContentItem
from app.services.exceptions import ConfigError, NotionServiceError


class NotionService:
    REQUIRED_PROPERTIES = {
        "标题": "title",
        "原链接": "url",
        "来源平台": "select",
        "内容类型": "select",
        "AI总结": "rich_text",
        "分类": "select",
        "标签": "multi_select",
        "作者": "rich_text",
        "发布时间": "date",
        "译文路径": "rich_text",
        "翻译状态": "status",
        "处理状态": "status",
        "创建时间": "date",
        "更新时间": "date",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.notion_api_key and self.settings.notion_database_id)

    def validate_database(self) -> None:
        client = self._client()
        try:
            database = client.databases.retrieve(database_id=self.settings.notion_database_id)
        except Exception as exc:
            raise NotionServiceError(f"Unable to retrieve Notion database: {exc}") from exc

        properties = database.get("properties", {})
        missing: list[str] = []
        mismatched: list[str] = []
        for name, expected_type in self.REQUIRED_PROPERTIES.items():
            if name not in properties:
                missing.append(name)
                continue
            actual_type = properties[name].get("type")
            if actual_type != expected_type:
                mismatched.append(f"{name}({actual_type} != {expected_type})")
        if missing or mismatched:
            message_parts = []
            if missing:
                message_parts.append(f"missing properties: {', '.join(missing)}")
            if mismatched:
                message_parts.append(f"mismatched properties: {', '.join(mismatched)}")
            raise NotionServiceError("; ".join(message_parts))

    def upsert_page(self, item: ContentItem) -> str:
        client = self._client()
        properties = self._build_properties(item)
        try:
            if item.notion_page_id:
                client.pages.update(page_id=item.notion_page_id, properties=properties)
                return item.notion_page_id

            page = client.pages.create(parent={"database_id": self.settings.notion_database_id}, properties=properties)
            return page["id"]
        except Exception as exc:
            raise NotionServiceError(f"Failed to write to Notion: {exc}") from exc

    def _client(self) -> Client:
        if not self.is_configured():
            raise ConfigError("NOTION_API_KEY or NOTION_DATABASE_ID is not configured")
        return Client(auth=self.settings.notion_api_key)

    def _build_properties(self, item: ContentItem) -> dict[str, Any]:
        return {
            "标题": {"title": [{"text": {"content": item.title[:2000] or "Untitled"}}]},
            "原链接": {"url": item.source_url or None},
            "来源平台": {"select": {"name": item.source_platform.value}},
            "内容类型": {"select": {"name": item.content_type.value}},
            "AI总结": {"rich_text": [{"text": {"content": item.summary[:2000] or "暂无总结"}}]},
            "分类": {"select": {"name": item.category or "待整理"}},
            "标签": {"multi_select": [{"name": tag} for tag in item.tags_list()]},
            "作者": {"rich_text": [{"text": {"content": item.author[:2000]}}]} if item.author else {"rich_text": []},
            "发布时间": {"date": {"start": self._to_date(item.published_at)}} if item.published_at else {"date": None},
            "译文路径": {
                "rich_text": [{"text": {"content": item.translated_text_path[:2000]}}]
            }
            if item.translated_text_path
            else {"rich_text": []},
            "翻译状态": {"status": {"name": item.translation_status.value}},
            "处理状态": {"status": {"name": item.process_status.value}},
            "创建时间": {"date": {"start": self._to_date(item.created_at)}},
            "更新时间": {"date": {"start": self._to_date(item.updated_at)}},
        }

    def _to_date(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

