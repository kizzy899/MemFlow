from fastapi.testclient import TestClient

from app.main import app
from app.models.content_item import (
    ContentItem,
    ContentType,
    Importance,
    NotionSyncStatus,
    ProcessStatus,
    SourcePlatform,
)


def test_collect_rejects_invalid_url() -> None:
    with TestClient(app) as client:
        response = client.post("/api/collect", json={"input_type": "url", "content": "not-a-url"})
    assert response.status_code == 422


def test_collect_returns_structured_response(monkeypatch) -> None:
    item = ContentItem(
        id="item-id",
        title="整理后的标题",
        source_platform=SourcePlatform.MANUAL,
        content_type=ContentType.NOTE,
        summary="中文摘要",
        category_level_1="AI",
        category_level_2="Agent 开发",
        tags="AI,Agent",
        core_points='["核心观点"]',
        action_items='["执行动作"]',
        importance=Importance.HIGH,
        original_language="en",
        is_translated=True,
        process_status=ProcessStatus.COMPLETED,
        notion_sync_status=NotionSyncStatus.PENDING,
    )
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.container.content_pipeline_service,
            "process_collect",
            lambda db, input_type, content: item,
        )
        response = client.post("/api/collect", json={"input_type": "text", "content": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["item_id"] == "item-id"
    assert body["data"]["keywords"] == ["AI", "Agent"]
    assert body["data"]["notion_sync_status"] == "pending"
