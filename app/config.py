from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MemFlow"
    app_env: str = "development"

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: Optional[str] = Field(default=None, alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")

    notion_api_key: str = Field(default="", alias="NOTION_API_KEY")
    notion_database_id: str = Field(default="", alias="NOTION_DATABASE_ID")

    xhs_cookie: str = Field(default="", alias="XHS_COOKIE")
    xhs_browser_profile_path: str = Field(default="", alias="XHS_BROWSER_PROFILE_PATH")
    xhs_username: str = Field(default="", alias="XHS_USERNAME")
    xhs_password: str = Field(default="", alias="XHS_PASSWORD")

    translation_output_dir: str = Field(default="files/translated", alias="TRANSLATION_OUTPUT_DIR")
    raw_output_dir: str = Field(default="files/raw", alias="RAW_OUTPUT_DIR")
    database_url: str = Field(default="sqlite:///data/app.db", alias="DATABASE_URL")
    proxy_url: str = Field(default="", alias="PROXY_URL")

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def translation_output_path(self) -> Path:
        return (self.base_dir / self.translation_output_dir).resolve()

    @property
    def raw_output_path(self) -> Path:
        return (self.base_dir / self.raw_output_dir).resolve()

    @property
    def sqlite_file_path(self) -> Optional[Path]:
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            relative = self.database_url[len(prefix) :]
            return (self.base_dir / relative).resolve()
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

