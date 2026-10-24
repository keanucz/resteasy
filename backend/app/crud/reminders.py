"""Data access for reminders and each time one falls due (the Routine agent)."""

from typing import Any

from supabase import AsyncClient

from app.crud.crud_constants import (
    OCCURRENCE_KEY,
    REMINDER_OCCURRENCES_TABLE,
    REMINDERS_TABLE,
)
from app.crud.supabase_query import fetch_one

OPEN = ["waiting", "due"]  # occurrence statuses still being worked on


async def list_reminders(db: AsyncClient, resident_id: str) -> list[dict[str, Any]]:
    """The resident's reminders, earliest in the day first."""
    response = await (
        db.table(REMINDERS_TABLE).select("*").eq("resident_id", resident_id).order("time_of_day").execute()
    )
    return response.data


async def get_reminder(db: AsyncClient, resident_id: str, reminder_id: int) -> dict[str, Any] | None:
    """One of the resident's reminders, or None (also when it belongs to someone else)."""
    return await fetch_one(
        db.table(REMINDERS_TABLE).select("*").eq("id", reminder_id).eq("resident_id", resident_id)
    )


async def create_reminder(db: AsyncClient, resident_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    response = await db.table(REMINDERS_TABLE).insert({"resident_id": resident_id, **fields}).execute()
    return response.data[0]


async def update_reminder(
    db: AsyncClient, resident_id: str, reminder_id: int, fields: dict[str, Any]
) -> dict[str, Any] | None:
    """Change a reminder; None if the resident has no such reminder."""
    response = await (
        db.table(REMINDERS_TABLE)
        .update(fields)
        .eq("id", reminder_id)
        .eq("resident_id", resident_id)
        .execute()
    )
    return response.data[0] if response.data else None


async def delete_reminder(db: AsyncClient, resident_id: str, reminder_id: int) -> bool:
    """Delete a reminder (its occurrences go with it); False if there was none."""
    response = await (
        db.table(REMINDERS_TABLE).delete().eq("id", reminder_id).eq("resident_id", resident_id).execute()
    )
    return bool(response.data)


async def list_active_reminders(db: AsyncClient) -> list[dict[str, Any]]:
    """Every active reminder of a resident who has a pillow, with the resident's name and timezone
    and their pillows' ids, for the tick."""
    response = await (
        db.table(REMINDERS_TABLE)
        .select("*, residents(preferred_name, timezone, pillows(id))")
        .eq("active", True)
        .execute()
    )
    return [r for r in response.data if r["residents"] and r["residents"]["pillows"]]


async def claim_occurrence(db: AsyncClient, reminder_id: int, due_at_iso: str) -> None:
    """Create the occurrence for this due time unless it already exists (safe to repeat)."""
    row = {"reminder_id": reminder_id, "due_at": due_at_iso}
    await (
        db.table(REMINDER_OCCURRENCES_TABLE)
        .upsert(row, on_conflict=OCCURRENCE_KEY, ignore_duplicates=True)
        .execute()
    )


async def list_open_occurrences(db: AsyncClient, reminder_ids: list[int]) -> list[dict[str, Any]]:
    """The waiting or due occurrences of these reminders."""
    if not reminder_ids:
        return []
    response = await (
        db.table(REMINDER_OCCURRENCES_TABLE)
        .select("*")
        .in_("reminder_id", reminder_ids)
        .in_("status", OPEN)
        .execute()
    )
    return response.data


async def list_occurrences(
    db: AsyncClient, resident_id: str, since_iso: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    """The resident's occurrences (due at or after `since`, in `status`), oldest first, each with
    its reminder."""
    query = (
        db.table(REMINDER_OCCURRENCES_TABLE)
        .select("*, reminders!inner(resident_id, label, kind, confirm)")
        .eq("reminders.resident_id", resident_id)
        .order("due_at")
    )
    if since_iso is not None:
        query = query.gte("due_at", since_iso)
    if status is not None:
        query = query.eq("status", status)
    return (await query.execute()).data


async def get_occurrence(db: AsyncClient, occurrence_id: int) -> dict[str, Any] | None:
    """An occurrence with its reminder's resident and settings, or None."""
    return await fetch_one(
        db.table(REMINDER_OCCURRENCES_TABLE)
        .select("*, reminders(resident_id, label, confirm)")
        .eq("id", occurrence_id)
    )


async def move_occurrence(db: AsyncClient, occurrence_id: int, expected: str, fields: dict[str, Any]) -> bool:
    """Update an occurrence only if it is still in status `expected`, so the tick and a result
    arriving at the same moment can't both move it. True if this call moved it."""
    response = await (
        db.table(REMINDER_OCCURRENCES_TABLE)
        .update(fields)
        .eq("id", occurrence_id)
        .eq("status", expected)
        .execute()
    )
    return bool(response.data)
