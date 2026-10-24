"""Schemas for the signed-in app user: who they are, their pillows, voices and settings."""

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.agents.guardian import CONFIG_BOUNDS
from app.core.voice_constants import VOICE_IDS

TIMEOUT_MIN, TIMEOUT_MAX = CONFIG_BOUNDS["checkin_timeout_min"]


class AccountPillow(BaseModel):
    """A pillow the user looks after, with the person it belongs to and the user's role there."""

    pillow_id: str
    resident_id: str
    preferred_name: str
    role: Literal["owner", "contact"]


class Account(BaseModel):
    """The contact linked to the signed-in login, or no contact yet (a fresh sign-up)."""

    contact_id: str | None
    full_name: str | None
    pillows: list[AccountPillow]


class Voice(BaseModel):
    """One voice the pillow can speak with."""

    id: str
    name: str
    description: str


class Preferences(BaseModel):
    """The resident settings the owner changes from the app."""

    voice_id: str
    quiet_start: time
    quiet_end: time
    checkin_timeout_min: int
    monitoring_paused: bool


class PreferencesPatch(BaseModel):
    """Any subset of the preferences; the check-in timeout keeps the Guardian's bounds."""

    voice_id: str | None = None
    quiet_start: time | None = None
    quiet_end: time | None = None
    checkin_timeout_min: int | None = Field(default=None, ge=TIMEOUT_MIN, le=TIMEOUT_MAX)
    monitoring_paused: bool | None = None

    @field_validator("voice_id")
    @classmethod
    def known_voice(cls, voice_id: str | None) -> str | None:
        """Only the voices the app offers, so a typo can't leave the pillow without a voice."""
        if voice_id is not None and voice_id not in VOICE_IDS:
            raise ValueError("not one of the offered voices (GET /api/voices)")
        return voice_id
