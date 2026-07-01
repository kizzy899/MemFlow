from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "from",
    "share_from",
    "share_source",
    "timestamp",
    "fbclid",
    "gclid",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("content must be a valid HTTP(S) URL")

    netloc = f"[{hostname}]" if ":" in hostname else hostname
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_PARAMETERS
    ]
    query.sort()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?，。；：！？、)]}）】》"


def extract_first_url(text: str | None) -> str | None:
    """Return the first HTTP(S) URL in pasted text without sentence punctuation."""
    match = _URL_PATTERN.search(text or "")
    if not match:
        return None
    value = match.group(0).rstrip(_URL_TRAILING_PUNCTUATION)
    return value or None
