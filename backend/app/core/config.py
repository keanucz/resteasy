"""Typed application settings loaded from environment variables and `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.app_constants import (
    DEFAULT_APP_NAME,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_ENVIRONMENT,
    ENV_FILE,
)


class Settings(BaseSettings):
    """Every configurable value the backend reads from its environment."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_name: str = DEFAULT_APP_NAME
    environment: str = DEFAULT_ENVIRONMENT
    cors_origins: list[str] = DEFAULT_CORS_ORIGINS


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, parsed once on first use."""
    return Settings()
