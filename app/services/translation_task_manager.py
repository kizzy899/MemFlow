from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db import SessionLocal
from app.models.content_item import ContentItem
from app.services.exceptions import TranslationError
from app.services.translation_service import TranslationService


class TranslationTaskManager:
    def __init__(self, translation_service: TranslationService) -> None:
        self.translation_service = translation_service
        self._lock = threading.Lock()
        self._state = self._idle()

    def set_translation_service(self, service: TranslationService) -> None:
        self.translation_service = service

    def start(self, url: str) -> dict[str, Any]:
        with self._lock:
            if self._state["status"] == "processing":
                return dict(self._state)
            task_id = str(uuid.uuid4())
            self._state = {
                **self._idle(),
                "task_id": task_id,
                "status": "processing",
                "source_url": url,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            threading.Thread(target=self._run, args=(task_id, url), daemon=True, name="memflow-translation-task").start()
            return dict(self._state)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def state_for_existing(self, item: ContentItem) -> dict[str, Any]:
        state = {
            **self._idle(),
            "status": "success",
            "source_url": item.source_url or "",
            "title": item.title,
            "translated_file_path": item.translated_text_path,
            "item_id": item.id,
            "notion_page_id": item.notion_page_id or "",
            "notion_page_url": item.notion_page_url or "",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._state = state
            return dict(self._state)

    def _run(self, task_id: str, url: str) -> None:
        try:
            with SessionLocal() as db:
                item = self.translation_service.translate_url(db, url)
            with self._lock:
                if self._state.get("task_id") != task_id:
                    return
                self._state.update(
                    status="success",
                    title=item.title,
                    translated_file_path=item.translated_text_path,
                    item_id=item.id,
                    notion_page_id=item.notion_page_id or "",
                    notion_page_url=item.notion_page_url or "",
                    last_error="",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        except TranslationError as exc:
            self._fail(task_id, str(exc))
        except Exception as exc:  # pylint: disable=broad-except
            self._fail(task_id, str(exc))

    def _fail(self, task_id: str, message: str) -> None:
        with self._lock:
            if self._state.get("task_id") != task_id:
                return
            self._state.update(status="failed", last_error=message, finished_at=datetime.now(timezone.utc).isoformat())

    @staticmethod
    def _idle() -> dict[str, Any]:
        return {
            "task_id": None,
            "status": "idle",
            "source_url": "",
            "title": "",
            "translated_file_path": "",
            "item_id": "",
            "notion_page_id": "",
            "notion_page_url": "",
            "last_error": "",
            "started_at": None,
            "finished_at": None,
        }
