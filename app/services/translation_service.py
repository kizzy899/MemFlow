from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.content_item import (
    ContentItem,
    ContentType,
    InputType,
    NotionSyncStatus,
    ProcessStatus,
    SourcePlatform,
    StageStatus,
    TranslationStatus,
)
from app.services.exceptions import TranslationError
from app.services.file_storage_service import FileStorageService
from app.services.item_service import ItemService
from app.services.web_parser_service import WebParserService
from app.utils.content_identity import content_hash, normalize_text, normalize_url


@dataclass
class TranslationArtifact:
    article_id: str
    article_dir: Path
    source_path: Path
    translation_path: Path
    qa_path: Path
    title: str
    source_text: str
    qa: dict


class TranslationService:
    def __init__(
        self,
        settings: Settings,
        web_parser_service: WebParserService,
        file_storage_service: FileStorageService,
        item_service: ItemService,
    ) -> None:
        self.settings = settings
        self.web_parser_service = web_parser_service
        self.file_storage_service = file_storage_service
        self.item_service = item_service

    def find_existing_translation(self, db: Session, url: str) -> ContentItem | None:
        item = self.item_service.find_by_normalized_url(db, normalize_url(url))
        if item and item.translated_text_path:
            return item
        return None

    def translate_url(self, db: Session, url: str) -> ContentItem:
        existing = self.find_existing_translation(db, url)
        if existing:
            return existing
        if not self.settings.gemini_api_key:
            raise TranslationError("GEMINI_API_KEY 未配置，无法自动完成整篇文章翻译")

        artifact = self._run_global_translation_pipeline(url)
        self._validate_artifact(artifact)
        translated_file_path = self._display_path(artifact.translation_path)
        normalized = normalize_url(url)
        item = self.item_service.find_by_normalized_url(db, normalized)
        if not item:
            item = ContentItem(source_url=url, normalized_url=normalized)

        item.input_type = InputType.URL
        item.title = artifact.title or url
        item.source_url = url
        item.normalized_url = normalized
        item.content_hash = None
        item.source_platform = SourcePlatform.TRANSLATION
        item.content_type = ContentType.TRANSLATION
        item.raw_text = artifact.source_text
        item.clean_content = normalize_text(artifact.source_text)
        item.raw_excerpt = artifact.source_text[:200]
        item.summary = f"原链接：\n{url}\n\n一句话总结：\n翻译任务已完成\n"
        item.category = "英语学习"
        item.category_level_1 = "学习"
        item.category_level_2 = "翻译"
        item.tags = "翻译,中文译文"
        item.original_language = "en"
        item.is_translated = True
        item.translated_text_path = translated_file_path
        item.translation_status = TranslationStatus.TRANSLATED
        item.process_status = ProcessStatus.COMPLETED
        item.fetch_status = StageStatus.SUCCESS
        item.ai_status = StageStatus.SUCCESS
        if item.notion_sync_status == NotionSyncStatus.FAILED:
            item.notion_sync_status = NotionSyncStatus.PENDING
            item.notion_error_message = ""
        self.item_service.save(db, item)
        return self.item_service.attempt_notion_sync(db, item)

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
            input_type=InputType.URL if source_url else InputType.TEXT,
            title=title,
            source_url=source_url or None,
            normalized_url=normalize_url(source_url) if source_url else None,
            content_hash=content_hash(raw_text) if not source_url else None,
            source_platform=SourcePlatform.TRANSLATION,
            content_type=ContentType.TRANSLATION,
            raw_text=raw_text,
            clean_content=normalize_text(raw_text),
            raw_excerpt=source_text[:200],
            summary=f"原链接：\n{source_url or 'N/A'}\n\n一句话总结：\n翻译任务已完成\n",
            category="英语学习",
            tags="翻译,中文译文",
            author=author,
            published_at=published_at,
            translated_text_path=translated_file_path,
            translation_status=TranslationStatus.TRANSLATED,
            process_status=ProcessStatus.COMPLETED,
            fetch_status=StageStatus.SUCCESS if source_url else StageStatus.SKIPPED,
            ai_status=StageStatus.SKIPPED,
        )
        return item, translated_text

    def _invoke_skill(self, text: str) -> str:
        try:
            module = import_module("skills.translation_skill")
            translate_text = getattr(module, "translate_text")
            return str(translate_text(text=text, source_lang="auto", target_lang="zh-CN"))
        except Exception as exc:
            raise TranslationError(f"Translation skill failed: {exc}") from exc

    def _run_global_translation_pipeline(self, url: str) -> TranslationArtifact:
        script_path = self.settings.base_dir / "skills" / "global-tech-translation" / "scripts" / "run_translation_pipeline.py"
        if not script_path.exists():
            raise TranslationError(f"翻译流水线脚本不存在：{script_path}")
        command = [
            sys.executable,
            str(script_path),
            "--url",
            url,
            "--mode",
            "deep",
            "--translator",
            "auto",
            "--output-dir",
            str(self.settings.translation_output_path),
            "--gemini-api-key",
            self.settings.gemini_api_key,
        ]
        try:
            result = subprocess.run(
                command,
                cwd=str(self.settings.base_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.settings.translation_task_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TranslationError("翻译任务超时，请稍后重试或缩短文章长度") from exc
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "unknown error").strip()
            raise TranslationError(f"翻译流水线失败：{message}")

        fields = self._parse_pipeline_stdout(result.stdout)
        try:
            article_dir = Path(fields["output_dir"])
            source_path = Path(fields["source_markdown"])
            translation_path = Path(fields["translation_markdown"])
            qa_path = Path(fields["qa_report"])
        except KeyError as exc:
            raise TranslationError(f"翻译流水线输出缺少字段：{exc.args[0]}") from exc
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        source_meta, source_body = self._read_frontmatter(source_path)
        return TranslationArtifact(
            article_id=fields.get("article_id", ""),
            article_dir=article_dir,
            source_path=source_path,
            translation_path=translation_path,
            qa_path=qa_path,
            title=source_meta.get("title", "") or article_dir.name,
            source_text=source_body,
            qa=qa,
        )

    def _validate_artifact(self, artifact: TranslationArtifact) -> None:
        if not artifact.translation_path.exists():
            raise TranslationError(f"翻译文件未生成：{artifact.translation_path}")
        if artifact.qa.get("resolved_translator") == "codex":
            raise TranslationError("翻译流水线进入 Codex 接管模式，未生成可交付译文")
        if artifact.qa.get("requires_agent_completion"):
            raise TranslationError("翻译流水线需要人工或 Codex 接管，未生成可交付译文")
        if artifact.qa.get("verdict") != "ready":
            issues = "; ".join(str(item) for item in artifact.qa.get("issues", []))
            raise TranslationError(f"翻译质检未通过：{artifact.qa.get('verdict') or 'unknown'} {issues}".strip())
        if not artifact.translation_path.read_text(encoding="utf-8").strip():
            raise TranslationError("翻译文件为空")

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.settings.base_dir))
        except ValueError:
            return str(path)

    @staticmethod
    def _parse_pipeline_stdout(stdout: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for line in stdout.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
        return fields

    @staticmethod
    def _read_frontmatter(path: Path) -> tuple[dict[str, str], str]:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return {}, text
        parts = text.split("---\n", 2)
        if len(parts) < 3:
            return {}, text
        meta: dict[str, str] = {}
        for line in parts[1].splitlines():
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            meta[key.strip()] = value.strip().strip('"')
        return meta, parts[2].lstrip("\n")
