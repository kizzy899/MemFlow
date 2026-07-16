from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.models.content_item import ContentItem, ProcessStatus, TranslationStatus
from app.services.file_storage_service import FileStorageService
from app.services.translation_service import TranslationArtifact, TranslationService


class FakeItemService:
    def __init__(self, existing=None):
        self.existing = existing
        self.saved = []
        self.synced = []

    def find_by_normalized_url(self, db, normalized_url):
        return self.existing

    def save(self, db, item):
        self.saved.append(item)
        if not item.id:
            item.id = "new-item"
        return item

    def attempt_notion_sync(self, db, item):
        self.synced.append(item)
        item.notion_page_url = "https://notion/page"
        return item


def make_service(tmp_path: Path, api_key: str = "gemini-key", existing=None) -> TranslationService:
    settings = Settings(GEMINI_API_KEY=api_key, TRANSLATION_OUTPUT_DIR=str(tmp_path / "translated"))
    storage = FileStorageService(settings)
    return TranslationService(settings, web_parser_service=None, file_storage_service=storage, item_service=FakeItemService(existing))


def make_artifact(tmp_path: Path, qa: dict | None = None) -> TranslationArtifact:
    article_dir = tmp_path / "translated" / "article"
    article_dir.mkdir(parents=True, exist_ok=True)
    source_path = article_dir / "00-source.md"
    translation_path = article_dir / "translation.md"
    qa_path = article_dir / "qa.json"
    source_path.write_text('---\ntitle: Source Title\n---\n\nOriginal body', encoding="utf-8")
    translation_path.write_text("# 中文标题\n\n译文", encoding="utf-8")
    payload = qa or {"resolved_translator": "gemini", "requires_agent_completion": False, "verdict": "ready"}
    qa_path.write_text("{}", encoding="utf-8")
    return TranslationArtifact("art", article_dir, source_path, translation_path, qa_path, "Source Title", "Original body", payload)


def test_translate_task_rejects_invalid_url() -> None:
    with TestClient(app) as client:
        response = client.post("/api/translate/tasks", json={"url": "not-a-url"})
    assert response.status_code == 422


def test_translate_task_returns_existing_translation(monkeypatch) -> None:
    item = ContentItem(
        id="item-id",
        title="Existing Translation",
        source_url="https://example.com/article",
        translated_text_path="files/translated/article/translation.md",
        notion_page_id="page-id",
        notion_page_url="https://notion/page",
    )
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.container.translation_service, "find_existing_translation", lambda db, url: item)
        response = client.post("/api/translate/tasks", json={"url": "https://example.com/article"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["translated_file_path"] == "files/translated/article/translation.md"
    assert body["item_id"] == "item-id"


def test_translate_url_requires_gemini_key(tmp_path) -> None:
    service = make_service(tmp_path, api_key="")
    try:
        service.translate_url(None, "https://example.com/article")
    except Exception as exc:  # noqa: BLE001
        assert "GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected missing key failure")


def test_translate_url_rejects_unready_qa(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    artifact = make_artifact(tmp_path, {"resolved_translator": "gemini", "requires_agent_completion": False, "verdict": "needs_review", "issues": ["short"]})
    monkeypatch.setattr(service, "_run_global_translation_pipeline", lambda url: artifact)
    try:
        service.translate_url(None, "https://example.com/article")
    except Exception as exc:  # noqa: BLE001
        assert "翻译质检未通过" in str(exc)
    else:
        raise AssertionError("expected QA failure")


def test_translate_url_saves_ready_artifact(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    artifact = make_artifact(tmp_path)
    monkeypatch.setattr(service, "_run_global_translation_pipeline", lambda url: artifact)
    monkeypatch.setattr(service, "_display_path", lambda path: "files/translated/article/translation.md")
    item = service.translate_url(None, "https://example.com/article")
    assert item.title == "Source Title"
    assert item.translated_text_path == "files/translated/article/translation.md"
    assert item.translation_status == TranslationStatus.TRANSLATED
    assert item.process_status == ProcessStatus.COMPLETED
    assert item.notion_page_url == "https://notion/page"
