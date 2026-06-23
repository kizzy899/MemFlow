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
        "原始链接": "url",
        "来源平台": "select",
        "内容类型": "select",
        "一级分类": "select",
        "二级分类": "select",
        "摘要": "rich_text",
        "关键词": "multi_select",
        "核心观点": "rich_text",
        "行动建议": "rich_text",
        "原文语言": "select",
        "是否翻译": "checkbox",
        "阅读状态": "select",
        "重要程度": "select",
        "AI处理状态": "select",
        "创建时间": "date",
        "更新时间": "date",
    }
    PLATFORM_NAMES = {
        "web": "Web", "manual": "手动输入", "wechat": "微信公众号", "bilibili": "B站",
        "xiaohongshu": "小红书", "zhihu": "知乎", "github": "GitHub", "paper": "论文",
        "translation": "翻译",
    }
    CONTENT_TYPE_NAMES = {
        "article": "文章", "post": "帖子", "video": "视频", "note": "笔记", "tutorial": "教程",
        "paper": "论文", "code_project": "代码项目", "inspiration": "灵感", "tool": "工具",
        "resource_collection": "资料合集", "translation": "翻译",
    }
    IMPORTANCE_NAMES = {"low": "低", "medium": "中", "high": "高", "critical": "非常重要"}
    READ_STATUS_NAMES = {
        "unread": "未读", "read": "已读", "deep_read": "精读", "archived": "已归档", "pending": "待处理"
    }
    PROCESS_STATUS_NAMES = {
        "pending": "待处理", "processing": "处理中", "completed": "已完成", "failed": "失败"
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.notion_api_key and self.settings.notion_database_id)

    def validate_database_details(self) -> dict[str, Any]:
        missing_config = []
        if not self.settings.notion_api_key:
            missing_config.append("NOTION_API_KEY")
        if not self.settings.notion_database_id:
            missing_config.append("NOTION_DATABASE_ID")
        base: dict[str, Any] = {
            "configured": not missing_config,
            "database_accessible": False,
            "database_id": self.settings.notion_database_id or None,
            "missing_config": missing_config,
            "fields": [],
            "missing_fields": [],
            "type_mismatches": [],
            "error": None,
        }
        if missing_config:
            return {"success": False, "message": "Notion 未配置", "data": base}

        try:
            database = self._client().databases.retrieve(database_id=self.settings.notion_database_id)
        except Exception as exc:
            base["error"] = self.humanize_error(exc)
            return {"success": False, "message": base["error"], "data": base}

        base["database_accessible"] = True
        properties = database.get("properties", {})
        for name, expected_type in self.REQUIRED_PROPERTIES.items():
            property_data = properties.get(name)
            actual_type = property_data.get("type") if property_data else None
            exists = property_data is not None
            valid = exists and actual_type == expected_type
            base["fields"].append(
                {
                    "name": name,
                    "expected_type": expected_type,
                    "actual_type": actual_type,
                    "exists": exists,
                    "valid": valid,
                }
            )
            if not exists:
                base["missing_fields"].append(name)
            elif not valid:
                base["type_mismatches"].append(
                    {"name": name, "expected_type": expected_type, "actual_type": actual_type}
                )

        if base["missing_fields"]:
            return {"success": False, "message": "Notion 字段校验失败", "data": base}
        if base["type_mismatches"]:
            return {"success": False, "message": "Notion 字段类型不匹配", "data": base}
        return {"success": True, "message": "Notion 配置验证通过", "data": base}

    def validate_database(self) -> None:
        result = self.validate_database_details()
        if not result["success"]:
            raise NotionServiceError(self.validation_error_message(result))

    def upsert_page(self, item: ContentItem) -> str:
        page_id, _ = self.upsert_page_details(item)
        return page_id

    def upsert_page_details(self, item: ContentItem) -> tuple[str, str]:
        client = self._client()
        properties = self._build_properties(item)
        try:
            if item.notion_page_id:
                page = client.pages.update(page_id=item.notion_page_id, properties=properties)
            else:
                page = client.pages.create(
                    parent={"database_id": self.settings.notion_database_id}, properties=properties
                )
            return str(page["id"]), str(page.get("url", item.notion_page_url or ""))
        except Exception as exc:
            raise NotionServiceError(self.humanize_error(exc)) from exc

    def _client(self) -> Client:
        if not self.is_configured():
            raise ConfigError("Notion 未配置：缺少 NOTION_API_KEY 或 NOTION_DATABASE_ID")
        return Client(auth=self.settings.notion_api_key)

    def _build_properties(self, item: ContentItem) -> dict[str, Any]:
        platform_value = getattr(item.source_platform, "value", "") if item.source_platform else ""
        content_type_value = getattr(item.content_type, "value", "") if item.content_type else ""
        importance_value = getattr(item.importance, "value", "medium") if item.importance else "medium"
        read_status_value = getattr(item.read_status, "value", "unread") if item.read_status else "unread"
        process_value = getattr(item.process_status, "value", "completed") if item.process_status else "completed"
        return {
            "标题": {"title": self._rich_text(item.title or "未命名")},
            "原始链接": {"url": item.source_url or None},
            "来源平台": {"select": {"name": self.PLATFORM_NAMES.get(platform_value, "其他")}},
            "内容类型": {"select": {"name": self.CONTENT_TYPE_NAMES.get(content_type_value, "其他")}},
            "一级分类": {"select": {"name": item.category_level_1 or "其他"}},
            "二级分类": {"select": {"name": item.category_level_2 or "未分类"}},
            "摘要": {"rich_text": self._rich_text(item.summary)},
            "关键词": {"multi_select": [{"name": tag[:100]} for tag in item.tags_list()]},
            "核心观点": {"rich_text": self._rich_text(self._numbered(item.core_points_list()))},
            "行动建议": {"rich_text": self._rich_text(self._numbered(item.action_items_list()))},
            "原文语言": {"select": {"name": item.original_language or "未知"}},
            "是否翻译": {"checkbox": bool(item.is_translated)},
            "阅读状态": {"select": {"name": self.READ_STATUS_NAMES.get(read_status_value, "未读")}},
            "重要程度": {"select": {"name": self.IMPORTANCE_NAMES.get(importance_value, "中")}},
            "AI处理状态": {"select": {"name": self.PROCESS_STATUS_NAMES.get(process_value, "已完成")}},
            "创建时间": {"date": {"start": self._to_date(item.created_at)}},
            "更新时间": {"date": {"start": self._to_date(item.updated_at)}},
        }

    @staticmethod
    def _rich_text(value: str) -> list[dict[str, Any]]:
        if not value:
            return []
        marker = "...（内容过长已截断）"
        if len(value) > 2000:
            value = value[: 2000 - len(marker)] + marker
        return [{"text": {"content": value}}]

    @staticmethod
    def _numbered(items: list[str]) -> str:
        return "\n".join(f"{index}. {value}" for index, value in enumerate(items, start=1))

    @staticmethod
    def _to_date(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def validation_error_message(result: dict[str, Any]) -> str:
        data = result["data"]
        if data.get("missing_config"):
            return f"Notion 未配置：缺少 {', '.join(data['missing_config'])}"
        if data.get("missing_fields"):
            return "缺少 Notion 字段：" + "、".join(data["missing_fields"])
        if data.get("type_mismatches"):
            mismatch = data["type_mismatches"][0]
            return (
                f"字段「{mismatch['name']}」类型错误：应为 {mismatch['expected_type']}，"
                f"实际为 {mismatch['actual_type']}"
            )
        return str(data.get("error") or result["message"])

    @staticmethod
    def humanize_error(exc: Exception) -> str:
        message = str(exc)
        lowered = message.lower()
        if "object_not_found" in lowered or "could not find database" in lowered or "404" in lowered:
            return "无法访问 Notion 数据库：请检查 NOTION_DATABASE_ID，并确认 Integration 已添加到 Connections"
        if "unauthorized" in lowered or "401" in lowered:
            return "Notion API Key 无效或 Integration 没有访问权限"
        if "database_id" in lowered and ("invalid" in lowered or "validation" in lowered):
            return "NOTION_DATABASE_ID 不是有效的数据库 ID"
        if "property" in lowered or "validation_error" in lowered:
            return f"Notion 字段或请求格式错误：{message}"
        return f"Notion API 调用失败：{message}"
