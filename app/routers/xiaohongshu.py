from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
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

