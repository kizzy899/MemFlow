from __future__ import annotations
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models.content_item import ContentItem, NotionSyncStatus
from app.services.exceptions import ConfigError
from app.services.item_service import ItemService

class NotionSyncService:
 def __init__(self,item_service:ItemService):self.item_service=item_service
 def batch_sync_items_to_notion(self,db:Session,status:str|None=None,item_ids:list[str]|None=None,limit:int=20,force:bool=False)->dict:
  if not item_ids and status not in {"pending","failed","all_unsynced"}:raise ValueError("请提供 status 或 item_ids")
  limit=min(max(limit,1),100);query=select(ContentItem)
  if item_ids:query=query.where(ContentItem.id.in_(item_ids))
  elif status=="all_unsynced":query=query.where(ContentItem.notion_sync_status.in_([NotionSyncStatus.PENDING,NotionSyncStatus.FAILED]))
  else:query=query.where(ContentItem.notion_sync_status==NotionSyncStatus(status))
  items=list(db.scalars(query.order_by(ContentItem.created_at.asc()).limit(limit)).all());results=[]
  for item in items:
   if item.notion_sync_status==NotionSyncStatus.SYNCED and not force:
    results.append({"item_id":item.id,"status":"skipped","message":"该条目已同步，跳过","notion_page_url":item.notion_page_url or None});continue
   try:
    if force:item.notion_sync_status=NotionSyncStatus.PENDING
    synced,_=self.item_service.sync_notion(db,item);results.append({"item_id":item.id,"status":"synced","message":"同步成功","notion_page_url":synced.notion_page_url or None})
   except Exception as exc:results.append({"item_id":item.id,"status":"failed","message":str(exc),"notion_page_url":item.notion_page_url or None})
  counts={key:sum(x["status"]==key for x in results) for key in ("synced","skipped","failed")}
  return {"total":len(results),**counts,"results":results}
