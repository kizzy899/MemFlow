from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.content_item import ContentItem, NotionSyncStatus, ProcessStatus
from app.services.item_service import ItemService


class FakeNotion:
    def __init__(self, configured: bool = True, fail: bool = False) -> None:
        self.configured = configured
        self.fail = fail
        self.calls = 0

    def is_configured(self) -> bool:
        return self.configured

    def validate_database_details(self):
        return {"success": True, "message": "ok", "data": {}}

    def validation_error_message(self, result) -> str:
        return str(result["message"])

    def upsert_page_details(self, item: ContentItem) -> tuple[str, str]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("write failed")
        return "page-id", "https://www.notion.so/page-id"


def client_with_notion(notion: FakeNotion):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.__enter__()
    app.state.container.item_service = ItemService(notion)
    return client, testing_session


def close_client(client: TestClient) -> None:
    client.__exit__(None, None, None)
    app.dependency_overrides.clear()


def insert_item(testing_session, item_id: str, status: NotionSyncStatus, page_url: str = "") -> None:
    with testing_session() as db:
        db.add(
            ContentItem(
                id=item_id,
                title="Item",
                process_status=ProcessStatus.COMPLETED,
                notion_sync_status=status,
                notion_page_url=page_url,
            )
        )
        db.commit()


def test_retry_returns_404_for_missing_item() -> None:
    client, _ = client_with_notion(FakeNotion())
    try:
        response = client.post("/api/items/missing/sync-notion")
        assert response.status_code == 404
        assert response.json()["success"] is False
    finally:
        close_client(client)


def test_retry_returns_503_when_notion_is_unconfigured() -> None:
    client, sessions = client_with_notion(FakeNotion(configured=False))
    insert_item(sessions, "pending", NotionSyncStatus.PENDING)
    try:
        response = client.post("/api/items/pending/sync-notion")
        assert response.status_code == 503
        assert response.json()["data"]["notion_sync_status"] == "pending"
    finally:
        close_client(client)


def test_pending_and_failed_items_can_be_synced() -> None:
    notion = FakeNotion()
    client, sessions = client_with_notion(notion)
    insert_item(sessions, "pending", NotionSyncStatus.PENDING)
    insert_item(sessions, "failed", NotionSyncStatus.FAILED)
    try:
        for item_id in ("pending", "failed"):
            response = client.post(f"/api/items/{item_id}/sync-notion")
            assert response.status_code == 200
            assert response.json()["data"]["notion_sync_status"] == "synced"
        assert notion.calls == 2
    finally:
        close_client(client)


def test_synced_item_is_idempotent() -> None:
    notion = FakeNotion()
    client, sessions = client_with_notion(notion)
    insert_item(sessions, "synced", NotionSyncStatus.SYNCED, "https://www.notion.so/existing")
    try:
        response = client.post("/api/items/synced/sync-notion")
        assert response.status_code == 200
        assert "无需重复同步" in response.json()["message"]
        assert notion.calls == 0
    finally:
        close_client(client)


def test_sync_failure_is_persisted() -> None:
    notion = FakeNotion(fail=True)
    client, sessions = client_with_notion(notion)
    insert_item(sessions, "pending", NotionSyncStatus.PENDING)
    try:
        response = client.post("/api/items/pending/sync-notion")
        assert response.status_code == 502
        with sessions() as db:
            item = db.get(ContentItem, "pending")
            assert item.notion_sync_status == NotionSyncStatus.FAILED
            assert "write failed" in item.notion_error_message
    finally:
        close_client(client)
