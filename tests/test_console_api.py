from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from app.main import app
from app.services.exceptions import XiaohongshuFavoritesError, XiaohongshuLoginError


def test_console_read_apis_and_static_page_do_not_expose_secrets():
    with TestClient(app) as client:
        status=client.get('/api/config/status')
        assert status.status_code==200
        body=status.json(); text=status.text
        assert 'xhs_cookie' not in text.lower() and 'notion_api_key' not in text.lower()
        cookie=app.state.container.settings.xhs_cookie; token=app.state.container.settings.notion_api_key
        if cookie: assert cookie not in text
        if token: assert token not in text
        assert client.get('/api/inbox').status_code==200
        assert client.get('/api/processor/status').json()['data']['status'] in {'idle','processing','success','failed'}
        assert client.get('/api/notion/recent').status_code==200
        assert client.get('/api/hot').status_code==200
        page=client.get('/console')
        assert page.status_code==200 and 'Knowledge Console' in page.text

def test_xhs_check_distinguishes_login_and_favorites_failures(monkeypatch):
    with TestClient(app) as client:
        async def login_failed(limit):
            raise XiaohongshuLoginError("Cookie 已失效")

        monkeypatch.setattr(app.state.container.xiaohongshu_service, "fetch_favorites", login_failed)
        response = client.post("/api/xiaohongshu/test")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "login_failed"
        assert response.json()["message"].startswith("登录失败：")

        async def favorites_failed(limit):
            raise XiaohongshuFavoritesError("收藏入口不可见")

        monkeypatch.setattr(app.state.container.xiaohongshu_service, "fetch_favorites", favorites_failed)
        response = client.post("/api/xiaohongshu/test")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "favorites_unavailable"
        assert response.json()["message"].startswith("登录成功，但没有读取到收藏页：")

def test_xhs_check_never_returns_an_empty_failure_message(monkeypatch):
    with TestClient(app) as client:
        async def timed_out(limit):
            raise TimeoutError()

        monkeypatch.setattr(app.state.container.xiaohongshu_service, "fetch_favorites", timed_out)
        response = client.post("/api/xiaohongshu/test")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "failed"
        assert body["message"] == "检测失败：页面加载或浏览器操作超时，请检查网络、代理和小红书页面是否可访问。"


def test_saving_xhs_config_immediately_reads_favorites(monkeypatch):
    with TestClient(app) as client:
        container = app.state.container
        monkeypatch.setattr(container.config_service, "update", lambda values: None)
        monkeypatch.setattr("app.routers.console._reload", lambda current: None)
        fetch = AsyncMock(return_value=[object()])
        monkeypatch.setattr(container.xiaohongshu_service, "fetch_favorites", fetch)

        response = client.post(
            "/api/config/xhs",
            json={"xhs_cookie": "cookie", "xhs_username": "", "xhs_password": ""},
        )

        assert response.status_code == 200
        assert response.json()["data"]["check"]["status"] == "configured"
        fetch.assert_awaited_once_with(limit=1)
