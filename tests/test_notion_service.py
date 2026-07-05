from app.config import Settings
from datetime import datetime, timezone

from app.models.content_item import (
    ContentItem,
    ContentType,
    Importance,
    ProcessStatus,
    ReadStatus,
    SourcePlatform,
)
from app.services.notion_service import NotionService


def test_build_properties_matches_mvp_schema() -> None:
    service = NotionService(Settings())
    service._database_properties = {
        "原文语言": {"type": "select"},
        "是否翻译": {"type": "checkbox"},
    }
    item = ContentItem(
        title="测试文章",
        source_url="https://example.com",
        source_platform=SourcePlatform.WEB,
        content_type=ContentType.ARTICLE,
        summary="摘要",
        category_level_1="AI",
        category_level_2="Agent 开发",
        tags="AI,Agent",
        core_points='["观点"]',
        action_items='["行动"]',
        original_language="en",
        is_translated=True,
        importance=Importance.HIGH,
        read_status=ReadStatus.UNREAD,
        process_status=ProcessStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    properties = service._build_properties(item)

    assert set(service.REQUIRED_PROPERTIES).issubset(set(properties))
    assert properties["原文语言"]["select"]["name"] == "en"
    assert properties["是否翻译"]["checkbox"] is True
    assert properties["关键词"]["multi_select"] == [{"name": "AI"}, {"name": "Agent"}]


def test_rich_text_truncation_keeps_marker() -> None:
    rich_text = NotionService._rich_text("x" * 2100)
    content = rich_text[0]["text"]["content"]

    assert len(content) == 2000
    assert content.endswith("...（内容过长已截断）")


def test_video_page_contains_managed_video_toggle() -> None:
    from app.services.notion_page_service import build_notion_page_children
    item = ContentItem(title="视频", content_type=ContentType.VIDEO, source_type="小红书视频", raw_text="[视频语音转录]\n完整语音", media_provider="opencli")
    toggles = [block for block in build_notion_page_children(item) if block["type"] == "toggle"]
    assert len(toggles) == 1
    assert toggles[0]["toggle"]["rich_text"][0]["text"]["content"] == "MemFlow 视频内容"
