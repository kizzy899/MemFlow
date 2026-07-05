from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.content_item import ContentItem, ContentType, SourcePlatform
from app.schemas.content import XiaohongshuSyncRequest
from app.services.container import ServiceContainer
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


@router.post("/sync", status_code=202)
def sync_xiaohongshu(payload: XiaohongshuSyncRequest, request: Request):
    container: ServiceContainer = request.app.state.container
    try:
        return container.xhs_sync_manager.start(payload.limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sync/status")
def sync_status(request: Request):
    return request.app.state.container.xhs_sync_manager.status()


@router.post("/sync/cancel")
def cancel_sync(request: Request):
    return request.app.state.container.xhs_sync_manager.cancel()


@router.get("/providers")
def provider_status(request: Request):
    return request.app.state.container.xhs_media_pipeline.provider_status()


@router.post("/providers/opencli/check")
def check_opencli(request: Request):
    return request.app.state.container.xhs_media_pipeline.opencli.health()


@router.get("/media/candidates")
def media_candidates(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ContentItem).where(
            ContentItem.source_platform == SourcePlatform.XIAOHONGSHU,
            ContentItem.content_type == ContentType.VIDEO,
            or_(
                ContentItem.media_fetch_status.in_(["failed", "empty", "skipped"]),
                ContentItem.ocr_status.in_(["failed", "empty", "skipped"]),
                ContentItem.transcription_status.in_(["failed", "empty", "skipped"]),
                ContentItem.content_completeness != "complete",
            ),
        ).order_by(ContentItem.updated_at.desc()).limit(100)
    ).all()
    return {"items": [{"item_id": item.id, "title": item.title, "media_fetch_status": item.media_fetch_status, "media_provider": item.media_provider, "ocr_status": item.ocr_status, "transcription_status": item.transcription_status, "content_completeness": item.content_completeness, "updated_at": item.updated_at.isoformat()} for item in rows]}


@router.post("/media/reprocess", status_code=202)
def reprocess_media(payload: dict, request: Request, db: Session = Depends(get_db)):
    item_ids = list(dict.fromkeys(str(value) for value in payload.get("item_ids", []) if str(value)))
    if not 1 <= len(item_ids) <= 20:
        raise HTTPException(status_code=422, detail="item_ids must contain 1 to 20 unique IDs")
    rows = list(db.scalars(select(ContentItem).where(ContentItem.id.in_(item_ids))).all())
    if len(rows) != len(item_ids):
        raise HTTPException(status_code=404, detail="部分记录不存在")
    if any(item.source_platform != SourcePlatform.XIAOHONGSHU or item.content_type != ContentType.VIDEO for item in rows):
        raise HTTPException(status_code=422, detail="只能重新处理小红书视频条目")
    try:
        return request.app.state.container.xhs_sync_manager.start_reprocess(item_ids)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

