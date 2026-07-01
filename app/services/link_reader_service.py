from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.services.web_parser_service import WebParserService


class LinkFetchError(Exception):
    pass


class LinkParseError(Exception):
    pass


@dataclass
class ReadableLink:
    original_url: str
    title: str
    content: str
    source_type: str
    author: str = ""
    site_name: str = ""


class LinkReaderService:
    def __init__(self, settings: Settings, web_parser: WebParserService) -> None:
        self.settings = settings
        self.web_parser = web_parser

    def read(self, url: str) -> ReadableLink:
        github = self._github_repo(url)
        if github:
            try:
                return self._read_github(url, *github)
            except LinkFetchError:
                pass
        if urlsplit(url).path.lower().endswith(".pdf"):
            return self._read_pdf(url)
        try:
            parsed = self.web_parser.parse_url(url)
        except Exception as exc:
            message = str(exc)
            if any(token in message.lower() for token in ("fetch", "timeout", "403", "404", "connection")):
                raise LinkFetchError(message) from exc
            raise LinkParseError(message) from exc
        if not parsed.content.strip():
            raise LinkParseError("正文为空")
        return ReadableLink(url, parsed.title, parsed.content, self._infer_source_type(url), parsed.author, parsed.site_name)

    def _client(self) -> httpx.Client:
        return httpx.Client(follow_redirects=True, timeout=30.0, proxy=self.settings.proxy_url or None)

    def _read_pdf(self, url: str) -> ReadableLink:
        try:
            with self._client() as client:
                response = client.get(url, headers={"User-Agent": "MemFlow/1.0"})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LinkFetchError(f"PDF 获取失败：{exc}") from exc
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(response.content))
            text = "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
        except Exception as exc:
            raise LinkParseError(f"PDF 解析失败：{exc}") from exc
        if not text:
            raise LinkParseError("PDF 正文为空")
        title = str((reader.metadata or {}).get("/Title") or urlsplit(url).path.rsplit("/", 1)[-1] or "PDF")
        return ReadableLink(url, title, text, "PDF")

    def _read_github(self, url: str, owner: str, repo: str) -> ReadableLink:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        try:
            with self._client() as client:
                response = client.get(api_url, headers={"Accept": "application/vnd.github.raw+json", "User-Agent": "MemFlow/1.0"})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LinkFetchError(f"GitHub README 获取失败：{exc}") from exc
        content = response.text.strip()
        if not content:
            raise LinkParseError("GitHub README 为空")
        return ReadableLink(url, f"{owner}/{repo}", content, "代码", site_name="GitHub")

    @staticmethod
    def _github_repo(url: str) -> tuple[str, str] | None:
        parts = urlsplit(url)
        if parts.hostname not in {"github.com", "www.github.com"}:
            return None
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) != 2:
            return None
        return segments[0], segments[1].removesuffix(".git")

    @staticmethod
    def _infer_source_type(url: str) -> str:
        host = (urlsplit(url).hostname or "").lower()
        if host in {"youtube.com", "www.youtube.com", "youtu.be", "bilibili.com", "www.bilibili.com"}:
            return "视频笔记"
        return "网页"