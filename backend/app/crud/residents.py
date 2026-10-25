"""Data access for a resident's settings and the contacts who look after them, with the nights
each contact is away."""

from typing import Any

from supabase import AsyncClient

from app.crud.crud_constants import (
    CONTACT_AWAY_TABLE,
    CONTACTS_TABLE,
    RESIDENT_CONTACTS_TABLE,
    RESIDENTS_TABLE,
)
from app.crud.supabase_query import fetch_one


async def get_resident(db: AsyncClient, resident_id: str) -> dict[str, Any] | None:
    """Return the resident's row (name, timezone, quiet hours, timeouts), or None."""
    return await fetch_one(db.table(RESIDENTS_TABLE).select("*").eq("id", resident_id))


async def list_contacts_in_order(db: AsyncClient, resident_id: str) -> list[dict[str, Any]]:
    """Return the resident's contacts (id, name, on_call, quiet hours, and how each may be alerted:
    sms_consent, call_alerts, app_alerts), first to alert first."""
    response = await (
        db.table(RESIDENT_CONTACTS_TABLE)
        .select(
            "priority, contacts(id, full_name, on_call, quiet_start, quiet_end, sms_consent, call_alerts, "
            "app_alerts)"
        )
        .eq("resident_id", resident_id)
        .order("priority")
        .execute()
    )
    return [row["contacts"] for row in response.data]


async def update_resident(db: AsyncClient, resident_id: str, fields: dict[str, Any]) -> None:
    """Change the resident's settings (quiet hours, timeout); the caller has run the Guardian."""
    if fields:
        await db.table(RESIDENTS_TABLE).update(fields).eq("id", resident_id).execute()


async def set_contact_on_call(db: AsyncClient, contact_id: str, on_call: bool) -> None:
    """Set whether a contact is on call; Night Watch tries reachable contacts first (re-read every 60 s)."""
    await db.table(CONTACTS_TABLE).update({"on_call": on_call}).eq("id", contact_id).execute()


async def list_away(db: AsyncClient, contact_id: str, since: str) -> list[dict[str, Any]]:
    """The contact's away nights that end on or after `since` (YYYY-MM-DD), soonest first."""
    response = await (
        db.table(CONTACT_AWAY_TABLE)
        .select("id, from_date, until_date, note")
        .eq("contact_id", contact_id)
        .gte("until_date", since)
        .order("from_date")
        .execute()
    )
    return response.data


async def add_away(db: AsyncClient, contact_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    response = await db.table(CONTACT_AWAY_TABLE).insert({**fields, "contact_id": contact_id}).execute()
    row = response.data[0]
    return {k: row[k] for k in ("id", "from_date", "until_date", "note")}


async def clear_away(db: AsyncClient, contact_id: str) -> None:
    await db.table(CONTACT_AWAY_TABLE).delete().eq("contact_id", contact_id).execute()
