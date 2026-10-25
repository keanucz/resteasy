"""Typed application settings loaded from environment variables and `.env`."""

from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.app_constants import (
    DEFAULT_APP_NAME,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_ENVIRONMENT,
    DEFAULT_NOTIFY_PILLOW_IDS,
    ENV_FILE,
)


class Settings(BaseSettings):
    """Every configurable value the backend reads from its environment."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_name: str = DEFAULT_APP_NAME
    environment: str = DEFAULT_ENVIRONMENT
    cors_origins: list[str] = DEFAULT_CORS_ORIGINS
    supabase_url: str = ""
    supabase_secret_key: str = ""
    # Shared secret the base laptop sends as `Authorization: Bearer ...` with POST /checkin
    checkin_token: str = ""
    # Each Fetch.ai family agent's own bearer token, as JSON {"<contacts.id>": "<token>"}: the token
    # is who the agent speaks for. Empty = the agents still use CHECKIN_TOKEN with ?contact_id=.
    family_agent_tokens: dict[UUID, str] = {}
    # The Fetch.ai coordinator's bearer token, for the watch roster. Empty = CHECKIN_TOKEN still works.
    coordinator_token: str = ""
    # Claude, for the Family Liaison's wording (app/agents/liaison.py); empty = fixed messages only
    anthropic_api_key: str = ""
    # Cartesia, for the app's voice previews and clones (app/voice); empty = those routes answer 503
    cartesia_api_key: str = ""
    # Family alerts to real phones (app/notify): the iMessage sidecar (deploy/imessage) and Twilio
    # for SMS fallback and calls. Each is optional; with neither, sms/call rows stay queued.
    imessage_url: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # Pillows whose alerts reach real phones; test pillows' rows are never sent
    notify_pillow_ids: list[str] = DEFAULT_NOTIFY_PILLOW_IDS

    @property
    def supabase_configured(self) -> bool:
        """Whether both Supabase values are set, so the database-backed routes can work."""
        return bool(self.supabase_url and self.supabase_secret_key)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, parsed once on first use."""
    return Settings()
