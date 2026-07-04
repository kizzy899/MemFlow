import asyncio
import time

from app.services.xhs_sync_manager import XiaohongshuSyncManager


class WaitingXhsService:
    async def fetch_favorites(self, limit, progress=None, cancel_event=None):
        progress({"step": "opening_favorites", "message": "opening", "page_url": "https://www.xiaohongshu.com/user/profile/me"})
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        raise asyncio.CancelledError()


def test_xhs_manager_reports_progress_heartbeat_and_cancel():
    manager = XiaohongshuSyncManager(WaitingXhsService(), object())
    started = manager.start(3)
    assert started["status"] == "fetching"

    deadline = time.time() + 3
    while manager.status()["step"] != "opening_favorites" and time.time() < deadline:
        time.sleep(0.01)
    assert manager.status()["page_url"].endswith("/profile/me")

    cancelling = manager.cancel()
    assert cancelling["status"] == "cancelling"
    while manager.status()["status"] != "cancelled" and time.time() < deadline:
        time.sleep(0.01)
    assert manager.status()["status"] == "cancelled"
    assert manager.status()["finished_at"]
