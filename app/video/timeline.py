from __future__ import annotations

from pathlib import Path
from typing import Any

from app.video.common import read_json, seconds_to_stamp, write_json


def build_timeline(subtitle_path: Path, ocr_path: Path, vision_path: Path, output_path: Path) -> list[dict[str, Any]]:
    subtitles = read_json(subtitle_path, [])
    ocr_rows = read_json(ocr_path, [])
    vision_rows = read_json(vision_path, [])
    buckets: dict[int, dict[str, Any]] = {}

    def bucket_at(seconds: float) -> dict[str, Any]:
        key = int(round(seconds))
        return buckets.setdefault(key, {"time": seconds_to_stamp(key), "speech": "", "screen": "", "vision": ""})

    for row in subtitles:
        start = float(row.get("start") or 0)
        bucket = bucket_at(start)
        bucket["speech"] = _join(bucket["speech"], str(row.get("text") or ""))
    for row in ocr_rows:
        bucket = bucket_at(float(row.get("timestamp") or 0))
        bucket["screen"] = _join(bucket["screen"], str(row.get("text") or ""))
    for row in vision_rows:
        bucket = bucket_at(float(row.get("timestamp") or 0))
        bucket["vision"] = _join(bucket["vision"], str(row.get("description") or ""))

    timeline = [buckets[key] for key in sorted(buckets)]
    write_json(output_path, timeline)
    return timeline


def _join(left: str, right: str) -> str:
    right = right.strip()
    if not right:
        return left
    if not left:
        return right
    if right in left:
        return left
    return f"{left}\n{right}"
