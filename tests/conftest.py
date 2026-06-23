import pytest

from app.services.notion_service import NotionService


@pytest.fixture(autouse=True)
def prevent_external_notion_validation(monkeypatch):
    monkeypatch.setattr(NotionService, "validate_database", lambda self: None)
