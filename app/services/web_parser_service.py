from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json

from bs4 import BeautifulSoup
import httpx
from readability import Document
import trafilatura

from app.config import Settings
from app.services.exceptions import ParsingError
from app.services.file_storage_service import FileStorageService


@dataclass
class ParsedWebContent:
    source_url: str
    title: str
    content: str
    author: str
    published_at: datetime | None
    site_name: str
    raw_file_path: str


class WebParserService:
    def __init__(self, settings: Settings, file_storage_service: FileStorageService) -> None:
        self.settings = settings
        self.file_storage_service = file_storage_service

    def parse_url(self, url: str) -> ParsedWebContent:
        html = self._fetch(url)
        raw_file_path = self.file_storage_service.save_raw_content(url, html)

        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            output_format="txt",
            favor_precision=True,
        )
        metadata = trafilatura.extract_metadata(html)

        if extracted:
            title = (metadata.title if metadata else "") or self._extract_title_from_html(html)
            author = (metadata.author if metadata else "") or self._extract_author_from_html(html)
            date_raw = (metadata.date if metadata else "") or self._extract_published_date_from_html(html)
            site_name = (metadata.sitename if metadata else "") or self._extract_site_name_from_html(html, url)
            published_at = self._safe_parse_datetime(date_raw)
            return ParsedWebContent(
                source_url=url,
                title=title.strip() or url,
                content=extracted.strip(),
                author=author.strip(),
                published_at=published_at,
                site_name=site_name.strip(),
                raw_file_path=raw_file_path,
            )

        document = Document(html)
        summary_html = document.summary(html_partial=True)
        soup = BeautifulSoup(summary_html, "html.parser")
        content = soup.get_text("\n", strip=True)
        if not content:
            raise ParsingError(f"Unable to extract readable content from {url}")

        return ParsedWebContent(
            source_url=url,
            title=document.short_title() or self._extract_title_from_html(html) or url,
            content=content,
            author=self._extract_author_from_html(html),
            published_at=self._safe_parse_datetime(self._extract_published_date_from_html(html)),
            site_name=self._extract_site_name_from_html(html, url),
            raw_file_path=raw_file_path,
        )

    def _fetch(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
        proxy = self.settings.proxy_url or None
        try:
            with httpx.Client(follow_redirects=True, timeout=20.0, proxy=proxy) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            raise ParsingError(f"Unable to fetch {url}: {exc}") from exc

    def _extract_title_from_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            return og_title["content"]
        title = soup.find("title")
        return title.get_text(strip=True) if title else ""

    def _extract_author_from_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        meta_names = ["author", "article:author", "parsely-author"]
        for name in meta_names:
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return tag["content"]
        return ""

    def _extract_published_date_from_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        meta_names = [
            "article:published_time",
            "publishdate",
            "pubdate",
            "datePublished",
            "parsely-pub-date",
        ]
        for name in meta_names:
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return tag["content"]
        json_ld_tags = soup.find_all("script", attrs={"type": "application/ld+json"})
        for tag in json_ld_tags:
            try:
                data = json.loads(tag.string or "{}")
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("datePublished"):
                return str(data["datePublished"])
        return ""

    def _extract_site_name_from_html(self, html: str, url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        og_site_name = soup.find("meta", attrs={"property": "og:site_name"})
        if og_site_name and og_site_name.get("content"):
            return og_site_name["content"]
        return httpx.URL(url).host or ""

    def _safe_parse_datetime(self, raw_value: str) -> datetime | None:
        if not raw_value:
            return None
        raw_value = raw_value.strip()
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None
