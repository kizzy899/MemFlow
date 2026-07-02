from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.content_item import ContentItem, ContentType, Importance, InputType, NotionSyncStatus, ProcessStatus, SourcePlatform, StageStatus
from app.services.ai_service import AIService
from app.services.archive_note_service import build_archive_markdown, parse_json
from app.services.item_service import ItemService
from app.services.link_archive_ai_service import LinkArchiveAIService
from app.services.link_reader_service import LinkFetchError, LinkParseError, LinkReaderService
from app.services.notion_service import NotionService
from app.services.taxonomy_service import normalize_category_level_1, normalize_category_level_2, normalize_keywords
from app.services.content_pipeline_service import ContentPipelineService
from app.utils.content_identity import normalize_url

logger = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING = ".,;:!?，。；：！？、)]}）】》"
FAILURE_PREFIX = "> 处理失败："
HOT_BEGIN = "<!-- MEMFLOW:HOT:BEGIN -->"
HOT_END = "<!-- MEMFLOW:HOT:END -->"


class ArchiveRunError(Exception):
    pass


@dataclass
class InboxBlock:
    text: str

    @property
    def source_text(self) -> str:
        return "\n".join(line for line in self.text.splitlines() if not line.strip().startswith(FAILURE_PREFIX)).strip()

    @property
    def urls(self) -> list[str]:
        result: list[str] = []
        for match in URL_RE.finditer(self.source_text):
            url = match.group(0).rstrip(TRAILING)
            if url and url not in result:
                result.append(url)
        return result

    def with_failure(self, reason: str, timestamp: str) -> "InboxBlock":
        lines = [line for line in self.text.splitlines() if not line.strip().startswith(FAILURE_PREFIX)]
        clean = " ".join(str(reason).split())[:500]
        return InboxBlock("\n".join(lines).rstrip() + f"\n{FAILURE_PREFIX}{clean}，时间：{timestamp}")


def parse_inbox(text: str) -> list[InboxBlock]:
    blocks: list[InboxBlock] = []
    paragraph: list[str] = []
    def flush() -> None:
        if paragraph:
            blocks.append(InboxBlock("\n".join(paragraph).strip()))
            paragraph.clear()
    for line in text.splitlines():
        stripped = line.strip()
        source = stripped[2:].strip() if stripped.startswith("- ") else stripped
        if not stripped:
            flush()
            continue
        if URL_RE.fullmatch(source.rstrip(TRAILING)):
            flush(); blocks.append(InboxBlock(line.strip())); continue
        if stripped.startswith(FAILURE_PREFIX) and blocks and not paragraph:
            blocks[-1] = InboxBlock(blocks[-1].text + "\n" + line.strip()); continue
        paragraph.append(line)
    flush()
    return blocks


def render_inbox(blocks: list[InboxBlock]) -> str:
    return ("\n\n".join(block.text.strip() for block in blocks if block.text.strip()) + "\n") if blocks else ""


class FileLock:
    def __init__(self, path: Path) -> None: self.path = path; self.fd: int | None = None
    def __enter__(self) -> "FileLock":
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, f"pid={os.getpid()} time={datetime.now(timezone.utc).isoformat()}".encode())
            return self
        except FileExistsError as exc:
            raise ArchiveRunError("归档任务正在运行，锁文件已存在") from exc
    def __exit__(self, *_: object) -> None:
        if self.fd is not None: os.close(self.fd)
        self.path.unlink(missing_ok=True)


class LinkArchiveService:
    def __init__(self, root: Path, reader: LinkReaderService, ai: AIService, archive_ai: LinkArchiveAIService, item_service: ItemService, notion: NotionService) -> None:
        self.root = root
        self.inbox = root / "inbox" / "links.md"
        self.backup = root / "inbox" / ".links.md.bak"
        self.lock = root / "inbox" / ".links.lock"
        self.hot = root / "hot.md"
        self.log = root / "logs" / "link-archive.jsonl"
        self.reader, self.ai, self.archive_ai, self.item_service, self.notion = reader, ai, archive_ai, item_service, notion

    def run(self, db: Session, progress=None) -> dict[str, Any]:
        if not self.inbox.exists(): raise ArchiveRunError("缺少 inbox/links.md")
        run_id = str(uuid.uuid4()); results: list[dict[str, Any]] = []; attempted: set[str] = set(); result_cache: dict[str, dict[str, Any]] = {}; successes: list[ContentItem] = []
        with FileLock(self.lock):
            shutil.copy2(self.inbox, self.backup)
            self.notion.ensure_archive_schema()
            while True:
                blocks = parse_inbox(self.inbox.read_text(encoding="utf-8-sig"))
                changed = False; progress_made = False; output: list[InboxBlock] = []
                for block in blocks:
                    urls = block.urls
                    block_results: list[dict[str, Any]] = []
                    sources = [(url, False) for url in urls] if urls else [(block.source_text, True)]
                    for source, is_text in sources:
                        if not source:
                            continue
                        url = "" if is_text else source
                        cache_key = f"text:{self._text_digest(source)}" if is_text else self._safe_normalize(url)
                        normalized = "" if is_text else cache_key
                        if cache_key in result_cache:
                            block_results.append(result_cache[cache_key])
                            continue
                        attempted.add(cache_key); progress_made = True
                        if progress: progress("processing", {"current_url": source[:200]})
                        result, item = self._process_text(db, source) if is_text else self._process_url(db, url, normalized)
                        if progress: progress("result", result)
                        result_cache[cache_key] = result
                        block_results.append(result); results.append(result); self._log(run_id, result)
                        if item and result["status"] == "processed": successes.append(item)
                    failed = [entry for entry in block_results if entry["status"].startswith("failed_")]
                    if failed:
                        reason = "；".join(f"{entry['original_url'] or '纯文字'}：{entry['message']}" for entry in failed)
                        output.append(block.with_failure(reason, datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")))
                        changed = True
                    elif block_results and all(entry["status"] in {"processed", "skipped_duplicate"} for entry in block_results):
                        changed = True
                    else:
                        output.append(block)
                if changed: self._atomic_write(render_inbox(output))
                if not progress_made: break
            remaining = len(parse_inbox(self.inbox.read_text(encoding="utf-8-sig")))
            hot_updated = bool(successes)
            if hot_updated: self._update_hot(successes, results, remaining)
        counts = {status: sum(x["status"] == status for x in results) for status in ("processed", "skipped_duplicate", "failed_fetch", "failed_parse", "failed_notion")}
        return {"run_id": run_id, **counts, "remaining": remaining, "hot_updated": hot_updated, "results": results}

    def _process_url(self, db: Session, original: str, normalized: str) -> tuple[dict[str, Any], ContentItem | None]:
        item = self.item_service.find_by_normalized_url(db, normalized)
        if item and item.notion_sync_status == NotionSyncStatus.SYNCED:
            return self._result(original, normalized, "skipped_duplicate", "SQLite 中已归档", item), item
        try:
            notion_page = self.notion.find_page_by_normalized_url(normalized)
        except Exception as exc:
            return self._result(original, normalized, "failed_notion", str(exc), item), item
        if notion_page:
            if item:
                item.notion_page_id = notion_page.get("id", "")
                item.notion_page_url = notion_page.get("url", "")
                item.notion_sync_status = NotionSyncStatus.SYNCED
                item.notion_error_message = ""
                self.item_service.save(db, item)
            return self._result(original, normalized, "skipped_duplicate", "Notion 中已归档", item, notion_page.get("url")), item
        if item and item.archive_markdown and item.ai_status == StageStatus.SUCCESS:
            return self._write_notion(db, item, original, normalized)
        if not item:
            item = ContentItem(input_type=InputType.URL, source_url=original, normalized_url=normalized, source_platform=ContentPipelineService.detect_platform(normalized), process_status=ProcessStatus.PROCESSING, fetch_status=StageStatus.SKIPPED, ai_status=StageStatus.SKIPPED, notion_sync_status=NotionSyncStatus.PENDING)
            self.item_service.save(db, item)
        try:
            readable = self.reader.read(original)
            item.raw_text = readable.content; item.clean_content = readable.content; item.title = readable.title
            item.author = readable.author; item.site_name = readable.site_name; item.source_type = readable.source_type; item.fetch_status = StageStatus.SUCCESS
            self.item_service.save(db, item)
        except LinkFetchError as exc:
            return self._fail(db, item, original, normalized, "failed_fetch", str(exc), fetch=True)
        except LinkParseError as exc:
            return self._fail(db, item, original, normalized, "failed_parse", str(exc), fetch=False)
        try:
            analysis = self.ai.analyze(original, item.title, item.clean_content)
            item.title = analysis.title; item.summary = analysis.summary
            item.core_points = json.dumps(analysis.core_points, ensure_ascii=False); item.action_items = json.dumps(analysis.action_items, ensure_ascii=False)
            item.category_level_1 = normalize_category_level_1(analysis.category_level_1); item.category = item.category_level_1
            item.category_level_2 = normalize_category_level_2(analysis.category_level_2, item.clean_content)
            item.tags = ",".join(normalize_keywords(analysis.keywords)); item.content_type = ContentType(analysis.content_type)
            item.importance = Importance(analysis.importance); item.original_language = analysis.original_language; item.is_translated = analysis.is_translated
            candidates = self._candidates(db, item)
            enrichment = self.archive_ai.enrich(item.title, item.clean_content, candidates)
            item.key_concepts = json.dumps([x.model_dump() for x in enrichment.key_concepts], ensure_ascii=False)
            item.related_entities = enrichment.entities.model_dump_json()
            item.knowledge_relations = json.dumps([x.model_dump() for x in enrichment.knowledge_relations], ensure_ascii=False)
            item.ai_status = StageStatus.SUCCESS; item.process_status = ProcessStatus.COMPLETED; item.archived_at = datetime.now(timezone.utc)
            item.archive_markdown = build_archive_markdown(item); item.error_message = ""; self.item_service.save(db, item)
        except Exception as exc:
            return self._fail(db, item, original, normalized, "failed_parse", f"AI 整理失败：{exc}", fetch=False)
        return self._write_notion(db, item, original, normalized)

    def _process_text(self, db: Session, text: str) -> tuple[dict[str, Any], ContentItem | None]:
        digest = self._text_digest(text)
        item = self.item_service.find_by_content_hash(db, digest)
        if item and item.notion_sync_status == NotionSyncStatus.SYNCED:
            return self._result("", "", "skipped_duplicate", "SQLite 中已有相同文字归档", item), item
        if item and item.archive_markdown and item.ai_status == StageStatus.SUCCESS:
            return self._write_notion(db, item, "", "")
        if not item:
            item = ContentItem(input_type=InputType.TEXT, content_hash=digest, source_platform=SourcePlatform.MANUAL, raw_text=text, clean_content=text, source_type="text", process_status=ProcessStatus.PROCESSING, fetch_status=StageStatus.SKIPPED, ai_status=StageStatus.SKIPPED, notion_sync_status=NotionSyncStatus.PENDING)
            self.item_service.save(db, item)
        try:
            analysis = self.ai.analyze("", item.title, item.clean_content)
            item.title = analysis.title; item.summary = analysis.summary
            item.core_points = json.dumps(analysis.core_points, ensure_ascii=False); item.action_items = json.dumps(analysis.action_items, ensure_ascii=False)
            item.category_level_1 = normalize_category_level_1(analysis.category_level_1); item.category = item.category_level_1
            item.category_level_2 = normalize_category_level_2(analysis.category_level_2, item.clean_content)
            item.tags = ",".join(normalize_keywords(analysis.keywords)); item.content_type = ContentType(analysis.content_type)
            item.importance = Importance(analysis.importance); item.original_language = analysis.original_language; item.is_translated = analysis.is_translated
            enrichment = self.archive_ai.enrich(item.title, item.clean_content, self._candidates(db, item))
            item.key_concepts = json.dumps([x.model_dump() for x in enrichment.key_concepts], ensure_ascii=False)
            item.related_entities = enrichment.entities.model_dump_json()
            item.knowledge_relations = json.dumps([x.model_dump() for x in enrichment.knowledge_relations], ensure_ascii=False)
            item.ai_status = StageStatus.SUCCESS; item.process_status = ProcessStatus.COMPLETED; item.archived_at = datetime.now(timezone.utc)
            item.archive_markdown = build_archive_markdown(item); item.error_message = ""; self.item_service.save(db, item)
        except Exception as exc:
            return self._fail(db, item, "", "", "failed_parse", f"AI 整理失败：{exc}", fetch=False)
        return self._write_notion(db, item, "", "")

    def _write_notion(self, db: Session, item: ContentItem, original: str, normalized: str) -> tuple[dict[str, Any], ContentItem]:
        try:
            page_id, page_url = self.notion.create_archive_page(item)
            item.notion_page_id = page_id; item.notion_page_url = page_url; item.notion_sync_status = NotionSyncStatus.SYNCED; item.notion_error_message = ""; self.item_service.save(db, item)
            return self._result(original, normalized, "processed", "归档成功", item), item
        except Exception as exc:
            item.notion_sync_status = NotionSyncStatus.FAILED; item.notion_error_message = str(exc); self.item_service.save(db, item)
            return self._result(original, normalized, "failed_notion", str(exc), item), item

    def _fail(self, db: Session, item: ContentItem, original: str, normalized: str, status: str, message: str, fetch: bool) -> tuple[dict[str, Any], ContentItem]:
        item.process_status = ProcessStatus.FAILED; item.error_message = message
        item.fetch_status = StageStatus.FAILED if fetch else item.fetch_status; item.ai_status = StageStatus.FAILED if not fetch else item.ai_status
        self.item_service.save(db, item); return self._result(original, normalized, status, message, item), item

    def _candidates(self, db: Session, item: ContentItem) -> list[dict[str, str]]:
        terms = item.tags_list()[:5]
        clauses = [ContentItem.category_level_1 == item.category_level_1]
        clauses.extend(ContentItem.tags.ilike(f"%{term}%") for term in terms)
        rows = db.scalars(select(ContentItem).where(ContentItem.id != item.id, ContentItem.process_status == ProcessStatus.COMPLETED, or_(*clauses)).order_by(ContentItem.updated_at.desc()).limit(10)).all()
        return [{"item_id": row.id, "title": row.title, "summary": row.summary[:500], "keywords": row.tags} for row in rows]

    def _atomic_write(self, text: str) -> None:
        temp = self.inbox.with_name(f".links.{uuid.uuid4().hex}.tmp")
        temp.write_text(text, encoding="utf-8"); os.replace(temp, self.inbox)

    def _update_hot(self, items: list[ContentItem], results: list[dict[str, Any]], remaining: int) -> None:
        concepts, entities = [], {"people": [], "organizations": [], "projects": [], "tools": []}
        for item in items:
            concepts.extend(x.get("name", "") for x in parse_json(item.key_concepts, []))
            data = parse_json(item.related_entities, {})
            for key in entities: entities[key].extend(data.get(key, []))
        unique = lambda values: list(dict.fromkeys(value for value in values if value))
        failures = [x for x in results if x["status"].startswith("failed_")]
        managed = [HOT_BEGIN, "## 新增重要概念", *([f"- {x}" for x in unique(concepts)] or ["- 无"]), "", "## 新增实体"]
        labels = (("人物", "people"), ("机构", "organizations"), ("项目", "projects"), ("工具", "tools"))
        managed += [f"- {label}：{'、'.join(unique(entities[key])) or '无'}" for label, key in labels]
        managed += ["", "## 当前任务进展", f"- 本轮成功归档：{len(items)}", f"- 剩余链接：{remaining}", "", "## 下一步待办"]
        managed += [f"- {x['original_url']}：{x['message']}" for x in failures] or ["- 继续补充 inbox/links.md"]
        managed += ["", "## 重要决策", "- 仅在 Notion 完整写入成功后移除 inbox 原文", HOT_END]
        old = self.hot.read_text(encoding="utf-8-sig") if self.hot.exists() else "# MemFlow Hot\n"
        region = "\n".join(managed)
        if HOT_BEGIN in old and HOT_END in old:
            old = old[:old.index(HOT_BEGIN)] + region + old[old.index(HOT_END)+len(HOT_END):]
        else: old = old.rstrip() + "\n\n" + region + "\n"
        temp = self.hot.with_name(f".hot.{uuid.uuid4().hex}.tmp")
        temp.write_text(old, encoding="utf-8")
        os.replace(temp, self.hot)

    def _log(self, run_id: str, result: dict[str, Any]) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        record = {"run_id": run_id, "time": datetime.now(timezone.utc).isoformat(), **result}
        with self.log.open("a", encoding="utf-8") as handle: handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _safe_normalize(url: str) -> str:
        try: return normalize_url(url)
        except ValueError: return url

    @staticmethod
    def _text_digest(text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _result(original: str, normalized: str, status: str, message: str, item: ContentItem | None = None, page_url: str | None = None) -> dict[str, Any]:
        return {"original_url": original, "normalized_url": normalized, "status": status, "message": " ".join(message.split())[:500], "item_id": item.id if item else None, "notion_page_url": page_url or (item.notion_page_url if item else None) or None}
