"""Schemas for what the family-facing agents read and write: the night, the Morning Brief,
goodnight messages and settings changes."""

from typing import Any

from pydantic import BaseModel, Field


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
    """Settings the family agent may change; the Guardian whitelists and bounds them."""

    checkin_timeout_min: int | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None
    path_light_pct: int | None = None


class SettingsResult(BaseModel):
    applied: dict[str, Any]
    guardian: str
    reason: str | None = None


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
