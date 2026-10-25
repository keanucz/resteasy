"""Schemas for the signed-in app user: who they are, their pillows, voices and settings."""

import re
from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, StringConstraints, field_validator

from app.agents.guardian import CONFIG_BOUNDS
from app.core.app_constants import ALERT_SWITCH_COLUMNS, PHONE_INVALID, PHONE_PATTERN, RESIDENT_NAME_MAX
from app.core.voice_constants import VOICE_IDS

TIMEOUT_MIN, TIMEOUT_MAX = CONFIG_BOUNDS["checkin_timeout_min"]
CLOCK_FORMAT = "%H:%M"

# A time of day in her timezone, read and written as "HH:MM" (quiet hours never need seconds)
ClockTime = Annotated[time, PlainSerializer(lambda t: t.strftime(CLOCK_FORMAT), return_type=str)]
# The check-in wait the owner may choose, within the Guardian's bounds
CheckinTimeout = Annotated[int, Field(ge=TIMEOUT_MIN, le=TIMEOUT_MAX)]


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


class NewPillow(BaseModel):
    """"Connect pillow" on a fresh sign-up: who the pillow is for, as the app should call them."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=RESIDENT_NAME_MAX)]


class Voice(BaseModel):
    """One voice the pillow can speak with."""

    id: str
    name: str
    description: str


class Preferences(BaseModel):
    """The resident settings the owner changes from the app."""

    voice_id: str
    quiet_start: ClockTime
    quiet_end: ClockTime
    checkin_timeout_min: int
    monitoring_paused: bool


class PreferencesPatch(BaseModel):
    """Any subset of the preferences; the check-in timeout keeps the Guardian's bounds."""

    voice_id: str | None = None
    quiet_start: time | None = None
    quiet_end: time | None = None
    checkin_timeout_min: CheckinTimeout | None = None
    monitoring_paused: bool | None = None

    @field_validator("voice_id")
    @classmethod
    def known_voice(cls, voice_id: str | None) -> str | None:
        """Only the voices the app offers, so a typo can't leave the pillow without a voice."""
        if voice_id is not None and voice_id not in VOICE_IDS:
            raise ValueError("not one of the offered voices (GET /api/voices)")
        return voice_id


class WatchHours(BaseModel):
    """When it watches: from quiet_start to quiet_end in her timezone; equal times watch all day."""

    quiet_start: ClockTime
    quiet_end: ClockTime


class CheckinWait(BaseModel):
    """Before telling family: minutes she may be up before the pillow checks on her, then tells family."""

    checkin_timeout_min: int


class CheckinWaitUpdate(BaseModel):
    """A new check-in wait from the owner, within the Guardian's bounds."""

    checkin_timeout_min: CheckinTimeout


class AlertSettings(BaseModel):
    """How the signed-in person is reached in an alert: the in-app alert, texts and calls, the mobile
    number they go to, and whether this server can send texts and calls at all."""

    phone: str | None
    app: bool
    sms: bool
    call: bool
    twilio_ready: bool


class AlertSettingsPatch(BaseModel):
    """Any subset of the alert settings. An empty phone removes the number."""

    phone: str | None = None
    app: bool | None = None
    sms: bool | None = None
    call: bool | None = None

    @field_validator("phone")
    @classmethod
    def e164(cls, phone: str | None) -> str | None:
        """Normalise to E.164 ("+447700900123"): drop spaces, dashes and brackets, "00" means "+"."""
        if phone is None or not phone.strip():
            return None
        number = re.sub(r"[\s\-().]", "", phone)
        if not number.startswith("+"):
            number = "+" + number.removeprefix("00")
        if not re.fullmatch(PHONE_PATTERN, number):
            raise ValueError(PHONE_INVALID)
        return number

    def columns(self) -> dict[str, str | bool | None]:
        """The fields the caller sent, as contacts columns."""
        names = {"phone": "phone"} | ALERT_SWITCH_COLUMNS
        return {names[key]: getattr(self, key) for key in self.model_fields_set}


class AlertTest(BaseModel):
    """Which test to send now: a text or a call to the person's own number."""

    channel: Literal["sms", "call"]


class AlertTestResult(BaseModel):
    """How the test went: sent (and how) or not, and why."""

    sent: bool
    via: str | None = None  # "imessage" / "sms" / "call"
    error: str | None = None
