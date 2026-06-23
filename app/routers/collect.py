from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.content import CollectData, CollectRequest, CollectResponse
from app.services.container import ServiceContainer
from app.services.exceptions import AIServiceError, ConfigError, ParsingError


router = APIRouter(prefix="/api", tags=["collect"])


@router.post("/collect", response_model=CollectResponse)
def collect_content(
    payload: CollectRequest, request: Request, db: Session = Depends(get_db)
) -> CollectResponse:
    container: ServiceContainer = request.app.state.container
    try:
        item = container.content_pipeline_service.process_collect(db, payload.input_type, payload.content)
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ParsingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    message = "内容已整理并同步到 Notion"
    if item.notion_sync_status.value == "pending":
        message = "内容已整理并保存到本地，等待同步 Notion"
    elif item.notion_sync_status.value == "failed":
        message = "内容已整理并保存到本地，但 Notion 同步失败"
    return CollectResponse(
        success=True,
        message=message,
        data=CollectData(
            item_id=item.id,
            title=item.title,
            source_url=item.source_url or "",
            platform=item.source_platform.value,
            content_type=item.content_type.value,
            category_level_1=item.category_level_1,
            category_level_2=item.category_level_2,
            summary=item.summary,
            keywords=item.tags_list(),
            core_points=item.core_points_list(),
            action_items=item.action_items_list(),
            importance=item.importance.value,
            original_language=item.original_language,
            is_translated=item.is_translated,
            process_status=item.process_status.value,
            notion_sync_status=item.notion_sync_status.value,
            notion_page_id=item.notion_page_id or "",
            notion_page_url=item.notion_page_url or "",
        ),
    )
