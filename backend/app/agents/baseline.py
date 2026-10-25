"""Her personal night baseline, from the past week of trips (plain stats, never a model).

Rules (coord/CONTEXT.md decisions log, Fri 23 Oct and Sat 24 Oct):
- The window is the 7 nights before the night being looked at (a night runs 18:00 to noon).
- A usual trip is shorter than the week-one 20 min wait, so it never ran into a check-in. Longer
  trips never move the baseline; they are listed for family instead, never silently absorbed.
- Learning mode until there are enough usual trips over enough nights; the owner's wait applies.
- Learned wait = her usual trip length (p90, nearest rank) + a margin, clamped to the Guardian's
  10-30 min. The owner's `checkin_timeout_min` is the longest she is ever left: the shorter wins.
- A trip starting more than an hour outside the week's earliest-latest start times is unusual.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.agents.guardian import CONFIG_BOUNDS

WINDOW_NIGHTS = 7
LEARNING_TIMEOUT_MIN = 20  # the fixed week-one wait; a trip this long ran into a check-in
MIN_USUAL_TRIPS = 5
MIN_NIGHTS = 4  # usual trips on at least this many different nights of the window
MARGIN_MIN = 5
TIMEOUT_BOUNDS = CONFIG_BOUNDS["checkin_timeout_min"]
UNUSUAL_HOUR_SLACK_MIN = 60
NIGHT_STARTS_H = 18  # same night as night_summary: 18:00 ...
NIGHT_LENGTH_MIN = 18 * 60  # ... to noon


def history_start(night_start: datetime) -> datetime:
    """Where the window of past nights begins, for the night that starts at `night_start`."""
    return night_start - timedelta(days=WINDOW_NIGHTS)


def _night_clock(t: time) -> int:
    """Minutes since 18:00, so 23:30 sorts before 01:00."""
    return (t.hour * 60 + t.minute - NIGHT_STARTS_H * 60) % (24 * 60)


def _night_of(left: datetime) -> date:
    return (left - timedelta(hours=12)).date()  # 01:00 on the 24th belongs to the 23rd's night


def _hhmm(minutes: int) -> str:
    total = (minutes + NIGHT_STARTS_H * 60) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True)
class Baseline:
    """What the past week says about her trips, and the check-in wait that follows from it."""

    owner_timeout_min: int
    trips: int
    nights_with_trips: int
    usual_trips: int
    usual_nights: int
    usual_trip_min: int | None  # p90 of usual trips, whole minutes
    learned_timeout_min: int | None  # None while learning
    earliest: int | None  # night-clock minutes of the earliest and latest trip start
    latest: int | None
    long_trips: tuple[tuple[str, int], ...]  # ("Wed 03:12", 31)

    @property
    def learning(self) -> bool:
        return self.learned_timeout_min is None

    @property
    def checkin_timeout_min(self) -> int:
        """The wait Night Watch uses: the owner's, or the learned one when that is shorter."""
        if self.learned_timeout_min is None:
            return self.owner_timeout_min
        return min(self.owner_timeout_min, self.learned_timeout_min)

    @property
    def trips_per_night(self) -> float:
        return round(self.trips / WINDOW_NIGHTS, 1)

    def unusual_hour(self, left: time) -> bool:
        """A trip starting more than an hour outside the week's range (never while learning)."""
        if self.learning or self.earliest is None or self.latest is None:
            return False
        at = _night_clock(left)
        return at < self.earliest - UNUSUAL_HOUR_SLACK_MIN or at > self.latest + UNUSUAL_HOUR_SLACK_MIN

    def usual_hours(self) -> str | None:
        if self.earliest is None or self.latest is None:
            return None
        return f"{_hhmm(self.earliest)}-{_hhmm(self.latest)}"

    def drift(self, last_night_trips: int) -> list[str]:
        """Plain sentences for the night summary: what changed, so family hear it."""
        lines: list[str] = []
        if (not self.learning and last_night_trips >= 2
                and last_night_trips >= self.trips_per_night + 1):
            lines.append(f"{last_night_trips} trips last night; her usual is {self.trips_per_night:g} "
                         f"a night over the past {WINDOW_NIGHTS} nights")
        if self.long_trips:
            each = ", ".join(f"{m} min on {at}" for at, m in self.long_trips)
            n = len(self.long_trips)
            lines.append(f"{n} trip{'s' if n > 1 else ''} over {LEARNING_TIMEOUT_MIN} min in the past "
                         f"{WINDOW_NIGHTS} nights ({each}); not counted as usual")
        if self.learned_timeout_min is not None and self.learned_timeout_min > self.owner_timeout_min:
            lines.append(f"her usual trip is up to {self.usual_trip_min} min, close to the "
                         f"{self.owner_timeout_min}-min check-in wait, so she may be checked on during "
                         f"ordinary trips")
        return lines

    def note(self) -> str:
        """One line for the family app's live log when the wait changes."""
        if self.learning:
            return (f"check-in wait {self.checkin_timeout_min} min (learning her usual trips: "
                    f"{self.usual_trips} on {self.usual_nights} nights so far)")
        return (f"check-in wait {self.checkin_timeout_min} min: her usual trip is up to "
                f"{self.usual_trip_min} min (past {WINDOW_NIGHTS} nights)")

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "learning" if self.learning else "learned",
            "nights": WINDOW_NIGHTS,
            "trips": self.trips,
            "nights_with_trips": self.nights_with_trips,
            "trips_per_night": self.trips_per_night,
            "usual_trips": self.usual_trips,
            "usual_trip_min": self.usual_trip_min,
            "usual_hours": self.usual_hours(),
            "long_trips": [{"at": at, "min": m} for at, m in self.long_trips],
            "learned_timeout_min": self.learned_timeout_min,
            "owner_timeout_min": self.owner_timeout_min,
            "checkin_timeout_min": self.checkin_timeout_min,
        }


def build_baseline(
    trips: list[dict[str, Any]], night_start: datetime, timezone: str, owner_timeout_min: int
) -> Baseline:
    """The baseline for the night starting at `night_start`, from `night_trips` rows
    (`left_at` ISO, `trip_min`). Rows outside the window or in the daytime are ignored."""
    tz = ZoneInfo(timezone)
    start = history_start(night_start)
    rows: list[tuple[datetime, float]] = []
    for t in trips:
        left = datetime.fromisoformat(t["left_at"]).astimezone(tz)
        if start <= left < night_start and _night_clock(left.time()) < NIGHT_LENGTH_MIN:
            rows.append((left, float(t["trip_min"])))
    rows.sort()

    usual = [(left, m) for left, m in rows if m < LEARNING_TIMEOUT_MIN]
    usual_nights = len({_night_of(left) for left, _ in usual})
    p90 = None
    if usual:
        lengths = sorted(m for _, m in usual)
        p90 = math.ceil(lengths[math.ceil(0.9 * len(lengths)) - 1])
    learned = None
    if p90 is not None and len(usual) >= MIN_USUAL_TRIPS and usual_nights >= MIN_NIGHTS:
        lo, hi = TIMEOUT_BOUNDS
        learned = max(lo, min(hi, p90 + MARGIN_MIN))
    starts = [_night_clock(left.time()) for left, _ in rows]
    return Baseline(
        owner_timeout_min=owner_timeout_min,
        trips=len(rows),
        nights_with_trips=len({_night_of(left) for left, _ in rows}),
        usual_trips=len(usual),
        usual_nights=usual_nights,
        usual_trip_min=p90,
        learned_timeout_min=learned,
        earliest=min(starts) if starts else None,
        latest=max(starts) if starts else None,
        long_trips=tuple((f"{left:%a %H:%M}", round(m)) for left, m in rows if m >= LEARNING_TIMEOUT_MIN),
    )
