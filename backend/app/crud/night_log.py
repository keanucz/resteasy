"""Data access for what happens at night: events, incidents, notifications and the agent log."""

from datetime import UTC, datetime
from typing import Any

from supabase import AsyncClient

from app.crud.crud_constants import (
    AGENT_LOG_TABLE,
    EVENTS_TABLE,
    INCIDENTS_TABLE,
    NIGHT_TRIPS_VIEW,
    NOTIFICATIONS_TABLE,
)


def _iso(ts: float) -> str:
    """Unix seconds (device or simulator clock) as an ISO timestamp for a timestamptz column."""
    return datetime.fromtimestamp(ts, UTC).isoformat()


async def add_event(db: AsyncClient, pillow_id: str, event_type: str, ts: float, data: dict) -> None:
    """Append a derived pillow event (lay_down, bed_exit, ...)."""
    row = {"pillow_id": pillow_id, "event_type": event_type, "device_ts": _iso(ts), "data": data}
    await db.table(EVENTS_TABLE).insert(row).execute()


async def open_incident(db: AsyncClient, pillow_id: str, kind: str, summary: str) -> int:
    """Open an incident (an alert in progress) and return its id."""
    row = {"pillow_id": pillow_id, "kind": kind, "summary": summary}
    response = await db.table(INCIDENTS_TABLE).insert(row).execute()
    return response.data[0]["id"]


async def update_incident(db: AsyncClient, incident_id: int, fields: dict[str, Any]) -> None:
    """Update an incident's step or status."""
    await db.table(INCIDENTS_TABLE).update(fields).eq("id", incident_id).execute()


async def add_notification(db: AsyncClient, incident_id: int, contact_id: str, channel: str) -> None:
    """Record a message to a contact as queued; a sender (Twilio, not built) delivers it."""
    row = {"incident_id": incident_id, "contact_id": contact_id, "channel": channel}
    await db.table(NOTIFICATIONS_TABLE).insert(row).execute()


async def log_action(
    db: AsyncClient,
    pillow_id: str,
    agent: str,
    intent: str,
    tool: str | None = None,
    args: dict | None = None,
    incident_id: int | None = None,
    guardian: str | None = None,
    reason: str | None = None,
) -> None:
    """Append one agent decision to agent_log, which the family app shows live.

    `guardian` is the Guardian's verdict on it ("allowed" / "blocked"), None for a plain note."""
    row = {"pillow_id": pillow_id, "agent": agent, "intent": intent, "tool": tool, "args": args or {},
           "incident_id": incident_id, "guardian": guardian, "reason": reason}
    await db.table(AGENT_LOG_TABLE).insert(row).execute()


async def list_events_between(db: AsyncClient, pillow_id: str, start_iso: str, end_iso: str) -> list[dict]:
    """The pillow's events in [start, end), oldest first (one night, for the summary)."""
    response = await (
        db.table(EVENTS_TABLE).select("event_type, device_ts, data").eq("pillow_id", pillow_id)
        .gte("device_ts", start_iso).lt("device_ts", end_iso).order("device_ts").execute()
    )
    return response.data


async def list_trips_between(db: AsyncClient, pillow_id: str, start_iso: str, end_iso: str) -> list[dict]:
    """The pillow's completed trips (bed_exit to bed_return) that started in [start, end), oldest first."""
    response = await (
        db.table(NIGHT_TRIPS_VIEW).select("left_at, trip_min").eq("pillow_id", pillow_id)
        .gte("left_at", start_iso).lt("left_at", end_iso).order("left_at").execute()
    )
    return response.data


async def list_recent_events_of_type(
    db: AsyncClient, pillow_id: str, types: list[str], limit: int = 20
) -> list[dict]:
    """The pillow's latest events of the given types, oldest first."""
    response = await (
        db.table(EVENTS_TABLE).select("event_type, device_ts, data").eq("pillow_id", pillow_id)
        .in_("event_type", types).order("device_ts", desc=True).limit(limit).execute()
    )
    return list(reversed(response.data))


async def list_agent_log_between(db: AsyncClient, pillow_id: str, start_iso: str, end_iso: str) -> list[dict]:
    """What the agents did in [start, end), oldest first: intent, tool, Guardian verdict, reason."""
    response = await (
        db.table(AGENT_LOG_TABLE).select("ts, agent, intent, tool, args, guardian, reason")
        .eq("pillow_id", pillow_id).gte("ts", start_iso).lt("ts", end_iso).order("ts").execute()
    )
    return response.data


async def latest_log_row(db: AsyncClient, pillow_id: str, agent: str) -> dict | None:
    """The most recent agent_log row written by `agent` (e.g. the last Morning Brief), or None."""
    response = await (
        db.table(AGENT_LOG_TABLE).select("ts, agent, intent, args, guardian, reason")
        .eq("pillow_id", pillow_id).eq("agent", agent).order("ts", desc=True).limit(1).execute()
    )
    return response.data[0] if response.data else None
