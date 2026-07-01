from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourcePlatform(str, Enum):
    XIAOHONGSHU = "xiaohongshu"
    BILIBILI = "bilibili"
    WECHAT = "wechat"
    ZHIHU = "zhihu"
    GITHUB = "github"
    PAPER = "paper"
    WEB = "web"
    MANUAL = "manual"
    TRANSLATION = "translation"


class ContentType(str, Enum):
    ARTICLE = "article"
    POST = "post"
    VIDEO = "video"
    NOTE = "note"
    TUTORIAL = "tutorial"
    PAPER = "paper"
    CODE_PROJECT = "code_project"
    INSPIRATION = "inspiration"
    TOOL = "tool"
    RESOURCE_COLLECTION = "resource_collection"
    TRANSLATION = "translation"


class TranslationStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    TRANSLATED = "translated"
    FAILED = "failed"


class ProcessStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class NotionSyncStatus(str, Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class ReadStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
    DEEP_READ = "deep_read"
    ARCHIVED = "archived"
    PENDING = "pending"


class Importance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InputType(str, Enum):
    URL = "url"
    TEXT = "text"


class StageStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    input_type: Mapped[InputType] = mapped_column(
        SqlEnum(InputType, values_callable=lambda values: [value.value for value in values]), default=InputType.URL
    )
    title: Mapped[str] = mapped_column(String(500), default="")
    source_url: Mapped[str | None] = mapped_column(String(2048), unique=True, nullable=True, index=True)
    normalized_url: Mapped[str | None] = mapped_column(String(2048), unique=True, nullable=True, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    source_platform: Mapped[SourcePlatform] = mapped_column(SqlEnum(SourcePlatform), default=SourcePlatform.WEB)
    content_type: Mapped[ContentType] = mapped_column(SqlEnum(ContentType), default=ContentType.ARTICLE)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    clean_content: Mapped[str] = mapped_column(Text, default="")
    raw_excerpt: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="待整理")
    category_level_1: Mapped[str] = mapped_column(String(100), default="其他")
    category_level_2: Mapped[str] = mapped_column(String(100), default="待整理")
    tags: Mapped[str] = mapped_column(String(500), default="")
    core_points: Mapped[str] = mapped_column(Text, default="[]")
    action_items: Mapped[str] = mapped_column(Text, default="[]")
    key_concepts: Mapped[str] = mapped_column(Text, default="[]")
    related_entities: Mapped[str] = mapped_column(Text, default="{}")
    knowledge_relations: Mapped[str] = mapped_column(Text, default="[]")
    archive_markdown: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(50), default="")
    importance: Mapped[Importance] = mapped_column(SqlEnum(Importance), default=Importance.MEDIUM)
    original_language: Mapped[str] = mapped_column(String(50), default="zh-CN")
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)
    read_status: Mapped[ReadStatus] = mapped_column(SqlEnum(ReadStatus), default=ReadStatus.UNREAD)
    author: Mapped[str] = mapped_column(String(255), default="")
    site_name: Mapped[str] = mapped_column(String(255), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    translated_text_path: Mapped[str] = mapped_column(String(1024), default="")
    translation_status: Mapped[TranslationStatus] = mapped_column(
        SqlEnum(TranslationStatus), default=TranslationStatus.NOT_REQUIRED
    )
    process_status: Mapped[ProcessStatus] = mapped_column(SqlEnum(ProcessStatus), default=ProcessStatus.PENDING)
    fetch_status: Mapped[StageStatus] = mapped_column(
        SqlEnum(StageStatus, values_callable=lambda values: [value.value for value in values]),
        default=StageStatus.SKIPPED,
    )
    ai_status: Mapped[StageStatus] = mapped_column(
        SqlEnum(StageStatus, values_callable=lambda values: [value.value for value in values]),
        default=StageStatus.SKIPPED,
    )
    notion_page_id: Mapped[str] = mapped_column(String(255), default="")
    notion_page_url: Mapped[str] = mapped_column(String(2048), default="")
    notion_sync_status: Mapped[NotionSyncStatus] = mapped_column(
        SqlEnum(NotionSyncStatus), default=NotionSyncStatus.PENDING
    )
    notion_error_message: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def tags_list(self) -> list[str]:
        return [tag.strip() for tag in (self.tags or "").split(",") if tag.strip()]

    def core_points_list(self) -> list[str]:
        return self._json_list(self.core_points)

    def action_items_list(self) -> list[str]:
        return self._json_list(self.action_items)

    @staticmethod
    def _json_list(value: str) -> list[str]:
        import json

        try:
            parsed = json.loads(value or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

