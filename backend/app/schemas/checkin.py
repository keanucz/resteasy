"""Schemas for the voice check-in result the base laptop reports back."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CheckinResult(BaseModel):
    """How the check-in ended (voice/checkin.py Outcome): escalate, and why, in one plain sentence.
    `distress`: she asked for help, so every contact is called at once."""

    escalate: bool
    reason: str = Field(max_length=300)
    # She said something alarming ("help", "I've fallen"): phone family at once (older clients omit it)
    distress: bool = False


class Acknowledgement(BaseModel):
    """A contact pressed "I'm on it" in the app for the pillow's open alert."""

    contact_id: UUID


class NightStatus(BaseModel):
    """Night Watch's state for the pillow after taking the result."""

    night_state: str


class CheckinCooldown(BaseModel):
    """Alert debug: whether the pillow waits `minutes` after a check-in before checking again."""

    on: bool
    minutes: int


class CheckinCooldownChange(BaseModel):
    """Alert debug: turn the wait between check-ins on, or off so the pillow asks every time."""

    on: bool


class KeyPress(BaseModel):
    """A key on the bedside pad, sent by the base laptop (POST /keys)."""

    key: Literal["fine", "family", "talk"]
