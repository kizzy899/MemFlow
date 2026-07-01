import pytest
import shutil
import gc
import uuid
from pathlib import Path

from app.services.notion_service import NotionService


@pytest.fixture(autouse=True)
def prevent_external_notion_validation(monkeypatch):
    monkeypatch.setattr(NotionService, "validate_database", lambda self: None)
@pytest.fixture
def tmp_path():
    """Workspace-local replacement for environments that deny the OS temp directory."""
    path = Path("data") / f"pytest-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
