from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.content import XiaohongshuSyncRequest, XiaohongshuSyncResponse
from app.services.container import ServiceContainer
from app.services.exceptions import XiaohongshuFavoritesError, XiaohongshuLoginError
from app.services.xhs_login_service import LoginServiceError


router = APIRouter(prefix="/api/xhs", tags=["xiaohongshu"])


def login_error(exc: LoginServiceError):
    status = 503 if exc.code == "AUTH_KEY_MISSING" else 400
    return JSONResponse(status_code=status, content=exc.public())


@router.get("/login/qrcode")
async def login_qrcode(request: Request):
    try:
        return await request.app.state.container.xhs_login_service.start_login()
    except LoginServiceError as exc:
        return login_error(exc)


@router.post("/login/chrome")
async def connect_chrome(request: Request):
    try:
        return await request.app.state.container.xhs_login_service.connect_chrome()
    except LoginServiceError as exc:
        return login_error(exc)


@router.get("/login/status")
async def login_status(request: Request):
    return await request.app.state.container.xhs_login_service.poll_login()


@router.get("/session")
def session_status(request: Request):
    return request.app.state.container.xhs_login_service.session_status()


@router.post("/session/refresh")
async def refresh_session(request: Request):
    try:
        return await request.app.state.container.xhs_login_service.refresh()
    except LoginServiceError as exc:
        return login_error(exc)


@router.post("/logout")
async def logout(request: Request):
    await request.app.state.container.xhs_login_service.logout()
    return {"status": "idle", "loggedIn": False}


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

