from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.container import ServiceContainer


router = APIRouter(prefix="/api/notion", tags=["notion"])


@router.get("/validate")
def validate_notion(request: Request):
    container: ServiceContainer = request.app.state.container
    return container.notion_service.validate_database_details()
