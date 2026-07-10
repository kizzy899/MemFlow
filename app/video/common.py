from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import imageio_ffmpeg


@dataclass
class StepStatus:
    name: str
    status: str = "skipped"
    error: str = ""


@dataclass
class VideoWorkspace:
    root: Path
    url: str
    url_hash: str
    warnings: list[str] = field(default_factory=list)
    steps: dict[str, StepStatus] = field(default_factory=dict)

    @property
    def videos_dir(self) -> Path:
        return self.root / "videos"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def frames_dir(self) -> Path:
        return self.root / "frames"

    def mark(self, name: str, status: str, error: str = "") -> None:
        self.steps[name] = StepStatus(name=name, status=status, error=error)
        if error:
            self.warnings.append(f"{name}: {error}")


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def copy_tree_contents(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def ffmpeg_binary() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args: list[str], timeout: int) -> None:
    process = subprocess.run(
        [ffmpeg_binary(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"ffmpeg exited with {process.returncode}")


def seconds_to_stamp(value: float) -> str:
    total = max(0, int(round(value)))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
