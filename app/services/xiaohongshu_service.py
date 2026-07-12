from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import Settings
from app.models.content_item import ContentItem, ContentType, SourcePlatform
from app.services.exceptions import XiaohongshuFavoritesError, XiaohongshuLoginError
from app.services.xhs_login_service import XiaohongshuLoginService


class XiaohongshuService:
    HOME_URL = "https://www.xiaohongshu.com/explore"
    BASE_URL = "https://www.xiaohongshu.com"

    def __init__(self, settings: Settings, login_service: XiaohongshuLoginService | None = None, agent_search_service: Any | None = None, media_pipeline: Any | None = None) -> None:
        self.settings = settings
        self.login_service = login_service
        self.agent_search_service = agent_search_service
        self.media_pipeline = media_pipeline
        self._media_results: dict[str, dict[str, Any]] = {}

    async def fetch_favorites(self, limit: int = 20, progress=None, cancel_event: threading.Event | None = None) -> list[ContentItem]:
        if os.name == "nt":
            return await asyncio.to_thread(self._fetch_favorites_in_proactor_thread, limit, progress, cancel_event)
        return await self._fetch_favorites(limit, progress, cancel_event)

    def _fetch_favorites_in_proactor_thread(self, limit: int, progress=None, cancel_event: threading.Event | None = None) -> list[ContentItem]:
        loop = asyncio.ProactorEventLoop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._fetch_favorites(limit, progress, cancel_event))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()

    async def _fetch_favorites(self, limit: int, progress=None, cancel_event: threading.Event | None = None) -> list[ContentItem]:
        if not self.login_service or not self.login_service.session.storage_state:
            raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")

        def report(step: str, message: str, **values: Any) -> None:
            if progress:
                progress({"step": step, "message": message, **values})

        def check_cancelled() -> None:
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError("收藏读取已由用户取消")

        async with async_playwright() as playwright:
            owned_page = None
            cdp_mode = False
            if self.login_service.cdp_connected:
                cdp_mode = True
                check_cancelled(); report("connecting", "正在连接 Chrome 远程调试端口")
                cdp_browser = await asyncio.wait_for(
                    playwright.chromium.connect_over_cdp(await self.login_service.resolve_cdp_endpoint(), timeout=8000), timeout=10
                )
                if not cdp_browser.contexts:
                    raise XiaohongshuLoginError("Chrome CDP 没有可用的浏览器上下文。")
                context = cdp_browser.contexts[0]
                page = self._select_existing_xhs_page(context.pages)
                if page:
                    check_cancelled(); report("opening_page", "正在复用已打开的小红书页面", page_url=page.url)
                else:
                    check_cancelled(); report("opening_page", "正在创建小红书读取标签页")
                    page = owned_page = await asyncio.wait_for(context.new_page(), timeout=10)
            else:
                check_cancelled(); report("opening_browser", "正在启动本地浏览器会话")
                context = await self._create_context(playwright)
                page = await context.new_page() if not context.pages else context.pages[0]
            try:
                if not self._is_xhs_page(page.url):
                    check_cancelled(); report("opening_home", "正在打开小红书首页", page_url=self.HOME_URL)
                    await self._goto_lenient(page, self.HOME_URL)
                if "login" in page.url.lower():
                    raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")
                if not self._is_favorites_page(page.url):
                    await self._open_favorites(page, report, check_cancelled)
                items = await self._extract_items(page, limit, report, check_cancelled, cancel_event or threading.Event())
                if not items:
                    raise XiaohongshuFavoritesError("已进入个人收藏页，但没有识别到收藏内容；可能收藏为空或页面结构已变化。")
                return items
            except TimeoutError as exc:
                raise XiaohongshuFavoritesError("小红书页面操作超时，请检查 Chrome 页面、网络或风控提示后重试。") from exc
            finally:
                if owned_page and not cdp_mode:
                    try:
                        await asyncio.wait_for(owned_page.close(), timeout=5)
                    except Exception:
                        pass
                elif not cdp_mode:
                    try:
                        await asyncio.wait_for(context.close(), timeout=5)
                    except Exception:
                        pass

    async def _create_context(self, playwright: Any) -> BrowserContext:
        browser = await playwright.chromium.launch(headless=True)
        return await browser.new_context(storage_state=self.login_service.session.storage_state)

    def _select_existing_xhs_page(self, pages: list[Page]) -> Page | None:
        live_pages = [page for page in pages if not page.is_closed()]
        for page in live_pages:
            if self._is_favorites_page(page.url):
                return page
        for page in live_pages:
            if self._is_xhs_page(page.url):
                return page
        return None

    @staticmethod
    def _is_xhs_page(url: str) -> bool:
        return "xiaohongshu.com" in (url or "").lower()

    @staticmethod
    def _is_favorites_page(url: str) -> bool:
        value = (url or "").lower()
        return "xiaohongshu.com/user/profile/" in value and ("tab=fav" in value or "subtab=note" in value)

    async def _goto_lenient(self, page: Page, url: str) -> None:
        try:
            await asyncio.wait_for(page.goto(url, wait_until="domcontentloaded", timeout=30000), timeout=35)
            return
        except Exception:
            if self._is_xhs_page(page.url):
                return
        response = await asyncio.wait_for(page.goto(url, wait_until="commit", timeout=60000), timeout=65)
        if response is None and not self._is_xhs_page(page.url):
            raise XiaohongshuFavoritesError("小红书页面导航失败，请检查网络或风控提示后重试。")

    async def _open_favorites(self, page: Page, report=None, check_cancelled=None) -> None:
        report = report or (lambda *args, **kwargs: None)
        check_cancelled = check_cancelled or (lambda: None)
        if "/user/profile/" not in (page.url or ""):
            check_cancelled(); report("locating_profile", "正在查找当前账号个人主页", page_url=page.url)
            profile_href = await self._find_current_profile_href(page)
            if not profile_href:
                raise XiaohongshuLoginError("Current account profile entry was not found; confirm the login state is valid")
            profile_url = self._normalize_profile_url(profile_href)
            if not profile_url:
                raise XiaohongshuLoginError("当前账号的个人主页入口无效。")
            check_cancelled(); report("opening_profile", "正在进入个人主页", page_url=profile_url)
            await self._goto_lenient(page, profile_url)
            if "login" in page.url.lower():
                raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")
        try:
            check_cancelled(); report("opening_favorites", "Opening favorites tab", page_url=page.url)
            await self._open_favorites_tab(page)
            await page.wait_for_timeout(2000)
        except Exception as exc:
            raise XiaohongshuFavoritesError("Profile page opened, but the favorites tab was not found or is not visible") from exc

    async def _open_favorites_tab(self, page: Page) -> None:
        try:
            favorites_tab = page.get_by_text("\u6536\u85cf", exact=True).first
            await favorites_tab.wait_for(state="visible", timeout=5000)
            await favorites_tab.click()
            return
        except Exception:
            pass
        clicked = await page.evaluate(
            """() => {
                const candidates = Array.from(document.querySelectorAll('.reds-tab-item, [class*="tab"]'));
                const tab = candidates.find((node) => {
                    const text = (node.innerText || node.textContent || '').trim();
                    const rect = node.getBoundingClientRect();
                    return text === '\u6536\u85cf' && rect.width > 0 && rect.height > 0;
                });
                if (!tab) return false;
                tab.click();
                return true;
            }"""
        )
        if not clicked:
            raise XiaohongshuFavoritesError("Favorites tab was not found")

    async def _find_current_profile_href(self, page: Page) -> str | None:
        try:
            me_link = page.locator("a[href^='/user/profile/']").filter(has_text="\u6211").first
            await me_link.wait_for(state="visible", timeout=3000)
            href = await me_link.get_attribute("href")
            if href:
                return href
        except Exception:
            pass
        return await page.evaluate(
            """() => {
                const links = Array.from(document.querySelectorAll('a[href*="/user/profile/"]'));
                const normalized = links.map((node) => {
                    const href = node.href || node.getAttribute('href') || '';
                    const text = (node.innerText || node.textContent || '').trim();
                    const rect = node.getBoundingClientRect();
                    const visible = rect.width > 0 && rect.height > 0;
                    const className = String(node.className || '');
                    let url = null;
                    try { url = new URL(href, location.origin); } catch (_) {}
                    return { href, text, visible, className, url, x: rect.x };
                }).filter((item) => item.url && item.url.pathname.startsWith('/user/profile/'));
                const own = normalized.find((item) => item.visible && item.text === '\u6211');
                if (own) return own.url.href;
                const nav = normalized.find((item) =>
                    item.visible &&
                    item.x < 180 &&
                    !item.url.search &&
                    /link-wrapper|bottom-channel/.test(item.className)
                );
                if (nav) return nav.url.href;
                const bare = normalized.find((item) => item.visible && !item.url.search);
                return bare ? bare.url.href : null;
            }"""
        )

    def _normalize_profile_url(self, href: str | None) -> str | None:
        if not href:
            return None
        if href.startswith(f"{self.BASE_URL}/user/profile/"):
            return href
        if href.startswith("/user/profile/"):
            return f"{self.BASE_URL}{href}"
        return None
    async def _extract_items(self, page: Page, limit: int, report, check_cancelled, cancel_event: threading.Event) -> list[ContentItem]:
        check_cancelled(); report("locating_items", "正在识别收藏卡片", page_url=page.url)
        selectors = [
            "section.note-item",
            "div.note-item",
            "a.cover.mask.ld",
            "[data-testid='note-item']",
        ]
        for selector in selectors:
            if await page.locator(selector).count():
                return await self._read_locator_items(page, selector, limit, report, check_cancelled, cancel_event)
        return []

    async def _read_locator_items(self, page: Page, selector: str, limit: int, report, check_cancelled, cancel_event: threading.Event) -> list[ContentItem]:
        results: list[ContentItem] = []
        locator = page.locator(selector)
        count = min(await locator.count(), limit)
        for index in range(count):
            check_cancelled()
            node = locator.nth(index)
            title = await self._safe_inner_text(node.locator("a, .title, .footer, .note-content").first)
            href = await node.get_attribute("href")
            if not href:
                href = await node.locator("a").first.get_attribute("href")
            note_url = self._normalize_note_url(href)
            text = self._sanitize_content(await self._safe_inner_text(node))
            content_type = ContentType.POST
            source_type = "小红书图文"
            report("reading_item", f"正在读取第 {index + 1}/{count} 条收藏", current_index=index + 1, discovered=count, current_title=title or f"小红书收藏 {index + 1}", page_url=note_url or page.url)
            if note_url:
                detail_text, is_video, extraction_status = await asyncio.wait_for(
                    self._read_note_detail(page, note_url, report, check_cancelled, index + 1, count, cancel_event), timeout=self.settings.video_step_timeout_seconds + 90
                )
                if detail_text:
                    text = self._sanitize_content("\n".join(value for value in (title, detail_text) if value))
                if is_video:
                    content_type = ContentType.VIDEO
                    source_type = f"小红书视频（{extraction_status}）"
            external_id = note_url.rsplit("/", 1)[-1].split("?", 1)[0] if note_url else f"xhs-{index}"
            results.append(
                ContentItem(
                    title=title or f"小红书收藏 {index + 1}",
                    source_url=note_url,
                    source_platform=SourcePlatform.XIAOHONGSHU,
                    content_type=content_type,
                    source_type=source_type,
                    raw_text=text,
                    raw_excerpt=text[:200],
                    external_id=external_id,
                    **self._media_item_fields(note_url),
                )
            )
        return results

    async def _read_note_detail(self, page: Page, note_url: str, report=None, check_cancelled=None, index: int = 1, count: int = 1, cancel_event: threading.Event | None = None) -> tuple[str, bool, str]:
        report = report or (lambda *args, **kwargs: None)
        check_cancelled = check_cancelled or (lambda: None)
        detail = None
        try:
            check_cancelled(); report("opening_detail", f"正在打开第 {index}/{count} 条详情", current_index=index, discovered=count, page_url=note_url)
            detail = await asyncio.wait_for(page.context.new_page(), timeout=10)
            await asyncio.wait_for(detail.goto(note_url, wait_until="domcontentloaded", timeout=30000), timeout=35)
            detail_text = ""
            detail_selector = ""
            for selector in ("#detail-desc", ".note-content", ".desc", "[class*='note-content']"):
                detail_text = await self._safe_inner_text(detail.locator(selector).first)
                if detail_text:
                    detail_selector = selector
                    break
            if detail_selector:
                links = await detail.locator(f"{detail_selector} a[href]").evaluate_all(
                    "nodes => nodes.map(node => ({label: (node.innerText || '').trim(), url: node.href})).filter(item => /^https?:/.test(item.url))"
                )
                if links:
                    detail_text += "\n[正文显式链接]\n" + "\n".join(
                        f"{entry.get('label') or '名称待确认'}｜{entry['url']}" for entry in links
                    )
            video = detail.locator("video").first
            if not await video.count():
                return detail_text, False, "无需 OCR"
            video_source = await video.evaluate("node => node.currentSrc || node.src || node.querySelector('source')?.src || ''")
            if self.media_pipeline:
                result = await asyncio.to_thread(self.media_pipeline.process, note_url, str(video_source or ""), detail_text, report, cancel_event or threading.Event())
                self._media_results[note_url] = result
                return result["raw_text"], True, self._media_status_label(result)
            check_cancelled(); report("video_ocr", f"正在识别第 {index}/{count} 条视频文字", current_index=index, discovered=count, page_url=note_url)
            marker, ocr_text, resources = await asyncio.wait_for(self._extract_video_text(str(video_source or "")), timeout=60)
            parts = [detail_text, marker]
            if ocr_text: parts.extend(["[视频 OCR 全文]", ocr_text])
            if resources: parts.extend(["[视频中识别到的资源链接]", *(f"{entry.get('label') or '名称待确认'}｜{entry['url']}" for entry in resources)])
            return "\n".join(part for part in parts if part), True, marker.strip("[]")
        except Exception as exc:
            message = " ".join(str(exc).split())[:200] or type(exc).__name__
            return f"[详情内容提取失败：{message}]", False, "详情提取失败"
        finally:
            if detail is not None:
                try:
                    await asyncio.wait_for(detail.close(), timeout=5)
                except Exception:
                    pass

    def _media_item_fields(self, note_url: str | None) -> dict[str, Any]:
        result = self._media_results.pop(note_url, None) if note_url else None
        if not result: return {}
        fields = {key: result[key] for key in ("media_fetch_status", "media_provider", "ocr_status", "transcription_status", "content_completeness", "media_error_message")}
        fields["clean_content"] = result.get("ai_text", result.get("raw_text", ""))
        return fields

    def reprocess_saved_item(self, item: ContentItem, progress, cancel_event: threading.Event) -> ContentItem:
        if not self.media_pipeline or not item.source_url:
            raise XiaohongshuFavoritesError("该条目缺少媒体流水线或小红书笔记链接。")
        body = item.raw_text.split("[视频画面 OCR]", 1)[0].split("[视频语音转录]", 1)[0].strip()
        result = self.media_pipeline.process(item.source_url, "", body, progress, cancel_event)
        item.raw_text = result["raw_text"]
        item.clean_content = result["ai_text"]
        for key in ("media_fetch_status", "media_provider", "ocr_status", "transcription_status", "content_completeness", "media_error_message"):
            setattr(item, key, result[key])
        item.content_type = ContentType.VIDEO
        item.source_type = f"小红书视频（{self._media_status_label(result)}）"
        return item

    @staticmethod
    def _media_status_label(result: dict[str, Any]) -> str:
        return f"媒体:{result['media_fetch_status']} OCR:{result['ocr_status']} 语音:{result['transcription_status']}"

    async def _extract_video_text(self, video_source: str) -> tuple[str, str, list[dict[str, str]]]:
        if not video_source.startswith(("http://", "https://")):
            return "[视频文字提取失败：未取得可下载的视频地址]", "", []
        if not self.agent_search_service:
            return "[视频文字提取失败：OCR 服务不可用]", "", []
        try:
            result = await asyncio.to_thread(self.agent_search_service.extract, "video", video_source, 1.0, 1800)
        except Exception as exc:
            message = " ".join(str(exc).split())[:200] or type(exc).__name__
            return f"[视频文字提取失败：{message}]", "", []
        text = str(result.get("text", "")).strip()
        resources = [entry for entry in result.get("resources", []) if isinstance(entry, dict) and entry.get("url")]
        if not text:
            return "[视频文字提取为空：画面中未识别到清晰文字]", "", resources
        segments = len(result.get("segments", []))
        return f"[视频文字提取成功：OCR 共 {segments} 个有效片段]", text, resources

    @staticmethod
    def _sanitize_content(text: str) -> str:
        social_metric = re.compile(r"^(?:点赞|赞|收藏|评论|关注|粉丝|获赞)\s*[:：]?\s*[\d.]+(?:万|千|w|k)?$|^[\d.]+(?:万|千|w|k)?\s*(?:赞|点赞|收藏|评论|关注|粉丝|获赞)$", re.IGNORECASE)
        lines = []
        for line in text.splitlines():
            clean = " ".join(line.split()).strip()
            if not clean or social_metric.fullmatch(clean) or re.match(r"^(?:作者|博主|用户)\s*[:：]", clean):
                continue
            if clean not in lines:
                lines.append(clean)
        return "\n".join(lines)
    async def _safe_inner_text(self, locator: Any) -> str:
        try:
            return (await locator.inner_text(timeout=5000)).strip()
        except Exception:
            return ""

    def _normalize_note_url(self, href: str | None) -> str | None:
        if not href:
            return None
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"{self.BASE_URL}{href}"
        return None

    def _parse_cookie_header(self, cookie_header: str) -> list[dict[str, Any]]:
        stripped = cookie_header.strip()
        if not stripped:
            return []

        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return []

        cookies: list[dict[str, Any]] = []
        for pair in stripped.split(";"):
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            cookies.append(
                {
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                }
            )
        return cookies
