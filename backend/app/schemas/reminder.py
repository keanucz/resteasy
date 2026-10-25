"""Schemas for reminders (the Routine agent), each time one falls due, and the family calendar."""

from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.app_constants import (
    CALENDAR_MAX_DAYS,
    CONSENT_PENDING,
    CONSENT_RESET_FIELDS,
    REMIND_PURPOSE,
)
from app.schemas.account import ClockTime

Kind = Literal["meds", "call", "custom"]
Channel = Literal["voice", "sms", "email"]  # only voice is delivered today
Consent = Literal["pending", "agreed", "declined"]
Purpose = Literal["remind", "consent"]
OccurrenceStatus = Literal["waiting", "due", "announced", "done", "missed"]
Weekdays = list[int]  # ISO weekdays, 1 = Monday .. 7 = Sunday
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]

# Fields the app may clear with an explicit null (a one-off becomes recurring again)
NULLABLE_FIELDS = frozenset({"on_date"})


def _weekdays(days: Weekdays | None) -> Weekdays | None:
    if days is None:
        return None
    if not days or any(d not in range(1, 8) for d in days):
        raise ValueError("days must be ISO weekdays 1 (Monday) to 7 (Sunday), at least one")
    return sorted(set(days))


def _label(label: str | None) -> str | None:
    """An action phrase spoken as "it's time to <label>.": trimmed, no trailing full stop."""
    if label is None:
        return None
    label = label.strip().rstrip(".").strip()
    if not label:
        raise ValueError("label must not be empty")
    return label


def _channels(channels: list[Channel] | None) -> list[Channel] | None:
    """At least one channel, each once, in the order given."""
    if channels is None:
        return None
    if not channels:
        raise ValueError("channels must name at least one of voice, sms, email")
    return list(dict.fromkeys(channels))


def _dates(dates: list[date] | None) -> list[date] | None:
    return None if dates is None else sorted(set(dates))


class ReminderCreate(BaseModel):
    """A reminder set up in the family app, one-off (`on_date`) or on `days` each week.

    `confirm`: ask her to confirm, and retry if she doesn't. It plays only once she agrees."""

    label: str = Field(max_length=80, examples=["take your heart tablets"])
    kind: Kind = "custom"
    time_of_day: ClockTime
    days: Weekdays = ALL_DAYS
    on_date: date | None = None
    confirm: bool = False
    channels: list[Channel] = ["voice"]

    _check_label = field_validator("label")(_label)
    _check_days = field_validator("days")(_weekdays)
    _check_channels = field_validator("channels")(_channels)

    def to_fields(self, created_by: str) -> dict[str, Any]:
        """The new row's columns: always waiting for her consent."""
        return {**self.model_dump(mode="json"), "consent": CONSENT_PENDING, "created_by": created_by}


class ReminderUpdate(BaseModel):
    """Change any of a reminder's fields; `active` false pauses it, `on_date` null makes it recurring."""

    label: str | None = Field(None, max_length=80)
    kind: Kind | None = None
    time_of_day: ClockTime | None = None
    days: Weekdays | None = None
    on_date: date | None = None
    confirm: bool | None = None
    channels: list[Channel] | None = None
    active: bool | None = None
    skip_dates: list[date] | None = None

    _check_label = field_validator("label")(_label)
    _check_days = field_validator("days")(_weekdays)
    _check_channels = field_validator("channels")(_channels)
    _check_skip_dates = field_validator("skip_dates")(_dates)

    def to_fields(self, current: "Reminder") -> dict[str, Any]:
        """The columns that differ from `current` (empty: nothing to write). Changing what is said
        or when asks her consent again; skipping days, pausing, confirming or channels keep it."""
        now = current.model_dump(mode="json")
        fields = {
            key: value
            for key, value in self.model_dump(mode="json", exclude_unset=True).items()
            if (value is not None or key in NULLABLE_FIELDS) and value != now[key]
        }
        if CONSENT_RESET_FIELDS & fields.keys():
            fields |= {"consent": CONSENT_PENDING, "consent_at": None}
        return fields


class Reminder(BaseModel):
    id: int
    label: str
    kind: Kind
    time_of_day: ClockTime
    days: Weekdays
    on_date: date | None
    skip_dates: list[date]
    channels: list[Channel]
    confirm: bool
    active: bool
    consent: Consent
    consent_at: datetime | None
    created_by_name: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        """A reminders row with its `creator` contact embedded (crud REMINDER_COLUMNS)."""
        return cls(**row, created_by_name=(row.get("creator") or {}).get("full_name"))


class Occurrence(BaseModel):
    """One time a reminder fell due, for the app's "Today" list."""

    id: int
    reminder_id: int
    purpose: Purpose
    label: str
    kind: Kind
    confirm: bool
    due_at: datetime
    status: OccurrenceStatus
    attempts: int
    answered_at: datetime | None
    reply: str | None


class DueReminder(BaseModel):
    """What the laptop says now: `text` is the whole line; with `confirm` it asks and listens.

    `purpose` "consent": the line asks whether she agrees to a new or changed reminder."""

    occurrence_id: int
    text: str
    confirm: bool
    purpose: Purpose = REMIND_PURPOSE


class ReminderResult(BaseModel):
    """The laptop's report after saying a due reminder."""

    outcome: Literal["announced", "done", "not_done", "no_answer", "distress"]
    reply: str | None = Field(None, max_length=300)


class ReminderStatus(BaseModel):
    status: str


class CalendarRange(BaseModel):
    """GET /reminders/calendar query: `start` to `end` inclusive, at most CALENDAR_MAX_DAYS days."""

    start: date
    end: date

    @model_validator(mode="after")
    def bounded(self) -> Self:
        days = (self.end - self.start).days + 1
        if days < 1:
            raise ValueError("end must be on or after start")
        if days > CALENDAR_MAX_DAYS:
            raise ValueError(f"the range must be at most {CALENDAR_MAX_DAYS} days")
        return self


class CalendarEntry(BaseModel):
    """One time an active reminder plays (or would, once she agrees) within the range.

    `status` is how that time went, null until it falls due."""

    reminder_id: int
    date: date
    due_at: datetime
    label: str
    kind: Kind
    confirm: bool
    consent: Consent
    recurring: bool
    status: OccurrenceStatus | None
