"""Data access for app logins: the contact behind a login, and the pillows they look after."""

from typing import Any

from supabase import AsyncClient

from app.crud.crud_constants import CONTACTS_TABLE, PILLOWS_TABLE, RESIDENT_CONTACTS_TABLE
from app.crud.supabase_query import fetch_one


async def get_contact_for_user(db: AsyncClient, user_id: str) -> dict[str, Any] | None:
    """Return the contact linked to Supabase Auth user `user_id` (id, full_name), or None."""
    return await fetch_one(db.table(CONTACTS_TABLE).select("id, full_name").eq("user_id", user_id))


async def list_account_pillows(db: AsyncClient, contact_id: str) -> list[dict[str, Any]]:
    """Every pillow of every resident the contact looks after, with the resident's name and the role."""
    links = await (
        db.table(RESIDENT_CONTACTS_TABLE)
        .select("role, residents(id, preferred_name)")
        .eq("contact_id", contact_id)
        .order("priority")
        .execute()
    )
    by_resident = {link["residents"]["id"]: link for link in links.data}
    if not by_resident:
        return []
    pillows = await (
        db.table(PILLOWS_TABLE)
        .select("id, resident_id")
        .in_("resident_id", list(by_resident))
        .order("id")
        .execute()
    )
    return [
        {
            "pillow_id": pillow["id"],
            "resident_id": pillow["resident_id"],
            "preferred_name": by_resident[pillow["resident_id"]]["residents"]["preferred_name"],
            "role": by_resident[pillow["resident_id"]]["role"],
        }
        for pillow in pillows.data
    ]


async def get_role(db: AsyncClient, contact_id: str, resident_id: str) -> str | None:
    """The contact's role for this resident ('owner' or 'contact'), or None if they aren't linked."""
    link = await fetch_one(
        db.table(RESIDENT_CONTACTS_TABLE)
        .select("role")
        .eq("contact_id", contact_id)
        .eq("resident_id", resident_id)
    )
    return link["role"] if link else None
