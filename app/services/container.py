from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.services.ai_service import AIService
from app.services.agent_search_service import AgentSearchService
from app.services.classifier_service import ClassifierService
from app.services.config_service import ConfigService
from app.services.console_inbox_service import ConsoleInboxService
from app.services.content_pipeline_service import ContentPipelineService
from app.services.export_service import ExportService
from app.services.file_storage_service import FileStorageService
from app.services.item_service import ItemService
from app.services.link_archive_ai_service import LinkArchiveAIService
from app.services.link_archive_service import LinkArchiveService
from app.services.link_reader_service import LinkReaderService
from app.services.notion_service import NotionService
from app.services.notion_sync_service import NotionSyncService
from app.services.processor_manager import ProcessorManager
from app.services.translation_service import TranslationService
from app.services.web_parser_service import WebParserService
from app.services.xiaohongshu_service import XiaohongshuService
from app.services.xhs_login_service import XiaohongshuLoginService


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.config_service = ConfigService(self.root, settings)
        self.agent_search_service = AgentSearchService(self.root)
        self.console_inbox_service = ConsoleInboxService(self.root)
        self.processor_manager: ProcessorManager | None = None
        self._build(settings)
        self.processor_manager = ProcessorManager(self.link_archive_service)

    def reload_settings(self, settings: Settings) -> None:
        self.config_service.set_settings(settings)
        self._build(settings)
        if self.processor_manager:
            self.processor_manager.set_archive_service(self.link_archive_service)

    def _build(self, settings: Settings) -> None:
        self.settings = settings
        self.classifier_service = ClassifierService()
        self.file_storage_service = FileStorageService(settings)
        self.web_parser_service = WebParserService(settings, self.file_storage_service)
        self.ai_service = AIService(settings, self.classifier_service)
        self.notion_service = NotionService(settings)
        self.item_service = ItemService(self.notion_service)
        self.notion_sync_service = NotionSyncService(self.item_service)
        self.export_service = ExportService()
        self.translation_service = TranslationService(self.web_parser_service, self.file_storage_service)
        self.xhs_login_service = XiaohongshuLoginService(self.root, settings.memflow_auth_key, settings.chrome_cdp_url)
        self.xiaohongshu_service = XiaohongshuService(settings, self.xhs_login_service, self.agent_search_service)
        self.content_pipeline_service = ContentPipelineService(self.web_parser_service, self.ai_service, self.item_service)
        self.link_reader_service = LinkReaderService(settings, self.web_parser_service)
        self.link_archive_ai_service = LinkArchiveAIService(settings)
        self.link_archive_service = LinkArchiveService(self.root, self.link_reader_service, self.ai_service, self.link_archive_ai_service, self.item_service, self.notion_service)
