import importlib.util
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app

SCRIPT = Path(__file__).resolve().parents[1] / "skills/agent-search/scripts/agent_search.py"
SPEC = importlib.util.spec_from_file_location("agent_search_skill", SCRIPT)
agent_search = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(agent_search)


def test_article_extracts_and_classifies_resource_links(tmp_path):
    article = tmp_path / "article.html"
    article.write_text(
        '<h1>Tools</h1><a href="https://github.com/acme/demo">project source</a>'
        '<a href="https://example.com/skills/demo/SKILL.md">Agent Skill</a>'
        '<a href="https://docs.example.com/guide">recommended guide</a>',
        encoding="utf-8",
    )
    result = agent_search.read_article(str(article))
    categories = {item["url"]: item["category"] for item in result["resources"]}
    assert categories["https://github.com/acme/demo"] == "project"
    assert categories["https://example.com/skills/demo/SKILL.md"] == "skill"
    assert categories["https://docs.example.com/guide"] == "recommended"


def test_video_ocr_reads_visible_frame_text(tmp_path):
    video = tmp_path / "sample.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 2.0, (960, 320))
    frame = np.full((320, 960, 3), 255, dtype=np.uint8)
    cv2.putText(frame, "GitHub Project Skill URL", (25, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 4)
    for _ in range(4): writer.write(frame)
    writer.release()

    result = agent_search.read_video(str(video), interval=1.0, max_frames=4)
    assert "GitHub" in result["text"]
    assert result["segments"][0]["timestamp"] == 0.0
    assert result["metadata"]["sampled_frames"] >= 1


def test_agent_search_api_extracts_article_resources():
    with TestClient(app) as client:
        response = client.post("/api/agent-search/extract", json={
            "source_type": "article",
            "source": "Project https://github.com/acme/demo and Skill https://example.com/SKILL.md",
        })
        assert response.status_code == 200
        resources = response.json()["data"]["resources"]
        assert {item["category"] for item in resources} == {"project", "skill"}


def test_agent_search_api_validates_video_limits():
    with TestClient(app) as client:
        response = client.post("/api/agent-search/extract", json={"source_type": "video", "source": "x.mp4", "interval": 0})
        assert response.status_code == 422
