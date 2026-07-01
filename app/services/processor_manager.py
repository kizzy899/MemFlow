from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.db import SessionLocal


class ProcessorManager:
    def __init__(self, archive_service) -> None:
        self.archive_service = archive_service
        self._lock = threading.Lock()
        self._state = self._idle()

    def set_archive_service(self, service) -> None:
        self.archive_service = service

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._state["status"] == "processing": raise RuntimeError("整理任务正在运行")
            task_id = str(uuid.uuid4())
            self._state = {**self._idle(), "task_id": task_id, "status": "processing", "started_at": datetime.now(timezone.utc).isoformat()}
            threading.Thread(target=self._run, args=(task_id,), daemon=True, name="memflow-link-processor").start()
            return dict(self._state)

    def status(self) -> dict[str, Any]:
        with self._lock: return dict(self._state)

    def _run(self, task_id: str) -> None:
        try:
            with SessionLocal() as db:
                result = self.archive_service.run(db, progress=self._progress)
            failed = result["failed_fetch"] + result["failed_parse"] + result["failed_notion"]
            with self._lock:
                self._state.update(status="failed" if failed else "success", current_url="", processed=len(result["results"]), success=result["processed"], skipped_duplicate=result["skipped_duplicate"], failed=failed, last_error=next((x["message"] for x in result["results"] if x["status"].startswith("failed_")), ""), result=result, finished_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            with self._lock: self._state.update(status="failed", current_url="", last_error=str(exc), finished_at=datetime.now(timezone.utc).isoformat())

    def _progress(self, event: str, payload: dict[str, Any]) -> None:
        with self._lock:
            if event == "processing": self._state["current_url"] = payload.get("current_url", "")
            elif event == "result":
                self._state["processed"] += 1
                status = payload.get("status", "")
                if status == "processed": self._state["success"] += 1
                elif status == "skipped_duplicate": self._state["skipped_duplicate"] += 1
                elif status.startswith("failed_"): self._state["failed"] += 1; self._state["last_error"] = payload.get("message", "")

    @staticmethod
    def _idle() -> dict[str, Any]:
        return {"task_id": None, "status": "idle", "current_url": "", "processed": 0, "success": 0, "skipped_duplicate": 0, "failed": 0, "last_error": "", "started_at": None, "finished_at": None, "result": None}