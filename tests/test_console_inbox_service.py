import pytest
from app.services.console_inbox_service import ConsoleInboxService
from app.services.link_archive_service import ArchiveRunError


def test_console_inbox_append_list_delete_and_conflict(tmp_path):
    (tmp_path/"inbox").mkdir(); (tmp_path/"inbox"/"links.md").write_text("# Inbox\n",encoding="utf-8")
    service=ConsoleInboxService(tmp_path)
    snap=service.append("说明 https://example.com/a")
    assert snap["pending_url_count"]==1 and snap["items"][-1]["status"]=="pending"
    with pytest.raises(ArchiveRunError): service.delete(snap["items"][-1]["item_id"],"stale")
    latest=service.snapshot(); result=service.delete(latest["items"][-1]["item_id"],latest["version"])
    assert result["pending_url_count"]==0
    assert (tmp_path/"inbox"/".links.md.bak").exists()

def test_append_keeps_each_text_paste_atomic_and_separates_url_list(tmp_path):
    (tmp_path/"inbox").mkdir(); (tmp_path/"inbox"/"links.md").write_text("",encoding="utf-8")
    service=ConsoleInboxService(tmp_path)
    text=service.append("第一段文字\n\n第二段文字\nhttps://example.com/in-text")
    assert len(text["items"]) == 1
    assert "第一段文字 第二段文字 https://example.com/in-text" == text["items"][0]["content"]

    links=service.append("https://example.com/a\nhttps://example.com/b")
    assert [item["urls"] for item in links["items"][-2:]] == [["https://example.com/a"],["https://example.com/b"]]
    raw=(tmp_path/"inbox"/"links.md").read_text(encoding="utf-8")
    assert "https://example.com/a\n\nhttps://example.com/b" in raw

def test_batch_delete_is_single_version_checked_transaction(tmp_path):
    (tmp_path/"inbox").mkdir(); (tmp_path/"inbox"/"links.md").write_text("https://a.example\n\nhttps://b.example\n\nhttps://c.example\n",encoding="utf-8")
    service=ConsoleInboxService(tmp_path); snap=service.snapshot()
    result=service.delete_many([snap["items"][0]["item_id"],snap["items"][2]["item_id"]],snap["version"])
    assert len(result["items"]) == 1
    assert result["items"][0]["urls"] == ["https://b.example"]
    with pytest.raises(ArchiveRunError): service.delete_many([result["items"][0]["item_id"]],snap["version"])
