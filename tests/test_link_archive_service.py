import json
import shutil
import uuid
import pytest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models.content_item import ContentItem, NotionSyncStatus
from app.services.ai_service import AnalysisResult
from app.services.item_service import ItemService
from app.services.link_archive_ai_service import ArchiveEnrichment, Concept, EntityGroups
from app.services.link_archive_service import LinkArchiveService
from app.services.link_reader_service import LinkFetchError, ReadableLink



@pytest.fixture
def archive_root():
    root = Path("data") / f"test-link-archive-{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)

class Reader:
    def __init__(self, failures=None): self.failures = set(failures or [])
    def read(self, url):
        if url in self.failures: raise LinkFetchError("403 forbidden")
        return ReadableLink(url, "Source", "正文内容足够用于测试", "网页")


class AI:
    def analyze(self, source_url, title, text):
        return AnalysisResult(title="归档标题", summary="第一句。第二句。第三句。", core_points=["观点一", "观点二", "观点三"], action_items=["执行建议"], content_type="article", category_level_1="AI", category_level_2="Agent开发", keywords=["AI", "Agent"], importance="high", original_language="zh-CN", is_translated=False)


class ArchiveAI:
    def enrich(self, title, content, candidates):
        return ArchiveEnrichment(key_concepts=[Concept(name="智能体", explanation="自动执行任务")], entities=EntityGroups(projects=["MemFlow"], tools=["Notion"]), knowledge_relations=[])


class Notion:
    def __init__(self, fail=False, duplicates=None): self.fail=fail; self.duplicates=set(duplicates or []); self.created=[]; self.schema_calls=0
    def ensure_archive_schema(self): self.schema_calls += 1
    def find_page_by_normalized_url(self, url): return {"id":"old", "url":"https://notion/old"} if url in self.duplicates else None
    def create_archive_page(self, item):
        if self.fail: raise RuntimeError("notion down")
        self.created.append(item.id); return "page", "https://notion/page"


def make_service(root: Path, notion=None, reader=None):
    notion = notion or Notion(); item_service = ItemService(notion)
    return LinkArchiveService(root, reader or Reader(), AI(), ArchiveAI(), item_service, notion), notion


def prepare(root: Path, text: str):
    (root / "inbox").mkdir(); (root / "inbox" / "links.md").write_text(text, encoding="utf-8")
    (root / "hot.md").write_text("人工内容\n\n<!-- MEMFLOW:HOT:BEGIN -->\n旧内容\n<!-- MEMFLOW:HOT:END -->\n", encoding="utf-8")


def test_success_deletes_block_updates_hot_backup_and_log(archive_root):
    prepare(archive_root, "备注 https://example.com/a?utm_source=x\n")
    service, notion = make_service(archive_root)
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db: data=service.run(db)
    assert data["processed"] == 1 and data["remaining"] == 0 and data["hot_updated"] is True
    assert (archive_root / "inbox" / "links.md").read_text(encoding="utf-8") == ""
    assert (archive_root / "inbox" / ".links.md.bak").exists()
    assert "人工内容" in (archive_root / "hot.md").read_text(encoding="utf-8")
    assert json.loads((archive_root / "logs" / "link-archive.jsonl").read_text(encoding="utf-8"))["status"] == "processed"


def test_fetch_failure_retains_block_and_replaces_failure(archive_root):
    url="https://example.com/fail"; prepare(archive_root, url+"\n")
    service, _ = make_service(archive_root, reader=Reader([url]))
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        first=service.run(db); second=service.run(db)
    text=(archive_root/"inbox"/"links.md").read_text(encoding="utf-8")
    assert first["failed_fetch"] == 1 and second["failed_fetch"] == 1
    assert url in text and text.count("> 处理失败：") == 1


def test_notion_duplicate_deletes_without_fetch(archive_root):
    url="https://example.com/already"; prepare(archive_root, url+"\n")
    service, _ = make_service(archive_root, notion=Notion(duplicates={url}), reader=Reader([url]))
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db: data=service.run(db)
    assert data["skipped_duplicate"] == 1 and data["remaining"] == 0


def test_multi_url_paragraph_is_atomic_on_partial_failure(archive_root):
    good="https://example.com/good"; bad="https://example.com/bad"; prepare(archive_root, f"一起阅读 {good} 和 {bad}\n")
    service, _ = make_service(archive_root, reader=Reader([bad]))
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db: data=service.run(db)
    text=(archive_root/"inbox"/"links.md").read_text(encoding="utf-8")
    assert data["processed"] == 1 and data["failed_fetch"] == 1
    assert good in text and bad in text


def test_notion_failure_keeps_source_and_failed_item(archive_root):
    url="https://example.com/notion"; prepare(archive_root, url+"\n")
    service, _ = make_service(archive_root, notion=Notion(fail=True))
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        data=service.run(db); item=db.query(ContentItem).one()
        assert item.notion_sync_status == NotionSyncStatus.FAILED
    assert data["failed_notion"] == 1 and url in (archive_root/"inbox"/"links.md").read_text(encoding="utf-8")

def test_repeated_url_blocks_reuse_result_and_both_are_removed(archive_root):
    url="https://example.com/repeated"
    prepare(archive_root, f"{url}\n\n另一段 {url}\n")
    service, notion = make_service(archive_root)
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db: data=service.run(db)
    assert data["processed"] == 1
    assert data["remaining"] == 0
    assert len(notion.created) == 1


def test_plain_text_is_analyzed_archived_and_removed(archive_root):
    prepare(archive_root, "这是一段没有链接但需要整理的项目想法。\n")
    service, notion = make_service(archive_root)
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        data=service.run(db)
        item=db.query(ContentItem).one()
        assert item.input_type.value == "text"
        assert item.content_hash
        assert item.raw_text.startswith("这是一段")
    assert data["processed"] == 1 and data["remaining"] == 0
    assert len(notion.created) == 1
    assert (archive_root/"inbox"/"links.md").read_text(encoding="utf-8") == ""


def test_plain_text_notion_failure_stays_in_inbox(archive_root):
    text = "没有链接的失败重试内容"
    prepare(archive_root, text + "\n")
    service, _ = make_service(archive_root, notion=Notion(fail=True))
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db: data=service.run(db)
    assert data["failed_notion"] == 1
    assert text in (archive_root/"inbox"/"links.md").read_text(encoding="utf-8")
