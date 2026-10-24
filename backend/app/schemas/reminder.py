"""Schemas for recurring reminders (the Routine agent) and each time one falls due."""

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Kind = Literal["meds", "call", "custom"]
Weekdays = list[int]  # ISO weekdays, 1 = Monday .. 7 = Sunday


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


class ReminderCreate(BaseModel):
    """A reminder set up in the family app. `confirm`: ask her to confirm, and retry if she doesn't."""

    label: str = Field(max_length=80, examples=["take your heart tablets"])
    kind: Kind = "custom"
    time_of_day: time
    days: Weekdays = [1, 2, 3, 4, 5, 6, 7]
    confirm: bool = False

    _check_label = field_validator("label")(_label)
    _check_days = field_validator("days")(_weekdays)


class ReminderUpdate(BaseModel):
    """Change any of a reminder's fields; `active` false pauses it."""

    label: str | None = Field(None, max_length=80)
    kind: Kind | None = None
    time_of_day: time | None = None
    days: Weekdays | None = None
    confirm: bool | None = None
    active: bool | None = None

    _check_label = field_validator("label")(_label)
    _check_days = field_validator("days")(_weekdays)


class Reminder(BaseModel):
    id: int
    label: str
    kind: Kind
    time_of_day: time
    days: Weekdays
    confirm: bool
    active: bool


class Occurrence(BaseModel):
    """One time a reminder fell due, for the app's "Today" list."""

    id: int
    reminder_id: int
    label: str
    kind: Kind
    confirm: bool
    due_at: datetime
    status: Literal["waiting", "due", "announced", "done", "missed"]
    attempts: int
    answered_at: datetime | None
    reply: str | None


class DueReminder(BaseModel):
    """What the laptop says now: `text` is the whole line; with `confirm` it asks and listens."""

    occurrence_id: int
    text: str
    confirm: bool


class ReminderResult(BaseModel):
    """The laptop's report after saying a due reminder."""

    outcome: Literal["announced", "done", "not_done", "no_answer", "distress"]
    reply: str | None = Field(None, max_length=300)


class ReminderStatus(BaseModel):
    status: str
