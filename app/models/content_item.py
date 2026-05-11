from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourcePlatform(str, Enum):
    XIAOHONGSHU = "xiaohongshu"
    WEB = "web"
    MANUAL = "manual"
    TRANSLATION = "translation"


class ContentType(str, Enum):
    ARTICLE = "article"
    POST = "post"
    VIDEO = "video"
    NOTE = "note"
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


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), default="")
    source_url: Mapped[str | None] = mapped_column(String(2048), unique=True, nullable=True, index=True)
    source_platform: Mapped[SourcePlatform] = mapped_column(SqlEnum(SourcePlatform), default=SourcePlatform.WEB)
    content_type: Mapped[ContentType] = mapped_column(SqlEnum(ContentType), default=ContentType.ARTICLE)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    raw_excerpt: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="待整理")
    tags: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str] = mapped_column(String(255), default="")
    site_name: Mapped[str] = mapped_column(String(255), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    translated_text_path: Mapped[str] = mapped_column(String(1024), default="")
    translation_status: Mapped[TranslationStatus] = mapped_column(
        SqlEnum(TranslationStatus), default=TranslationStatus.NOT_REQUIRED
    )
    process_status: Mapped[ProcessStatus] = mapped_column(SqlEnum(ProcessStatus), default=ProcessStatus.PENDING)
    notion_page_id: Mapped[str] = mapped_column(String(255), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def tags_list(self) -> list[str]:
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

