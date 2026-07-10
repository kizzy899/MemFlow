from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.video.common import run_ffmpeg, write_json


def platform_from_url(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith("xiaohongshu.com") or host.endswith("xhslink.com"):
        return "xiaohongshu"
    if host.endswith("douyin.com"):
        return "douyin"
    if host.endswith("bilibili.com") or host == "b23.tv":
        return "bilibili"
    if host.endswith("youtube.com") or host == "youtu.be":
        return "youtube"
    return "web"


def is_video_url(url: str) -> bool:
    return platform_from_url(url) in {"xiaohongshu", "douyin", "bilibili", "youtube"}


def metadata_from_info(url: str, info: dict[str, Any], duration: float | None = None) -> dict[str, Any]:
    return {
        "title": str(info.get("title") or ""),
        "author": str(info.get("uploader") or info.get("creator") or info.get("channel") or ""),
        "publish_time": str(info.get("upload_date") or info.get("timestamp") or ""),
        "duration": float(info.get("duration") or duration or 0),
        "platform": platform_from_url(url),
        "url": url,
    }


def probe_duration(video_path: Path, timeout: int = 30) -> float:
    try:
        import cv2

        capture = cv2.VideoCapture(str(video_path))
        fps = capture.get(cv2.CAP_PROP_FPS) or 0
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        capture.release()
        return float(frames / fps) if fps else 0.0
    except Exception:
        return 0.0


def save_metadata(path: Path, metadata: dict[str, Any]) -> None:
    write_json(path, metadata)
