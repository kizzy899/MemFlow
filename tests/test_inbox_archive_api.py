from fastapi.testclient import TestClient
from app.main import app


def test_archive_links_api(monkeypatch):
    data={"processed":1,"skipped_duplicate":0,"failed_fetch":0,"failed_parse":0,"failed_notion":0,"remaining":0,"hot_updated":True,"results":[],"run_id":"r"}
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.container.link_archive_service, "run", lambda db: data)
        response=client.post("/api/inbox/archive-links")
    assert response.status_code == 200
    assert response.json()["data"]["processed"] == 1