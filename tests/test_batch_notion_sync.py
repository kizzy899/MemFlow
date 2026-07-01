from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models.content_item import ContentItem,NotionSyncStatus
from app.services.item_service import ItemService
from app.services.notion_sync_service import NotionSyncService
class FakeNotion:
 def is_configured(self):return True
 def validate_database_details(self):return {"success":True}
 def upsert_page_details(self,item):
  if item.id=="bad":raise RuntimeError("bad")
  return "p-"+item.id,"https://notion/"+item.id

def test_batch_filters_skips_and_continues():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);service=NotionSyncService(ItemService(FakeNotion()))
 with Session(engine) as db:
  db.add_all([ContentItem(id="ok",notion_sync_status=NotionSyncStatus.PENDING),ContentItem(id="bad",notion_sync_status=NotionSyncStatus.PENDING),ContentItem(id="done",notion_sync_status=NotionSyncStatus.SYNCED,notion_page_url="x")]);db.commit()
  data=service.batch_sync_items_to_notion(db,status="all_unsynced");assert data["total"]==2 and data["synced"]==1 and data["failed"]==1
  selected=service.batch_sync_items_to_notion(db,item_ids=["done"]);assert selected["skipped"]==1
  forced=service.batch_sync_items_to_notion(db,item_ids=["done"],force=True);assert forced["synced"]==1
def test_batch_requires_selector():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  try:NotionSyncService(ItemService(FakeNotion())).batch_sync_items_to_notion(db)
  except ValueError:return
  assert False
