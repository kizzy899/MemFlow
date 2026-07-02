from __future__ import annotations

import argparse, json, re, sys, tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING = ".,;:!?，。；：！？、)]}）】》"

def error(code: str, message: str, detail: str = "", retryable: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail, "retryable": retryable}

def unique_text(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = " ".join(value.split())
        if not value or any(SequenceMatcher(None, value, old).ratio() >= 0.9 for old in result[-30:]): continue
        result.append(value)
    return result

def classify_url(url: str, label: str = "", context: str = "") -> str:
    parsed = urlparse(url); text = f"{url} {label} {context}".lower()
    parts = [part for part in parsed.path.split("/") if part]
    if any(word in text for word in ("skill", "plugin", "mcp", "agent", "marketplace", "能力")) or parsed.path.lower().endswith("skill.md"): return "skill"
    if parsed.netloc.lower() in {"github.com", "gitlab.com", "gitee.com"} and len(parts) >= 2: return "project"
    if any(word in text for word in ("project", "repo", "repository", "source code", "源码", "项目")): return "project"
    return "recommended"

def resources_from_text(text: str, candidates: list[tuple[str, str, str]] | None = None) -> list[dict[str, str]]:
    values = list(candidates or [])
    values.extend((match.group(0).rstrip(TRAILING), "", "") for match in URL_RE.finditer(text))
    output: list[dict[str, str]] = []; seen: set[str] = set()
    for url, label, context in values:
        url = url.rstrip(TRAILING)
        if url in seen or urlparse(url).scheme not in {"http", "https"}: continue
        seen.add(url)
        output.append({"url": url, "category": classify_url(url, label, context), "label": label, "context": context[:300]})
    return output

def read_article(source: str) -> dict[str, Any]:
    from bs4 import BeautifulSoup
    import requests
    source_name, base_url, path = source, "", Path(source)
    if source.startswith(("http://", "https://")):
        response = requests.get(source, timeout=30, headers={"User-Agent": "Mozilla/5.0 MemFlow-AgentSearch/1.0"})
        response.raise_for_status(); raw = response.text; base_url = source
    elif path.exists() and path.is_file():
        raw = path.read_text(encoding="utf-8-sig", errors="replace"); source_name = str(path.resolve())
    else: raw, source_name = source, "<inline-text>"
    candidates: list[tuple[str, str, str]] = []
    if "<" in raw and ">" in raw:
        soup = BeautifulSoup(raw, "html.parser")
        for node in soup(["script", "style", "noscript"]): node.decompose()
        for anchor in soup.find_all("a", href=True):
            label = anchor.get_text(" ", strip=True)
            container = anchor.find_parent(["li", "p", "article"])
            candidates.append((urljoin(base_url, str(anchor.get("href", ""))), label, container.get_text(" ", strip=True) if container else label))
        text = soup.get_text("\n", strip=True)
    else: text = raw
    text = "\n".join(unique_text(text.splitlines()))
    return {"source_type": "article", "source": source_name, "text": text, "segments": [], "resources": resources_from_text(text, candidates), "metadata": {"method": "html-or-text"}, "errors": []}

def download_video(url: str, directory: Path) -> Path:
    import imageio_ffmpeg
    from yt_dlp import YoutubeDL
    options = {"quiet": True, "no_warnings": True, "format": "best[ext=mp4]/best", "outtmpl": str(directory / "source.%(ext)s"), "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(), "noplaylist": True}
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        return Path(downloader.prepare_filename(info))

def read_video(source: str, interval: float, max_frames: int) -> dict[str, Any]:
    import cv2
    from rapidocr import RapidOCR
    temp = None
    if source.startswith(("http://", "https://")):
        temp_root = Path.cwd() / "data/agent-search-tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="run-", dir=temp_root, ignore_cleanup_errors=True)
        path = download_video(source, Path(temp.name))
    else:
        path = Path(source).resolve()
    try:
        if not path.exists(): raise FileNotFoundError(f"video not found: {source}")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened(): raise RuntimeError("OpenCV could not open the video")
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total / fps if total else 0.0
        step = max(1, int(fps * interval)); engine = RapidOCR()
        segments: list[dict[str, Any]] = []; frame_index = sampled = 0
        while sampled < max_frames:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok: break
            result = engine(frame); texts = list(result.txts or ()); scores = list(result.scores or ())
            joined = " ".join(unique_text(texts))
            if joined and not any(SequenceMatcher(None, joined, item["text"]).ratio() >= 0.9 for item in segments[-20:]):
                segments.append({"timestamp": round(frame_index / fps, 3), "text": joined, "score": round(sum(scores) / len(scores), 4) if scores else None})
            sampled += 1; frame_index += step
            if total and frame_index >= total: break
        capture.release(); text = "\n".join(item["text"] for item in segments)
        return {"source_type": "video", "source": source, "text": text, "segments": segments, "resources": resources_from_text(text), "metadata": {"method": "sampled-frame-ocr", "sampled_frames": sampled, "duration": round(duration, 3), "interval": interval}, "errors": []}
    finally:
        if temp: temp.cleanup()

def main() -> int:
    parser = argparse.ArgumentParser(description="MemFlow agent-search extractor")
    parser.add_argument("mode", choices=("video", "article")); parser.add_argument("source")
    parser.add_argument("--interval", type=float, default=2.0); parser.add_argument("--max-frames", type=int, default=300); parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        if args.interval <= 0 or args.max_frames <= 0: raise ValueError("interval and max-frames must be positive")
        result = read_video(args.source, args.interval, args.max_frames) if args.mode == "video" else read_article(args.source); code = 0
    except Exception as exc:
        safe_source = args.source if args.source.startswith(("http://", "https://")) else str(Path(args.source))
        result = {"source_type": args.mode, "source": safe_source, "text": "", "segments": [], "resources": [], "metadata": {}, "errors": [error("AGENT_SEARCH_FAILED", "Extraction failed", f"{type(exc).__name__}: {exc}", True)]}; code = 1
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)); return code

if __name__ == "__main__": sys.exit(main())
