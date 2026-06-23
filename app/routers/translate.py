from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ContentItem
from app.schemas.content import TranslateRequest, TranslateResponse
from app.services.container import ServiceContainer
from app.services.exceptions import TranslationError


router = APIRouter(prefix="/api", tags=["translate"])


@router.post("/translate", response_model=TranslateResponse)
def submit_translation(
    payload: TranslateRequest, request: Request, db: Session = Depends(get_db)
) -> TranslateResponse:
    container: ServiceContainer = request.app.state.container
    try:
        generated_item, _ = container.translation_service.translate(payload.type, payload.content)
        item = generated_item
        existing = None
        if generated_item.normalized_url:
            existing = container.item_service.find_by_normalized_url(db, generated_item.normalized_url)
        elif generated_item.content_hash:
            existing = container.item_service.find_by_content_hash(db, generated_item.content_hash)
        if existing:
            existing.title = generated_item.title or existing.title
            existing.raw_text = generated_item.raw_text or existing.raw_text
            existing.clean_content = generated_item.clean_content or existing.clean_content
            existing.raw_excerpt = generated_item.raw_excerpt or existing.raw_excerpt
            existing.author = generated_item.author or existing.author
            existing.published_at = generated_item.published_at or existing.published_at
            existing.translated_text_path = generated_item.translated_text_path
            existing.translation_status = generated_item.translation_status
            existing.process_status = generated_item.process_status
            existing.fetch_status = generated_item.fetch_status
            existing.ai_status = generated_item.ai_status
            existing.summary = existing.summary or generated_item.summary
            item = existing
        container.item_service.save(db, item)
        item = container.item_service.attempt_notion_sync(db, item)
    except TranslationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TranslateResponse(
        status="success",
        translated_file_path=item.translated_text_path,
        notion_page_id=item.notion_page_id,
        item_id=item.id,
    )
