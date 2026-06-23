from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from app.config import Settings


class FileStorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ensure_directories(self) -> None:
        self.settings.translation_output_path.mkdir(parents=True, exist_ok=True)
        self.settings.raw_output_path.mkdir(parents=True, exist_ok=True)
        sqlite_path = self.settings.sqlite_file_path
        if sqlite_path is not None:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    def save_raw_content(self, source_url: str, raw_content: str) -> str:
        filename = self._build_filename(source_url or "raw-content", suffix=".html")
        path = self.settings.raw_output_path / filename
        path.write_text(raw_content, encoding="utf-8")
        return self._display_path(path)

    def save_translation_markdown(self, title: str, source_url: str, translated_text: str) -> str:
        filename = self._build_filename(title or source_url or "translation", suffix=".md")
        path = self.settings.translation_output_path / filename
        content = (
            f"# {title or 'Untitled Translation'}\n\n"
            f"原链接：{source_url or 'N/A'}\n\n"
            f"生成时间：{datetime.now(timezone.utc).isoformat()}\n\n"
            f"---\n\n"
            f"{translated_text.strip()}\n"
        )
        path.write_text(content, encoding="utf-8")
        return self._display_path(path)

    def _build_filename(self, value: str, suffix: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
        if not slug:
            slug = "item"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{slug[:60]}-{timestamp}{suffix}"

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.settings.base_dir))
        except ValueError:
            return str(path)
