from app.config import Settings
from app.main import app
from app.services.notion_service import NotionService
from fastapi.testclient import TestClient


class FakeDatabases:
    def __init__(self, properties=None, error: Exception | None = None) -> None:
        self.properties = properties or {}
        self.error = error

    def retrieve(self, database_id: str):
        if self.error:
            raise self.error
        return {"id": database_id, "properties": self.properties}


class FakeClient:
    def __init__(self, properties=None, error: Exception | None = None) -> None:
        self.databases = FakeDatabases(properties, error)


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def valid_properties() -> dict[str, dict[str, str]]:
    return {name: {"type": expected} for name, expected in NotionService.REQUIRED_PROPERTIES.items()}


def test_validate_reports_missing_configuration() -> None:
    result = NotionService(settings()).validate_database_details()

    assert result["success"] is False
    assert result["data"]["configured"] is False
    assert result["data"]["missing_config"] == ["NOTION_API_KEY", "NOTION_DATABASE_ID"]


def test_validate_accepts_complete_schema(monkeypatch) -> None:
    service = NotionService(settings(NOTION_API_KEY="secret", NOTION_DATABASE_ID="database"))
    monkeypatch.setattr(service, "_client", lambda: FakeClient(valid_properties()))

    result = service.validate_database_details()

    assert result["success"] is True
    assert result["data"]["database_accessible"] is True
    assert all(field["valid"] for field in result["data"]["fields"])


def test_validate_reports_missing_field(monkeypatch) -> None:
    properties = valid_properties()
    del properties["摘要"]
    service = NotionService(settings(NOTION_API_KEY="secret", NOTION_DATABASE_ID="database"))
    monkeypatch.setattr(service, "_client", lambda: FakeClient(properties))

    result = service.validate_database_details()

    assert result["success"] is False
    assert result["data"]["missing_fields"] == ["摘要"]


def test_validate_reports_type_mismatch(monkeypatch) -> None:
    properties = valid_properties()
    properties["二级分类"] = {"type": "rich_text"}
    service = NotionService(settings(NOTION_API_KEY="secret", NOTION_DATABASE_ID="database"))
    monkeypatch.setattr(service, "_client", lambda: FakeClient(properties))

    result = service.validate_database_details()

    assert result["success"] is False
    assert result["data"]["type_mismatches"] == [
        {"name": "二级分类", "expected_type": "select", "actual_type": "rich_text"}
    ]


def test_validate_humanizes_database_access_error(monkeypatch) -> None:
    service = NotionService(settings(NOTION_API_KEY="secret", NOTION_DATABASE_ID="database"))
    monkeypatch.setattr(
        service,
        "_client",
        lambda: FakeClient(error=RuntimeError("Could not find database with ID: database")),
    )

    result = service.validate_database_details()

    assert result["success"] is False
    assert "Connections" in result["data"]["error"]


def test_validate_endpoint_returns_200_for_invalid_diagnostic(monkeypatch) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.container.notion_service,
            "validate_database_details",
            lambda: {
                "success": False,
                "message": "Notion 未配置",
                "data": {"configured": False, "database_accessible": False},
            },
        )
        response = client.get("/api/notion/validate")

    assert response.status_code == 200
    assert response.json()["success"] is False
