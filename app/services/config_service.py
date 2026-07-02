from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings


class ConfigService:
    ALLOWED = {"NOTION_API_KEY", "NOTION_DATABASE_ID"}

    def __init__(self, root: Path, settings: Settings) -> None:
        self.root = root
        self.env_path = root / ".env"
        self.settings = settings
        self.xhs_check: dict[str, Any] = {"status": "unknown", "message": "尚未检测"}
        self.notion_check: dict[str, Any] = {"status": "unknown", "message": "尚未检测"}

    def update(self, values: dict[str, str]) -> None:
        updates = {key: value for key, value in values.items() if key in self.ALLOWED and str(value).strip()}
        if updates:
            self._write(updates)

    def clear(self, keys: set[str]) -> None:
        self._write({key: "" for key in keys if key in self.ALLOWED})

    def _write(self, updates: dict[str, str]) -> None:
        lines = self.env_path.read_text(encoding="utf-8-sig").splitlines() if self.env_path.exists() else []
        seen: set[str] = set(); output: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output.append(line); continue
            key = line.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={json.dumps(str(updates[key]), ensure_ascii=False)}"); seen.add(key)
            else:
                output.append(line)
        for key, value in updates.items():
            if key not in seen: output.append(f"{key}={json.dumps(str(value), ensure_ascii=False)}")
        temp = self.env_path.with_name(f".env.{uuid.uuid4().hex}.tmp")
        temp.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
        os.replace(temp, self.env_path)

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> dict[str, Any]:
        s = self.settings
        return {
            "notion": {
                "configured": bool(s.notion_api_key and s.notion_database_id),
                "token_saved": bool(s.notion_api_key),
                "token_length": len(s.notion_api_key),
                "database_id": s.notion_database_id,
                "check": self.notion_check,
            },
        }

    @staticmethod
    def _mask(value: str) -> str:
        if not value: return ""
        if len(value) <= 2: return "*" * len(value)
        return value[0] + "*" * min(6, len(value) - 2) + value[-1]
