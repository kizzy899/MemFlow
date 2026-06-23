from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import Base, engine
from app.db_migrations import run_sqlite_migrations
from app.routers import collect, items, notion, translate, web_links, xiaohongshu
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
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(collect.router)
app.include_router(web_links.router)
app.include_router(xiaohongshu.router)
app.include_router(translate.router)
app.include_router(notion.router)
app.include_router(items.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

