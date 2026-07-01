from pathlib import Path
from app.config import Settings
from app.services.config_service import ConfigService


def test_config_update_is_atomic_masked_and_blank_preserves(tmp_path):
    env=tmp_path/".env"; env.write_text("# keep\nXHS_COOKIE=old-cookie\nNOTION_API_KEY=old-token\n",encoding="utf-8")
    service=ConfigService(tmp_path,Settings(_env_file=None))
    service.update({"XHS_COOKIE":"new-cookie","NOTION_API_KEY":"","UNSAFE":"no"})
    text=env.read_text(encoding="utf-8")
    assert "# keep" in text and "new-cookie" in text and "old-token" in text and "UNSAFE" not in text
    service.set_settings(Settings(_env_file=env))
    status=service.status()
    assert status["xhs"]["cookie_length"]==10
    assert "new-cookie" not in str(status)
    service.clear({"XHS_COOKIE"})
    assert 'XHS_COOKIE=""' in env.read_text(encoding="utf-8")