from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.console_security import require_loopback

router = APIRouter(prefix="/api/agent-search", tags=["agent-search"], dependencies=[Depends(require_loopback)])


class AgentSearchRequest(BaseModel):
    source_type: Literal["video", "article"]
    source: str = Field(min_length=1, max_length=100000)
    interval: float = Field(default=2.0, gt=0, le=60)
    max_frames: int = Field(default=300, ge=1, le=3000)


@router.post("/extract")
async def extract(payload: AgentSearchRequest, request: Request):
    service = request.app.state.container.agent_search_service
    result = await asyncio.to_thread(service.extract, payload.source_type, payload.source, payload.interval, payload.max_frames)
    return {"success": True, "message": "extraction completed", "data": result}
