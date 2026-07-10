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

    memflow_auth_key: str = Field(default="", alias="MEMFLOW_AUTH_KEY")
    chrome_cdp_url: str = Field(default="http://127.0.0.1:9223", alias="CHROME_CDP_URL")
    opencli_command: str = Field(default="opencli", alias="OPENCLI_COMMAND")
    xhs_media_provider_chain: str = Field(default="browser,opencli", alias="XHS_MEDIA_PROVIDER_CHAIN")
    video_ocr_enabled: bool = Field(default=True, alias="VIDEO_OCR_ENABLED")
    video_transcription_enabled: bool = Field(default=True, alias="VIDEO_TRANSCRIPTION_ENABLED")
    whisper_model: str = Field(default="small", alias="WHISPER_MODEL")
    whisper_device: str = Field(default="cpu", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="int8", alias="WHISPER_COMPUTE_TYPE")
    video_step_timeout_seconds: int = Field(default=180, alias="VIDEO_STEP_TIMEOUT_SECONDS")
    video_max_duration_seconds: int = Field(default=1800, alias="VIDEO_MAX_DURATION_SECONDS")
    video_download_timeout_seconds: int = Field(default=600, alias="VIDEO_DOWNLOAD_TIMEOUT_SECONDS")
    video_frame_interval_seconds: float = Field(default=1.0, alias="VIDEO_FRAME_INTERVAL_SECONDS")
    video_vision_enabled: bool = Field(default=False, alias="VIDEO_VISION_ENABLED")
    video_vision_model: str = Field(default="gpt-4.1-mini", alias="VIDEO_VISION_MODEL")
    video_vision_sample_every: int = Field(default=1, alias="VIDEO_VISION_SAMPLE_EVERY")
    video_summary_timeline_limit: int = Field(default=800, alias="VIDEO_SUMMARY_TIMELINE_LIMIT")

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
    def xhs_media_temp_path(self) -> Path:
        return (self.base_dir / "data" / "xhs-media-tmp").resolve()

    @property
    def whisper_model_path(self) -> Path:
        return (self.base_dir / "data" / "models" / "whisper").resolve()

    @property
    def video_output_path(self) -> Path:
        return (self.base_dir / "data" / "video").resolve()

    @property
    def video_cache_path(self) -> Path:
        return (self.base_dir / "cache" / "video").resolve()

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

