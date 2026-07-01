from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models.content_item import ContentItem,NotionSyncStatus
from app.services.export_service import ExportService
def test_json_and_markdown_export():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  db.add(ContentItem(id="x",title="标题",summary="摘要",core_points='["观点"]',action_items='["行动"]',raw_text="raw",category_level_1="AI",notion_sync_status=NotionSyncStatus.PENDING));db.commit();service=ExportService()
  data=service.export_items_as_json(db,{"limit":100});assert data["format"]=="json" and "raw_content" not in data["items"][0]
  raw=service.export_items_as_json(db,{"limit":100,"include_raw_content":True});assert raw["items"][0]["raw_content"]=="raw"
  md=service.export_items_as_markdown(db,{"category_level_1":"AI","limit":5000});assert all(x in md for x in ["标题","摘要","观点","行动"])
