"""Data access for what happens at night: events, incidents, notifications and the agent log."""

from datetime import UTC, datetime
from typing import Any

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.crud.crud_constants import (
    AGENT_LOG_TABLE,
    CLEARED_REASON,
    EVENTS_TABLE,
    INCIDENTS_TABLE,
    LIVE_INCIDENT_STATUSES,
    MISSING_COLUMN,
    NIGHT_TRIPS_VIEW,
    NOTIFICATIONS_TABLE,
)
from app.crud.pillows import list_pillow_ids_for_resident


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


def _cleared() -> dict[str, Any]:
    """Resolved, now, as "cleared"."""
    now = datetime.now(UTC).isoformat()
    return {"status": "resolved", "resolved_at": now, "resolved_reason": CLEARED_REASON}


async def clear_incident(db: AsyncClient, incident_id: int) -> None:
    """Resolve the incident as "cleared" if it is still live; one already resolved keeps its reason."""
    await (db.table(INCIDENTS_TABLE).update(_cleared()).eq("id", incident_id)
           .in_("status", list(LIVE_INCIDENT_STATUSES)).execute())


async def clear_live_incidents(db: AsyncClient, pillow_id: str) -> None:
    """Resolve every live incident of the pillow as "cleared": the ladder that owned them is gone
    (a restart forgets it), so the app must stop showing them as alerts in progress."""
    await (db.table(INCIDENTS_TABLE).update(_cleared()).eq("pillow_id", pillow_id)
           .in_("status", list(LIVE_INCIDENT_STATUSES)).execute())
async def update_live_incidents(db: AsyncClient, pillow_id: str, fields: dict[str, Any],
                                statuses: tuple[str, ...] = ("open", "acknowledged")) -> None:
    """Update every incident of the pillow still in `statuses`: an alert the backend lost track of
    (a restart mid-alert) ends, or is acknowledged, with the one it is running."""
    await (db.table(INCIDENTS_TABLE).update(fields).eq("pillow_id", pillow_id)
           .in_("status", list(statuses)).execute())


async def add_notification(
    db: AsyncClient, incident_id: int, contact_id: str, channel: str, message: str | None = None
) -> None:
    """Record a message to a contact as queued; app/notify's sender delivers sms and call rows."""
    row = {"incident_id": incident_id, "contact_id": contact_id, "channel": channel, "message": message}
    try:
        await db.table(NOTIFICATIONS_TABLE).insert(row).execute()
    except APIError as err:
        if err.code != MISSING_COLUMN:
            raise
        # The message column's migration isn't applied yet: queue it without the words, never drop it
        del row["message"]
        await db.table(NOTIFICATIONS_TABLE).insert(row).execute()


async def list_sendable_notifications(
    db: AsyncClient, channels: list[str], pillow_ids: list[str], since_iso: str
) -> list[dict]:
    """Queued notifications on these channels and pillows created since `since_iso`, oldest first,
    with the contact's phone and consent and the incident's pillow and summary."""
    response = await (
        db.table(NOTIFICATIONS_TABLE)
        .select(
            "id, incident_id, contact_id, channel, message, created_at, "
            "contacts(full_name, phone, sms_consent, call_alerts), "
            "incidents!inner(pillow_id, summary)"
        )
        .eq("status", "queued")
        .in_("channel", channels)
        .in_("incidents.pillow_id", pillow_ids)
        .gte("created_at", since_iso)
        .order("created_at")
        .execute()
    )
    return response.data


async def finish_notification(
    db: AsyncClient, notification_id: int, status: str, provider_ref: str | None, error: str | None
) -> None:
    """Mark a notification sent or failed, with the provider's reference and any error."""
    fields = {"status": status, "provider_ref": provider_ref, "error": error}
    await db.table(NOTIFICATIONS_TABLE).update(fields).eq("id", notification_id).execute()


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
    row = {
        "pillow_id": pillow_id,
        "agent": agent,
        "intent": intent,
        "tool": tool,
        "args": args or {},
        "incident_id": incident_id,
        "guardian": guardian,
        "reason": reason,
    }
    await db.table(AGENT_LOG_TABLE).insert(row).execute()


async def log_resident_action(
    db: AsyncClient,
    resident_id: str,
    agent: str,
    intent: str,
    tool: str | None = None,
    args: dict | None = None,
) -> None:
    """Append the action to the agent log of each of the resident's pillows.

    agent_log rows belong to a pillow, so a resident with no pillow yet gets no row."""
    for pillow_id in await list_pillow_ids_for_resident(db, resident_id):
        await log_action(db, pillow_id, agent, intent, tool=tool, args=args)


async def list_events_between(db: AsyncClient, pillow_id: str, start_iso: str, end_iso: str) -> list[dict]:
    """The pillow's events in [start, end), oldest first (one night, for the summary)."""
    response = await (
        db.table(EVENTS_TABLE)
        .select("event_type, device_ts, data")
        .eq("pillow_id", pillow_id)
        .gte("device_ts", start_iso)
        .lt("device_ts", end_iso)
        .order("device_ts")
        .execute()
    )
    return response.data


async def list_trips_between(db: AsyncClient, pillow_id: str, start_iso: str, end_iso: str) -> list[dict]:
    """The pillow's completed trips (bed_exit to bed_return) that started in [start, end), oldest first."""
    response = await (
        db.table(NIGHT_TRIPS_VIEW)
        .select("left_at, trip_min")
        .eq("pillow_id", pillow_id)
        .gte("left_at", start_iso)
        .lt("left_at", end_iso)
        .order("left_at")
        .execute()
    )
    return response.data


async def list_recent_events_of_type(
    db: AsyncClient, pillow_id: str, types: list[str], limit: int = 20
) -> list[dict]:
    """The pillow's latest events of the given types, oldest first."""
    response = await (
        db.table(EVENTS_TABLE)
        .select("event_type, device_ts, data")
        .eq("pillow_id", pillow_id)
        .in_("event_type", types)
        .order("device_ts", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(response.data))


async def list_agent_log_between(db: AsyncClient, pillow_id: str, start_iso: str, end_iso: str) -> list[dict]:
    """What the agents did in [start, end), oldest first: intent, tool, Guardian verdict, reason."""
    response = await (
        db.table(AGENT_LOG_TABLE)
        .select("ts, agent, intent, tool, args, guardian, reason")
        .eq("pillow_id", pillow_id)
        .gte("ts", start_iso)
        .lt("ts", end_iso)
        .order("ts")
        .execute()
    )
    return response.data


async def latest_log_row(db: AsyncClient, pillow_id: str, agent: str, tool: str | None = None) -> dict | None:
    """The most recent agent_log row written by `agent` (e.g. the last baseline change), optionally
    only rows for `tool`, or None."""
    query = db.table(AGENT_LOG_TABLE).select("ts, agent, intent, args, guardian, reason")
    query = query.eq("pillow_id", pillow_id).eq("agent", agent)
    if tool is not None:
        query = query.eq("tool", tool)
    response = await query.order("ts", desc=True).limit(1).execute()
    return response.data[0] if response.data else None
