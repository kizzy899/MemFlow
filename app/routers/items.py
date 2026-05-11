from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ContentItem
from app.schemas.content import ItemStatusResponse


router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("/{item_id}", response_model=ItemStatusResponse)
def get_item(item_id: str, db: Session = Depends(get_db)) -> ItemStatusResponse:
    item = db.get(ContentItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return ItemStatusResponse(
        id=item.id,
        title=item.title,
        process_status=item.process_status.value,
        translation_status=item.translation_status.value,
        notion_page_id=item.notion_page_id,
        error_message=item.error_message,
        updated_at=item.updated_at,
    )

