from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from app.video.common import ensure_dirs, file_sha256, write_json
from app.video.metadata import metadata_from_info, probe_duration


class VideoDownloader:
    def __init__(self, timeout_seconds: int = 600) -> None:
        self.timeout_seconds = timeout_seconds

    def download(self, url: str, output_dir: Path) -> tuple[Path | None, dict[str, Any]]:
        ensure_dirs(output_dir)
        target_template = output_dir / "video.%(ext)s"
        options = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(target_template),
            "noplaylist": True,
            "socket_timeout": self.timeout_seconds,
        }
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            prepared = Path(downloader.prepare_filename(info))
        candidates = sorted(output_dir.glob("video.*"))
        video_path = next((path for path in candidates if path.suffix.lower() == ".mp4"), None)
        if not video_path and prepared.exists():
            video_path = prepared
        if not video_path:
            video_path = next((path for path in candidates if path.is_file()), None)
        if not video_path:
            return None, metadata_from_info(url, info or {})
        normalized = output_dir / "video.mp4"
        if video_path.resolve() != normalized.resolve():
            shutil.move(str(video_path), normalized)
        metadata = metadata_from_info(url, info or {}, probe_duration(normalized))
        metadata["video_hash"] = file_sha256(normalized)
        write_json(output_dir.parent / "metadata.json", metadata)
        return normalized, metadata
