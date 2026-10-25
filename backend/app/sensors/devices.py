"""Whether the pillow's boards are answering, judged from the latest state report.

Plain code with no I/O: the router reads the state and asks `check_devices` what it says."""

from datetime import datetime, timedelta

from app.schemas.pillow_state import PillowPing, PillowState
from app.sensors.sensor_constants import PING_CLOCK_SKEW_S, PING_FRESH_S


def check_devices(pillow_id: str, state: PillowState | None, since: datetime, now: datetime) -> PillowPing:
    """Which boards answered a ping started at `since`: a report from `PING_FRESH_S` before it or
    later counts, one stamped in the future (seeded demo data) never does."""
    seen = state.last_seen_at if state else None
    fresh = seen is not None and since - timedelta(seconds=PING_FRESH_S) <= seen <= now + timedelta(
        seconds=PING_CLOCK_SKEW_S
    )
    link = state.link if state and fresh else None
    node_alive = fresh
    voice_unit_alive = fresh and link is not None
    return PillowPing(
        pillow_id=pillow_id,
        active=node_alive and voice_unit_alive,
        node_alive=node_alive,
        voice_unit_alive=voice_unit_alive,
        link=link,
        last_seen_at=seen,
        checked_at=now,
    )
