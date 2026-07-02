from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


class AgentSearchService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        script = self.root / "skills/agent-search/scripts/agent_search.py"
        spec = importlib.util.spec_from_file_location("memflow_agent_search", script)
        if not spec or not spec.loader:
            raise RuntimeError("agent-search skill is unavailable")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def extract(self, source_type: str, source: str, interval: float = 2.0, max_frames: int = 300) -> dict[str, Any]:
        if source_type == "article":
            return self.module.read_article(source)
        path = Path(source)
        if not source.startswith(("http://", "https://")):
            resolved = path.resolve()
            if self.root not in resolved.parents:
                raise ValueError("local video must be inside the MemFlow workspace")
        return self.module.read_video(source, interval, max_frames)
