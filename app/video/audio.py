from __future__ import annotations

from pathlib import Path

from app.video.common import ensure_dirs, run_ffmpeg


def extract_audio(video_path: Path, audio_dir: Path, timeout_seconds: int) -> Path:
    ensure_dirs(audio_dir)
    audio_path = audio_dir / "audio.wav"
    run_ffmpeg(["-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", str(audio_path)], timeout_seconds)
    return audio_path
