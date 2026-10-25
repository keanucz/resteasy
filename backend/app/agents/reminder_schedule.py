"""When reminders play, and how the pillow says it: pure functions over `reminders` rows, no database.

Shared by the Routine agent's tick (what is due today) and the family calendar (what plays when).
A row is recurring on its ISO `days` minus `skip_dates`, or a one-off on `on_date`; times are in
the resident's timezone.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.app_constants import (
    CONSENT_AGREED,
    FAMILY_FALLBACK_NAME,
    MONTH_NAMES,
    WEEKDAY_NAMES,
)

CONSENT_QUESTION = "Is that alright?"
EVERY_DAY = frozenset(range(1, 8))
WEEKDAYS = frozenset(range(1, 6))
WEEKEND = frozenset({6, 7})


def is_one_off(reminder: dict[str, Any]) -> bool:
    return reminder["on_date"] is not None


def plays_on(reminder: dict[str, Any], day: date, *, agreed_only: bool = False) -> bool:
    """Whether an active `reminder` plays on `day`. The tick passes `agreed_only` (nothing plays
    until she agrees); the calendar shows every consent."""
    if not reminder["active"] or (agreed_only and reminder["consent"] != CONSENT_AGREED):
        return False
    if is_one_off(reminder):
        return day == date.fromisoformat(reminder["on_date"])
    return day.isoweekday() in reminder["days"] and day.isoformat() not in reminder["skip_dates"]


def due_at(reminder: dict[str, Any], day: date, timezone: str) -> datetime:
    """The moment `reminder` plays on `day`, in the resident's timezone."""
    return datetime.combine(day, time.fromisoformat(reminder["time_of_day"]), ZoneInfo(timezone))


def expand(reminder: dict[str, Any], start: date, end: date, timezone: str) -> list[tuple[date, datetime]]:
    """Every (day, due time) `reminder` plays from `start` to `end` inclusive, earliest first."""
    days = (start + timedelta(days=n) for n in range((end - start).days + 1))
    return [(day, due_at(reminder, day, timezone)) for day in days if plays_on(reminder, day)]


def day_bounds(start: date, end: date, timezone: str) -> tuple[datetime, datetime]:
    """From midnight starting `start` to midnight ending `end`, in the resident's timezone."""
    tz = ZoneInfo(timezone)
    return datetime.combine(start, time(), tz), datetime.combine(end + timedelta(days=1), time(), tz)


# ---------- how the pillow says it ----------


def spoken_time(value: str) -> str:
    """ "08:00" -> "8 am", "18:30" -> "6:30 pm"."""
    t = time.fromisoformat(value)
    minutes = f":{t.minute:02d}" if t.minute else ""
    return f"{t.hour % 12 or 12}{minutes} {'am' if t.hour < 12 else 'pm'}"


def spoken_date(day: date) -> str:
    """ "Saturday 1 November"."""
    return f"{WEEKDAY_NAMES[day.isoweekday() - 1]} {day.day} {MONTH_NAMES[day.month - 1]}"


def spoken_days(days: Iterable[int]) -> str:
    """ "every day", "on weekdays", "on weekends", "on Mondays and Thursdays"."""
    chosen = frozenset(days)
    named = {EVERY_DAY: "every day", WEEKDAYS: "on weekdays", WEEKEND: "on weekends"}
    if chosen in named:
        return named[chosen]
    plural = [f"{WEEKDAY_NAMES[d - 1]}s" for d in sorted(chosen)]
    listed = plural[0] if len(plural) == 1 else f"{', '.join(plural[:-1])} and {plural[-1]}"
    return f"on {listed}"


def spoken_when(reminder: dict[str, Any]) -> str:
    """ "at 8 am every day", "at 6:30 pm on weekdays", "at 3 pm on Saturday 1 November"."""
    on = (
        f"on {spoken_date(date.fromisoformat(reminder['on_date']))}"
        if is_one_off(reminder)
        else spoken_days(reminder["days"])
    )
    return f"at {spoken_time(reminder['time_of_day'])} {on}"


def first_name(full_name: str | None) -> str:
    """Who is asking: the family member's first name, or "Your family"."""
    parts = (full_name or "").split()
    return parts[0] if parts else FAMILY_FALLBACK_NAME


def consent_line(reminder: dict[str, Any], created_by_name: str | None) -> str:
    """The pillow asks whether she agrees to a reminder before it ever plays."""
    asker, when = first_name(created_by_name), spoken_when(reminder)
    return f"{asker} would like to remind you to {reminder['label']} {when}. {CONSENT_QUESTION}"


def spoken_line(name: str, label: str) -> str:
    """The reminder itself: "<name>, it's time to <label>."."""
    return f"{name}, it's time to {label}."
