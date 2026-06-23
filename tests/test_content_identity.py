from app.utils.content_identity import content_hash, normalize_text, normalize_url


def test_normalize_url_removes_tracking_and_sorts_query() -> None:
    result = normalize_url(
        "HTTPS://Example.COM:443/path?utm_source=x&b=2&a=1&share_source=y#section"
    )
    assert result == "https://example.com/path?a=1&b=2"


def test_text_hash_uses_collapsed_whitespace() -> None:
    assert normalize_text(" hello\n  world ") == "hello world"
    assert content_hash("hello world") == content_hash(" hello\n  world ")
