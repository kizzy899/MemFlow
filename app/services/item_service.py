from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.content_item import (
    ContentItem,
    InputType,
    NotionSyncStatus,
    ProcessStatus,
    SourcePlatform,
    StageStatus,
)
from app.services.exceptions import ConfigError, NotionServiceError
from app.services.notion_service import NotionService


@dataclass
class ItemPage:
    items: list[ContentItem]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


class ItemService:
    PLATFORM_ALIASES = {
        "web": SourcePlatform.WEB, "网页": SourcePlatform.WEB,
        "manual": SourcePlatform.MANUAL, "手动输入": SourcePlatform.MANUAL,
        "xiaohongshu": SourcePlatform.XIAOHONGSHU, "小红书": SourcePlatform.XIAOHONGSHU,
        "bilibili": SourcePlatform.BILIBILI, "b站": SourcePlatform.BILIBILI,
        "wechat": SourcePlatform.WECHAT, "微信公众号": SourcePlatform.WECHAT,
        "zhihu": SourcePlatform.ZHIHU, "知乎": SourcePlatform.ZHIHU,
        "github": SourcePlatform.GITHUB,
        "paper": SourcePlatform.PAPER, "论文": SourcePlatform.PAPER,
        "translation": SourcePlatform.TRANSLATION, "翻译": SourcePlatform.TRANSLATION,
    }

    def __init__(self, notion_service: NotionService) -> None:
        self.notion_service = notion_service

    def save(self, db: Session, item: ContentItem) -> ContentItem:
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def get(self, db: Session, item_id: str) -> ContentItem | None:
        return db.get(ContentItem, item_id)

    def find_by_normalized_url(self, db: Session, normalized_url: str) -> ContentItem | None:
        return db.scalar(select(ContentItem).where(ContentItem.normalized_url == normalized_url))

    def find_by_content_hash(self, db: Session, digest: str) -> ContentItem | None:
        return db.scalar(select(ContentItem).where(ContentItem.content_hash == digest))

    def sync_notion(self, db: Session, item: ContentItem) -> tuple[ContentItem, bool]:
        if item.notion_sync_status == NotionSyncStatus.SYNCED and item.notion_page_url:
            return item, True
        if not self.notion_service.is_configured():
            raise ConfigError("Notion 未配置：缺少 NOTION_API_KEY 或 NOTION_DATABASE_ID")

        try:
            validation = self.notion_service.validate_database_details()
            if not validation["success"]:
                raise NotionServiceError(self.notion_service.validation_error_message(validation))
            page_id, page_url = self.notion_service.upsert_page_details(item)
            item.notion_page_id = page_id
            item.notion_page_url = page_url
            item.notion_sync_status = NotionSyncStatus.SYNCED
            item.notion_error_message = ""
            return self.save(db, item), False
        except ConfigError:
            raise
        except Exception as exc:
            item.notion_sync_status = NotionSyncStatus.FAILED
            item.notion_error_message = str(exc)
            self.save(db, item)
            if isinstance(exc, NotionServiceError):
                raise
            raise NotionServiceError(str(exc)) from exc

    def attempt_notion_sync(self, db: Session, item: ContentItem) -> ContentItem:
        try:
            synced, _ = self.sync_notion(db, item)
            return synced
        except ConfigError:
            if item.notion_sync_status != NotionSyncStatus.FAILED:
                item.notion_sync_status = NotionSyncStatus.PENDING
            item.notion_error_message = "Notion 未配置"
            return self.save(db, item)
        except NotionServiceError:
            return item

    def list_items(
        self,
        db: Session,
        page: int,
        page_size: int,
        notion_sync_status: str | None = None,
        input_type: str | None = None,
        platform: str | None = None,
        keyword: str | None = None,
        failed_only: bool = False,
    ) -> ItemPage:
        filters = []
        if notion_sync_status:
            try:
                filters.append(ContentItem.notion_sync_status == NotionSyncStatus(notion_sync_status.lower()))
            except ValueError as exc:
                raise ValueError("notion_sync_status must be pending, synced, or failed") from exc
        if input_type:
            try:
                filters.append(ContentItem.input_type == InputType(input_type.lower()))
            except ValueError as exc:
                raise ValueError("input_type must be url or text") from exc
        if platform:
            platform_value = self.PLATFORM_ALIASES.get(platform.strip().lower())
            if not platform_value:
                raise ValueError("platform is not supported")
            filters.append(ContentItem.source_platform == platform_value)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    ContentItem.title.ilike(pattern),
                    ContentItem.summary.ilike(pattern),
                    ContentItem.tags.ilike(pattern),
                    ContentItem.source_url.ilike(pattern),
                    ContentItem.normalized_url.ilike(pattern),
                )
            )
        if failed_only:
            filters.append(
                or_(
                    ContentItem.process_status == ProcessStatus.FAILED,
                    ContentItem.fetch_status == StageStatus.FAILED,
                    ContentItem.ai_status == StageStatus.FAILED,
                    ContentItem.notion_sync_status == NotionSyncStatus.FAILED,
                )
            )

        total = db.scalar(select(func.count()).select_from(ContentItem).where(*filters)) or 0
        items = list(
            db.scalars(
                select(ContentItem)
                .where(*filters)
                .order_by(ContentItem.created_at.desc(), ContentItem.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return ItemPage(items=items, total=total, page=page, page_size=page_size)
