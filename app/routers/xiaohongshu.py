from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.content import XiaohongshuSyncRequest, XiaohongshuSyncResponse
from app.services.container import ServiceContainer
from app.services.exceptions import XiaohongshuFavoritesError, XiaohongshuLoginError


router = APIRouter(prefix="/api/xiaohongshu", tags=["xiaohongshu"])


@router.post("/sync", response_model=XiaohongshuSyncResponse)
async def sync_xiaohongshu(
    payload: XiaohongshuSyncRequest, request: Request, db: Session = Depends(get_db)
) -> XiaohongshuSyncResponse:
    container: ServiceContainer = request.app.state.container
    try:
        items = await container.xiaohongshu_service.fetch_favorites(limit=payload.limit)
    except (XiaohongshuLoginError, XiaohongshuFavoritesError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    synced_count = 0
    for item in items:
        processed = container.content_pipeline_service.process_xiaohongshu_item(db, item)
        if processed.process_status.value == "completed":
            synced_count += 1

    return XiaohongshuSyncResponse(status="success", synced_count=synced_count)

