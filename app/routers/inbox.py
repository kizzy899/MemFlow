from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.console_security import require_loopback
from app.services.link_archive_service import ArchiveRunError
from app.services.exceptions import ConfigError, NotionServiceError

router = APIRouter(prefix="/api/inbox", tags=["inbox"], dependencies=[Depends(require_loopback)])


@router.post("/archive-links")
def archive_links(request: Request, db: Session = Depends(get_db)):
    try:
        data = request.app.state.container.link_archive_service.run(db)
    except (ArchiveRunError, ConfigError) as exc:
        return JSONResponse(status_code=409, content={"success": False, "message": str(exc), "data": None})
    except NotionServiceError as exc:
        return JSONResponse(status_code=502, content={"success": False, "message": str(exc), "data": None})
    partial = any(data[name] for name in ("failed_fetch", "failed_parse", "failed_notion"))
    return {"success": True, "message": "归档完成，部分链接处理失败" if partial else "归档完成", "data": data}