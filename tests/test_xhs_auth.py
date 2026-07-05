from cryptography.fernet import Fernet
import pytest
from app.services.auth.cookie_store import AuthKeyError, CookieStore
from app.services.auth.session_manager import AuthState, SessionManager
from app.services.xhs_login_service import XiaohongshuLoginService


def test_cookie_store_encrypts_and_deletes(tmp_path):
    store=CookieStore(tmp_path/"xiaohongshu.json",Fernet.generate_key().decode())
    store.save({"storageState":{"cookies":[{"value":"secret-cookie"}]}})
    assert "secret-cookie" not in store.path.read_text(encoding="utf-8")
    assert store.load()["storageState"]["cookies"][0]["value"]=="secret-cookie"
    store.delete()
    assert not store.path.exists()


def test_invalid_key_and_public_session():
    store=CookieStore(__import__("pathlib").Path("unused"),"bad")
    assert store.configured is False
    with pytest.raises(AuthKeyError): store.save({})
    session=SessionManager(state=AuthState.AUTHENTICATED)
    public=session.public()
    assert public["loggedIn"] is True and "storage_state" not in public


def test_risk_control_detail_does_not_expose_page_content(tmp_path):
    service=XiaohongshuLoginService(tmp_path,Fernet.generate_key().decode())
    service._page=type("Page",(),{"url":"https://www.xiaohongshu.com/website-login/error?error_code=300012&error_msg=secret"})()
    assert service._risk_detail()=="error_code=300012"


def test_cdp_endpoint_uses_websocket_url_without_trailing_slash_failure(tmp_path, monkeypatch):
    import asyncio
    service=XiaohongshuLoginService(tmp_path,Fernet.generate_key().decode(),"http://127.0.0.1:9223")
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"webSocketDebuggerUrl":"ws://127.0.0.1:9223/devtools/browser/test"}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,url):
            assert url.endswith("/json/version") and not url.endswith("/")
            return Response()
    monkeypatch.setattr("app.services.xhs_login_service.httpx.AsyncClient",lambda **kwargs:Client())
    assert asyncio.run(service.resolve_cdp_endpoint())=="ws://127.0.0.1:9223/devtools/browser/test"
