from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.video.audio import extract_audio
from app.video.common import copy_tree_contents, ensure_dirs, read_json, stable_hash, write_json
from app.video.downloader import VideoDownloader
from app.video.frames import extract_frames
from app.video.metadata import is_video_url
from app.video.ocr import FrameOcr
from app.video.summarize import VideoSummarizer
from app.video.timeline import build_timeline
from app.video.vision import FrameVisionAnalyzer
from app.video.whisper import WhisperTranscriber


@dataclass
class VideoPipelineResult:
    metadata: dict[str, Any]
    summary_markdown: str
    workspace: Path
    video_path: Path | None
    audio_path: Path | None
    subtitle_path: Path
    ocr_path: Path
    vision_path: Path
    timeline_path: Path
    summary_path: Path
    warnings: list[str]
    statuses: dict[str, str]
    from_cache: bool = False

    @property
    def ai_text(self) -> str:
        timeline = read_json(self.timeline_path, [])
        return self.summary_markdown + "\n\n[timeline.json]\n" + "\n".join(
            f"{row.get('time')} speech={row.get('speech','')} screen={row.get('screen','')} vision={row.get('vision','')}"
            for row in timeline[:300]
        )


class VideoPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.downloader = VideoDownloader(settings.video_download_timeout_seconds)
        self.transcriber = WhisperTranscriber(settings)
        self.ocr = FrameOcr()
        self.vision = FrameVisionAnalyzer(settings)
        self.summarizer = VideoSummarizer(settings)

    def can_process(self, url: str) -> bool:
        return is_video_url(url)

    def process(self, url: str) -> VideoPipelineResult:
        url_hash = stable_hash(url)
        workspace = self.settings.video_output_path / url_hash
        cache_dir = self.settings.video_cache_path / url_hash
        if (cache_dir / "summary.md").exists() and (cache_dir / "timeline.json").exists():
            copy_tree_contents(cache_dir, workspace)
            return self._result_from_workspace(workspace, from_cache=True)

        ensure_dirs(workspace, workspace / "videos", workspace / "audio", workspace / "frames", self.settings.video_cache_path)
        statuses: dict[str, str] = {}
        warnings: list[str] = []
        video_path: Path | None = None
        audio_path: Path | None = None

        try:
            video_path, metadata = self.downloader.download(url, workspace / "videos")
            statuses["download"] = "success" if video_path else "empty"
            if not video_path:
                warnings.append("Download unavailable")
        except Exception as exc:
            metadata = {"title": "", "author": "", "publish_time": "", "duration": 0, "platform": "", "url": url}
            statuses["download"] = "failed"
            warnings.append(f"Download unavailable: {type(exc).__name__}: {exc}")
        write_json(workspace / "metadata.json", metadata)

        if video_path:
            try:
                audio_path = extract_audio(video_path, workspace / "audio", self.settings.video_step_timeout_seconds)
                statuses["audio"] = "success"
            except Exception as exc:
                statuses["audio"] = "failed"
                warnings.append(f"Audio unavailable: {type(exc).__name__}: {exc}")

        subtitle_path = workspace / "audio" / "subtitle.json"
        if audio_path:
            try:
                result = self.transcriber.transcribe(audio_path, workspace / "audio")
                statuses["whisper"] = str(result.get("status") or "failed")
            except Exception as exc:
                write_json(subtitle_path, [])
                (workspace / "audio" / "subtitle.txt").write_text("", encoding="utf-8")
                (workspace / "audio" / "subtitle.srt").write_text("", encoding="utf-8")
                statuses["whisper"] = "failed"
                warnings.append(f"Whisper unavailable: {type(exc).__name__}: {exc}")
        else:
            write_json(subtitle_path, [])
            statuses["whisper"] = "skipped"

        if video_path:
            try:
                extract_frames(video_path, workspace / "frames", self.settings.video_frame_interval_seconds, self.settings.video_step_timeout_seconds)
                statuses["frames"] = "success"
            except Exception as exc:
                write_json(workspace / "frames" / "frames.json", [])
                statuses["frames"] = "failed"
                warnings.append(f"Frames unavailable: {type(exc).__name__}: {exc}")

        ocr_path = workspace / "ocr.json"
        try:
            rows = self.ocr.analyze(workspace / "frames", ocr_path)
            statuses["ocr"] = "success" if any(row.get("text") for row in rows) else "empty"
        except Exception as exc:
            write_json(ocr_path, [])
            statuses["ocr"] = "failed"
            warnings.append(f"OCR unavailable: {type(exc).__name__}: {exc}")

        vision_path = workspace / "vision.json"
        try:
            rows = self.vision.analyze(workspace / "frames", vision_path, self.settings.video_vision_sample_every)
            statuses["vision"] = "success" if any(row.get("description") for row in rows) else "empty"
            if statuses["vision"] == "empty":
                warnings.append("Vision unavailable")
        except Exception as exc:
            write_json(vision_path, [])
            statuses["vision"] = "failed"
            warnings.append(f"Vision unavailable: {type(exc).__name__}: {exc}")

        timeline_path = workspace / "timeline.json"
        timeline = build_timeline(subtitle_path, ocr_path, vision_path, timeline_path)
        statuses["timeline"] = "success" if timeline else "empty"

        summary_path = workspace / "summary.md"
        summary = self.summarizer.summarize(metadata, timeline_path, subtitle_path, ocr_path, warnings, summary_path)
        write_json(workspace / "status.json", {"statuses": statuses, "warnings": warnings})
        copy_tree_contents(workspace, cache_dir)
        return VideoPipelineResult(metadata, summary, workspace, video_path, audio_path, subtitle_path, ocr_path, vision_path, timeline_path, summary_path, warnings, statuses)

    def _result_from_workspace(self, workspace: Path, from_cache: bool) -> VideoPipelineResult:
        metadata = read_json(workspace / "metadata.json", {})
        status = read_json(workspace / "status.json", {"statuses": {}, "warnings": []})
        summary_path = workspace / "summary.md"
        return VideoPipelineResult(
            metadata=metadata,
            summary_markdown=summary_path.read_text(encoding="utf-8") if summary_path.exists() else "",
            workspace=workspace,
            video_path=workspace / "videos" / "video.mp4" if (workspace / "videos" / "video.mp4").exists() else None,
            audio_path=workspace / "audio" / "audio.wav" if (workspace / "audio" / "audio.wav").exists() else None,
            subtitle_path=workspace / "audio" / "subtitle.json",
            ocr_path=workspace / "ocr.json",
            vision_path=workspace / "vision.json",
            timeline_path=workspace / "timeline.json",
            summary_path=summary_path,
            warnings=list(status.get("warnings") or []),
            statuses=dict(status.get("statuses") or {}),
            from_cache=from_cache,
        )
