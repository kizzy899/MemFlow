from datetime import datetime, timezone
from app.config import Settings
from app.models.content_item import ContentItem
from app.services.notion_service import NotionService


class Databases:
    def __init__(self, has_property=False, duplicate=False): self.has_property=has_property; self.duplicate=duplicate; self.updated=[]
    def retrieve(self, database_id): return {"properties": {"规范链接": {"type":"url"}} if self.has_property else {}}
    def update(self, **kwargs): self.updated.append(kwargs); self.has_property=True; return {}
    def query(self, **kwargs): return {"results": [{"id":"p", "url":"https://notion/p"}]} if self.duplicate else {"results": []}


class Pages:
    def __init__(self): self.created=[]
    def create(self, **kwargs): self.created.append(kwargs); return {"id":"new", "url":"https://notion/new"}


class Client:
    def __init__(self, database): self.databases=database; self.pages=Pages()


def service_with(client):
    service=NotionService(Settings(NOTION_API_KEY="x", NOTION_DATABASE_ID="db")); service._client=lambda: client; return service


def test_archive_schema_is_created_and_duplicate_is_queried():
    database=Databases(duplicate=True); client=Client(database); service=service_with(client)
    service.ensure_archive_schema()
    assert database.updated[0]["properties"] == {"规范链接": {"url": {}}}
    assert service.find_page_by_normalized_url("https://example.com/")["id"] == "p"


def test_archive_page_requires_children_and_normalized_property():
    client=Client(Databases(has_property=True)); service=service_with(client)
    item=ContentItem(title="标题", normalized_url="https://example.com/", source_url="https://example.com", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    page_id, _=service.create_archive_page(item)
    payload=client.pages.created[0]
    assert page_id == "new"
    assert payload["properties"]["规范链接"]["url"] == "https://example.com/"
    assert payload["children"]