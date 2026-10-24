"""Schemas for the voice check-in result the base laptop reports back."""

from uuid import UUID

from pydantic import BaseModel, Field


class CheckinResult(BaseModel):
    """How the check-in ended (voice/checkin.py Outcome): escalate, and why, in one plain sentence."""

    escalate: bool
    reason: str = Field(max_length=300)


class Acknowledgement(BaseModel):
    """A contact pressed "I'm on it" in the app for the pillow's open alert."""

    contact_id: UUID


class NightStatus(BaseModel):
    """Night Watch's state for the pillow after taking the result."""

    night_state: str
