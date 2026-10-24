"""One night, summarised from the events table in plain code.

The Morning Brief (Factory Droid) and the family agent (Fetch.ai) both read this, so the numbers
family see are computed, never guessed by a model. Times are in the resident's timezone.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.agents.baseline import Baseline

NIGHT_STARTS_H = 18  # a "night" runs from 18:00 ...
NIGHT_ENDS_H = 12  # ... to noon the next day
LONG_TRIP_MIN = 15  # a trip this long is worth a line in the brief


def last_night_window(now_ts: float, timezone: str) -> tuple[datetime, datetime]:
    """The most recent night: from 18:00 the evening before, to noon or to now if that's sooner."""
    tz = ZoneInfo(timezone)
    now = datetime.fromtimestamp(now_ts, tz)
    start_day = now.date() if now.hour >= NIGHT_STARTS_H else now.date() - timedelta(days=1)
    start = datetime.combine(start_day, datetime.min.time(), tz).replace(hour=NIGHT_STARTS_H)
    end = min(now, start + timedelta(hours=24 - NIGHT_STARTS_H + NIGHT_ENDS_H))
    return start, end


def _local(iso: str, tz: ZoneInfo) -> datetime:
    return datetime.fromisoformat(iso).astimezone(tz)


def _hhmm(dt: datetime | None) -> str | None:
    return dt.strftime("%H:%M") if dt else None


def summarize_night(
    events: list[dict[str, Any]], timezone: str, baseline: Baseline | None = None
) -> dict[str, Any]:
    """Trips, check-ins, escalations and anything unusual, from events ordered by time. Given her
    `baseline` (app/agents/baseline.py), it also flags trips at unusual hours and drift."""
    tz = ZoneInfo(timezone)
    rows = sorted(events, key=lambda e: e["device_ts"])
    trips: list[dict[str, Any]] = []
    open_trip: datetime | None = None
    lay_down = asleep = got_up = None
    checkins = escalations = restless = 0
    acked: list[str] = []
    for e in rows:
        kind, when, data = e["event_type"], _local(e["device_ts"], tz), e.get("data") or {}
        if kind == "lay_down" and lay_down is None:
            lay_down = when
        elif kind == "asleep" and asleep is None:
            asleep = when
        elif kind == "got_up":
            got_up = when
        elif kind == "bed_exit":
            if open_trip is not None:
                trips.append({"left": _hhmm(open_trip), "back": None, "min": None})
            open_trip = when
        elif kind == "bed_return" and open_trip is not None:
            minutes = round((when - open_trip).total_seconds() / 60)
            trips.append({"left": _hhmm(open_trip), "back": _hhmm(when), "min": minutes})
            open_trip = None
        elif kind == "checkin_result":
            checkins += 1
            if data.get("escalate"):
                escalations += 1
        elif kind == "checkin_timeout":
            escalations += 1
        elif kind == "family_ack":
            acked.append(data.get("contact", "family"))
        elif kind == "restless":
            restless += 1
    if open_trip is not None:
        trips.append({"left": _hhmm(open_trip), "back": None, "min": None})

    lengths = [t["min"] for t in trips if t["min"] is not None]
    unusual: list[str] = []
    if escalations:
        unusual.append(f"family were alerted {escalations} time{'s' if escalations > 1 else ''}")
    for t in trips:
        if t["min"] is None:
            unusual.append(f"got up at {t['left']} and had not come back to bed by morning")
        elif t["min"] >= LONG_TRIP_MIN:
            unusual.append(f"a {t['min']}-minute trip at {t['left']}")
        if baseline is not None and baseline.unusual_hour(time.fromisoformat(t["left"])):
            unusual.append(f"got up at {t['left']}, over an hour outside her usual {baseline.usual_hours()}")
    if len(trips) >= 3:
        unusual.append(f"{len(trips)} trips in one night")
    if baseline is not None:
        unusual += baseline.drift(len(trips))
    return {
        "lay_down": _hhmm(lay_down),
        "asleep": _hhmm(asleep),
        "got_up": _hhmm(got_up),
        "trips": trips,
        "trip_count": len(trips),
        "longest_trip_min": max(lengths) if lengths else 0,
        "checkins": checkins,
        "escalations": escalations,
        "acknowledged_by": acked,
        "restless_spells": restless,
        "unusual": unusual,
        **({"baseline": baseline.as_dict()} if baseline is not None else {}),
    }


def pending_goodnight(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The latest queued goodnight message that hasn't been played yet (events in time order)."""
    pending = None
    for e in sorted(events, key=lambda e: e["device_ts"]):
        if e["event_type"] == "goodnight_queued":
            pending = e.get("data") or {}
        elif e["event_type"] == "goodnight_played":
            pending = None
    return pending
