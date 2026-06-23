from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, HttpUrl, field_validator, model_validator


class WebLinkSubmitRequest(BaseModel):
    url: HttpUrl


class WebLinkSubmitResponse(BaseModel):
    status: str
    item_id: str
    notion_page_id: str = ""


class CollectRequest(BaseModel):
    input_type: Literal["url", "text"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content cannot be empty")
        return stripped

    @model_validator(mode="after")
    def validate_input_type(self) -> "CollectRequest":
        if self.input_type == "url":
            self.content = str(HttpUrl(self.content))
        return self

class CollectData(BaseModel):
    item_id: str
    title: str
    source_url: str = ""
    platform: str
    content_type: str
    category_level_1: str
    category_level_2: str
    summary: str
    keywords: list[str]
    core_points: list[str]
    action_items: list[str]
    importance: str
    original_language: str
    is_translated: bool
    process_status: str
    notion_sync_status: str
    notion_page_id: str = ""
    notion_page_url: str = ""


class CollectResponse(BaseModel):
    success: bool
    message: str
    data: CollectData


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
    notion_page_url: str = ""
    notion_sync_status: str = "pending"
    error_message: str = ""
    updated_at: Optional[datetime] = None


class ItemSummary(BaseModel):
    item_id: str
    title: str
    source_url: str = ""
    input_type: str
    platform: str
    content_type: str
    category_level_1: str
    category_level_2: str
    keywords: list[str]
    importance: str
    notion_sync_status: str
    notion_page_url: str = ""
    created_at: datetime
    updated_at: datetime


class PaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ItemListData(BaseModel):
    items: list[ItemSummary]
    pagination: PaginationData


class ItemListResponse(BaseModel):
    success: bool
    message: str
    data: ItemListData


class ItemDetail(BaseModel):
    id: str
    item_id: str
    input_type: str
    source_url: str = ""
    normalized_url: str = ""
    title: str
    platform: str
    content_type: str
    category_level_1: str
    category_level_2: str
    summary: str
    key_points: list[str]
    action_items: list[str]
    keywords: list[str]
    importance: str
    language: str
    is_translated: bool
    fetch_status: str
    ai_status: str
    process_status: str
    notion_sync_status: str
    notion_page_url: str = ""
    notion_error: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ItemDetailResponse(BaseModel):
    success: bool
    message: str
    data: ItemDetail


class NotionSyncData(BaseModel):
    item_id: str
    notion_sync_status: str
    notion_page_url: str = ""
    notion_error: Optional[str] = None


class NotionSyncResponse(BaseModel):
    success: bool
    message: str
    data: NotionSyncData

