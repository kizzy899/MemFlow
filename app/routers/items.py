from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.content_item import ContentItem
from app.schemas.content import (
    ItemDetail,
    ItemDetailResponse,
    ItemListData,
    ItemListResponse,
    ItemSummary,
    NotionSyncData,
    NotionSyncResponse,
    PaginationData,
)
from app.services.container import ServiceContainer
from app.services.exceptions import ConfigError, NotionServiceError
from app.services.item_service import ItemPage


router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("", response_model=ItemListResponse)
def list_items(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    notion_sync_status: str | None = None,
    input_type: str | None = None,
    platform: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
):
    validation_error = _validate_pagination(page, page_size)
    if validation_error:
        return validation_error
    container: ServiceContainer = request.app.state.container
    try:
        result = container.item_service.list_items(
            db, page, page_size, notion_sync_status, input_type, platform, keyword
        )
    except ValueError as exc:
        return _error(422, str(exc))
    return _list_response(result)


@router.get("/failed", response_model=ItemListResponse)
def list_failed_items(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    validation_error = _validate_pagination(page, page_size)
    if validation_error:
        return validation_error
    container: ServiceContainer = request.app.state.container
    result = container.item_service.list_items(db, page, page_size, failed_only=True)
    return _list_response(result)


@router.post("/{item_id}/sync-notion", response_model=NotionSyncResponse)
def sync_item_to_notion(item_id: str, request: Request, db: Session = Depends(get_db)):
    container: ServiceContainer = request.app.state.container
    item = container.item_service.get(db, item_id)
    if not item:
        return _error(404, "记录不存在")
    try:
        item, already_synced = container.item_service.sync_notion(db, item)
    except ConfigError as exc:
        return _error(
            503,
            str(exc),
            {"item_id": item.id, "notion_sync_status": item.notion_sync_status.value},
        )
    except NotionServiceError as exc:
        return _error(
            502,
            f"Notion 同步失败：{exc}",
            {
                "item_id": item.id,
                "notion_sync_status": item.notion_sync_status.value,
                "notion_page_url": item.notion_page_url or "",
                "notion_error": item.notion_error_message or str(exc),
            },
        )
    message = "该条目已同步到 Notion，无需重复同步" if already_synced else "Notion 同步成功"
    return NotionSyncResponse(
        success=True,
        message=message,
        data=NotionSyncData(
            item_id=item.id,
            notion_sync_status=item.notion_sync_status.value,
            notion_page_url=item.notion_page_url or "",
            notion_error=item.notion_error_message or None,
        ),
    )


@router.get("/{item_id}", response_model=ItemDetailResponse)
def get_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    container: ServiceContainer = request.app.state.container
    item = container.item_service.get(db, item_id)
    if not item:
        return _error(404, "记录不存在")
    return ItemDetailResponse(success=True, message="查询成功", data=_detail(item))


def _summary(item: ContentItem) -> ItemSummary:
    return ItemSummary(
        item_id=item.id,
        title=item.title,
        source_url=item.source_url or "",
        input_type=item.input_type.value,
        platform=item.source_platform.value,
        content_type=item.content_type.value,
        category_level_1=item.category_level_1,
        category_level_2=item.category_level_2,
        keywords=item.tags_list(),
        importance=item.importance.value,
        notion_sync_status=item.notion_sync_status.value,
        notion_page_url=item.notion_page_url or "",
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _detail(item: ContentItem) -> ItemDetail:
    return ItemDetail(
        id=item.id,
        item_id=item.id,
        input_type=item.input_type.value,
        source_url=item.source_url or "",
        normalized_url=item.normalized_url or "",
        title=item.title,
        platform=item.source_platform.value,
        content_type=item.content_type.value,
        category_level_1=item.category_level_1,
        category_level_2=item.category_level_2,
        summary=item.summary,
        key_points=item.core_points_list(),
        action_items=item.action_items_list(),
        keywords=item.tags_list(),
        importance=item.importance.value,
        language=item.original_language,
        is_translated=item.is_translated,
        fetch_status=item.fetch_status.value,
        ai_status=item.ai_status.value,
        process_status=item.process_status.value,
        notion_sync_status=item.notion_sync_status.value,
        notion_page_url=item.notion_page_url or "",
        notion_error=item.notion_error_message or None,
        error_message=item.error_message or None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _list_response(result: ItemPage) -> ItemListResponse:
    return ItemListResponse(
        success=True,
        message="查询成功",
        data=ItemListData(
            items=[_summary(item) for item in result.items],
            pagination=PaginationData(
                page=result.page,
                page_size=result.page_size,
                total=result.total,
                total_pages=result.total_pages,
            ),
        ),
    )


def _validate_pagination(page: int, page_size: int) -> JSONResponse | None:
    if page < 1:
        return _error(422, "page must be at least 1")
    if page_size < 1 or page_size > 100:
        return _error(422, "page_size must be between 1 and 100")
    return None


def _error(status_code: int, message: str, data=None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "message": message, "data": data})
