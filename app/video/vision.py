from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import Settings
from app.video.common import read_json, write_json


class FrameVisionAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def analyze(self, frames_dir: Path, output_path: Path, sample_every: int = 1) -> list[dict[str, Any]]:
        frames = read_json(frames_dir / "frames.json", [])
        rows: list[dict[str, Any]] = []
        for index, frame in enumerate(frames):
            description = ""
            if sample_every <= 1 or index % sample_every == 0:
                description = self._describe(frames_dir / str(frame["frame"]))
            rows.append(
                {
                    "frame": frame["frame"],
                    "timestamp": frame["timestamp"],
                    "time": frame["time"],
                    "description": description,
                }
            )
        write_json(output_path, rows)
        return rows

    def _describe(self, image_path: Path) -> str:
        if not self.settings.openai_api_key or not self.settings.video_vision_enabled:
            return ""
        client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None)
        image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        response = client.chat.completions.create(
            model=self.settings.video_vision_model or self.settings.openai_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "用一句中文描述这一帧中发生了什么，重点关注操作、界面、工具和可见文字。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=120,
        )
        return str(response.choices[0].message.content or "").strip()
