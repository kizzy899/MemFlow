from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, HttpUrl, field_validator


class WebLinkSubmitRequest(BaseModel):
    url: HttpUrl


class WebLinkSubmitResponse(BaseModel):
    status: str
    item_id: str
    notion_page_id: str = ""


class TranslateRequest(BaseModel):
    type: Literal["url", "text"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content cannot be empty")
        return stripped


class TranslateResponse(BaseModel):
    status: str
    translated_file_path: str
    notion_page_id: str = ""
    item_id: str


class XiaohongshuSyncRequest(BaseModel):
    limit: int = 20


class XiaohongshuSyncResponse(BaseModel):
    status: str
    synced_count: int


class ItemStatusResponse(BaseModel):
    id: str
    title: str
    process_status: str
    translation_status: str
    notion_page_id: str
    error_message: str = ""
    updated_at: Optional[datetime] = None

