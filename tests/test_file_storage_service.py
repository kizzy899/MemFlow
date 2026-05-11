from pathlib import Path

from app.config import Settings
from app.services.file_storage_service import FileStorageService


def test_save_translation_markdown(tmp_path: Path) -> None:
    translated_dir = tmp_path / "translated"
    raw_dir = tmp_path / "raw"
    settings = Settings(
        TRANSLATION_OUTPUT_DIR=str(translated_dir),
        RAW_OUTPUT_DIR=str(raw_dir),
        DATABASE_URL=f"sqlite:///{tmp_path / 'app.db'}",
    )
    service = FileStorageService(settings)
    service.ensure_directories()

    output_path_str = service.save_translation_markdown("Hello", "https://example.com", "Translated content")
    output_path = Path(output_path_str)

    assert output_path.exists()
    assert "Translated content" in output_path.read_text(encoding="utf-8")
