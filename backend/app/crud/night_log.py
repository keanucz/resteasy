"""Data access for what happens at night: events, incidents, notifications and the agent log."""

from datetime import UTC, datetime
from typing import Any

from supabase import AsyncClient

from app.crud.crud_constants import AGENT_LOG_TABLE, EVENTS_TABLE, INCIDENTS_TABLE, NOTIFICATIONS_TABLE


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
    reason: str | None = None,
) -> None:
    """Append one agent decision to agent_log, which the family app shows live."""
    row = {"pillow_id": pillow_id, "agent": agent, "intent": intent, "tool": tool, "args": args or {},
           "incident_id": incident_id, "reason": reason}
    await db.table(AGENT_LOG_TABLE).insert(row).execute()
