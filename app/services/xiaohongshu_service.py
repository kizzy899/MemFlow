from __future__ import annotations

import json
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import Settings
from app.models.content_item import ContentItem, ContentType, SourcePlatform
from app.services.exceptions import XiaohongshuLoginError


class XiaohongshuService:
    FAVORITES_URL = "https://www.xiaohongshu.com/explore"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch_favorites(self, limit: int = 20) -> list[ContentItem]:
        if not self.settings.xhs_browser_profile_path and not self.settings.xhs_cookie:
            raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")

        async with async_playwright() as playwright:
            context = await self._create_context(playwright)
            try:
                page = await context.new_page() if not context.pages else context.pages[0]
                await page.goto(self.FAVORITES_URL, wait_until="networkidle", timeout=30000)
                if "login" in page.url.lower():
                    raise XiaohongshuLoginError("需要重新配置 Cookie 或浏览器登录态。")
                items = await self._extract_items(page, limit)
                if not items:
                    raise XiaohongshuLoginError("未读取到收藏内容，请确认当前登录态可以访问收藏页。")
                return items
            finally:
                await context.close()

    async def _create_context(self, playwright: Any) -> BrowserContext:
        if self.settings.xhs_browser_profile_path:
            return await playwright.chromium.launch_persistent_context(
                user_data_dir=self.settings.xhs_browser_profile_path,
                headless=True,
            )

        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        cookies = self._parse_cookie_header(self.settings.xhs_cookie)
        if cookies:
            await context.add_cookies(cookies)
        return context

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
            text = await self._safe_inner_text(node)
            external_id = note_url.rsplit("/", 1)[-1] if note_url else f"xhs-{index}"
            results.append(
                ContentItem(
                    title=title or f"小红书收藏 {index + 1}",
                    source_url=note_url,
                    source_platform=SourcePlatform.XIAOHONGSHU,
                    content_type=ContentType.POST,
                    raw_text=text,
                    raw_excerpt=text[:200],
                    external_id=external_id,
                )
            )
        return results

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
            return f"https://www.xiaohongshu.com{href}"
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

