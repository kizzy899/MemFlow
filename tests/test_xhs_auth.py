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
