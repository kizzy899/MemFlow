from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db import SessionLocal


class XiaohongshuSyncManager:
    """Run a favorites import outside the HTTP request and expose polling state."""

    def __init__(self, xhs_service, content_pipeline_service) -> None:
        self.xhs_service = xhs_service
        self.content_pipeline_service = content_pipeline_service
        self._lock = threading.Lock()
        self._state = self._idle()
        self._cancel_event = threading.Event()
        self._heartbeat_stop = threading.Event()

    def set_services(self, xhs_service, content_pipeline_service) -> None:
        self.xhs_service = xhs_service
        self.content_pipeline_service = content_pipeline_service

    def start(self, limit: int) -> dict[str, Any]:
        with self._lock:
            if self._state["status"] in {"fetching", "processing", "cancelling"}:
                raise RuntimeError("Xiaohongshu sync is already running")
            self._cancel_event = threading.Event()
            self._heartbeat_stop = threading.Event()
            task_id = str(uuid.uuid4())
            now = self._now()
            self._state = {
                **self._idle(), "task_id": task_id, "status": "fetching",
                "phase": "fetching", "message": "正在从小红书收藏页读取条目",
                "requested": limit, "started_at": now, "updated_at": now,
            }
            threading.Thread(target=self._run, args=(task_id, limit), daemon=True, name="memflow-xhs-sync").start()
            threading.Thread(target=self._heartbeat, args=(task_id,), daemon=True, name="memflow-xhs-heartbeat").start()
            return dict(self._state)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if self._state["status"] not in {"fetching", "processing", "cancelling"}:
                return dict(self._state)
            self._cancel_event.set()
            self._state.update(status="cancelling", message="正在取消任务，请等待当前页面操作退出", updated_at=self._now())
            return dict(self._state)

    def _run(self, task_id: str, limit: int) -> None:
        try:
            items = asyncio.run(self.xhs_service.fetch_favorites(limit=limit, progress=self._fetch_progress, cancel_event=self._cancel_event))
            if self._cancel_event.is_set():
                raise asyncio.CancelledError("收藏读取已由用户取消")
            with self._lock:
                if self._state["task_id"] != task_id:
                    return
                self._state.update(
                    status="processing", phase="processing", fetched=len(items),
                    message="收藏读取完成，开始逐条分析并同步 Notion",
                    updated_at=self._now(),
                )
            with SessionLocal() as db:
                for index, item in enumerate(items, start=1):
                    if self._cancel_event.is_set():
                        raise asyncio.CancelledError("收藏读取已由用户取消")
                    with self._lock:
                        self._state.update(
                            current_index=index,
                            current_title=getattr(item, "title", "") or "未命名收藏",
                            message="正在分析内容并同步 Notion",
                            updated_at=self._now(),
                        )
                    processed = self.content_pipeline_service.process_xiaohongshu_item(db, item)
                    with self._lock:
                        self._state["processed"] += 1
                        if processed.process_status.value == "completed":
                            self._state["success"] += 1
                        else:
                            self._state["failed"] += 1
                            self._state["last_error"] = getattr(processed, "error_message", "") or "该条收藏处理失败"
                        self._state["updated_at"] = self._now()
            with self._lock:
                failed = self._state["failed"]
                now = self._now()
                self._state.update(
                    status="success" if not failed else "failed", phase="completed",
                    message="全部收藏处理完成" if not failed else "任务结束，部分收藏处理失败",
                    current_title="", finished_at=now, updated_at=now,
                )
        except asyncio.CancelledError:
            with self._lock:
                now = self._now()
                self._state.update(status="cancelled", phase="cancelled", message="任务已取消", current_title="", finished_at=now, updated_at=now)
        except Exception as exc:
            with self._lock:
                now = self._now()
                self._state.update(
                    status="failed", phase="failed", message="收藏任务执行失败",
                    current_title="", last_error=str(exc), finished_at=now, updated_at=now,
                )
        finally:
            self._heartbeat_stop.set()

    def _fetch_progress(self, payload: dict[str, Any]) -> None:
        with self._lock:
            if self._state["status"] == "cancelling":
                return
            self._state.update(
                step=payload.get("step", self._state["step"]),
                message=payload.get("message", self._state["message"]),
                page_url=payload.get("page_url", self._state["page_url"]),
                current_index=payload.get("current_index", self._state["current_index"]),
                current_title=payload.get("current_title", self._state["current_title"]),
                discovered=payload.get("discovered", self._state["discovered"]),
                last_progress_at=self._now(), updated_at=self._now(),
            )

    def _heartbeat(self, task_id: str) -> None:
        while not self._heartbeat_stop.wait(2):
            with self._lock:
                if self._state["task_id"] != task_id or self._state["status"] not in {"fetching", "processing", "cancelling"}:
                    return
                self._state["heartbeat_at"] = self._now()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _idle() -> dict[str, Any]:
        return {
            "task_id": None, "status": "idle", "phase": "idle", "step": "idle", "message": "等待开始",
            "requested": 0, "fetched": 0, "processed": 0, "success": 0, "failed": 0,
            "discovered": 0, "current_index": 0, "current_title": "", "page_url": "", "last_error": "",
            "started_at": None, "updated_at": None, "last_progress_at": None, "heartbeat_at": None, "finished_at": None,
        }
