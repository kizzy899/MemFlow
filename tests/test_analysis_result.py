import pytest
from pydantic import ValidationError

from app.services.ai_service import AIService, AnalysisResult


def valid_payload() -> dict[str, object]:
    return {
        "title": "标题",
        "summary": "摘要",
        "core_points": ["观点一"],
        "action_items": [],
        "content_type": "article",
        "category_level_1": "AI",
        "category_level_2": "Agent 开发",
        "keywords": ["AI", "ai", "Agent"],
        "importance": "medium",
        "original_language": "zh-CN",
        "is_translated": False,
    }


def test_analysis_result_deduplicates_keywords() -> None:
    result = AnalysisResult.model_validate(valid_payload())
    assert result.keywords == ["AI", "Agent"]


def test_analysis_result_normalizes_and_truncates_long_title() -> None:
    payload = valid_payload()
    payload["title"] = "  GitHub   项目：" + "很长的标题" * 10

    result = AnalysisResult.model_validate(payload)

    assert len(result.title) == 40
    assert result.title.endswith("…")
    assert "  " not in result.title


def test_analysis_result_rejects_missing_fields() -> None:
    payload = valid_payload()
    del payload["summary"]
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(payload)


def test_analysis_result_rejects_non_array_keywords() -> None:
    payload = valid_payload()
    payload["keywords"] = "AI,Agent"
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(payload)

def test_recommendation_notes_can_keep_more_than_five_resources() -> None:
    payload = valid_payload()
    payload["core_points"] = [f"工具{i}｜https://example.com/{i}｜介绍" for i in range(8)]
    result = AnalysisResult.model_validate(payload)
    assert len(result.core_points) == 8


def test_xiaohongshu_rules_focus_on_content_resources_and_ocr_failures() -> None:
    rules = AIService.XIAOHONGSHU_RULES
    for phrase in ("忽略作者姓名", "点赞数", "覆盖全部 OCR 内容", "完整网页链接", "视频文字提取失败"):
        assert phrase in rules
