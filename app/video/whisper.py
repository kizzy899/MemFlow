from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings
from app.video.common import write_json


def _srt_time(value: float) -> str:
    milliseconds = int(round(max(0, value) * 1000))
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


class WhisperTranscriber:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None

    def transcribe(self, audio_path: Path, output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        from faster_whisper import WhisperModel

        if self._model is None:
            self.settings.whisper_model_path.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
                download_root=str(self.settings.whisper_model_path),
            )
        segments, info = self._model.transcribe(str(audio_path), beam_size=5, vad_filter=True)
        rows: list[dict[str, Any]] = []
        for segment in segments:
            text = str(segment.text or "").strip()
            if text:
                rows.append({"start": round(segment.start, 3), "end": round(segment.end, 3), "text": text})
        subtitle_text = "\n".join(row["text"] for row in rows)
        (output_dir / "subtitle.txt").write_text(subtitle_text, encoding="utf-8")
        srt_lines = []
        for index, row in enumerate(rows, start=1):
            srt_lines.extend([str(index), f"{_srt_time(row['start'])} --> {_srt_time(row['end'])}", row["text"], ""])
        (output_dir / "subtitle.srt").write_text("\n".join(srt_lines), encoding="utf-8")
        write_json(output_dir / "subtitle.json", rows)
        return {"status": "success" if rows else "empty", "language": getattr(info, "language", ""), "segments": rows, "text": subtitle_text}
