from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.content import WebLinkSubmitRequest, WebLinkSubmitResponse
from app.services.container import ServiceContainer


router = APIRouter(prefix="/api/web-links", tags=["web-links"])


@router.post("/submit", response_model=WebLinkSubmitResponse)
def submit_web_link(
    payload: WebLinkSubmitRequest, request: Request, db: Session = Depends(get_db)
) -> WebLinkSubmitResponse:
    container: ServiceContainer = request.app.state.container
    item = container.content_pipeline_service.process_web_link(db, str(payload.url))
    if item.process_status.value == "failed":
        raise HTTPException(status_code=400, detail=item.error_message)
    return WebLinkSubmitResponse(status="success", item_id=item.id, notion_page_id=item.notion_page_id)

