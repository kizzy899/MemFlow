from __future__ import annotations

from pathlib import Path

from app.video.common import ensure_dirs, run_ffmpeg, seconds_to_stamp, write_json


def extract_frames(video_path: Path, frames_dir: Path, interval_seconds: float, timeout_seconds: int) -> list[dict[str, object]]:
    ensure_dirs(frames_dir)
    fps = 1 / interval_seconds if interval_seconds > 0 else 1
    run_ffmpeg(["-y", "-i", str(video_path), "-vf", f"fps={fps}", "-q:v", "2", str(frames_dir / "%04d.jpg")], timeout_seconds)
    frames = sorted(frames_dir.glob("*.jpg"))
    rows = [
        {
            "frame": frame.name,
            "timestamp": round(index * interval_seconds, 3),
            "time": seconds_to_stamp(index * interval_seconds),
        }
        for index, frame in enumerate(frames)
    ]
    write_json(frames_dir / "frames.json", rows)
    return rows
