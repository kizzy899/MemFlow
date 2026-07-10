from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.db import Base
from app.db_migrations import run_sqlite_migrations
from app.models.content_item import ContentItem, ContentType, ProcessStatus, SourcePlatform
from app.services.ai_service import AnalysisResult
from app.services.content_pipeline_service import ContentPipelineService
from app.services.item_service import ItemService


class ParserShouldNotRun:
    def parse_url(self, url: str):
        raise AssertionError("video URLs should not use the article parser")


class FakeAI:
    def analyze(self, source_url: str, title: str, text: str) -> AnalysisResult:
        assert "timeline.json" in text
        return AnalysisResult(
            title="视频知识提取",
            summary="视频已经基于字幕、OCR 和时间轴生成结构化总结。",
            core_points=["先生成结构化产物", "再基于 timeline 总结"],
            action_items=["复核 summary.md"],
            content_type="video",
            category_level_1="AI",
            category_level_2="视频知识库",
            keywords=["视频", "OCR"],
            importance="high",
            original_language="zh-CN",
            is_translated=False,
        )


class FakeNotion:
    def is_configured(self) -> bool:
        return False


class FakeVideoPipeline:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls = 0

    def can_process(self, url: str) -> bool:
        return "youtube.com" in url

    def process(self, url: str):
        self.calls += 1
        workspace = self.root / "video-workspace"
        workspace.mkdir(parents=True)
        timeline = workspace / "timeline.json"
        summary = workspace / "summary.md"
        subtitle = workspace / "subtitle.json"
        ocr = workspace / "ocr.json"
        vision = workspace / "vision.json"
        timeline.write_text('[{"time":"00:01","speech":"hello","screen":"Cursor","vision":"打开编辑器"}]', encoding="utf-8")
        summary.write_text("# Demo\n\n## 命令\n\n```bash\nnpm test\n```", encoding="utf-8")
        subtitle.write_text('[{"start":0,"end":1,"text":"hello"}]', encoding="utf-8")
        ocr.write_text("[]", encoding="utf-8")
        vision.write_text("[]", encoding="utf-8")

        class Result:
            metadata = {"title": "Demo Video", "author": "Alice", "duration": 12, "platform": "youtube", "url": url}
            summary_markdown = summary.read_text(encoding="utf-8")
            video_path = workspace / "videos" / "video.mp4"
            audio_path = workspace / "audio" / "audio.wav"
            subtitle_path = subtitle
            ocr_path = ocr
            vision_path = vision
            timeline_path = timeline
            summary_path = summary
            warnings = []
            statuses = {"download": "success", "whisper": "success", "ocr": "empty", "vision": "empty"}

            @property
            def ai_text(self):
                return self.summary_markdown + "\n\n[timeline.json]\n00:01 speech=hello screen=Cursor vision=打开编辑器"

        return Result()


def test_video_url_uses_structured_video_pipeline(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        video = FakeVideoPipeline(tmp_path)
        pipeline = ContentPipelineService(ParserShouldNotRun(), FakeAI(), ItemService(FakeNotion()), video)

        item = pipeline.process_collect(db, "url", "https://www.youtube.com/watch?v=abc")

        assert video.calls == 1
        assert item.source_platform == SourcePlatform.YOUTUBE
        assert item.content_type == ContentType.VIDEO
        assert item.process_status == ProcessStatus.COMPLETED
        assert item.video_platform == "youtube"
        assert item.video_duration == 12
        assert item.has_video is True
        assert item.has_subtitle is True
        assert item.timeline_path.endswith("timeline.json")
        assert item.summary_path.endswith("summary.md")
        assert "timeline.json" in item.clean_content


def test_video_columns_are_migrated(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE content_items (id VARCHAR(36) PRIMARY KEY, source_url VARCHAR(2048), "
            "source_platform VARCHAR(20), raw_text TEXT NOT NULL DEFAULT '', process_status VARCHAR(20), created_at DATETIME)"
        )
    run_sqlite_migrations(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("content_items")}
    assert {"subtitle_path", "ocr_path", "timeline_path", "summary_path", "video_duration", "video_platform", "has_video", "has_subtitle"} <= columns