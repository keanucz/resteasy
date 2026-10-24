"""Data access for a resident's settings and the contacts who look after them."""

from typing import Any

from supabase import AsyncClient

from app.crud.crud_constants import RESIDENT_CONTACTS_TABLE, RESIDENTS_TABLE
from app.crud.supabase_query import fetch_one


async def get_resident(db: AsyncClient, resident_id: str) -> dict[str, Any] | None:
    """Return the resident's row (name, timezone, quiet hours, timeouts), or None."""
    return await fetch_one(db.table(RESIDENTS_TABLE).select("*").eq("id", resident_id))


async def list_contacts_in_order(db: AsyncClient, resident_id: str) -> list[dict[str, Any]]:
    """Return the resident's contacts as {id, full_name}, first to alert first."""
    response = await (
        db.table(RESIDENT_CONTACTS_TABLE)
        .select("priority, contacts(id, full_name)")
        .eq("resident_id", resident_id)
        .order("priority")
        .execute()
    )
    return [row["contacts"] for row in response.data]
