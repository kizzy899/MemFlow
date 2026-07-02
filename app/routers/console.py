from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.console_security import require_loopback
from app.db import get_db
from app.models.content_item import ContentItem, NotionSyncStatus
from app.services.exceptions import ConfigError, NotionServiceError, XiaohongshuFavoritesError, XiaohongshuLoginError
from app.services.link_archive_service import ArchiveRunError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["console"], dependencies=[Depends(require_loopback)])


class NotionConfigRequest(BaseModel):
    notion_token: str = ""
    notion_database_id: str = ""


class InboxAppendRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100000)


class InboxDeleteRequest(BaseModel):
    item_id: str
    version: str

class InboxBatchDeleteRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1)
    version: str


def _describe_xhs_exception(exc: Exception) -> str:
    detail = " ".join(str(exc).split())
    if detail:
        return detail
    exception_name = type(exc).__name__
    if "timeout" in exception_name.lower():
        return "页面加载或浏览器操作超时，请检查网络、代理和小红书页面是否可访问。"
    return f"{exception_name}（异常未提供详细信息，请查看启动终端日志。）"


def _container(request: Request): return request.app.state.container

def _ensure_idle(container) -> None:
    if container.processor_manager.status()["status"] == "processing":
        raise HTTPException(status_code=409, detail="整理任务运行期间不能修改配置")


def _reload(container) -> None:
    get_settings.cache_clear(); container.reload_settings(get_settings())


async def _read_xhs_favorites(container) -> dict:
    try:
        items = await container.xiaohongshu_service.fetch_favorites(limit=1)
        return {"status":"configured","message":"登录成功：已开始读取收藏页内容。","sample_count":len(items)}
    except XiaohongshuLoginError as exc:
        return {"status":"login_failed","message":f"登录失败：{exc}","sample_count":0}
    except XiaohongshuFavoritesError as exc:
        return {"status":"favorites_unavailable","message":f"登录成功，但没有读取到收藏页：{exc}","sample_count":0}
    except Exception as exc:
        logger.exception("Xiaohongshu login check failed")
        return {"status":"failed","message":f"检测失败：{_describe_xhs_exception(exc)}","sample_count":0}

@router.get("/api/config/status")
def config_status(request: Request):
    return {"success": True, "message": "查询成功", "data": _container(request).config_service.status()}


@router.post("/api/config/notion")
def save_notion(payload: NotionConfigRequest, request: Request):
    container=_container(request); _ensure_idle(container)
    container.config_service.update({"NOTION_API_KEY":payload.notion_token,"NOTION_DATABASE_ID":payload.notion_database_id}); _reload(container)
    return {"success":True,"message":"Notion 配置已保存","data":container.config_service.status()["notion"]}


@router.delete("/api/config/notion")
def clear_notion(request: Request):
    container=_container(request); _ensure_idle(container); container.config_service.clear({"NOTION_API_KEY","NOTION_DATABASE_ID"}); _reload(container)
    return {"success":True,"message":"Notion 配置已清除","data":container.config_service.status()["notion"]}


@router.post("/api/notion/test")
def test_notion(request: Request):
    container=_container(request)
    try:
        validation=container.notion_service.validate_database_details()
        if not validation["success"]: raise NotionServiceError(container.notion_service.validation_error_message(validation))
        database=container.notion_service._client().databases.retrieve(database_id=container.settings.notion_database_id)
        title="".join(part.get("plain_text","") for part in database.get("title",[])) or "未命名数据库"
        result={"status":"configured","message":"Notion 连接成功","database_name":title,"database_url":str(database.get("url", ""))}
        container.config_service.notion_check=result
        return {"success":True,"message":result["message"],"data":result}
    except Exception as exc:
        result={"status":"failed","message":str(exc),"database_name":"","database_url":""}; container.config_service.notion_check=result
        return JSONResponse(status_code=502,content={"success":False,"message":str(exc),"data":result})


@router.get("/api/inbox")
def get_inbox(request: Request): return {"success":True,"message":"查询成功","data":_container(request).console_inbox_service.snapshot()}


@router.post("/api/inbox")
def append_inbox(payload: InboxAppendRequest, request: Request):
    try: data=_container(request).console_inbox_service.append(payload.content)
    except ArchiveRunError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
    return {"success":True,"message":"已加入待整理队列","data":data}


@router.delete("/api/inbox/item")
def delete_inbox(payload: InboxDeleteRequest, request: Request):
    try: data=_container(request).console_inbox_service.delete(payload.item_id,payload.version)
    except ArchiveRunError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
    except KeyError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
    return {"success":True,"message":"已删除待处理内容","data":data}



@router.delete("/api/inbox/items")
def delete_inbox_items(payload: InboxBatchDeleteRequest, request: Request):
    try:
        data = _container(request).console_inbox_service.delete_many(payload.item_ids, payload.version)
    except ArchiveRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "message": f"已删除 {len(payload.item_ids)} 条待处理内容", "data": data}

@router.post("/api/processor/start",status_code=202)
def start_processor(request: Request):
    try: data=_container(request).processor_manager.start()
    except RuntimeError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
    return {"success":True,"message":"整理任务已启动","data":data}


@router.get("/api/processor/status")
def processor_status(request: Request): return {"success":True,"message":"查询成功","data":_container(request).processor_manager.status()}


@router.get("/api/notion/recent")
def notion_recent(limit:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    rows=db.scalars(select(ContentItem).where(ContentItem.notion_sync_status==NotionSyncStatus.SYNCED,ContentItem.archive_markdown!="").order_by(ContentItem.archived_at.desc(),ContentItem.updated_at.desc()).limit(limit)).all()
    items=[{"item_id":x.id,"title":x.title,"original_url":x.source_url or "","normalized_url":x.normalized_url or "","notion_url":x.notion_page_url or "","created_at":(x.archived_at or x.updated_at).isoformat(),"status":"archived"} for x in rows]
    return {"success":True,"message":"查询成功","data":{"items":items,"total":len(items)}}


@router.get("/api/hot")
def get_hot(request:Request):
    path=Path(__file__).resolve().parents[2]/"hot.md"
    content=path.read_text(encoding="utf-8-sig") if path.exists() else "暂无项目记忆"
    sections={}; current=None
    for line in content.splitlines():
        if line.startswith("## "): current=line[3:].strip(); sections[current]=[]
        elif current and line.strip(): sections[current].append(line)
    return {"success":True,"message":"查询成功","data":{"content":content,"sections":{key:"\n".join(value) for key,value in sections.items()}}}
