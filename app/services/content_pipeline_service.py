from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content_item import ContentItem, ContentType, ProcessStatus, SourcePlatform, TranslationStatus
from app.services.ai_service import AIService
from app.services.notion_service import NotionService
from app.services.web_parser_service import WebParserService


class ContentPipelineService:
    def __init__(self, web_parser_service: WebParserService, ai_service: AIService, notion_service: NotionService) -> None:
        self.web_parser_service = web_parser_service
        self.ai_service = ai_service
        self.notion_service = notion_service

    def process_web_link(self, db: Session, url: str) -> ContentItem:
        existing = db.scalar(select(ContentItem).where(ContentItem.source_url == url))
        if existing:
            if not existing.summary or existing.process_status != ProcessStatus.COMPLETED:
                return self._refresh_item(db, existing, url)
            return existing
        return self._create_item_from_url(db, url)

    def process_xiaohongshu_item(self, db: Session, item: ContentItem) -> ContentItem:
        existing = None
        if item.source_url:
            existing = db.scalar(select(ContentItem).where(ContentItem.source_url == item.source_url))
        elif item.external_id:
            existing = db.scalar(select(ContentItem).where(ContentItem.external_id == item.external_id))
        if existing:
            item = existing
        else:
            item.translation_status = TranslationStatus.NOT_REQUIRED
            item.process_status = ProcessStatus.PROCESSING
            db.add(item)
            db.commit()
            db.refresh(item)

        try:
            analysis = self.ai_service.summarize_and_classify(item.source_url or "", item.title, item.raw_text)
            item.summary = str(analysis["summary"])
            item.category = str(analysis["category"])
            item.tags = ",".join(analysis["tags"])
            item.raw_excerpt = str(analysis["raw_excerpt"])
            item.process_status = ProcessStatus.COMPLETED
            item.error_message = ""
            self._sync_notion(item)
        except Exception as exc:
            item.process_status = ProcessStatus.FAILED
            item.error_message = str(exc)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def _create_item_from_url(self, db: Session, url: str) -> ContentItem:
        item = ContentItem(
            source_url=url,
            source_platform=SourcePlatform.WEB,
            content_type=ContentType.ARTICLE,
            translation_status=TranslationStatus.NOT_REQUIRED,
            process_status=ProcessStatus.PROCESSING,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return self._refresh_item(db, item, url)

    def _refresh_item(self, db: Session, item: ContentItem, url: str) -> ContentItem:
        try:
            parsed = self.web_parser_service.parse_url(url)
            analysis = self.ai_service.summarize_and_classify(parsed.source_url, parsed.title, parsed.content)
            item.title = parsed.title
            item.raw_text = parsed.content
            item.raw_excerpt = str(analysis["raw_excerpt"])
            item.author = parsed.author
            item.site_name = parsed.site_name
            item.published_at = parsed.published_at
            item.summary = str(analysis["summary"])
            item.category = str(analysis["category"])
            item.tags = ",".join(analysis["tags"])
            item.process_status = ProcessStatus.COMPLETED
            item.error_message = ""
            self._sync_notion(item)
        except Exception as exc:
            item.process_status = ProcessStatus.FAILED
            item.error_message = str(exc)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def _sync_notion(self, item: ContentItem) -> None:
        if not self.notion_service.is_configured():
            return
        notion_page_id = self.notion_service.upsert_page(item)
        item.notion_page_id = notion_page_id
