from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.xhs_login_service import LoginServiceError


def test_console_read_apis_do_not_expose_secrets():
    with TestClient(app) as client:
        text=client.get("/api/config/status").text.lower()
        assert "xhs_cookie" not in text and "notion_api_key" not in text
        assert client.get("/api/xhs/session").status_code==200
        assert client.get("/api/inbox").status_code==200
        assert client.get("/console").status_code==200


def test_xhs_session_and_logout(monkeypatch):
    with TestClient(app) as client:
        service=app.state.container.xhs_login_service
        monkeypatch.setattr(service,"session_status",lambda:{"loggedIn":True,"status":"authenticated"})
        assert client.get("/api/xhs/session").json()["loggedIn"] is True
        logout=AsyncMock()
        monkeypatch.setattr(service,"logout",logout)
        assert client.post("/api/xhs/logout").json()=={"status":"idle","loggedIn":False}
        logout.assert_awaited_once()


def test_qr_error_contract(monkeypatch):
    with TestClient(app) as client:
        service=app.state.container.xhs_login_service
        monkeypatch.setattr(service,"start_login",AsyncMock(side_effect=LoginServiceError("AUTH_KEY_MISSING","missing",retryable=False)))
        response=client.get("/api/xhs/login/qrcode")
        assert response.status_code==503
        assert response.json()=={"code":"AUTH_KEY_MISSING","message":"missing","detail":"","retryable":False}


def test_chrome_cdp_connect_api(monkeypatch):
    with TestClient(app) as client:
        service=app.state.container.xhs_login_service
        result={"loggedIn":True,"status":"authenticated","mode":"chrome_cdp"}
        connect=AsyncMock(return_value=result)
        monkeypatch.setattr(service,"connect_chrome",connect)
        response=client.post("/api/xhs/login/chrome")
        assert response.status_code==200 and response.json()==result
        connect.assert_awaited_once()


def test_legacy_xhs_routes_are_removed():
    with TestClient(app) as client:
        assert client.post("/api/xiaohongshu/test").status_code==404
        assert client.post("/api/config/xhs",json={}).status_code==404


def test_xhs_sync_limit_is_bounded():
    with TestClient(app) as client:
        assert client.post("/api/xhs/sync",json={"limit":0}).status_code==422
        assert client.post("/api/xhs/sync",json={"limit":101}).status_code==422


def test_xhs_sync_starts_background_task_and_reports_status(monkeypatch):
    with TestClient(app) as client:
        manager = app.state.container.xhs_sync_manager
        state = {"task_id": "xhs-1", "status": "fetching", "requested": 12}
        monkeypatch.setattr(manager, "start", lambda limit: state | {"requested": limit})
        monkeypatch.setattr(manager, "status", lambda: state)

        response = client.post("/api/xhs/sync", json={"limit": 12})
        assert response.status_code == 202
        assert response.json()["requested"] == 12
        assert client.get("/api/xhs/sync/status").json() == state


def test_xhs_sync_cancel_endpoint(monkeypatch):
    with TestClient(app) as client:
        manager = app.state.container.xhs_sync_manager
        state = {"task_id": "xhs-1", "status": "cancelling"}
        monkeypatch.setattr(manager, "cancel", lambda: state)
        response = client.post("/api/xhs/sync/cancel")
        assert response.status_code == 200
        assert response.json() == state


def test_xhs_provider_health_and_manual_video_reprocess(monkeypatch):
    from app.db import SessionLocal
    from app.models.content_item import ContentItem, ContentType, SourcePlatform
    item = ContentItem(title="历史视频", source_url="https://www.xiaohongshu.com/explore/test-media", source_platform=SourcePlatform.XIAOHONGSHU, content_type=ContentType.VIDEO, media_fetch_status="failed", ocr_status="failed", transcription_status="skipped", content_completeness="partial")
    with SessionLocal() as db:
        db.add(item); db.commit(); item_id = item.id
    try:
        with TestClient(app) as client:
            manager = app.state.container.xhs_sync_manager
            monkeypatch.setattr(manager, "start_reprocess", lambda ids: {"task_id": "media-1", "status": "processing", "requested": len(ids)})
            health = client.get("/api/xhs/providers")
            assert health.status_code == 200
            assert "cookie" not in health.text.lower()
            candidates = client.get("/api/xhs/media/candidates").json()["items"]
            assert any(row["item_id"] == item_id for row in candidates)
            response = client.post("/api/xhs/media/reprocess", json={"item_ids": [item_id]})
            assert response.status_code == 202 and response.json()["requested"] == 1
    finally:
        with SessionLocal() as db:
            saved = db.get(ContentItem, item_id)
            if saved: db.delete(saved); db.commit()
