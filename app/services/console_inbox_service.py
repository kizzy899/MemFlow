from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from app.services.link_archive_service import FAILURE_PREFIX, TRAILING, URL_RE, FileLock, InboxBlock, parse_inbox, render_inbox, ArchiveRunError


class ConsoleInboxService:
    def __init__(self, root: Path) -> None:
        self.path = root / "inbox" / "links.md"
        self.backup = root / "inbox" / ".links.md.bak"
        self.lock = root / "inbox" / ".links.lock"

    def snapshot(self) -> dict[str, Any]:
        raw = self.path.read_text(encoding="utf-8-sig") if self.path.exists() else ""
        blocks = parse_inbox(raw)
        items = []
        for index, block in enumerate(blocks):
            failure = next((line[len(FAILURE_PREFIX):].strip() for line in block.text.splitlines() if line.strip().startswith(FAILURE_PREFIX)), "")
            items.append({"item_id": self._id(index, block), "content": block.source_text, "urls": block.urls, "status": "failed" if failure else "pending", "failure_reason": failure})
        return {"version": hashlib.sha256(raw.encode()).hexdigest(), "raw_content": raw, "pending_url_count": sum(len(x["urls"]) for x in items), "items": items}

    def append(self, content: str) -> dict[str, Any]:
        value = self._prepare_content(content)
        if not value: raise ValueError("content 不能为空")
        if len(value) > 100_000: raise ValueError("content 不能超过 100000 字符")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists(): self.path.write_text("", encoding="utf-8")
        with FileLock(self.lock):
            shutil.copy2(self.path, self.backup)
            current = self.path.read_text(encoding="utf-8-sig").rstrip()
            self._write((current + "\n\n" if current else "") + value + "\n")
        return self.snapshot()

    def delete(self, item_id: str, version: str) -> dict[str, Any]:
        with FileLock(self.lock):
            current = self.snapshot()
            if current["version"] != version: raise ArchiveRunError("inbox 已变化，请刷新后重试")
            blocks = parse_inbox(current["raw_content"])
            index = next((i for i, block in enumerate(blocks) if self._id(i, block) == item_id), None)
            if index is None: raise KeyError("待处理内容不存在")
            shutil.copy2(self.path, self.backup)
            del blocks[index]; self._write(render_inbox(blocks))
        return self.snapshot()


    @staticmethod
    def _prepare_content(content: str) -> str:
        """Keep one text paste atomic; render pure URL lists as blank-line-separated blocks."""
        value = content.strip()
        if not value:
            return ""
        nonempty = [line.strip() for line in value.splitlines() if line.strip()]
        pure_urls = bool(nonempty) and all(
            URL_RE.fullmatch((line[2:].strip() if line.startswith("- ") else line).rstrip(TRAILING))
            for line in nonempty
        )
        if pure_urls:
            return "\n\n".join(nonempty)
        return re.sub(r"\s+", " ", value)
    def _write(self, content: str) -> None:
        temp = self.path.with_name(f".links.{uuid.uuid4().hex}.tmp")
        temp.write_text(content, encoding="utf-8"); os.replace(temp, self.path)

    @staticmethod
    def _id(index: int, block: InboxBlock) -> str:
        return hashlib.sha256(f"{index}\0{block.text}".encode()).hexdigest()[:20]