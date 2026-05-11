from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.services.container import ServiceContainer
from app.services.exceptions import ConfigError, NotionServiceError


router = APIRouter(prefix="/api/notion", tags=["notion"])


@router.get("/validate")
def validate_notion(request: Request) -> dict[str, str]:
    container: ServiceContainer = request.app.state.container
    try:
        container.notion_service.validate_database()
    except (NotionServiceError, ConfigError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success"}
