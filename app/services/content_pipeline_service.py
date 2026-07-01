from __future__ import annotations

import json
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content_item import (
    ContentItem,
    ContentType,
    Importance,
    InputType,
    NotionSyncStatus,
    ProcessStatus,
    SourcePlatform,
    StageStatus,
    TranslationStatus,
)
from app.services.ai_service import AIService, AnalysisResult
from app.services.item_service import ItemService
from app.services.web_parser_service import WebParserService
from app.utils.content_identity import content_hash, extract_first_url, normalize_text, normalize_url
from app.services.taxonomy_service import normalize_category_level_1, normalize_category_level_2, normalize_keywords


class ContentPipelineService:
    def __init__(self, web_parser_service: WebParserService, ai_service: AIService, item_service: ItemService) -> None:
        self.web_parser_service = web_parser_service
        self.ai_service = ai_service
        self.item_service = item_service

    def process_collect(self, db: Session, input_type: str, content: str) -> ContentItem:
        if input_type == "url":
            return self._process_url(db, content.strip(), normalize_url(content))
        return self._process_text(db, content.strip())

    def process_web_link(self, db: Session, url: str) -> ContentItem:
        return self.process_collect(db, "url", url)

    def _process_url(self, db: Session, source_url: str, normalized_url: str) -> ContentItem:
        existing = self.item_service.find_by_normalized_url(db, normalized_url)
        if existing:
            if existing.process_status == ProcessStatus.COMPLETED and existing.notion_sync_status != NotionSyncStatus.SYNCED:
                return self.item_service.attempt_notion_sync(db, existing)
            return existing

        item = ContentItem(
            input_type=InputType.URL,
            source_url=source_url,
            normalized_url=normalized_url,
            source_platform=self.detect_platform(normalized_url),
            content_type=ContentType.ARTICLE,
            translation_status=TranslationStatus.NOT_REQUIRED,
            process_status=ProcessStatus.PROCESSING,
            fetch_status=StageStatus.SKIPPED,
            ai_status=StageStatus.SKIPPED,
            notion_sync_status=NotionSyncStatus.PENDING,
        )
        self.item_service.save(db, item)

        try:
            parsed = self.web_parser_service.parse_url(source_url)
            item.raw_text = parsed.content
            item.clean_content = parsed.content
            item.author = parsed.author
            item.site_name = parsed.site_name
            item.published_at = parsed.published_at
            item.fetch_status = StageStatus.SUCCESS
            self.item_service.save(db, item)
        except Exception as exc:
            item.fetch_status = StageStatus.FAILED
            item.ai_status = StageStatus.SKIPPED
            item.process_status = ProcessStatus.FAILED
            item.error_message = str(exc)
            self.item_service.save(db, item)
            raise

        try:
            analysis = self.ai_service.analyze(parsed.source_url, parsed.title, parsed.content)
            self._apply_analysis(item, analysis)
            item.raw_excerpt = analysis.summary[:200]
            item.ai_status = StageStatus.SUCCESS
            item.process_status = ProcessStatus.COMPLETED
            item.error_message = ""
        except Exception as exc:
            item.ai_status = StageStatus.FAILED
            item.process_status = ProcessStatus.FAILED
            item.error_message = str(exc)
            self.item_service.save(db, item)
            raise

        self.item_service.save(db, item)
        return self.item_service.attempt_notion_sync(db, item)

    def _process_text(self, db: Session, text: str) -> ContentItem:
        cleaned = normalize_text(text)
        digest = content_hash(cleaned)
        source_url = extract_first_url(text)
        normalized_source_url = normalize_url(source_url) if source_url else None
        existing = self.item_service.find_by_content_hash(db, digest)
        if existing:
            if source_url and not existing.source_url:
                linked_item = self.item_service.find_by_normalized_url(db, normalized_source_url or "")
                if not linked_item or linked_item.id == existing.id:
                    existing.source_url = source_url
                    existing.normalized_url = normalized_source_url
                    existing.source_platform = self.detect_platform(normalized_source_url or source_url)
                    existing.category_level_2 = normalize_category_level_2(
                        existing.category_level_2,
                        " ".join([existing.title, existing.summary, existing.tags, existing.raw_text]),
                    )
                    if existing.category_level_2 == "Agent面试":
                        existing.tags = ",".join(normalize_keywords(["Agent面试", *existing.tags_list()]))
                    existing.notion_sync_status = NotionSyncStatus.PENDING
                    self.item_service.save(db, existing)
            if existing.process_status == ProcessStatus.COMPLETED and existing.notion_sync_status != NotionSyncStatus.SYNCED:
                return self.item_service.attempt_notion_sync(db, existing)
            return existing
        if normalized_source_url:
            existing_url = self.item_service.find_by_normalized_url(db, normalized_source_url)
            if existing_url:
                return existing_url

        item = ContentItem(
            input_type=InputType.TEXT,
            content_hash=digest,
            source_url=source_url,
            normalized_url=normalized_source_url,
            source_platform=self.detect_platform(normalized_source_url) if normalized_source_url else SourcePlatform.MANUAL,
            content_type=ContentType.NOTE,
            raw_text=text,
            clean_content=cleaned,
            raw_excerpt=cleaned[:200],
            translation_status=TranslationStatus.NOT_REQUIRED,
            process_status=ProcessStatus.PROCESSING,
            fetch_status=StageStatus.SKIPPED,
            ai_status=StageStatus.SKIPPED,
            notion_sync_status=NotionSyncStatus.PENDING,
        )
        self.item_service.save(db, item)
        try:
            analysis = self.ai_service.analyze(source_url or "", "", cleaned)
            self._apply_analysis(item, analysis)
            item.ai_status = StageStatus.SUCCESS
            item.process_status = ProcessStatus.COMPLETED
            item.error_message = ""
        except Exception as exc:
            item.ai_status = StageStatus.FAILED
            item.process_status = ProcessStatus.FAILED
            item.error_message = str(exc)
            self.item_service.save(db, item)
            raise

        self.item_service.save(db, item)
        return self.item_service.attempt_notion_sync(db, item)

    def process_xiaohongshu_item(self, db: Session, item: ContentItem) -> ContentItem:
        existing = None
        if item.source_url:
            item.input_type = InputType.URL
            item.normalized_url = normalize_url(item.source_url)
            existing = self.item_service.find_by_normalized_url(db, item.normalized_url)
        elif item.external_id:
            existing = db.scalar(select(ContentItem).where(ContentItem.external_id == item.external_id))
        item = existing or item
        if existing:
            return existing

        item.translation_status = TranslationStatus.NOT_REQUIRED
        item.process_status = ProcessStatus.PROCESSING
        item.fetch_status = StageStatus.SUCCESS
        self.item_service.save(db, item)
        try:
            analysis = self.ai_service.analyze(item.source_url or "", item.title, item.raw_text)
            self._apply_analysis(item, analysis)
            item.clean_content = item.raw_text
            item.ai_status = StageStatus.SUCCESS
            item.process_status = ProcessStatus.COMPLETED
            item.error_message = ""
            self.item_service.save(db, item)
            return self.item_service.attempt_notion_sync(db, item)
        except Exception as exc:
            item.ai_status = StageStatus.FAILED
            item.process_status = ProcessStatus.FAILED
            item.error_message = str(exc)
            return self.item_service.save(db, item)

    def _apply_analysis(self, item: ContentItem, analysis: AnalysisResult) -> None:
        item.title = analysis.title
        item.content_type = ContentType(analysis.content_type)
        item.summary = analysis.summary
        item.category = normalize_category_level_1(analysis.category_level_1)
        item.category_level_1 = item.category
        item.category_level_2 = normalize_category_level_2(
            analysis.category_level_2,
            " ".join([analysis.title, analysis.summary, *analysis.keywords, item.clean_content or item.raw_text]),
        )
        keywords = analysis.keywords
        if item.category_level_2 == "Agent面试":
            keywords = ["Agent面试", *keywords]
        item.tags = ",".join(normalize_keywords(keywords))
        item.core_points = json.dumps(analysis.core_points, ensure_ascii=False)
        item.action_items = json.dumps(analysis.action_items, ensure_ascii=False)
        item.importance = Importance(analysis.importance)
        item.original_language = analysis.original_language
        item.is_translated = analysis.is_translated

    @staticmethod
    def normalize_url(url: str) -> str:
        return normalize_url(url)

    @staticmethod
    def detect_platform(url: str) -> SourcePlatform:
        host = (urlsplit(url).hostname or "").lower()
        if host == "mp.weixin.qq.com":
            return SourcePlatform.WECHAT
        if host.endswith("bilibili.com") or host == "b23.tv":
            return SourcePlatform.BILIBILI
        if host.endswith("xiaohongshu.com") or host.endswith("xhslink.com"):
            return SourcePlatform.XIAOHONGSHU
        if host.endswith("zhihu.com"):
            return SourcePlatform.ZHIHU
        if host == "github.com" or host.endswith(".github.com"):
            return SourcePlatform.GITHUB
        if host == "arxiv.org" or host == "doi.org":
            return SourcePlatform.PAPER
        return SourcePlatform.WEB
