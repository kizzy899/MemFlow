from pathlib import Path
import threading

import pytest

from app.config import Settings
from app.services.xhs_media_service import MediaFetchResult, MediaProviderError, OpenCliMediaProvider, VideoContentAssembler, XhsMediaPipeline, _validate_note_url


class FailedProvider:
    name = "browser"
    def fetch(self, note_url, direct_video_url, workspace, cancel_event):
        raise MediaProviderError("BROWSER_MEDIA_EMPTY", "missing")


class SuccessfulProvider:
    name = "opencli"
    def fetch(self, note_url, direct_video_url, workspace, cancel_event):
        path = workspace / "video.mp4"; path.write_bytes(b"fake")
        return MediaFetchResult(self.name, note_url, [path], status="success")


class FakeAgentSearch:
    def extract(self, mode, source, interval, max_frames):
        assert mode == "video" and Path(source).exists()
        return {"text": "画面工具 Alpha", "resources": [{"label": "Alpha", "url": "https://alpha.example"}], "errors": []}


class FakeTranscriber:
    def transcribe(self, path, cancel_event):
        return {"status": "success", "text": "语音推荐 Alpha", "segments": [{"start": 0, "end": 1, "text": "语音推荐 Alpha"}], "error": None}


def test_provider_chain_falls_back_and_combines_ocr_transcript(monkeypatch):
    pipeline = XhsMediaPipeline(Settings(_env_file=None), FakeAgentSearch(), FakeTranscriber())
    pipeline.providers = [FailedProvider(), SuccessfulProvider()]
    monkeypatch.setattr(pipeline, "_duration", lambda path: 10)
    events = []
    result = pipeline.process("https://www.xiaohongshu.com/explore/note", "", "笔记正文", events.append, threading.Event())
    assert result["media_provider"] == "opencli"
    assert result["ocr_status"] == result["transcription_status"] == "success"
    assert "[视频画面 OCR]" in result["raw_text"] and "[视频语音转录]" in result["raw_text"]
    assert "https://alpha.example" in result["raw_text"]
    assert any(event["step"] == "opencli_download" for event in events)


def test_content_assembler_keeps_full_text_and_caps_ai_input():
    full, ai_text = VideoContentAssembler.assemble("正文" * 40_000, {"text": "OCR"}, {"text": "语音"}, [], [])
    assert len(full) > 60_000 and len(ai_text) == 60_000 and "已截断" in ai_text


def test_note_url_validation_rejects_arbitrary_hosts():
    with pytest.raises(MediaProviderError, match="小红书"):
        _validate_note_url("https://example.com/note")


def test_opencli_health_does_not_expose_paths(monkeypatch):
    provider = OpenCliMediaProvider(Settings(_env_file=None)); monkeypatch.setattr(provider, "command", None)
    assert provider.health() == {"installed": False, "available": False, "version": "", "message": "OpenCLI 未安装"}
