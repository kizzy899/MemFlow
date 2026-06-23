from app.services.classifier_service import ClassifierService


def test_normalize_category_falls_back_to_default() -> None:
    service = ClassifierService()
    assert service.normalize_category("unknown") == "其他"


def test_normalize_tags_limits_and_deduplicates() -> None:
    service = ClassifierService()
    result = service.normalize_tags(["AI", "ai", "Python", "Agent", "Prompt", "FastAPI", "Extra"])
    assert result == ["AI", "Python", "Agent", "Prompt", "FastAPI"]

