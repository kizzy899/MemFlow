from app.config import Settings
from app.services.config_service import ConfigService


def test_config_only_allows_notion_secrets(tmp_path):
    env=tmp_path/".env"; env.write_text("# keep\nNOTION_API_KEY=old-token\n",encoding="utf-8")
    service=ConfigService(tmp_path,Settings(_env_file=None))
    service.update({"XHS_COOKIE":"forbidden","NOTION_DATABASE_ID":"db"})
    text=env.read_text(encoding="utf-8")
    assert "XHS_COOKIE" not in text and "NOTION_DATABASE_ID" in text
    assert "xhs" not in service.status()
