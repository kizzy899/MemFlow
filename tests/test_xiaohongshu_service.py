from unittest.mock import AsyncMock, MagicMock
import asyncio
import pytest
from app.config import Settings
from app.services.exceptions import XiaohongshuFavoritesError, XiaohongshuLoginError
from app.services.xiaohongshu_service import XiaohongshuService

def service(): return XiaohongshuService(Settings(_env_file=None))

def test_profile_url_validation():
    s=service()
    assert s._normalize_profile_url('/user/profile/abc') == 'https://www.xiaohongshu.com/user/profile/abc'
    assert s._normalize_profile_url('https://example.com/user/profile/abc') is None

def test_open_favorites_navigates_and_clicks_tab():
    s,page,me,tab=service(),MagicMock(),MagicMock(),MagicMock()
    page.locator.return_value.filter.return_value=MagicMock(first=me)
    page.get_by_text.return_value=MagicMock(first=tab)
    me.wait_for,me.get_attribute=AsyncMock(),AsyncMock(return_value='/user/profile/abc')
    tab.wait_for,tab.click=AsyncMock(),AsyncMock()
    page.goto,page.wait_for_timeout=AsyncMock(),AsyncMock()
    page.url='https://www.xiaohongshu.com/user/profile/abc'
    asyncio.run(s._open_favorites(page))
    tab.click.assert_awaited_once()

def test_open_favorites_fails_without_profile_entry():
    s,page,me=service(),MagicMock(),MagicMock()
    page.get_by_text.return_value=MagicMock(first=me)
    me.wait_for=AsyncMock(side_effect=TimeoutError)
    with pytest.raises(XiaohongshuLoginError, match='个人主页入口'):
        asyncio.run(s._open_favorites(page))


def test_open_favorites_distinguishes_logged_in_but_missing_favorites():
    s, page, me, tab = service(), MagicMock(), MagicMock(), MagicMock()
    page.locator.return_value.filter.return_value = MagicMock(first=me)
    page.get_by_text.return_value = MagicMock(first=tab)
    me.wait_for, me.get_attribute = AsyncMock(), AsyncMock(return_value="/user/profile/abc")
    page.goto = AsyncMock()
    page.url = "https://www.xiaohongshu.com/user/profile/abc"
    tab.wait_for = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(XiaohongshuFavoritesError, match="已进入个人主页"):
        asyncio.run(s._open_favorites(page))

def test_windows_fetch_runs_browser_on_worker_thread(monkeypatch):
    s = XiaohongshuService(Settings(_env_file=None, XHS_COOKIE="a=b"))
    expected = [object()]
    monkeypatch.setattr("app.services.xiaohongshu_service.os.name", "nt")
    monkeypatch.setattr(s, "_fetch_favorites_in_proactor_thread", lambda limit: expected)

    assert asyncio.run(s.fetch_favorites(limit=1)) is expected
