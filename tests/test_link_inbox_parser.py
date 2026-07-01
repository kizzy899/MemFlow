from app.services.link_archive_service import FAILURE_PREFIX, parse_inbox, render_inbox


def test_parse_url_lines_and_paragraphs():
    blocks = parse_inbox("https://a.example/x\nhttps://b.example/y\n\n说明文字 https://c.example/z。\n下一行\n")
    assert [block.urls for block in blocks] == [["https://a.example/x"], ["https://b.example/y"], ["https://c.example/z"]]
    assert "下一行" in blocks[2].source_text


def test_failure_annotation_is_replaced_not_duplicated():
    block = parse_inbox("正文 https://a.example/x\n> 处理失败：旧原因，时间：2025-01-01 00:00:00\n")[0]
    updated = block.with_failure("新原因", "2026-01-01 00:00:00")
    assert updated.text.count(FAILURE_PREFIX) == 1
    assert "新原因" in updated.text and "旧原因" not in updated.text
    assert updated.urls == ["https://a.example/x"]


def test_render_preserves_non_url_blocks():
    text = render_inbox(parse_inbox("# 标题\n\n普通说明\n"))
    assert "# 标题" in text and "普通说明" in text