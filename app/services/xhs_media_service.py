from __future__ import annotations

import json
import importlib.util
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from app.config import Settings


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


class MediaProviderError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass
class MediaFetchResult:
    provider: str
    note_url: str
    video_paths: list[Path] = field(default_factory=list)
    image_paths: list[Path] = field(default_factory=list)
    status: str = "empty"
    warnings: list[str] = field(default_factory=list)


class XhsMediaProvider(Protocol):
    name: str

    def fetch(self, note_url: str, direct_video_url: str, workspace: Path, cancel_event: threading.Event) -> MediaFetchResult: ...


def _safe_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _validate_note_url(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "https" or not (parts.hostname or "").endswith("xiaohongshu.com"):
        raise MediaProviderError("INVALID_NOTE_URL", "只允许处理小红书 HTTPS 笔记链接", False)


class BrowserMediaProvider:
    name = "browser"

    def fetch(self, note_url: str, direct_video_url: str, workspace: Path, cancel_event: threading.Event) -> MediaFetchResult:
        if not direct_video_url.startswith(("http://", "https://")):
            raise MediaProviderError("BROWSER_MEDIA_EMPTY", "浏览器详情页未提供可下载视频地址")
        if cancel_event.is_set():
            raise MediaProviderError("TASK_CANCELLED", "任务已取消", False)
        from yt_dlp import YoutubeDL

        output = workspace / "browser-source.%(ext)s"
        options = {"quiet": True, "no_warnings": True, "format": "best[ext=mp4]/best", "outtmpl": str(output), "noplaylist": True}
        try:
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(direct_video_url, download=True)
                path = Path(downloader.prepare_filename(info)).resolve()
        except Exception as exc:
            raise MediaProviderError("MEDIA_DOWNLOAD_BLOCKED", f"浏览器视频下载失败：{type(exc).__name__}") from exc
        _assert_inside(path, workspace)
        return MediaFetchResult(self.name, note_url, [path], status="success")


class OpenCliMediaProvider:
    name = "opencli"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.command = shutil.which(settings.opencli_command)
        self._verified = False
        self._disabled_reason = ""

    def health(self) -> dict[str, Any]:
        if not self.command:
            return {"installed": False, "available": False, "version": "", "message": "OpenCLI 未安装"}
        try:
            result = subprocess.run([self.command, "--version"], capture_output=True, text=True, timeout=10, check=False)
            installed = result.returncode == 0
            return {"installed": True, "available": installed and self._verified and not self._disabled_reason, "verified": self._verified, "version": result.stdout.strip(), "message": self._disabled_reason or ("媒体下载已验证" if self._verified else "已安装，等待真实媒体下载验证")}
        except Exception as exc:
            return {"installed": True, "available": False, "version": "", "message": type(exc).__name__}

    def fetch(self, note_url: str, direct_video_url: str, workspace: Path, cancel_event: threading.Event) -> MediaFetchResult:
        _validate_note_url(note_url)
        if not self.command:
            raise MediaProviderError("OPENCLI_NOT_INSTALLED", "OpenCLI 未安装", False)
        if self._disabled_reason:
            raise MediaProviderError("OPENCLI_CIRCUIT_OPEN", self._disabled_reason, False)
        env = os.environ.copy()
        env["OPENCLI_CDP_ENDPOINT"] = self.settings.chrome_cdp_url
        args = [self.command, "xiaohongshu", "download", note_url, "--output", str(workspace), "--format", "json"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        deadline = time.monotonic() + 90
        while process.poll() is None:
            if cancel_event.is_set():
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill()
                raise MediaProviderError("TASK_CANCELLED", "任务已取消", False)
            if time.monotonic() >= deadline:
                process.kill()
                self._disabled_reason = "OpenCLI 本批次下载超时，已熔断后续调用"
                raise MediaProviderError("MEDIA_DOWNLOAD_TIMEOUT", "OpenCLI 下载超过 90 秒")
            time.sleep(0.2)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            combined = f"{stdout} {stderr}".lower()
            if process.returncode == 77 or "auth" in combined or "login" in combined:
                code, message, retryable = "OPENCLI_AUTH_REQUIRED", "OpenCLI 无法使用当前 Chrome 登录态", False
            elif process.returncode == 69:
                code, message, retryable = "OPENCLI_BRIDGE_UNAVAILABLE", "OpenCLI 无法连接 Chrome CDP", True
            elif process.returncode == 66:
                code, message, retryable = "OPENCLI_EMPTY_RESULT", "OpenCLI 未返回媒体文件", True
            else:
                code, message, retryable = "MEDIA_DOWNLOAD_BLOCKED", f"OpenCLI 下载失败（退出码 {process.returncode}）", True
            if code in {"OPENCLI_AUTH_REQUIRED", "OPENCLI_BRIDGE_UNAVAILABLE"}:
                self._disabled_reason = message + "，本批次已停止继续调用"
            raise MediaProviderError(code, message, retryable)
        videos, images = _media_files(workspace)
        if not videos and not images:
            raise MediaProviderError("OPENCLI_EMPTY_RESULT", "OpenCLI 未生成媒体文件")
        self._verified = True
        return MediaFetchResult(self.name, note_url, videos, images, "success")


def _assert_inside(path: Path, workspace: Path) -> None:
    root, candidate = workspace.resolve(), path.resolve()
    if candidate != root and root not in candidate.parents:
        raise MediaProviderError("MEDIA_PATH_ESCAPE", "媒体输出路径超出任务目录", False)


def _media_files(workspace: Path) -> tuple[list[Path], list[Path]]:
    videos, images = [], []
    for path in workspace.rglob("*"):
        if not path.is_file(): continue
        resolved = path.resolve(); _assert_inside(resolved, workspace)
        if resolved.suffix.lower() in VIDEO_SUFFIXES: videos.append(resolved)
        elif resolved.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}: images.append(resolved)
    return videos, images


class AudioTranscriptionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def transcribe(self, path: Path, cancel_event: threading.Event) -> dict[str, Any]:
        if cancel_event.is_set(): return {"status": "cancelled", "text": "", "segments": [], "error": "任务已取消"}
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                self.settings.whisper_model_path.mkdir(parents=True, exist_ok=True)
                self._model = WhisperModel(self.settings.whisper_model, device=self.settings.whisper_device, compute_type=self.settings.whisper_compute_type, download_root=str(self.settings.whisper_model_path))
            try:
                segments, info = self._model.transcribe(str(path), beam_size=5, vad_filter=True)
                rows = []
                for segment in segments:
                    if cancel_event.is_set(): return {"status": "cancelled", "text": "", "segments": rows, "error": "任务已取消"}
                    text = str(segment.text or "").strip()
                    if text: rows.append({"start": round(segment.start, 3), "end": round(segment.end, 3), "text": text})
                text = "\n".join(row["text"] for row in rows)
                return {"status": "success" if text else "empty", "language": getattr(info, "language", ""), "text": text, "segments": rows, "model": self.settings.whisper_model, "error": None}
            except Exception as exc:
                return {"status": "failed", "text": "", "segments": [], "model": self.settings.whisper_model, "error": type(exc).__name__}


class VideoContentAssembler:
    AI_LIMIT = 60_000

    @staticmethod
    def assemble(body: str, ocr: dict[str, Any], transcript: dict[str, Any], resources: list[dict[str, str]], warnings: list[str]) -> tuple[str, str]:
        blocks = []
        if body.strip(): blocks.append("[笔记正文]\n" + body.strip())
        if ocr.get("text"): blocks.append("[视频画面 OCR]\n" + str(ocr["text"]).strip())
        if transcript.get("text"): blocks.append("[视频语音转录]\n" + str(transcript["text"]).strip())
        if resources: blocks.append("[视频中识别到的资源链接]\n" + "\n".join(f"{r.get('label') or '名称待确认'}｜{r['url']}" for r in resources if r.get("url")))
        if warnings: blocks.append("[提取警告]\n" + "\n".join(dict.fromkeys(warnings)))
        full = "\n\n".join(blocks)
        if len(full) <= VideoContentAssembler.AI_LIMIT: return full, full
        marker = "\n\n[提取警告]\nAI 输入超过 60000 字符，已截断；本地 raw_text 保留完整内容。"
        return full, full[: VideoContentAssembler.AI_LIMIT - len(marker)] + marker


class XhsMediaPipeline:
    def __init__(self, settings: Settings, agent_search_service, transcription_service: AudioTranscriptionService | None = None) -> None:
        self.settings = settings
        self.agent_search_service = agent_search_service
        self.transcription_service = transcription_service or AudioTranscriptionService(settings)
        self.opencli = OpenCliMediaProvider(settings)
        self.providers: list[XhsMediaProvider] = [BrowserMediaProvider(), self.opencli]
        self._ocr_lock = threading.Lock()

    def provider_status(self) -> dict[str, Any]:
        return {"browser": {"installed": True, "available": True, "message": "使用当前 CDP 会话"}, "opencli": self.opencli.health(), "whisper": {"installed": importlib.util.find_spec("faster_whisper") is not None, "model": self.settings.whisper_model, "device": self.settings.whisper_device}}

    def process(self, note_url: str, direct_video_url: str, body: str, progress, cancel_event: threading.Event) -> dict[str, Any]:
        task_dir = self.settings.xhs_media_temp_path / uuid.uuid4().hex
        task_dir.mkdir(parents=True, exist_ok=True)
        warnings, media = [], None
        try:
            for provider in self.providers:
                try:
                    progress({"step": "fetching_media" if provider.name == "browser" else "opencli_download", "message": f"正在通过 {provider.name} 获取视频", "page_url": _safe_url(note_url)})
                    media = provider.fetch(note_url, direct_video_url, task_dir, cancel_event)
                    if media.video_paths: break
                except MediaProviderError as exc:
                    warnings.append(f"{exc.code}: {exc.message}")
                    if exc.code == "TASK_CANCELLED": raise
            if not media or not media.video_paths:
                full, ai_text = VideoContentAssembler.assemble(body, {}, {}, [], warnings)
                return {"raw_text": full, "ai_text": ai_text, "media_provider": media.provider if media else "", "media_fetch_status": "failed", "ocr_status": "skipped", "transcription_status": "skipped", "content_completeness": "partial", "media_error_message": "；".join(warnings)}
            video = media.video_paths[0]
            duration = self._duration(video)
            if duration > self.settings.video_max_duration_seconds:
                warnings.append("VIDEO_TOO_LONG: 视频超过 30 分钟，已跳过 OCR 和语音转写")
                full, ai_text = VideoContentAssembler.assemble(body, {}, {}, [], warnings)
                return {"raw_text": full, "ai_text": ai_text, "media_provider": media.provider, "media_fetch_status": "success", "ocr_status": "skipped", "transcription_status": "skipped", "content_completeness": "partial", "media_error_message": "；".join(warnings)}

            def ocr_job():
                if not self.settings.video_ocr_enabled: return {"status": "skipped", "text": "", "resources": []}
                progress({"step": "video_ocr", "message": "正在识别视频画面文字"})
                with self._ocr_lock:
                    result = self.agent_search_service.extract("video", str(video), 1.0, 1800)
                return {"status": "success" if result.get("text") else "empty", "text": result.get("text", ""), "resources": result.get("resources", []), "error": (result.get("errors") or [None])[0]}

            def transcript_job():
                if not self.settings.video_transcription_enabled: return {"status": "skipped", "text": "", "segments": []}
                progress({"step": "audio_transcription", "message": "正在使用 Whisper 提取视频语音"})
                return self.transcription_service.transcribe(video, cancel_event)

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="xhs-media") as executor:
                ocr_future, transcript_future = executor.submit(ocr_job), executor.submit(transcript_job)
                ocr, transcript = ocr_future.result(timeout=self.settings.video_step_timeout_seconds), transcript_future.result(timeout=self.settings.video_step_timeout_seconds)
            if ocr.get("error"): warnings.append("OCR_FAILED: 画面文字提取失败")
            if transcript.get("error") and transcript.get("status") != "cancelled": warnings.append("TRANSCRIPTION_FAILED: " + str(transcript["error"])[:180])
            progress({"step": "assembling_content", "message": "正在合并正文、OCR 与语音转录"})
            full, ai_text = VideoContentAssembler.assemble(body, ocr, transcript, ocr.get("resources", []), warnings)
            complete = "complete" if (ocr.get("text") or transcript.get("text")) and body.strip() else "partial"
            return {"raw_text": full, "ai_text": ai_text, "media_provider": media.provider, "media_fetch_status": "success", "ocr_status": ocr.get("status", "failed"), "transcription_status": transcript.get("status", "failed"), "content_completeness": complete, "media_error_message": "；".join(warnings)}
        finally:
            shutil.rmtree(task_dir, ignore_errors=True)

    @staticmethod
    def _duration(path: Path) -> float:
        import cv2
        capture = cv2.VideoCapture(str(path))
        fps, frames = capture.get(cv2.CAP_PROP_FPS) or 0, capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        capture.release()
        return frames / fps if fps else 0
