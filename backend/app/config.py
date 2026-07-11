from functools import lru_cache
from pathlib import Path
import tempfile

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables only."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str | None = None
    max_upload_mb: int = 20
    model_name: str = "llama-3.3-70b-versatile"
    transcription_model: str = "whisper-large-v3-turbo"
    upload_dir: Path = Path(tempfile.gettempdir()) / "parallel-minds-uploads"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
