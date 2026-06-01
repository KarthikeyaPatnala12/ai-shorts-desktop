from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/ai_shorts.sqlite3"
    workspace_dir: Path = Path("./workspace")
    exports_dir: Path = Path("./exports")
    temp_dir: Path = Path("./temp")
    downloads_dir: Path = Path("./downloads")
    whisper_model: str = "base"
    whisper_device: Literal["auto", "cpu", "cuda"] = "cpu"
    whisper_compute_type: str = "int8"
    clip_count: int = 5
    min_clip_seconds: int = 45
    max_clip_seconds: int = 180

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_SHORTS_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
