from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models.content_item import ContentItem, NotionSyncStatus, ProcessStatus, SourcePlatform
from app.services.ai_service import AnalysisResult
from app.services.content_pipeline_service import ContentPipelineService
from app.services.exceptions import ParsingError
from app.services.item_service import ItemService
from app.services.web_parser_service import ParsedWebContent


class FakeParser:
    def parse_url(self, url: str) -> ParsedWebContent:
        return ParsedWebContent(
            source_url=url,
            title="Source title",
            content="An English article about building useful agents.",
            author="Author",
            published_at=datetime(2025, 1, 1),
            site_name="Example",
            raw_file_path="raw.html",
        )


class FakeAI:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, source_url: str, title: str, text: str) -> AnalysisResult:
        self.calls += 1
        return AnalysisResult(
            title="实用 Agent 指南",
            summary="文章介绍了如何构建实用的智能体。",
            core_points=["从明确目标开始", "保持流程可验证"],
            action_items=["先实现最小闭环"],
            content_type="article" if source_url else "note",
            category_level_1="AI",
            category_level_2="Agent 开发",
            keywords=["Agent", "自动化"],
            importance="high",
            original_language="en",
            is_translated=True,
        )


class FakeNotion:
    def __init__(self, configured: bool = False) -> None:
        self.configured = configured
        self.calls = 0

    def is_configured(self) -> bool:
        return self.configured

    def validate_database_details(self) -> dict[str, object]:
        return {"success": True, "message": "ok", "data": {}}

    def validation_error_message(self, result: dict[str, object]) -> str:
        return str(result["message"])

    def upsert_page_details(self, item: ContentItem) -> tuple[str, str]:
        self.calls += 1
        return "page-id", "https://www.notion.so/page-id"


class FailingParser:
    def parse_url(self, url: str) -> ParsedWebContent:
        raise ParsingError("network failed")


class FailingNotion(FakeNotion):
    def __init__(self) -> None:
        super().__init__(configured=True)

    def upsert_page_details(self, item: ContentItem) -> tuple[str, str]:
        raise RuntimeError("notion failed")


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_text_collection_creates_chinese_structured_note(db: Session) -> None:
    pipeline = ContentPipelineService(FakeParser(), FakeAI(), ItemService(FakeNotion()))
    item = pipeline.process_collect(db, "text", "Raw pasted text")

    assert item.title == "实用 Agent 指南"
    assert item.source_platform == SourcePlatform.MANUAL
    assert item.core_points_list() == ["从明确目标开始", "保持流程可验证"]
    assert item.is_translated is True
    assert item.process_status == ProcessStatus.COMPLETED
    assert item.notion_sync_status == NotionSyncStatus.PENDING


def test_url_is_normalized_deduplicated_and_retries_notion(db: Session) -> None:
    notion = FakeNotion(configured=False)
    pipeline = ContentPipelineService(FakeParser(), FakeAI(), ItemService(notion))

    first = pipeline.process_collect(db, "url", "HTTPS://Example.COM:443/article#section")
    notion.configured = True
    second = pipeline.process_collect(db, "url", "https://example.com/article")

    assert first.id == second.id
    assert second.normalized_url == "https://example.com/article"
    assert second.notion_sync_status == NotionSyncStatus.SYNCED
    assert notion.calls == 1
    assert len(db.scalars(select(ContentItem)).all()) == 1


def test_url_collection_uses_concise_ai_title_instead_of_source_title(db: Session) -> None:
    pipeline = ContentPipelineService(FakeParser(), FakeAI(), ItemService(FakeNotion()))

    item = pipeline.process_collect(db, "url", "https://example.com/long-title")

    assert item.title == "实用 Agent 指南"
    assert item.title != "Source title"


def test_platform_detection() -> None:
    assert ContentPipelineService.detect_platform("https://mp.weixin.qq.com/s/x") == SourcePlatform.WECHAT
    assert ContentPipelineService.detect_platform("https://www.bilibili.com/video/x") == SourcePlatform.BILIBILI
    assert ContentPipelineService.detect_platform("https://example.com/x") == SourcePlatform.WEB


def test_invalid_url_is_rejected() -> None:
    with pytest.raises(ValueError):
        ContentPipelineService.normalize_url("ftp://example.com/file")


def test_fetch_failure_is_persisted(db: Session) -> None:
    pipeline = ContentPipelineService(FailingParser(), FakeAI(), ItemService(FakeNotion()))
    with pytest.raises(ParsingError):
        pipeline.process_collect(db, "url", "https://example.com/failure")

    item = db.scalar(select(ContentItem))
    assert item is not None
    assert item.process_status == ProcessStatus.FAILED
    assert item.error_message == "network failed"


def test_notion_failure_does_not_fail_collection(db: Session) -> None:
    pipeline = ContentPipelineService(FakeParser(), FakeAI(), ItemService(FailingNotion()))
    item = pipeline.process_collect(db, "text", "Raw pasted text")

    assert item.process_status == ProcessStatus.COMPLETED
    assert item.notion_sync_status == NotionSyncStatus.FAILED
    assert item.notion_error_message == "notion failed"


def test_text_is_deduplicated_without_repeating_ai(db: Session) -> None:
    ai = FakeAI()
    pipeline = ContentPipelineService(FakeParser(), ai, ItemService(FakeNotion()))

    first = pipeline.process_collect(db, "text", "same   text\ncontent")
    second = pipeline.process_collect(db, "text", " same text content ")

    assert first.id == second.id
    assert ai.calls == 1


def test_tracking_parameters_do_not_create_duplicate_url(db: Session) -> None:
    ai = FakeAI()
    pipeline = ContentPipelineService(FakeParser(), ai, ItemService(FakeNotion()))

    first = pipeline.process_collect(db, "url", "https://example.com/article?utm_source=x&keep=1")
    second = pipeline.process_collect(db, "url", "https://example.com/article?keep=1&utm_campaign=y")

    assert first.id == second.id
    assert ai.calls == 1
