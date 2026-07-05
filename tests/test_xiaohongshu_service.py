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
    s = XiaohongshuService(Settings(_env_file=None))
    expected = [object()]
    monkeypatch.setattr("app.services.xiaohongshu_service.os.name", "nt")
    monkeypatch.setattr(s, "_fetch_favorites_in_proactor_thread", lambda limit, progress, cancel_event: expected)

    assert asyncio.run(s.fetch_favorites(limit=1)) is expected
class FakeAgentSearch:
    def __init__(self, result=None, failure=None):
        self.result = result or {"text": "工具 Alpha https://alpha.example", "segments": [{"timestamp": 0, "text": "工具 Alpha"}], "resources": [{"label": "Alpha", "url": "https://alpha.example"}]}
        self.failure = failure
        self.calls = []

    def extract(self, source_type, source, interval, max_frames):
        self.calls.append((source_type, source, interval, max_frames))
        if self.failure:
            raise self.failure
        return self.result


def test_video_ocr_collects_full_text_and_resources():
    agent = FakeAgentSearch()
    s = XiaohongshuService(Settings(_env_file=None), agent_search_service=agent)
    marker, text, resources = asyncio.run(s._extract_video_text("https://cdn.example/video.mp4"))
    assert "提取成功" in marker
    assert text == "工具 Alpha https://alpha.example"
    assert resources[0]["url"] == "https://alpha.example"
    assert agent.calls == [("video", "https://cdn.example/video.mp4", 1.0, 1800)]


def test_video_ocr_empty_and_failure_are_explicitly_marked():
    empty = FakeAgentSearch(result={"text": "", "segments": [], "resources": []})
    marker, text, _ = asyncio.run(XiaohongshuService(Settings(_env_file=None), agent_search_service=empty)._extract_video_text("https://cdn.example/empty.mp4"))
    assert "提取为空" in marker and text == ""
    failed = FakeAgentSearch(failure=RuntimeError("download blocked"))
    marker, text, _ = asyncio.run(XiaohongshuService(Settings(_env_file=None), agent_search_service=failed)._extract_video_text("https://cdn.example/fail.mp4"))
    assert "提取失败" in marker and "download blocked" in marker and text == ""


def test_xhs_content_sanitizer_removes_social_metrics_and_author_labels():
    value = XiaohongshuService._sanitize_content("作者：某某\n点赞 1.2万\n正文工具推荐\n300 收藏\nhttps://tool.example")
    assert value == "正文工具推荐\nhttps://tool.example"

def test_detail_text_includes_explicit_recommendation_links():
    s = service()
    page, context, detail = MagicMock(), MagicMock(), MagicMock()
    page.context = context
    context.new_page = AsyncMock(return_value=detail)
    detail.goto, detail.close = AsyncMock(), AsyncMock()
    description = MagicMock()
    description.first = description
    description.inner_text = AsyncMock(return_value="推荐 Alpha 工具")
    anchors = MagicMock()
    anchors.evaluate_all = AsyncMock(return_value=[{"label": "Alpha", "url": "https://alpha.example/app"}])
    video = MagicMock()
    video.first = video
    video.count = AsyncMock(return_value=0)
    def locate(selector):
        if selector == "#detail-desc": return description
        if selector == "#detail-desc a[href]": return anchors
        if selector == "video": return video
        fallback = MagicMock(); fallback.first = fallback; fallback.inner_text = AsyncMock(return_value="")
        return fallback
    detail.locator.side_effect = locate
    text, is_video, status = asyncio.run(s._read_note_detail(page, "https://www.xiaohongshu.com/explore/note"))
    assert "Alpha｜https://alpha.example/app" in text
    assert is_video is False and status == "无需 OCR"
    detail.close.assert_awaited_once()
