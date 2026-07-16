#!/usr/bin/env python3
"""Fetch article content and generate bilingual Markdown draft package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
X_DOMAINS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
STRUCTURED_SECTION_MARKERS = (
    "## 原英文标题",
    "## 原稿链接",
    "## 中文标题",
    "## 推荐公众号标题",
    "## 推荐摘要一句话",
    "## 正文翻译",
)
STRUCTURED_PLACEHOLDER = "（待补充）"
STRUCTURED_FRONTMATTER_FIELDS = (
    "original_title",
    "recommended_social_title",
    "summary",
)


@dataclass
class PipelineResult:
    article_id: str
    article_dir: Path
    source_path: Path
    translation_path: Path
    qa_path: Path
    handoff_path: Path | None
    agent_prompt_path: Path | None
    verdict: str
    resolved_translator: str


@dataclass
class ExtendConfig:
    source_language: str = "en"
    target_language: str = "zh-CN"
    audience: str = "技术行业女性专业读者"
    style: str = "专业、冷静、知性、利落"
    annotation_preference: str = "仅在文化背景或隐喻可能影响理解时补充简短解释"
    chunk_threshold: int = 6000
    max_chunk_chars: int = 6000
    glossary_overrides: list[tuple[str, str]] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="URL -> source.md + translation.md + assets + qa.json"
    )
    parser.add_argument("--url", help="Source article URL")
    parser.add_argument(
        "--resume-from",
        help="Resume from an existing article output directory",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Root directory for generated files. Defaults to the current repository's output/ directory.",
    )
    parser.add_argument(
        "--translator",
        choices=("auto", "gemini", "codex", "passthrough"),
        default="auto",
        help="Translation backend",
    )
    parser.add_argument(
        "--mode",
        choices=("quick", "standard", "deep"),
        default="deep",
        help="Translation workflow mode",
    )
    parser.add_argument("--gemini-api-key", default=os.getenv("GEMINI_API_KEY", ""))
    parser.add_argument(
        "--gemini-model",
        default=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    )
    parser.add_argument(
        "--gemini-endpoint",
        default=os.getenv(
            "GEMINI_ENDPOINT",
            "https://generativelanguage.googleapis.com/v1beta",
        ),
    )
    parser.add_argument("--max-images", type=int, default=30)
    parser.add_argument(
        "--max-chars",
        type=int,
        default=120_000,
        help="Hard cap for extracted source characters",
    )
    parser.add_argument(
        "--glossary",
        default=str(Path(__file__).resolve().parent.parent / "references" / "glossary.csv"),
    )
    parser.add_argument(
        "--prompt-file",
        default=str(
            Path(__file__).resolve().parent.parent / "references" / "women-stack-translator.md"
        ),
        help="Path to translator role/prompt file used in gemini mode",
    )
    parser.add_argument(
        "--extend-file",
        default=str(Path(__file__).resolve().parent.parent / "EXTEND.md"),
        help="Path to translation defaults and glossary override file",
    )
    args = parser.parse_args()
    if not args.url and not args.resume_from:
        parser.error("one of --url or --resume-from is required")
    return args


def fetch_url(url: str, timeout: int = 20) -> tuple[str, bytes]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:  # nosec: B310
        content_type = resp.headers.get("Content-Type", "")
        body = resp.read()
    return content_type, body


def fetch_json(url: str, timeout: int = 20) -> dict:
    content_type, raw = fetch_url(url, timeout=timeout)
    if "json" not in content_type.lower():
        raise ValueError(f"Expected JSON response from {url}, got: {content_type}")
    return json.loads(raw.decode("utf-8"))


def extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "Untitled"
    title = clean_text(match.group(1))
    return title or "Untitled"


def strip_html_tags(html: str) -> str:
    html = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p\s*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</h[1-6]\s*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    return clean_text(html)


def html_anchor_to_markdown(match: re.Match[str], base_url: str = "") -> str:
    tag = match.group(0)
    href_match = re.search(r'href=["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
    inner_match = re.search(r">(.+)</a\s*>", tag, flags=re.IGNORECASE | re.DOTALL)
    label = clean_text(strip_html_tags(inner_match.group(1))) if inner_match else ""
    href = href_match.group(1).strip() if href_match else ""
    if not href:
        return label
    resolved_href = urljoin(base_url, href) if base_url else href
    if not re.match(r"^https?://", resolved_href, flags=re.IGNORECASE):
        return label or resolved_href
    if not label:
        label = resolved_href
    return f"[{label}]({resolved_href})"


def html_to_markdownish(html: str, base_url: str = "") -> str:
    text = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<a\b[^>]*>.*?</a\s*>",
        lambda match: html_anchor_to_markdown(match, base_url),
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</h([1-6])\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<h1[^>]*>", "# ", text, flags=re.IGNORECASE)
    text = re.sub(r"<h2[^>]*>", "## ", text, flags=re.IGNORECASE)
    text = re.sub(r"<h3[^>]*>", "### ", text, flags=re.IGNORECASE)
    text = re.sub(r"<h4[^>]*>", "#### ", text, flags=re.IGNORECASE)
    text = re.sub(r"<h5[^>]*>", "##### ", text, flags=re.IGNORECASE)
    text = re.sub(r"<h6[^>]*>", "###### ", text, flags=re.IGNORECASE)
    text = re.sub(r"<pre[^>]*><code[^>]*>", "\n\n```\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</code></pre>", "\n```\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<code[^>]*>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"</code>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_references_section(references: list[tuple[int, str, str]]) -> list[str]:
    if not references:
        return []
    lines = ["", "## 引用", ""]
    for index, label, url in references:
        lines.append(f"[{index}] {label}: {url}")
    return lines


def replace_links_with_citations(body: str) -> tuple[str, list[tuple[int, str, str]]]:
    if not body.strip():
        return body, []

    normalized = re.sub(
        r"<a\b[^>]*>.*?</a\s*>",
        html_anchor_to_markdown,
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )

    reference_numbers: dict[str, int] = {}
    references: list[tuple[int, str, str]] = []
    reference_labels: dict[str, str] = {}

    def replacement(match: re.Match[str]) -> str:
        label = clean_text(match.group(1))
        url = match.group(2).strip()
        if not re.match(r"^https?://", url, flags=re.IGNORECASE):
            return match.group(0)
        if url not in reference_numbers:
            reference_numbers[url] = len(reference_numbers) + 1
            reference_labels[url] = label or url
            references.append((reference_numbers[url], reference_labels[url], url))
        return f"{label or url}[{reference_numbers[url]}]"

    converted = re.sub(
        r"(?<!!)\[([^\]]+)\]\((https?://[^)\s]+)\)",
        replacement,
        normalized,
    )
    return converted, references


def extract_image_assets(html: str, base_url: str, max_images: int) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for match in re.finditer(
        r"<img[^>]*>",
        html,
        flags=re.IGNORECASE,
    ):
        tag = match.group(0)
        src_match = re.search(r"src=[\"']([^\"']+)[\"']", tag, flags=re.IGNORECASE)
        if not src_match:
            continue
        src = src_match.group(1).strip()
        if not src or src.startswith("data:"):
            continue
        full = urljoin(base_url, src)
        if any(asset["original_url"] == full for asset in assets):
            continue
        alt_match = re.search(r"alt=[\"']([^\"']*)[\"']", tag, flags=re.IGNORECASE)
        title_match = re.search(r"title=[\"']([^\"']*)[\"']", tag, flags=re.IGNORECASE)
        assets.append(
            {
                "original_url": full,
                "alt_text": alt_match.group(1).strip() if alt_match else "",
                "title_text": title_match.group(1).strip() if title_match else "",
            }
        )
        if len(assets) >= max_images:
            break
    return assets


def extract_body_html_fragment(html: str) -> str:
    article_match = re.search(
        r"<article\b[^>]*>.*?</article>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if article_match:
        return article_match.group(0)

    main_match = re.search(
        r"<main\b[^>]*>.*?</main>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if main_match:
        return main_match.group(0)

    return html


def clean_paragraph_lines(lines: list[str]) -> list[str]:
    noise_patterns = (
        "Subscribe",
        "Disclosures",
        "Colophon",
        "All Microsoft",
        "Official Microsoft Blog",
        "Check us out on RSS",
        "Created:",
        "Last modified:",
        "Previous:",
        "Next:",
        "Chapters in this guide",
        "Guides >",
        "Skip to content",
        "Skip to main content",
    )
    cleaned: list[str] = []
    for line in lines:
        stripped = clean_text(line)
        if not stripped:
            continue
        if stripped in {"Home", "Subscribe"}:
            continue
        if any(pattern in stripped for pattern in noise_patterns):
            continue
        if re.fullmatch(r"[0-9 ]{4,}", stripped):
            continue
        if re.fullmatch(r"[A-Za-z0-9-]+", stripped) and len(stripped) < 4:
            continue
        cleaned.append(stripped)
    return cleaned


def extract_simonwillison_article(html: str) -> tuple[str, str] | None:
    title = extract_title(html)
    text = html_to_markdownish(html, "https://simonwillison.net/")
    lines = clean_paragraph_lines(text.splitlines())
    if not lines:
        return None
    title_candidates = [
        "AI should help us produce better code",
        title.replace(" - Agentic Engineering Patterns - Simon Willison's Weblog", "").strip(),
    ]
    start_idx = 0
    for idx, line in enumerate(lines):
        if any(candidate and candidate == line for candidate in title_candidates):
            start_idx = idx
            break
    end_markers = (
        "This is a chapter from the guide",
        "Chapters in this guide",
        "Created:",
        "Last modified:",
        "Previous:",
        "Next:",
    )
    end_idx = len(lines)
    for idx, line in enumerate(lines[start_idx:], start=start_idx):
        if any(marker in line for marker in end_markers):
            end_idx = idx
            break
    lines = lines[start_idx:end_idx]
    lines = [
        line
        for line in lines
        if line not in {"Simon Willison’s Weblog", "# Simon Willison’s Weblog"}
    ]
    lines = [
        line
        for line in lines
        if "← Anti-patterns: things to avoid" not in line and "Red/green TDD →" not in line
    ]
    if lines and lines[0] == title:
        lines = lines[1:]
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        is_structural = line.startswith(("#", "- ", "```", "|"))
        if is_structural:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            paragraphs.append(line)
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current).strip())
    body = "\n\n".join(p for p in paragraphs if p).strip()
    return title, body


def extract_main_content(
    url: str,
    html: str,
    max_images: int,
) -> tuple[str, str, str, list[dict[str, str]]]:
    domain = urlparse(url).netloc.lower()
    body_html = extract_body_html_fragment(html)
    image_assets = extract_image_assets(body_html, url, max_images=max_images)
    if "simonwillison.net" in domain:
        extracted = extract_simonwillison_article(html)
        if extracted:
            title, body = extracted
            return title, body, "html_simonwillison", image_assets

    title = extract_title(html)
    markdownish = html_to_markdownish(body_html, url)
    lines = clean_paragraph_lines(markdownish.splitlines())
    body = "\n\n".join(lines).strip()
    return title, body, "html_generic", image_assets


def clean_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def paragraph_split(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def slugify_heading(text: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        slug = "untitled"
    return slug[:max_length].rstrip("-")


def is_heading_paragraph(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return stripped.startswith("#") or (stripped.isupper() and len(stripped.split()) <= 12)


def paragraph_kind(paragraph: str, in_code_block: bool) -> tuple[str, bool]:
    stripped = paragraph.strip()
    fence_count = stripped.count("```")
    if in_code_block:
        return "code", fence_count % 2 == 1
    if stripped.startswith("```"):
        return "code", fence_count % 2 == 1
    if is_heading_paragraph(stripped):
        return "heading", False
    if stripped.startswith(("- ", "* ", "+ ")):
        return "list", False
    if re.match(r"^\d+\.\s", stripped):
        return "list", False
    if stripped.startswith("|") and "|" in stripped[1:]:
        return "table", False
    if re.match(r"^[-:| ]{3,}$", stripped):
        return "table", False
    return "paragraph", False


def build_markdown_blocks(paragraphs: list[str]) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    in_code_block = False
    current_kind = ""
    current_start = 0
    current_heading = ""

    for idx, paragraph in enumerate(paragraphs):
        kind, toggles_code = paragraph_kind(paragraph, in_code_block)
        if kind == "heading":
            current_heading = paragraph.lstrip("# ").strip()

        should_merge = False
        if blocks:
            previous = blocks[-1]
            previous_kind = str(previous["kind"])
            if kind == previous_kind and kind in {"list", "table", "code"}:
                should_merge = True
            if previous_kind == "heading" and kind in {"paragraph", "list", "table", "code"}:
                should_merge = True

        if should_merge:
            blocks[-1]["paragraph_end"] = idx + 1
            blocks[-1]["text"] = str(blocks[-1]["text"]) + "\n\n" + paragraph
        else:
            blocks.append(
                {
                    "kind": kind,
                    "paragraph_start": idx + 1,
                    "paragraph_end": idx + 1,
                    "heading_hint": current_heading,
                    "text": paragraph,
                }
            )

        if toggles_code:
            in_code_block = not in_code_block

    return blocks


def load_extend_config(path: str) -> ExtendConfig:
    config = ExtendConfig(glossary_overrides=[])
    file_path = Path(path)
    if not file_path.exists():
        return config

    in_glossary_section = False
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            in_glossary_section = "glossary" in line.lower()
            continue
        if in_glossary_section and line.startswith("- ") and "->" in line:
            left, right = line[2:].split("->", 1)
            config.glossary_overrides.append((left.strip(), right.strip()))
            continue
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        key = key.strip()
        value = value.strip()
        if key == "source_language":
            config.source_language = value
        elif key == "target_language":
            config.target_language = value
        elif key == "audience":
            config.audience = value
        elif key == "style":
            config.style = value
        elif key == "annotation_preference":
            config.annotation_preference = value
        elif key == "chunk_threshold":
            config.chunk_threshold = int(value)
        elif key == "max_chunk_chars":
            config.max_chunk_chars = int(value)
    return config


def merge_glossary(
    base_glossary: list[tuple[str, str]],
    overrides: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    merged: dict[str, str] = {en: zh for en, zh in base_glossary}
    for en, zh in overrides:
        merged[en] = zh
    return list(merged.items())


def resolve_chunk_strategy(
    resolved_translator: str,
    extend_config: ExtendConfig,
) -> tuple[int, int]:
    if resolved_translator == "codex":
        return (
            max(extend_config.chunk_threshold, 18000),
            max(extend_config.max_chunk_chars, 18000),
        )
    if resolved_translator == "passthrough":
        return (
            max(extend_config.chunk_threshold, 24000),
            max(extend_config.max_chunk_chars, 24000),
        )
    return extend_config.chunk_threshold, extend_config.max_chunk_chars


def chunk_paragraphs(
    paragraphs: list[str],
    mode: str,
    chunk_threshold: int,
    max_chunk_chars: int,
) -> list[dict[str, object]]:
    if mode == "quick":
        return [{"chunk_id": "part_001", "paragraph_start": 1, "paragraph_end": len(paragraphs)}]
    if sum(len(paragraph) for paragraph in paragraphs) <= chunk_threshold:
        return [{"chunk_id": "part_001", "paragraph_start": 1, "paragraph_end": len(paragraphs)}]

    blocks = build_markdown_blocks(paragraphs)
    chunks: list[dict[str, object]] = []
    start = 1
    current_chars = 0
    current_heading = ""
    chunk_heading = ""

    for block in blocks:
        block_start = int(block["paragraph_start"])
        block_text = str(block["text"])
        block_heading = str(block.get("heading_hint") or current_heading)
        block_chars = len(block_text)

        should_split = block_start > start and current_chars + block_chars > max_chunk_chars
        if should_split:
            chunks.append(
                {
                    "chunk_id": f"part_{len(chunks) + 1:03d}",
                    "paragraph_start": start,
                    "paragraph_end": block_start - 1,
                    "heading_hint": chunk_heading,
                }
            )
            start = block_start
            current_chars = 0
            chunk_heading = ""

        if block_heading:
            current_heading = block_heading
            if not chunk_heading:
                chunk_heading = block_heading
        current_chars += block_chars + 2

    if blocks:
        chunks.append(
            {
                "chunk_id": f"part_{len(chunks) + 1:03d}",
                "paragraph_start": start,
                "paragraph_end": len(paragraphs),
                "heading_hint": chunk_heading or current_heading,
            }
        )

    return chunks


def extract_x_status_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in X_DOMAINS:
        return None
    match = re.search(r"/status/(\d+)", parsed.path)
    if not match:
        return None
    return match.group(1)


def extract_x_post_from_syndication(status_id: str) -> tuple[str, str, list[str]] | None:
    endpoint = f"https://cdn.syndication.twimg.com/tweet-result?id={status_id}&lang=en"
    try:
        obj = fetch_json(endpoint, timeout=20)
    except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    text = clean_text(str(obj.get("text") or ""))
    if not text:
        return None

    user = obj.get("user") or {}
    user_name = clean_text(str(user.get("name") or user.get("screen_name") or ""))
    title = f"{user_name} on X" if user_name else f"X post {status_id}"
    images: list[str] = []
    for photo in obj.get("photos") or []:
        photo_url = str(photo.get("url") or "").strip()
        if photo_url:
            images.append(photo_url)
    return title, text, images


def extract_x_post_from_fxtwitter(status_id: str) -> tuple[str, str, list[str]] | None:
    endpoint = f"https://api.fxtwitter.com/status/{status_id}"
    try:
        obj = fetch_json(endpoint, timeout=20)
    except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    tweet = obj.get("tweet") or {}
    text = clean_text(str(tweet.get("text") or tweet.get("raw_text") or ""))
    if not text:
        return None

    author = tweet.get("author") or {}
    author_name = clean_text(str(author.get("name") or author.get("screen_name") or ""))
    title = f"{author_name} on X" if author_name else f"X post {status_id}"

    images: list[str] = []
    media = tweet.get("media") or {}
    photos = media.get("photos") or []
    for photo in photos:
        photo_url = str(photo.get("url") or "").strip()
        if photo_url:
            images.append(photo_url)

    return title, text, images


def extract_x_post_from_oembed(url: str, status_id: str) -> tuple[str, str, list[str]] | None:
    endpoint = (
        "https://publish.twitter.com/oembed?url="
        + quote(url, safe="")
        + "&omit_script=true&dnt=true"
    )
    try:
        obj = fetch_json(endpoint, timeout=20)
    except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    html = str(obj.get("html") or "")
    if not html:
        return None
    text = clean_text(strip_html_tags(html))
    if not text:
        return None
    author = clean_text(str(obj.get("author_name") or ""))
    title = f"{author} on X" if author else f"X post {status_id}"
    return title, text, []


def extract_x_post(url: str) -> tuple[str, str, list[str], str] | None:
    status_id = extract_x_status_id(url)
    if not status_id:
        return None

    fxtwitter = extract_x_post_from_fxtwitter(status_id)
    if fxtwitter:
        title, text, images = fxtwitter
        return title, text, images, "x_fxtwitter"

    syndication = extract_x_post_from_syndication(status_id)
    if syndication:
        title, text, images = syndication
        return title, text, images, "x_syndication"

    oembed = extract_x_post_from_oembed(url, status_id)
    if oembed:
        title, text, images = oembed
        return title, text, images, "x_oembed"

    return None


def load_glossary(path: str) -> list[tuple[str, str]]:
    glossary: list[tuple[str, str]] = []
    file_path = Path(path)
    if not file_path.exists():
        return glossary
    with file_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            en = (row.get("en") or "").strip()
            zh = (row.get("zh") or "").strip()
            if en and zh:
                glossary.append((en, zh))
    return glossary


def apply_glossary(text: str, glossary: Iterable[tuple[str, str]]) -> str:
    out = text
    for en, zh in glossary:
        out = re.sub(rf"\b{re.escape(en)}\b", zh, out)
    return out


def load_prompt_file(path: str) -> str:
    prompt_path = Path(path)
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8").strip()


def resolve_translator(translator: str, gemini_api_key: str) -> str:
    if translator == "auto":
        return "gemini" if gemini_api_key else "codex"
    return translator


def infer_target_audience(domain: str, title: str) -> str:
    lowered = f"{domain} {title}".lower()
    if any(keyword in lowered for keyword in ("openai", "microsoft", "github", "developer", "engineering")):
        return "技术行业专业读者"
    return "泛科技读者"


def build_analysis(
    title: str,
    paragraphs: list[str],
    glossary: list[tuple[str, str]],
    domain: str,
    extend_config: ExtendConfig,
) -> str:
    body = "\n\n".join(paragraphs[:8])
    capitalized_terms = sorted(set(re.findall(r"\b[A-Z][A-Za-z0-9.+-]{1,}\b", body)))
    notable_terms = capitalized_terms[:12]
    glossary_lines = [f"- `{en}` -> `{zh}`" for en, zh in glossary[:12]]
    risk_lines = [
        "- 注意避免把英文隐喻逐字硬译成中文意象。",
        "- 注意保留作者语气中的判断、保留或情绪色彩。",
        "- 如遇产品名、人名、组织名，优先统一译法而不是局部优化。",
    ]
    structure = [
        f"- 标题：{title}",
        f"- 段落数：{len(paragraphs)}",
        f"- 源语言：{extend_config.source_language}",
        f"- 目标语言：{extend_config.target_language}",
        f"- 目标读者：{extend_config.audience or infer_target_audience(domain, title)}",
        f"- 文章来源域名：{domain}",
    ]
    term_lines = [f"- `{term}`" for term in notable_terms] or ["- 未识别出明显英文专有名词，翻译时按上下文判断。"]
    glossary_section = glossary_lines or ["- 当前未命中额外术语表，按通用技术写作处理。"]

    chunks = [
        "# Analysis",
        "",
        "## Structure",
        *structure,
        "",
        "## Terms",
        *term_lines,
        "",
        "## Glossary Decisions",
        *glossary_section,
        "",
        "## Translation Risks",
        *risk_lines,
        "",
        "## Style Guidance",
        f"- 采用 `{extend_config.style}` 风格重写，不保留英文句法痕迹。",
        "- 标题允许适度中文化，但不要偏离原意。",
        "- 当原文是观点表达时，优先传达作者意图，而不是逐词对应。",
        f"- 译注偏好：{extend_config.annotation_preference}",
    ]
    return "\n".join(chunks).strip() + "\n"


def build_shared_prompt(
    translator_prompt: str,
    analysis_text: str,
    mode: str,
    resolved_translator: str,
    extend_config: ExtendConfig,
) -> str:
    workflow_note = {
        "quick": "当前为 quick 模式：直接生成可读译文，不做额外审校。",
        "standard": "当前为 standard 模式：先完成统一风格译文，必要时为后续润色保留空间。",
        "deep": "当前为 deep 模式：请在忠实翻译基础上尽量减少翻译腔，为后续审校和润色阶段提供高质量初稿。",
    }[mode]
    prompt_sections = [
        "# Shared Translation Prompt",
        "",
        f"- Resolved translator: `{resolved_translator}`",
        f"- Workflow mode: `{mode}`",
        f"- Source language: `{extend_config.source_language}`",
        f"- Target language: `{extend_config.target_language}`",
        f"- Audience: `{extend_config.audience}`",
        f"- Style: `{extend_config.style}`",
        f"- {workflow_note}",
        "",
        "## Role Prompt",
        translator_prompt or "当前运行模式未调用外部翻译 API，使用 Codex 作为翻译执行者。",
        "",
        "## Analysis Context",
        analysis_text.strip(),
    ]
    return "\n".join(prompt_sections).strip() + "\n"


def extract_primary_source_title(title: str) -> str:
    if " - " in title:
        return title.split(" - ", 1)[0].strip() or title.strip()
    return title.strip()


def heuristic_translate_title(source_title: str) -> str:
    primary_title = extract_primary_source_title(source_title)
    lowered = primary_title.lower().strip()
    exact_map = {
        "ai should help us produce better code": "AI 应该帮助我们写出更好的代码",
        "avoiding taking on technical debt": "避免背上技术债",
        "coding agents can handle these for us": "编码代理可以替我们处理这些事",
        "ai tools let us consider more options": "AI 工具让我们能考虑更多选项",
        "embrace the compound engineering loop": "拥抱复利式工程循环",
    }
    if lowered in exact_map:
        return exact_map[lowered]

    translated = primary_title
    replacements = [
        ("AI", "AI"),
        ("LLM", "LLM"),
        ("OpenAI", "OpenAI"),
        ("Codex", "Codex"),
        ("technical debt", "技术债"),
        ("coding agents", "编码代理"),
        ("agentic engineering", "代理式工程"),
        ("engineering patterns", "工程模式"),
        ("better code", "更好的代码"),
        ("code quality", "代码质量"),
        ("prototype", "原型"),
        ("prototyping", "原型验证"),
        ("should help us", "应该帮助我们"),
        ("help us", "帮助我们"),
        ("produce", "写出"),
        ("avoid", "避免"),
        ("avoiding", "避免"),
        ("embrace", "拥抱"),
        ("with", "与"),
        ("for", "用于"),
    ]
    for english, chinese in replacements:
        translated = re.sub(english, chinese, translated, flags=re.IGNORECASE)
    translated = re.sub(r"\s+", " ", translated).strip(" -:")
    if re.fullmatch(r"[A-Za-z0-9 ,:;'\-()]+", translated):
        return f"{primary_title}（中文标题待润色）"
    return translated


def heuristic_social_title(source_title: str, source_text: str, chinese_title: str) -> str:
    lowered = f"{source_title}\n{source_text}".lower()
    if "technical debt" in lowered and "coding agent" in lowered:
        return "有了编码代理，我们更不该接受“将就的代码”"
    if "better code" in lowered and "ai" in lowered:
        return "AI 真正的价值，不是更快写代码，而是写出更好的代码"
    return chinese_title or heuristic_translate_title(source_title)


def heuristic_summary(source_title: str, source_text: str) -> str:
    lowered = f"{source_title}\n{source_text}".lower()
    if "technical debt" in lowered and "coding agent" in lowered:
        return "作者认为，编码代理最有价值的地方，在于降低重构、原型验证与质量改进的成本，让团队能在交付新功能的同时持续减少技术债。"
    if "better code" in lowered and "quality" in lowered:
        return "这篇文章的核心观点是：是否因为 AI 交付出更差的代码，不是命运，而是团队流程和质量标准的选择。"
    first_paragraph = paragraph_split(source_text)[1] if len(paragraph_split(source_text)) > 1 else ""
    if first_paragraph:
        clipped = re.sub(r"\s+", " ", first_paragraph).strip()
        clipped = clipped[:72].rstrip(" ,.;:")
        return f"本文围绕“{extract_primary_source_title(source_title)}”展开，重点讨论 {clipped}。"
    return f"本文围绕“{extract_primary_source_title(source_title)}”展开，讨论作者对技术实践与代码质量的判断。"


def build_structured_translation_body(
    source_title: str,
    source_url: str,
    body: str,
    chinese_title: str = "",
    social_title: str = "",
    summary: str = "",
) -> str:
    primary_title = extract_primary_source_title(source_title)
    translated_title = chinese_title.strip() or STRUCTURED_PLACEHOLDER
    recommended_title = social_title.strip() or STRUCTURED_PLACEHOLDER
    recommended_summary = summary.strip() or STRUCTURED_PLACEHOLDER
    translated_body = body.strip() or STRUCTURED_PLACEHOLDER
    sections = [
        "## 原英文标题",
        "",
        primary_title,
        "",
        "## 原稿链接",
        "",
        source_url,
        "",
        "## 中文标题",
        "",
        translated_title,
        "",
        "## 推荐公众号标题",
        "",
        recommended_title,
        "",
        "## 推荐摘要一句话",
        "",
        recommended_summary,
        "",
        "## 正文翻译",
        "",
        translated_body,
        "",
    ]
    return "\n".join(sections).strip()


def build_agent_handoff(
    article_dir: Path,
    source_path: Path,
    analysis_path: Path,
    shared_prompt_path: Path,
    chunk_sources_dir: Path,
    chunk_prompts_dir: Path,
    merged_path: Path,
    translation_path: Path,
    critique_path: Path,
    revision_path: Path,
    mode: str,
    resolved_translator: str,
    agent_execution_mode: str,
) -> str:
    lines = [
        "# Agent Handoff",
        "",
        f"- Resolved translator: `{resolved_translator}`",
        f"- Workflow mode: `{mode}`",
        f"- Agent execution mode: `{agent_execution_mode}`",
        "",
        "## Why This File Exists",
        "- This package still needs the current agent to finish the translation workflow.",
        "- Do not treat placeholder or passthrough Chinese output as final delivery.",
        "",
        "## Read First",
        f"- Source: `{source_path}`",
        f"- Analysis: `{analysis_path}`",
        f"- Shared prompt: `{shared_prompt_path}`",
        f"- Chunk sources: `{chunk_sources_dir}`",
        f"- Chunk prompts: `{chunk_prompts_dir}`",
        f"- Merged draft: `{merged_path}`",
        "",
        "## Required Edits",
    ]
    if agent_execution_mode == "single_article":
        lines.extend(
            [
                "- This article is short enough to be handled as a single article task.",
                "- You may work from the single chunk package as one coherent draft instead of managing multiple chunk handoffs.",
                f"- Rewrite `{translation_path.name}` into a complete Chinese translation while preserving frontmatter, headings, structure, source fields, and image placeholders/descriptions.",
                "- Follow the output format required by the shared prompt: original English title, source URL, Chinese title, recommended公众号标题, one-sentence summary, then the full正文翻译.",
                "- Keep all generated artifacts inside the current repository's `output/` directory unless the user explicitly requested a different `--output-dir`.",
            ]
        )
    else:
        lines.extend(
            [
                "- Complete each chunk draft under `04-drafts/` using the matching prompt file from `04-chunk-prompts/`.",
                f"- Rewrite `{translation_path.name}` into a complete Chinese translation while preserving frontmatter, headings, structure, source fields, and image placeholders/descriptions.",
                "- When assembling the final file, follow the shared prompt output format instead of delivering body text only.",
                "- Keep all generated artifacts inside the current repository's `output/` directory unless the user explicitly requested a different `--output-dir`.",
            ]
        )
    if mode == "deep":
        lines.extend(
            [
                f"- Review `{critique_path.name}` and rewrite `{revision_path.name}` into a publication-ready revised Chinese draft.",
                f"- After revision is ready, sync the final polished body back into `{translation_path.name}`.",
            ]
        )
    else:
        lines.append("- Ensure the final translation reads naturally in Chinese and is not simple sentence-by-sentence passthrough text.")
    lines.extend(
        [
            "",
            "## Completion Criteria",
            "- The Chinese body is fully translated rather than copied from the source.",
            "- Technical terms remain accurate and consistent with the analysis and glossary.",
            "- Markdown structure, frontmatter, source URL, fetched time, and local asset references remain intact.",
        ]
    )
    if mode == "deep":
        lines.append("- `07-revision.md` is no longer a placeholder and matches the final quality bar.")
    lines.extend(
        [
            "",
            "## Output Directory",
            f"- `{article_dir}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_agent_completion_prompt(
    source_path: Path,
    analysis_path: Path,
    shared_prompt_path: Path,
    chunk_sources_dir: Path,
    chunk_prompts_dir: Path,
    merged_path: Path,
    translation_path: Path,
    critique_path: Path,
    revision_path: Path,
    qa_path: Path,
    mode: str,
    agent_execution_mode: str,
) -> str:
    lines = [
        "# Agent Completion Prompt",
        "",
        "请接管当前翻译任务，并在本轮完成未结束的步骤。",
        f"- 执行模式：`{agent_execution_mode}`",
        "",
        "## 必读文件",
        f"- `{source_path}`",
        f"- `{analysis_path}`",
        f"- `{shared_prompt_path}`",
        f"- `{chunk_sources_dir}`",
        f"- `{chunk_prompts_dir}`",
        f"- `{merged_path}`",
        f"- `{translation_path}`",
    ]
    if mode == "deep":
        lines.extend(
            [
                f"- `{critique_path}`",
                f"- `{revision_path}`",
            ]
        )
    lines.extend(
        [
            f"- `{qa_path}`",
            "",
            "## 执行要求",
            "- 以 `00-source.md` 为准，完成忠实、自然、适合中文技术读者的全文翻译。",
            "- 保留 `translation.md` 的 frontmatter、标题层级、来源字段和本地图片链接，并保留图片占位与描述。",
            "- 若 chunk 源文里出现 Markdown 链接，先在 chunk 草稿中保留原始 Markdown 链接，不要手工改写成局部 `[1]`、`[2]` 这类引用编号；统一由最终 `translation.md` 渲染阶段生成全局引用。",
            "- 参考分析文件与共享提示词统一术语、语气和风格。",
            "- 严格遵守共享提示词中的输出格式：补全原英文标题、原稿链接、中文标题、推荐公众号标题、推荐摘要一句话、正文翻译。",
            "- 若未显式指定 `--output-dir`，所有产物都应保留在当前仓库的 `output/` 目录中。",
        ]
    )
    if agent_execution_mode == "single_article":
        lines.append("- 当前仅有一个 chunk，可按单篇文章直接完成翻译；仍可参考同名 `04-chunk-prompts/*.md` 保持流程一致。")
    else:
        lines.append("- 逐个完成 `04-drafts/` 下的 chunk 草稿，优先参考同名的 `04-chunk-prompts/*.md`。")
    if mode == "deep":
        lines.extend(
            [
                "- 结合 `06-critique.md` 修订 `07-revision.md`，让其成为最终润色后的正文。",
                "- 将修订后的最终正文同步回 `translation.md`，不要让两个文件内容失配。",
            ]
        )
    lines.extend(
        [
            "- chunk 草稿完成后，先运行 `python3 scripts/rebuild_from_chunk_drafts.py --article-dir <文章目录> --sync-revision` 重建 `05-merged.md`、`07-revision.md` 和 `translation.md`。",
            "- 完成后，把 `qa.json` 中的 `requires_agent_completion` 更新为 `false`。",
            "- 最后运行 `python3 scripts/finalize_agent_translation.py --article-dir <文章目录>` 完成 QA 收口。",
            "- 若当前内容仍是原文直出、占位稿或明显未完成，不得向用户宣称已完成。",
            "",
            "## 完成标志",
            "- `translation.md` 是完整中文稿。",
        ]
    )
    if mode == "deep":
        lines.append("- `07-revision.md` 是最终修订稿，且与 `translation.md` 正文一致。")
    lines.extend(
        [
            "- `qa.json` 不再标记需要 agent 接管。",
            "",
        ]
    )
    return "\n".join(lines)


def build_chunk_source_markdown(
    chunk: dict[str, object],
    paragraphs: list[str],
) -> str:
    start = int(chunk["paragraph_start"]) - 1
    end = int(chunk["paragraph_end"])
    heading_hint = str(chunk.get("heading_hint") or "未提供")
    lines = [
        f"# Source for {chunk['chunk_id']}",
        "",
        f"- Paragraph range: {start + 1}-{end}",
        f"- Heading hint: {heading_hint}",
        "",
    ]
    for idx, paragraph in enumerate(paragraphs[start:end], start=start + 1):
        lines.extend(
            [
                f"## Paragraph {idx}",
                "",
                paragraph,
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_chunk_translation_prompt(
    chunk: dict[str, object],
    analysis_text: str,
    shared_prompt: str,
    chunk_source_text: str,
    mode: str,
) -> str:
    lines = [
        f"# Translation Task for {chunk['chunk_id']}",
        "",
        "请严格按照以下上下文完成当前 chunk 的中文翻译。",
        "",
        "## Rules",
        "- 只翻译当前 chunk，不要补写不在原文中的内容。",
        "- 保留原有 Markdown 结构、标题层级、列表和引用格式。",
        "- 若原文里是 Markdown 链接，chunk 译文里继续保留 Markdown 链接；不要在单个 chunk 内自行改写成 `[1]`、`[2]` 这类局部引用编号。",
        "- 减少翻译腔，但不要牺牲忠实度。",
        "- 若原文存在明显笔误或编号跳跃，保留其事实并用自然中文表达。",
        "",
        f"## Workflow Mode",
        f"- `{mode}`",
        "",
        "## Analysis",
        analysis_text.strip(),
        "",
        "## Shared Prompt",
        shared_prompt.strip(),
        "",
        "## Chunk Source",
        chunk_source_text.strip(),
        "",
        "## Output Requirement",
        "- 只输出这个 chunk 的中文 Markdown 正文，不要解释。",
        "- 不要在 chunk 中补写整篇文章的标题、摘要或发布包装栏目；这些内容统一放到最终 `translation.md`。",
        "- chunk 内如保留了 Markdown 链接，最终重建 `translation.md` 时会自动转成全局统一的文末引用。",
        "",
    ]
    return "\n".join(lines)


def build_chunk_draft_stub(
    chunk: dict[str, object],
    chunk_source_text: str,
    resolved_translator: str,
) -> str:
    heading_hint = str(chunk.get("heading_hint") or "未提供")
    lines = [
        f"# Draft for {chunk['chunk_id']}",
        "",
        f"- Status: `needs_translation`",
        f"- Translator mode: `{resolved_translator}`",
        f"- Heading hint: {heading_hint}",
        "",
        "<!-- Replace the block below with the finalized Chinese translation for this chunk. -->",
        "",
        "## Chinese Draft",
        "",
    ]
    if resolved_translator == "passthrough":
        lines.extend(
            [
                "> Pipeline ran in passthrough mode. Replace this placeholder with Chinese translation.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "> Pipeline ran in codex mode. Translate the source chunk below into polished Chinese and overwrite this section.",
                "",
            ]
        )
    lines.extend(
        [
            "## Source Snapshot",
            "",
            chunk_source_text.strip(),
            "",
        ]
    )
    return "\n".join(lines)


def extract_chunk_draft_body(text: str) -> str:
    marker = "## Chinese Draft"
    source_marker = "## Source Snapshot"
    if marker not in text:
        return text.strip()
    after_marker = text.split(marker, 1)[1].lstrip()
    if source_marker in after_marker:
        return after_marker.split(source_marker, 1)[0].strip()
    return after_marker.strip()


def run_gemini_text_prompt(
    prompt: str,
    api_key: str,
    model: str,
    endpoint: str,
) -> str:
    if not api_key:
        raise ValueError("GEMINI API key is required for gemini translator mode")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{endpoint}/models/{model}:generateContent?key={api_key}"
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:  # nosec: B310
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    candidates = obj.get("candidates") or []
    if not candidates:
        raise ValueError(f"No candidates returned by Gemini: {obj}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise ValueError(f"Empty translation from Gemini: {obj}")
    return text


def translate_with_gemini(
    paragraph: str,
    api_key: str,
    model: str,
    endpoint: str,
    translator_prompt: str,
) -> str:
    prompt = (
        f"{translator_prompt}\n\n"
        "请将下面的英文技术段落翻译为简体中文，保持 Markdown 结构与技术术语准确。"
        "只输出译文正文，不要额外说明。\n\n"
        f"[Source Paragraph]\n{paragraph}"
    )
    return run_gemini_text_prompt(prompt, api_key, model, endpoint)


def cached_translate(
    paragraph: str,
    cache: dict[str, str],
    translator: str,
    api_key: str,
    model: str,
    endpoint: str,
    translator_prompt: str,
) -> str:
    key = hashlib.sha1(paragraph.encode("utf-8")).hexdigest()
    if key in cache:
        return cache[key]

    if translator in ("passthrough", "codex"):
        translated = paragraph
    else:
        translated = translate_with_gemini(
            paragraph,
            api_key,
            model,
            endpoint,
            translator_prompt,
        )

    cache[key] = translated
    return translated


def build_critique_text(source_text: str, translated_text: str) -> str:
    findings: list[str] = []
    evidence: list[str] = []
    revision_guidance: list[str] = []

    source_paragraphs = paragraph_split(source_text)
    translated_paragraphs = paragraph_split(translated_text)
    source_heading_items = [p.strip() for p in source_paragraphs if p.strip().startswith("#")]
    translated_heading_items = [p.strip() for p in translated_paragraphs if p.strip().startswith("#")]
    source_headings = len(source_heading_items)
    translated_headings = len(translated_heading_items)
    source_lists = len([line for line in source_text.splitlines() if line.strip().startswith(("- ", "* ", "+ "))])
    translated_lists = len(
        [line for line in translated_text.splitlines() if line.strip().startswith(("- ", "* ", "+ "))]
    )
    allowed_terms = {
        "AI",
        "API",
        "UI",
        "LLM",
        "OpenAI",
        "Codex",
        "Claude",
        "Gemini",
        "Redis",
        "Pull",
        "Request",
        "Compound",
        "Engineering",
        "Every",
        "Dan",
        "Shipper",
        "Kieran",
        "Klaassen",
        "Jules",
        "groups",
        "teams",
    }
    english_tokens = re.findall(r"\b[A-Za-z][A-Za-z-]{1,}\b", translated_text)
    suspicious_english = [
        token
        for token in english_tokens
        if token not in allowed_terms
        and token.lower() not in {"web"}
        # Treat plain title-cased alpha tokens as likely names/proper nouns.
        and not (token.isalpha() and token[:1].isupper() and token[1:].islower())
    ]
    if len(suspicious_english) >= 6:
        findings.append("- 译文中仍保留较多英文片段，可能存在未充分本地化的内容。")
        samples = ", ".join(sorted(dict.fromkeys(suspicious_english))[:8])
        evidence.append(f"- 英文残留示例：`{samples}`")
        revision_guidance.append("- 区分专有名词与可翻译表达；对非必要英文词组优先改写为自然中文。")
    if "..." in translated_text or "……" in translated_text:
        findings.append("- 译文包含省略处理，需确认是否保留了原文完整信息。")
        evidence.append("- 检测到省略号标记。")
        revision_guidance.append("- 复核省略号所在句，确保没有压缩掉原文论证或语气。")
    long_lines = [line.strip() for line in translated_text.splitlines() if len(line.strip()) > 120]
    if long_lines:
        findings.append("- 译文中存在较长句或长段，读感可能偏紧。")
        evidence.append(f"- 长句示例：`{long_lines[0][:100]}`")
        revision_guidance.append("- 将长句拆成 2 到 3 个短句，优先保留判断关系和转折力度。")
    awkward_markers = [
        "围绕",
        "展开",
        "进行了",
        "进行",
        "对于",
        "基于",
        "使得",
        "从而",
        "进而",
        "将",
        "转化为",
        "本质上",
        "值得注意的是",
    ]
    awkward_lines = [
        line.strip()
        for line in translated_text.splitlines()
        if line.strip() and sum(marker in line for marker in awkward_markers) >= 2
    ]
    if awkward_lines:
        findings.append("- 译文中有些句子带有明显翻译腔，中文单读时会觉得拧巴。")
        evidence.append(f"- 可疑句示例：`{awkward_lines[0][:100]}`")
        revision_guidance.append("- 优先把抽象名词改成动作表达，删掉不必要的连接词，按中文母语语序重写。")
    nouny_patterns = ("性。", "化。", "度。", "感。")
    nouny_lines = [
        line.strip()
        for line in translated_text.splitlines()
        if line.strip() and sum(line.count(pattern) for pattern in nouny_patterns) >= 3
    ]
    if nouny_lines:
        findings.append("- 个别句子名词化偏重，信息虽然准确，但读起来发空。")
        evidence.append(f"- 名词化示例：`{nouny_lines[0][:100]}`")
        revision_guidance.append("- 把抽象结论还原成具体动作、判断或结果，避免连续堆叠“性/化/度/感”。")
    if source_text.strip() == translated_text.strip():
        findings.append("- 当前译文与原文几乎一致，说明尚未完成真正翻译。")
        evidence.append("- `05-merged.md` 与源文高度相同。")
        revision_guidance.append("- 先完成全文翻译，再进入润色和结构校对。")
    if translated_headings < source_headings or (source_headings > 0 and translated_headings == 0):
        findings.append("- 译文标题层级数量与原文不一致，需检查结构是否完整保留。")
        evidence.append(f"- 原文标题数：{source_headings}；译文标题数：{translated_headings}")
        if source_heading_items:
            evidence.append(f"- 原文标题示例：`{source_heading_items[0]}`")
        if translated_heading_items:
            evidence.append(f"- 译文标题示例：`{translated_heading_items[0]}`")
        revision_guidance.append("- 对齐标题层级和标题数量；若主标题只出现在 frontmatter 或外层文件，也应确认正文层次是否完整。")
    if source_lists != translated_lists:
        findings.append("- 译文项目符号数量与原文不一致，需检查列表内容是否遗漏或被并段。")
        evidence.append(f"- 原文列表项：{source_lists}；译文列表项：{translated_lists}")
        revision_guidance.append("- 对照原文列表逐项核对，避免把枚举项改写成普通段落。")
    if not findings:
        findings.append("- 未发现明显结构性问题，当前译文已具备进入人工润色阶段的基础。")
        evidence.append(f"- 标题数对齐：{source_headings} -> {translated_headings}")
        evidence.append(f"- 列表项对齐：{source_lists} -> {translated_lists}")
        revision_guidance.append("- 优先检查标题中文化是否充分，以及个别专有名词的保留是否有必要。")
        revision_guidance.append("- 逐段通读一遍，重点优化节奏感、判断句力度，以及“只看中文是否顺口”。")

    chunks = [
        "# Critique",
        "",
        "## Findings",
        *findings,
        "",
        "## Evidence",
        *evidence,
        "",
        "## Revision Guidance",
        *revision_guidance,
        "- 检查术语是否全篇一致。",
        "- 检查隐喻是否按中文语义重写，而不是逐字硬译。",
        "- 检查是否保留原文中的情感色彩、判断语气和重点。",
        "- 忘掉英文原文再读一遍中文；凡是需要脑中回译才能顺的句子，都应重写。",
    ]
    return "\n".join(chunks).strip() + "\n"


def critique_with_gemini(
    source_text: str,
    translated_text: str,
    analysis_text: str,
    api_key: str,
    model: str,
    endpoint: str,
) -> str:
    prompt = (
        "你是一名中文技术翻译审校编辑。请根据原文、译文和分析说明输出一份审校报告。"
        "重点检查：遗漏、误译、术语不一致、隐喻直译、情绪色彩丢失、翻译腔。"
        "请使用 Markdown 输出，包含 `# Critique`、`## Findings`、`## Revision Guidance` 三部分。\n\n"
        f"[Analysis]\n{analysis_text}\n\n"
        f"[Source]\n{source_text}\n\n"
        f"[Translation]\n{translated_text}\n"
    )
    return run_gemini_text_prompt(prompt, api_key, model, endpoint)


def revise_with_gemini(
    source_text: str,
    translated_text: str,
    analysis_text: str,
    critique_text: str,
    api_key: str,
    model: str,
    endpoint: str,
) -> str:
    prompt = (
        "你是一名中文技术翻译编辑。请参考原文、分析说明和审校意见，对译文进行修订。"
        "要求：忠实、自然、减少翻译腔，保留技术术语准确性。"
        "只输出修订后的中文正文，不要输出解释。\n\n"
        f"[Analysis]\n{analysis_text}\n\n"
        f"[Critique]\n{critique_text}\n\n"
        f"[Source]\n{source_text}\n\n"
        f"[Current Translation]\n{translated_text}\n"
    )
    return run_gemini_text_prompt(prompt, api_key, model, endpoint)


def save_bytes(url: str, content: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def ext_from_content_type(content_type: str) -> str:
    content_type = content_type.lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    return ".jpg"


def download_images(image_urls: list[str], assets_dir: Path) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for idx, image_item in enumerate(image_urls, start=1):
        if isinstance(image_item, dict):
            image_url = str(image_item.get("original_url") or "").strip()
            alt_text = str(image_item.get("alt_text") or "").strip()
            title_text = str(image_item.get("title_text") or "").strip()
        else:
            image_url = str(image_item).strip()
            alt_text = ""
            title_text = ""
        if not image_url:
            continue
        try:
            content_type, body = fetch_url(image_url, timeout=20)
            ext = ext_from_content_type(content_type)
            filename = f"img_{idx:03d}{ext}"
            path = assets_dir / filename
            save_bytes(image_url, body, path)
            assets.append(
                {
                    "original_url": image_url,
                    "local_path": f"./assets/{filename}",
                    "alt_text": alt_text,
                    "title_text": title_text,
                    "bytes": str(len(body)),
                }
            )
        except (URLError, HTTPError, TimeoutError):
            continue
    return assets


def frontmatter(meta: dict[str, str]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        escaped = str(value).replace('"', '\\"')
        lines.append(f'{key}: "{escaped}"')
    lines.append("---")
    return "\n".join(lines)


def render_markdown(
    meta: dict[str, str],
    heading: str,
    body: str,
    assets: list[dict[str, str]],
) -> str:
    rendered_body, references = replace_links_with_citations(body)
    chunks = [frontmatter(meta), "", f"# {heading}", "", rendered_body, ""]
    has_inline_assets = bool(re.search(r"!\[.*?\]\(\.?/assets/[^)]+\)", rendered_body))
    if assets and not has_inline_assets:
        chunks.append("## Images")
        chunks.append("")
        for idx, item in enumerate(assets, start=1):
            caption = str(item.get("alt_text") or "").strip() or str(item.get("title_text") or "").strip()
            if not caption:
                caption = f"图片 {idx}"
            chunks.append(f'![{caption}]({item["local_path"]})')
            chunks.append("")
            chunks.append(f"*图片说明：{caption or '待补充'}*")
            chunks.append("")
        chunks.append("")
    chunks.extend(render_references_section(references))
    if references:
        chunks.append("")
    chunks.append(f'Original URL: {meta["source_url"]}')
    return "\n".join(chunks).strip() + "\n"


def render_translation_markdown(
    meta: dict[str, str],
    source_title: str,
    source_text: str,
    body: str,
    assets: list[dict[str, str]],
    *,
    structured_output: bool,
    chinese_title: str = "",
    social_title: str = "",
    summary: str = "",
) -> str:
    if structured_output:
        generated_chinese_title = chinese_title.strip() or heuristic_translate_title(source_title)
        generated_social_title = social_title.strip() or heuristic_social_title(
            source_title,
            source_text,
            generated_chinese_title,
        )
        generated_summary = summary.strip() or heuristic_summary(source_title, source_text)
        heading = generated_chinese_title or extract_primary_source_title(source_title)
        structured_meta = dict(meta)
        structured_meta["title"] = heading
        structured_meta["original_title"] = extract_primary_source_title(source_title)
        structured_meta["recommended_social_title"] = generated_social_title
        structured_meta["summary"] = generated_summary
        return render_markdown(structured_meta, heading, body.strip(), assets)
    heading = chinese_title.strip() or source_title
    return render_markdown(meta, heading, body, assets)


def read_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text
    frontmatter_block = parts[1]
    body = parts[2].lstrip("\n")
    meta: dict[str, str] = {}
    for line in frontmatter_block.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, body


def load_resume_context(article_dir: Path) -> dict[str, object]:
    source_path = article_dir / "00-source.md"
    translation_path = article_dir / "translation.md"
    if not source_path.exists():
        source_path = article_dir / "en.md"
    if not translation_path.exists():
        translation_path = article_dir / "zh.md"
    analysis_path = article_dir / "01-analysis.md"
    shared_prompt_path = article_dir / "02-shared-prompt.md"
    merged_path = article_dir / "05-merged.md"
    chunks_path = article_dir / "03-chunks.json"
    for required in (source_path, translation_path, analysis_path, shared_prompt_path, merged_path, chunks_path):
        if not required.exists():
            raise FileNotFoundError(f"Resume file not found: {required}")

    en_meta, en_body = read_frontmatter(source_path)
    _, zh_body = read_frontmatter(translation_path)
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    return {
        "article_id": str(en_meta.get("article_id") or article_dir.name),
        "source_url": str(en_meta.get("source_url") or ""),
        "source_domain": str(en_meta.get("source_domain") or ""),
        "fetched_at": str(en_meta.get("fetched_at") or ""),
        "content_type": str(en_meta.get("content_type") or ""),
        "title": str(en_meta.get("title") or "Untitled"),
        "en_body": en_body.strip(),
        "zh_body": zh_body.strip(),
        "analysis_text": analysis_path.read_text(encoding="utf-8").strip(),
        "shared_prompt": shared_prompt_path.read_text(encoding="utf-8").strip(),
        "merged_text": merged_path.read_text(encoding="utf-8").strip(),
        "chunks": chunks,
        "source_path": source_path,
        "translation_path": translation_path,
    }


def build_article_dir(article_id: str, title: str, output_dir: str) -> Path:
    suffix = article_id.removeprefix("art_")
    dir_name = f"{slugify_heading(title)}-{suffix}"
    return resolve_output_dir(output_dir) / dir_name


def resolve_output_dir(output_dir: str) -> Path:
    output_path = Path(output_dir).expanduser()
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    return output_path.resolve()


def run_pipeline(args: argparse.Namespace) -> PipelineResult:
    if args.resume_from:
        article_dir = Path(args.resume_from).resolve()
        resume = load_resume_context(article_dir)
        article_id = str(resume["article_id"])
        assets_dir = article_dir / "assets"
        drafts_dir = article_dir / "04-drafts"
        chunk_sources_dir = article_dir / "04-chunk-sources"
        chunk_prompts_dir = article_dir / "04-chunk-prompts"
        article_dir.mkdir(parents=True, exist_ok=True)
        drafts_dir.mkdir(parents=True, exist_ok=True)
        chunk_sources_dir.mkdir(parents=True, exist_ok=True)
        chunk_prompts_dir.mkdir(parents=True, exist_ok=True)
    else:
        article_id = "art_" + hashlib.sha1(args.url.encode("utf-8")).hexdigest()[:12]
        article_dir = None
        assets_dir = None
        drafts_dir = None
        chunk_sources_dir = None
        chunk_prompts_dir = None

    extraction_method = "resume" if args.resume_from else "html"
    if args.resume_from:
        title = str(resume["title"])
        content_type = str(resume["content_type"])
        domain = str(resume["source_domain"])
        now_iso = str(resume["fetched_at"])
        en_text = str(resume["en_body"])
        paragraphs = paragraph_split(en_text)
        image_urls = []
        assets = []
    else:
        x_extract = extract_x_post(args.url)
        if x_extract:
            title, plain, image_urls, extraction_method = x_extract
            content_type = "application/x-x-post+json"
            paragraphs = paragraph_split(plain[: args.max_chars])
        else:
            content_type, raw = fetch_url(args.url)
            html = raw.decode("utf-8", errors="ignore")
            title, plain, extraction_method, image_urls = extract_main_content(
                args.url,
                html,
                args.max_images,
            )
            plain = plain[: args.max_chars]
            paragraphs = paragraph_split(plain)
        article_dir = build_article_dir(article_id, title, args.output_dir)
        assets_dir = article_dir / "assets"
        drafts_dir = article_dir / "04-drafts"
        chunk_sources_dir = article_dir / "04-chunk-sources"
        chunk_prompts_dir = article_dir / "04-chunk-prompts"
        article_dir.mkdir(parents=True, exist_ok=True)
        drafts_dir.mkdir(parents=True, exist_ok=True)
        chunk_sources_dir.mkdir(parents=True, exist_ok=True)
        chunk_prompts_dir.mkdir(parents=True, exist_ok=True)
        assets = download_images(image_urls, assets_dir)
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        domain = urlparse(args.url).netloc
    extend_config = load_extend_config(args.extend_file)
    glossary = merge_glossary(
        load_glossary(args.glossary),
        extend_config.glossary_overrides or [],
    )
    resolved_translator = resolve_translator(args.translator, args.gemini_api_key)
    chunk_threshold, max_chunk_chars = resolve_chunk_strategy(resolved_translator, extend_config)
    translator_prompt = ""
    if resolved_translator == "gemini":
        translator_prompt = load_prompt_file(args.prompt_file)

    meta_common = {
        "article_id": article_id,
        "source_url": str(resume["source_url"]) if args.resume_from else args.url,
        "source_domain": domain,
        "fetched_at": now_iso,
        "content_type": content_type,
    }

    if not args.resume_from:
        en_text = "\n\n".join(paragraphs)
    en_markdown = render_markdown(
        {**meta_common, "lang": "en", "title": title},
        title,
        en_text,
        assets,
    )
    source_path = article_dir / "00-source.md"
    if not args.resume_from:
        source_path.write_text(en_markdown, encoding="utf-8")

    analysis_path = article_dir / "01-analysis.md"
    if args.resume_from:
        analysis_text = str(resume["analysis_text"])
    else:
        analysis_text = build_analysis(title, paragraphs, glossary, domain, extend_config)
        analysis_path.write_text(analysis_text, encoding="utf-8")

    shared_prompt_path = article_dir / "02-shared-prompt.md"
    if args.resume_from:
        shared_prompt = str(resume["shared_prompt"])
    else:
        shared_prompt = build_shared_prompt(
            translator_prompt=translator_prompt or load_prompt_file(args.prompt_file),
            analysis_text=analysis_text,
            mode=args.mode,
            resolved_translator=resolved_translator,
            extend_config=extend_config,
        )
        shared_prompt_path.write_text(shared_prompt, encoding="utf-8")

    chunks_path = article_dir / "03-chunks.json"
    if args.resume_from:
        chunks = list(resume["chunks"])
    else:
        chunks = chunk_paragraphs(
            paragraphs,
            args.mode,
            chunk_threshold,
            max_chunk_chars,
        )
        chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    agent_execution_mode = "single_article" if len(chunks) == 1 else "chunked"

    cache_path = article_dir / "translation_cache.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        cache = {}

    merged_path = article_dir / "05-merged.md"
    if args.resume_from:
        zh_text = str(resume["merged_text"])
        zh_paragraphs = paragraph_split(zh_text)
    else:
        zh_paragraphs: list[str] = []
        for chunk in chunks:
            start = int(chunk["paragraph_start"]) - 1
            end = int(chunk["paragraph_end"])
            chunk_source_text = build_chunk_source_markdown(chunk, paragraphs)
            chunk_source_path = chunk_sources_dir / f"{chunk['chunk_id']}.md"
            chunk_source_path.write_text(chunk_source_text, encoding="utf-8")
            translated_chunk: list[str] = []
            if resolved_translator in {"codex", "passthrough"}:
                chunk_prompt_text = build_chunk_translation_prompt(
                    chunk=chunk,
                    analysis_text=analysis_text,
                    shared_prompt=shared_prompt,
                    chunk_source_text=chunk_source_text,
                    mode=args.mode,
                )
                chunk_prompt_path = chunk_prompts_dir / f"{chunk['chunk_id']}.md"
                chunk_prompt_path.write_text(chunk_prompt_text, encoding="utf-8")
                chunk_text = build_chunk_draft_stub(
                    chunk=chunk,
                    chunk_source_text=chunk_source_text,
                    resolved_translator=resolved_translator,
                )
            else:
                for idx, p in enumerate(paragraphs[start:end], start=start + 1):
                    translated = cached_translate(
                        p,
                        cache,
                        resolved_translator,
                        args.gemini_api_key,
                        args.gemini_model,
                        args.gemini_endpoint,
                        translator_prompt,
                    )
                    translated_chunk.append(translated)
                    zh_paragraphs.append(translated)
                    if idx % 8 == 0:
                        time.sleep(0.2)
                chunk_text = "\n\n".join(translated_chunk).strip() + "\n"
            draft_path = drafts_dir / f"{chunk['chunk_id']}.md"
            draft_path.write_text(chunk_text, encoding="utf-8")
            if resolved_translator in {"codex", "passthrough"}:
                zh_paragraphs.append(extract_chunk_draft_body(chunk_text))
        zh_text = apply_glossary("\n\n".join(part for part in zh_paragraphs if part.strip()), glossary)
        merged_path.write_text(zh_text.strip() + "\n", encoding="utf-8")
    critique_path = article_dir / "06-critique.md"
    revision_path = article_dir / "07-revision.md"
    handoff_path = article_dir / "08-agent-handoff.md"
    agent_prompt_path = article_dir / "09-agent-completion-prompt.md"
    final_body = zh_text
    if args.mode == "deep":
        if resolved_translator == "gemini":
            critique_text = critique_with_gemini(
                source_text=en_text,
                translated_text=zh_text,
                analysis_text=analysis_text,
                api_key=args.gemini_api_key,
                model=args.gemini_model,
                endpoint=args.gemini_endpoint,
            )
            revised_text = revise_with_gemini(
                source_text=en_text,
                translated_text=zh_text,
                analysis_text=analysis_text,
                critique_text=critique_text,
                api_key=args.gemini_api_key,
                model=args.gemini_model,
                endpoint=args.gemini_endpoint,
            )
            final_body = apply_glossary(revised_text, glossary)
        else:
            critique_text = build_critique_text(en_text, zh_text)
            revised_text = zh_text
        critique_path.write_text(critique_text.strip() + "\n", encoding="utf-8")
        revision_path.write_text(revised_text.strip() + "\n", encoding="utf-8")

    zh_title = extract_primary_source_title(title)
    zh_markdown = render_translation_markdown(
        {**meta_common, "lang": "zh", "title": zh_title},
        source_title=title,
        source_text=en_text,
        body=final_body,
        assets=assets,
        structured_output=resolved_translator in {"codex", "passthrough"},
        chinese_title="",
        social_title="",
        summary="",
    )
    translation_path = article_dir / "translation.md"
    translation_path.write_text(zh_markdown, encoding="utf-8")
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    translated_paragraphs_count = len(paragraph_split(zh_text)) if zh_text.strip() else 0
    para_ratio = 0.0
    if paragraphs:
        para_ratio = translated_paragraphs_count / len(paragraphs)
    verdict = "ready"
    issues: list[str] = []
    error_page_markers = (
        "Something went wrong, but don’t fret",
        "Something went wrong, but don't fret",
        "Try again Some privacy related extensions may cause issues on x.com",
    )
    if any(marker in en_text for marker in error_page_markers):
        verdict = "needs_review"
        issues.append("Source appears to be an error/interstitial page instead of article body.")
    if para_ratio < 0.9:
        verdict = "needs_review"
        issues.append("Translated paragraph count is lower than source paragraph count.")
    if not zh_text.strip():
        verdict = "failed"
        issues.append("Translated content is empty.")
    if resolved_translator == "codex":
        verdict = "needs_review"
        issues.append(
            "No API key detected. The current agent must translate chunk drafts from 04-chunk-prompts/ and finalize translation.md before delivery."
        )
    if resolved_translator in {"codex", "passthrough"} and not zh_text.strip():
        verdict = "needs_review"
        issues.append("Merged draft is still empty because chunk draft stubs have not been completed yet.")
    if args.mode == "deep":
        if resolved_translator != "gemini":
            issues.append(
                "Deep mode created critique and revision scaffolding; the current agent must complete chunk drafts, finish revision.md, and sync the final body back to translation.md."
            )
        if verdict == "ready" and resolved_translator != "gemini":
            verdict = "needs_review"

    handoff_required = resolved_translator in {"codex", "passthrough"}
    if handoff_required:
        handoff_text = build_agent_handoff(
            article_dir=article_dir,
            source_path=source_path,
            analysis_path=analysis_path,
            shared_prompt_path=shared_prompt_path,
            chunk_sources_dir=chunk_sources_dir,
            chunk_prompts_dir=chunk_prompts_dir,
            merged_path=merged_path,
            translation_path=translation_path,
            critique_path=critique_path,
            revision_path=revision_path,
            mode=args.mode,
            resolved_translator=resolved_translator,
            agent_execution_mode=agent_execution_mode,
        )
        handoff_path.write_text(handoff_text, encoding="utf-8")
        agent_prompt_text = build_agent_completion_prompt(
            source_path=source_path,
            analysis_path=analysis_path,
            shared_prompt_path=shared_prompt_path,
            chunk_sources_dir=chunk_sources_dir,
            chunk_prompts_dir=chunk_prompts_dir,
            merged_path=merged_path,
            translation_path=translation_path,
            critique_path=critique_path,
            revision_path=revision_path,
            qa_path=article_dir / "qa.json",
            mode=args.mode,
            agent_execution_mode=agent_execution_mode,
        )
        agent_prompt_path.write_text(agent_prompt_text, encoding="utf-8")

    qa = {
        "article_id": article_id,
        "source_url": args.url,
        "extraction_method": extraction_method,
        "mode": args.mode,
        "translator_mode": args.translator,
        "resolved_translator": resolved_translator,
        "extend_file": str(Path(args.extend_file).resolve()),
        "prompt_file": str(Path(args.prompt_file).resolve()) if resolved_translator == "gemini" else "",
        "analysis_file": str(analysis_path),
        "shared_prompt_file": str(shared_prompt_path),
        "chunks_file": str(chunks_path),
        "chunk_sources_dir": str(chunk_sources_dir) if handoff_required else "",
        "chunk_prompts_dir": str(chunk_prompts_dir) if handoff_required else "",
        "merged_file": str(merged_path),
        "critique_file": str(critique_path) if args.mode == "deep" else "",
        "revision_file": str(revision_path) if args.mode == "deep" else "",
        "agent_handoff_file": str(handoff_path) if handoff_required else "",
        "agent_completion_prompt_file": str(agent_prompt_path) if handoff_required else "",
        "translation_file": str(translation_path),
        "agent_execution_mode": agent_execution_mode if handoff_required else "",
        "chunk_threshold": chunk_threshold,
        "max_chunk_chars": max_chunk_chars,
        "chunk_count": len(chunks),
        "source_paragraphs": len(paragraphs),
        "translated_paragraphs": translated_paragraphs_count,
        "image_count": len(assets),
        "requires_agent_completion": handoff_required,
        "verdict": verdict,
        "issues": issues,
    }
    qa_path = article_dir / "qa.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    return PipelineResult(
        article_id,
        article_dir,
        source_path,
        translation_path,
        qa_path,
        handoff_path if handoff_required else None,
        agent_prompt_path if handoff_required else None,
        verdict,
        resolved_translator,
    )


def main() -> int:
    args = parse_args()
    try:
        result = run_pipeline(args)
    except Exception as exc:  # pylint: disable=broad-except
        sys.stderr.write(f"Pipeline failed: {exc}\n")
        return 1

    summary = textwrap.dedent(
        f"""
        article_id: {result.article_id}
        output_dir: {result.article_dir}
        source_markdown: {result.source_path}
        translation_markdown: {result.translation_path}
        qa_report: {result.qa_path}
        agent_handoff: {result.handoff_path or ""}
        agent_completion_prompt: {result.agent_prompt_path or ""}
        verdict: {result.verdict}
        resolved_translator: {result.resolved_translator}
        """
    ).strip()
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
