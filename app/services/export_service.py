from __future__ import annotations
from datetime import datetime,timezone
from sqlalchemy import or_,select
from sqlalchemy.orm import Session
from app.models.content_item import ContentItem,NotionSyncStatus,SourcePlatform
from app.services.taxonomy_service import normalize_content_type,normalize_importance,normalize_platform,normalize_keywords

class ExportService:
 def _items(self,db:Session,filters:dict)->list[ContentItem]:
  query=select(ContentItem)
  if filters.get("notion_sync_status"):query=query.where(ContentItem.notion_sync_status==NotionSyncStatus(filters["notion_sync_status"]))
  if filters.get("category_level_1"):query=query.where(ContentItem.category_level_1==filters["category_level_1"])
  if filters.get("platform"):
   aliases={"Web":"web","小红书":"xiaohongshu","B站":"bilibili","微信公众号":"wechat","知乎":"zhihu","GitHub":"github","论文":"paper","手动输入":"manual"};value=aliases.get(filters["platform"],filters["platform"].lower());query=query.where(ContentItem.source_platform==SourcePlatform(value))
  if filters.get("keyword"):
   p=f'%{filters["keyword"]}%';query=query.where(or_(ContentItem.title.ilike(p),ContentItem.summary.ilike(p),ContentItem.tags.ilike(p)))
  return list(db.scalars(query.order_by(ContentItem.created_at.desc(),ContentItem.id.desc()).limit(min(max(filters.get("limit",100),1),1000))).all())
 def _dict(self,x:ContentItem,raw:bool=False)->dict:
  d={"item_id":x.id,"title":x.title,"source_url":x.source_url or "","platform":normalize_platform(x.source_platform.value,x.source_url,x.input_type.value),"content_type":normalize_content_type(x.content_type.value),"category_level_1":x.category_level_1,"category_level_2":x.category_level_2,"summary":x.summary,"core_points":x.core_points_list(),"action_items":x.action_items_list(),"keywords":normalize_keywords(x.tags_list()),"importance":normalize_importance(x.importance.value),"original_language":x.original_language,"is_translated":x.is_translated,"notion_sync_status":x.notion_sync_status.value,"notion_page_url":x.notion_page_url or "","created_at":x.created_at.isoformat(),"updated_at":x.updated_at.isoformat()}
  if raw:d["raw_content"]=x.raw_text
  return d
 def export_items_as_json(self,db:Session,filters:dict)->dict:
  items=self._items(db,filters);return {"format":"json","exported_at":datetime.now(timezone.utc).isoformat(),"total":len(items),"items":[self._dict(x,bool(filters.get("include_raw_content"))) for x in items]}
 def export_items_as_markdown(self,db:Session,filters:dict)->str:
  items=[self._dict(x) for x in self._items(db,filters)];lines=["# MemFlow Knowledge Export","",f"导出时间：{datetime.now(timezone.utc).isoformat()}",f"导出数量：{len(items)}",""]
  for i,x in enumerate(items,1):
   lines += ["---","",f"## {i}. {x['title'] or '未命名'}","",f"- 来源平台：{x['platform']}",f"- 内容类型：{x['content_type']}",f"- 一级分类：{x['category_level_1']}",f"- 二级分类：{x['category_level_2']}",f"- 重要程度：{x['importance']}",f"- 原文语言：{x['original_language']}",f"- Notion 状态：{x['notion_sync_status']}",f"- 原始链接：{x['source_url'] or '无'}",f"- Notion 页面：{x['notion_page_url'] or '无'}",f"- 创建时间：{x['created_at']}","","### 摘要","",x['summary'] or "无","","### 核心观点",""]+[f"{n}. {v}" for n,v in enumerate(x['core_points'],1)]+["","### 行动建议",""]+[f"{n}. {v}" for n,v in enumerate(x['action_items'],1)]+["","### 关键词","","、".join(x['keywords']) or "无",""]
  return "\n".join(lines)
