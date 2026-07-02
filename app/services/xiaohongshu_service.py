from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import Settings
from app.models.content_item import ContentItem, ContentType, SourcePlatform
from app.services.exceptions import XiaohongshuFavoritesError, XiaohongshuLoginError
from app.services.xhs_login_service import XiaohongshuLoginService


class XiaohongshuService:
    HOME_URL = "https://www.xiaohongshu.com/explore"
    BASE_URL = "https://www.xiaohongshu.com"

    def __init__(self, settings: Settings, login_service: XiaohongshuLoginService | None = None, agent_search_service: Any | None = None) -> None:
        self.settings = settings
        self.login_service = login_service
        self.agent_search_service = agent_search_service

    async def fetch_favorites(self, limit: int = 20) -> list[ContentItem]:
        if os.name == "nt":
            return await asyncio.to_thread(self._fetch_favorites_in_proactor_thread, limit)
        return await self._fetch_favorites(limit)

    def _fetch_favorites_in_proactor_thread(self, limit: int) -> list[ContentItem]:
        loop = asyncio.ProactorEventLoop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._fetch_favorites(limit))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()

    async def _fetch_favorites(self, limit: int) -> list[ContentItem]:
        if not self.login_service or not self.login_service.session.storage_state:
            raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")

        async with async_playwright() as playwright:
            owned_page = None
            if self.login_service.cdp_connected:
                cdp_browser = await playwright.chromium.connect_over_cdp(self.login_service.cdp_url, timeout=5000)
                if not cdp_browser.contexts:
                    raise XiaohongshuLoginError("Chrome CDP 没有可用的浏览器上下文。")
                context = cdp_browser.contexts[0]
                page = owned_page = await context.new_page()
            else:
                context = await self._create_context(playwright)
                page = await context.new_page() if not context.pages else context.pages[0]
            try:
                await page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30000)
                if "login" in page.url.lower():
                    raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")
                await self._open_favorites(page)
                items = await self._extract_items(page, limit)
                if not items:
                    raise XiaohongshuFavoritesError("已进入个人收藏页，但没有识别到收藏内容；可能收藏为空或页面结构已变化。")
                return items
            finally:
                if owned_page:
                    await owned_page.close()
                else:
                    await context.close()

    async def _create_context(self, playwright: Any) -> BrowserContext:
        browser = await playwright.chromium.launch(headless=True)
        return await browser.new_context(storage_state=self.login_service.session.storage_state)

    async def _open_favorites(self, page: Page) -> None:
        me_link = page.locator("a[href^='/user/profile/']").filter(has_text="我").first
        try:
            await me_link.wait_for(state="visible", timeout=10000)
            profile_href = await me_link.get_attribute("href")
        except Exception as exc:
            raise XiaohongshuLoginError("未找到当前账号的个人主页入口，请确认登录态有效。") from exc
        profile_url = self._normalize_profile_url(profile_href)
        if not profile_url:
            raise XiaohongshuLoginError("当前账号的个人主页入口无效。")
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        if "login" in page.url.lower():
            raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")
        favorites_tab = page.get_by_text("收藏", exact=True).first
        try:
            await favorites_tab.wait_for(state="visible", timeout=15000)
            await favorites_tab.click()
            await page.wait_for_timeout(2000)
        except Exception as exc:
            raise XiaohongshuFavoritesError("已进入个人主页，但没有找到可访问的收藏入口；可能页面结构已变化或该入口不可见。") from exc

    def _normalize_profile_url(self, href: str | None) -> str | None:
        if not href:
            return None
        if href.startswith(f"{self.BASE_URL}/user/profile/"):
            return href
        if href.startswith("/user/profile/"):
            return f"{self.BASE_URL}{href}"
        return None
    async def _extract_items(self, page: Page, limit: int) -> list[ContentItem]:
        selectors = [
            "section.note-item",
            "div.note-item",
            "a.cover.mask.ld",
            "[data-testid='note-item']",
        ]
        for selector in selectors:
            if await page.locator(selector).count():
                return await self._read_locator_items(page, selector, limit)
        return []

    async def _read_locator_items(self, page: Page, selector: str, limit: int) -> list[ContentItem]:
        results: list[ContentItem] = []
        locator = page.locator(selector)
        count = min(await locator.count(), limit)
        for index in range(count):
            node = locator.nth(index)
            title = await self._safe_inner_text(node.locator("a, .title, .footer, .note-content").first)
            href = await node.get_attribute("href")
            if not href:
                href = await node.locator("a").first.get_attribute("href")
            note_url = self._normalize_note_url(href)
            text = self._sanitize_content(await self._safe_inner_text(node))
            content_type = ContentType.POST
            source_type = "小红书图文"
            if note_url:
                detail_text, is_video, extraction_status = await self._read_note_detail(page, note_url)
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
                )
            )
        return results

    async def _read_note_detail(self, page: Page, note_url: str) -> tuple[str, bool, str]:
        detail = None
        try:
            detail = await page.context.new_page()
            await detail.goto(note_url, wait_until="domcontentloaded", timeout=30000)
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
            marker, ocr_text, resources = await self._extract_video_text(str(video_source or ""))
            parts = [detail_text, marker]
            if ocr_text:
                parts.extend(["[视频 OCR 全文]", ocr_text])
            if resources:
                parts.append("[视频中识别到的资源链接]")
                parts.extend(f"{entry.get('label') or '名称待确认'}｜{entry['url']}" for entry in resources)
            return "\n".join(part for part in parts if part), True, marker.strip("[]")
        except Exception as exc:
            message = " ".join(str(exc).split())[:200] or type(exc).__name__
            return f"[详情内容提取失败：{message}]", False, "详情提取失败"
        finally:
            if detail is not None:
                await detail.close()

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

