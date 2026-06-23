from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app
from app.models.content_item import (
    ContentItem,
    ContentType,
    Importance,
    InputType,
    NotionSyncStatus,
    ProcessStatus,
    SourcePlatform,
    StageStatus,
)
from app.services.item_service import ItemService


class NoNotion:
    def is_configured(self) -> bool:
        return False


def make_item(index: int, **overrides) -> ContentItem:
    values = {
        "id": f"item-{index}",
        "input_type": InputType.URL,
        "source_url": f"https://example.com/{index}",
        "normalized_url": f"https://example.com/{index}",
        "title": f"Article {index}",
        "summary": "AI knowledge" if index == 1 else "Other topic",
        "tags": "AI,Agent" if index == 1 else "Python",
        "source_platform": SourcePlatform.WEB,
        "content_type": ContentType.ARTICLE,
        "importance": Importance.MEDIUM,
        "process_status": ProcessStatus.COMPLETED,
        "fetch_status": StageStatus.SUCCESS,
        "ai_status": StageStatus.SUCCESS,
        "notion_sync_status": NotionSyncStatus.SYNCED,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
    }
    values.update(overrides)
    return ContentItem(**values)


def seeded() -> tuple[Session, ItemService]:
    engine = create_engine("sqlite:///:memory:")
    ContentItem.metadata.create_all(engine)
    db = Session(engine)
    db.add_all(
        [
            make_item(1),
            make_item(2, notion_sync_status=NotionSyncStatus.PENDING),
            make_item(3, source_platform=SourcePlatform.GITHUB),
            make_item(
                4,
                input_type=InputType.TEXT,
                source_url=None,
                normalized_url=None,
                content_hash="a" * 64,
                source_platform=SourcePlatform.MANUAL,
            ),
            make_item(5, notion_sync_status=NotionSyncStatus.FAILED, notion_error_message="failed"),
        ]
    )
    db.commit()
    return db, ItemService(NoNotion())


def test_default_pagination_and_order() -> None:
    db, service = seeded()
    try:
        result = service.list_items(db, page=1, page_size=2)
        assert result.total == 5
        assert result.total_pages == 3
        assert [item.id for item in result.items] == ["item-5", "item-4"]
    finally:
        db.close()


def test_query_filters() -> None:
    db, service = seeded()
    try:
        assert service.list_items(db, 1, 20, notion_sync_status="pending").total == 1
        assert service.list_items(db, 1, 20, input_type="text").total == 1
        assert service.list_items(db, 1, 20, platform="GitHub").total == 1
        assert service.list_items(db, 1, 20, platform="网页").total == 3
        assert service.list_items(db, 1, 20, keyword="Agent").items[0].id == "item-1"
        assert service.list_items(db, 1, 20, failed_only=True).items[0].id == "item-5"
    finally:
        db.close()


def test_page_size_over_100_returns_uniform_422() -> None:
    with TestClient(app) as client:
        response = client.get("/api/items?page_size=101")

    assert response.status_code == 422
    assert response.json() == {"success": False, "message": "page_size must be between 1 and 100", "data": None}
