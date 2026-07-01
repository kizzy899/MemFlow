from app.utils.content_identity import content_hash, extract_first_url, normalize_text, normalize_url


def test_normalize_url_removes_tracking_and_sorts_query() -> None:
    result = normalize_url(
        "HTTPS://Example.COM:443/path?utm_source=x&b=2&a=1&share_source=y#section"
    )
    assert result == "https://example.com/path?a=1&b=2"


def test_text_hash_uses_collapsed_whitespace() -> None:
    assert normalize_text(" hello\n  world ") == "hello world"
    assert content_hash("hello world") == content_hash(" hello\n  world ")

def test_extract_first_url_trims_sentence_punctuation() -> None:
    assert extract_first_url("正文 https://xhslink.com/o/abc。 后文") == "https://xhslink.com/o/abc"
    assert extract_first_url("没有链接") is None

def test_normalize_url_removes_click_ids_and_trailing_slash() -> None:
    assert normalize_url("https://EXAMPLE.com/path/?fbclid=x&gclid=y&keep=1") == "https://example.com/path?keep=1"
    assert normalize_url("https://example.com/") == "https://example.com/"
