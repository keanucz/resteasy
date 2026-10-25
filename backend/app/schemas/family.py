"""Schemas for what the family-facing agents read and write: the night, the Morning Brief,
goodnight messages, settings changes and the nights a family member is away."""

from datetime import date
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.account import CheckinTimeout, ClockTime


class NightReport(BaseModel):
    """One night: the window, a plain-code summary, the raw events and what the agents did."""

    pillow_id: str
    resident: str
    window_start: str
    window_end: str
    summary: dict[str, Any]
    events: list[dict[str, Any]]
    agent_log: list[dict[str, Any]]
    settings: dict[str, Any]  # the keys the Morning Brief may propose changes to


class GoodnightCreate(BaseModel):
    """A message from family, played by the pillow when she next lies down."""

    message: str = Field(min_length=1, max_length=400)
    from_name: str = Field(min_length=1, max_length=80)


class Goodnight(BaseModel):
    message: str
    from_name: str


class BriefCreate(BaseModel):
    """What the Morning Brief droid produced: a family note and a proposed settings diff."""

    note: str = Field(min_length=1, max_length=2000)
    config_diff: dict[str, Any] = {}
    droid_session_id: str | None = None


class Brief(BaseModel):
    ts: str | None = None
    note: str
    proposed: dict[str, Any]
    applied: dict[str, Any]
    guardian: str
    reason: str | None = None


class SettingsPatch(BaseModel):
    """When it watches and the check-in wait, with the same types and bounds as the app's settings
    (the Guardian's); null or left out = unchanged."""

    checkin_timeout_min: CheckinTimeout | None = None
    quiet_start: ClockTime | None = None
    quiet_end: ClockTime | None = None


class SettingsResult(BaseModel):
    applied: dict[str, Any]


class AwayCreate(BaseModel):
    """Nights a family member can't be called first: `from_date` (first night) to `until_date`
    (last night), inclusive."""

    from_date: date
    until_date: date
    note: str = Field("away", min_length=1, max_length=80, examples=["in Denver"])

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.until_date < self.from_date:
            raise ValueError("until_date must be on or after from_date")
        return self


class Away(AwayCreate):
    id: int


class RosterContact(BaseModel):
    """A contact as the watch roster sees them: who, whether on call, their own quiet hours."""

    contact_id: str
    name: str
    on_call: bool
    quiet_start: str | None = None
    quiet_end: str | None = None


class Roster(BaseModel):
    """The resident's contacts, first to alert first, and her timezone (quiet hours are in it)."""

    resident: str
    timezone: str
    contacts: list[RosterContact]


class OnCallUpdate(BaseModel):
    """The Fetch.ai coordinator sets tonight's on-call flag from what the contact's agent said."""

    on_call: bool
    reason: str = Field(min_length=1, max_length=200)


class OnCallResult(BaseModel):
    contact_id: str
    on_call: bool  # what is stored now
    guardian: str
    reason: str | None = None
