"""Data access for reminders and each time one falls due (the Routine agent)."""

from typing import Any

from supabase import AsyncClient, PostgrestAPIError

from app.core.app_constants import CONSENT_PENDING
from app.crud.crud_constants import (
    OCCURRENCE_COLUMNS,
    OCCURRENCE_KEY,
    REMINDER_COLUMNS,
    REMINDER_OCCURRENCES_TABLE,
    REMINDERS_TABLE,
    UNIQUE_VIOLATION,
)
from app.crud.supabase_query import fetch_one

OPEN = ["waiting", "due"]  # occurrence statuses still being worked on


async def list_reminders(
    db: AsyncClient, resident_id: str, active_only: bool = False
) -> list[dict[str, Any]]:
    """The resident's reminders (only the active ones, when `active_only`), earliest in the day
    first, each with the name of who set it up."""
    query = db.table(REMINDERS_TABLE).select(REMINDER_COLUMNS).eq("resident_id", resident_id)
    if active_only:
        query = query.eq("active", True)
    return (await query.order("time_of_day").order("id").execute()).data


async def get_reminder(db: AsyncClient, resident_id: str, reminder_id: int) -> dict[str, Any] | None:
    """One of the resident's reminders with who set it up, or None (also when it belongs to
    someone else)."""
    return await fetch_one(
        db.table(REMINDERS_TABLE)
        .select(REMINDER_COLUMNS)
        .eq("id", reminder_id)
        .eq("resident_id", resident_id)
    )


async def create_reminder(db: AsyncClient, resident_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Insert a reminder and return it as `get_reminder` does."""
    response = await db.table(REMINDERS_TABLE).insert({"resident_id": resident_id, **fields}).execute()
    return await get_reminder(db, resident_id, response.data[0]["id"])


async def update_reminder(
    db: AsyncClient, resident_id: str, reminder_id: int, fields: dict[str, Any]
) -> dict[str, Any] | None:
    """Change a reminder and return it as `get_reminder` does; None if the resident has no such
    reminder."""
    response = await (
        db.table(REMINDERS_TABLE)
        .update(fields)
        .eq("id", reminder_id)
        .eq("resident_id", resident_id)
        .execute()
    )
    return await get_reminder(db, resident_id, reminder_id) if response.data else None


async def delete_reminder(db: AsyncClient, resident_id: str, reminder_id: int) -> dict[str, Any] | None:
    """Delete a reminder (its occurrences go with it) and return the deleted row; None if there was
    none."""
    response = await (
        db.table(REMINDERS_TABLE).delete().eq("id", reminder_id).eq("resident_id", resident_id).execute()
    )
    return response.data[0] if response.data else None


async def set_consent(db: AsyncClient, reminder_id: int, consent: str, at_iso: str) -> bool:
    """Record her answer, unless the reminder is no longer waiting for one. True if recorded."""
    response = await (
        db.table(REMINDERS_TABLE)
        .update({"consent": consent, "consent_at": at_iso})
        .eq("id", reminder_id)
        .eq("consent", CONSENT_PENDING)
        .execute()
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


async def claim_occurrence(db: AsyncClient, reminder_id: int, due_at_iso: str, purpose: str) -> None:
    """Create the occurrence for this due time and purpose unless it already exists (safe to
    repeat). Until the old (reminder_id, due_at) key is dropped, a slot of the other purpose at
    the same time counts as taken."""
    row = {"reminder_id": reminder_id, "due_at": due_at_iso, "purpose": purpose}
    try:
        await (
            db.table(REMINDER_OCCURRENCES_TABLE)
            .upsert(row, on_conflict=OCCURRENCE_KEY, ignore_duplicates=True)
            .execute()
        )
    except PostgrestAPIError as error:
        if error.code != UNIQUE_VIOLATION:
            raise


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
    db: AsyncClient,
    resident_id: str,
    since_iso: str | None = None,
    until_iso: str | None = None,
    status: str | None = None,
    purpose: str | None = None,
) -> list[dict[str, Any]]:
    """The resident's occurrences due in [since, until), in `status`, for `purpose`, oldest first,
    each with its reminder."""
    query = (
        db.table(REMINDER_OCCURRENCES_TABLE)
        .select(OCCURRENCE_COLUMNS)
        .eq("reminders.resident_id", resident_id)
        .order("due_at")
    )
    if since_iso is not None:
        query = query.gte("due_at", since_iso)
    if until_iso is not None:
        query = query.lt("due_at", until_iso)
    if status is not None:
        query = query.eq("status", status)
    if purpose is not None:
        query = query.eq("purpose", purpose)
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
