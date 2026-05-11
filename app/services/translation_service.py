from __future__ import annotations

from importlib import import_module

from app.models.content_item import ContentItem, ContentType, ProcessStatus, SourcePlatform, TranslationStatus
from app.services.exceptions import TranslationError
from app.services.file_storage_service import FileStorageService
from app.services.web_parser_service import WebParserService


class TranslationService:
    def __init__(self, web_parser_service: WebParserService, file_storage_service: FileStorageService) -> None:
        self.web_parser_service = web_parser_service
        self.file_storage_service = file_storage_service

    def translate(self, task_type: str, content: str) -> tuple[ContentItem, str]:
        if task_type == "url":
            parsed = self.web_parser_service.parse_url(content)
            source_text = parsed.content
            title = parsed.title
            source_url = parsed.source_url
            author = parsed.author
            published_at = parsed.published_at
            raw_text = parsed.content
        else:
            source_text = content
            title = "Manual Translation"
            source_url = ""
            author = ""
            published_at = None
            raw_text = content

        translated_text = self._invoke_skill(source_text)
        translated_file_path = self.file_storage_service.save_translation_markdown(title, source_url, translated_text)

        item = ContentItem(
            title=title,
            source_url=source_url or None,
            source_platform=SourcePlatform.TRANSLATION,
            content_type=ContentType.TRANSLATION,
            raw_text=raw_text,
            raw_excerpt=source_text[:200],
            summary=f"原链接：\n{source_url or 'N/A'}\n\n一句话总结：\n翻译任务已完成\n",
            category="英语学习",
            tags="翻译,中文译文",
            author=author,
            published_at=published_at,
            translated_text_path=translated_file_path,
            translation_status=TranslationStatus.TRANSLATED,
            process_status=ProcessStatus.COMPLETED,
        )
        return item, translated_text

    def _invoke_skill(self, text: str) -> str:
        try:
            module = import_module("skills.translation_skill")
            translate_text = getattr(module, "translate_text")
            return str(translate_text(text=text, source_lang="auto", target_lang="zh-CN"))
        except Exception as exc:
            raise TranslationError(f"Translation skill failed: {exc}") from exc

