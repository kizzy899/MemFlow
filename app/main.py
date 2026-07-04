from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, engine
from app.db_migrations import run_sqlite_migrations
from app.routers import agent_search, collect, console, export, inbox, items, notion, translate, web_links, xiaohongshu
from app.services.container import ServiceContainer
from app.services.exceptions import NotionServiceError


logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = ServiceContainer(settings)
    container.file_storage_service.ensure_directories()
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    if container.notion_service.is_configured():
        try:
            container.notion_service.validate_database()
        except NotionServiceError as exc:
            logger.warning("Notion validation failed during startup: %s", exc)
    app.state.container = container
    await container.xhs_login_service.restore()
    try:
        yield
    finally:
        container.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(collect.router)
app.include_router(web_links.router)
app.include_router(xiaohongshu.router)
app.include_router(agent_search.router)
app.include_router(translate.router)
app.include_router(notion.router)
app.include_router(items.router)
app.include_router(export.router)
app.include_router(inbox.router)
app.include_router(console.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
_console_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if (_console_dist / "assets").exists():
    app.mount("/console/assets", StaticFiles(directory=_console_dist / "assets"), name="console-assets")


@app.get("/console", include_in_schema=False)
@app.get("/console/{path:path}", include_in_schema=False)
def knowledge_console(path: str = ""):
    index = _console_dist / "index.html"
    if not index.exists():
        return JSONResponse(status_code=503, content={"message": "Knowledge Console 尚未构建，请运行 cd frontend && npm install && npm run build"})
    return FileResponse(index)
