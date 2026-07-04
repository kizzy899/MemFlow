from app.config import Settings
from app.services.notion_service import NotionService

class FakeDatabases:
    def __init__(self, properties=None, error=None):
        self.properties = properties or {}
        self.error = error

    def retrieve(self, database_id):
        if self.error:
            raise self.error
        return {"id": database_id, "properties": self.properties}

class FakeClient:
    def __init__(self, properties=None, error=None):
        self.databases = FakeDatabases(properties, error)

props = {name: {"type": expected} for name, expected in NotionService.REQUIRED_PROPERTIES.items()}
service = NotionService(Settings(_env_file=None, NOTION_API_KEY="secret", NOTION_DATABASE_ID="database"))
service._client = lambda: FakeClient(props)
result = service.validate_database_details()
print(result["success"])
for field in result["data"]["fields"]:
    print(field)
