from __future__ import annotations

from pathlib import Path
from typing import Any

from app.video.common import read_json, write_json


class FrameOcr:
    def __init__(self) -> None:
        self._engine: Any = None
        self._backend = ""

    def analyze(self, frames_dir: Path, output_path: Path) -> list[dict[str, Any]]:
        frames = read_json(frames_dir / "frames.json", [])
        if self._engine is None:
            self._engine, self._backend = self._load_engine()
        rows: list[dict[str, Any]] = []
        for frame in frames:
            text = self._read_text(frames_dir / str(frame["frame"]))
            rows.append({"frame": frame["frame"], "timestamp": frame["timestamp"], "time": frame["time"], "text": text})
        write_json(output_path, rows)
        return rows

    def _load_engine(self) -> tuple[Any, str]:
        try:
            from paddleocr import PaddleOCR

            return PaddleOCR(use_angle_cls=True, lang="ch"), "paddleocr"
        except Exception:
            from rapidocr import RapidOCR

            return RapidOCR(), "rapidocr"

    def _read_text(self, image_path: Path) -> str:
        try:
            if self._backend == "paddleocr":
                result = self._engine.ocr(str(image_path), cls=True)
                parts = []
                for group in result or []:
                    for line in group or []:
                        if len(line) >= 2:
                            parts.append(str(line[1][0]).strip())
                return "\n".join(part for part in parts if part)
            result = self._engine(str(image_path))
            parts = []
            boxes = getattr(result, "txts", None) or (result[0] if isinstance(result, tuple) and result else [])
            for value in boxes or []:
                if isinstance(value, str):
                    parts.append(value.strip())
                elif isinstance(value, (list, tuple)) and value:
                    parts.append(str(value[0]).strip())
            return "\n".join(part for part in parts if part)
        except Exception:
            return ""
