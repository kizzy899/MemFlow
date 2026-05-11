from __future__ import annotations

from app.config import Settings
from app.services.ai_service import AIService
from app.services.classifier_service import ClassifierService
from app.services.content_pipeline_service import ContentPipelineService
from app.services.file_storage_service import FileStorageService
from app.services.notion_service import NotionService
from app.services.translation_service import TranslationService
from app.services.web_parser_service import WebParserService
from app.services.xiaohongshu_service import XiaohongshuService


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.classifier_service = ClassifierService()
        self.file_storage_service = FileStorageService(settings)
        self.web_parser_service = WebParserService(settings, self.file_storage_service)
        self.ai_service = AIService(settings, self.classifier_service)
        self.notion_service = NotionService(settings)
        self.translation_service = TranslationService(self.web_parser_service, self.file_storage_service)
        self.xiaohongshu_service = XiaohongshuService(settings)
        self.content_pipeline_service = ContentPipelineService(
            self.web_parser_service, self.ai_service, self.notion_service
        )

