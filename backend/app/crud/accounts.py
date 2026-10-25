"""Data access for app logins: the contact behind a login, and the pillows they look after."""

from typing import Any

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.crud.crud_constants import (
    CONTACTS_TABLE,
    JOIN_PRIORITY_TRIES,
    PILLOWS_TABLE,
    RESIDENT_CONTACTS_TABLE,
)
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


async def get_link_for_user(db: AsyncClient, user_id: str, resident_id: str) -> dict[str, Any] | None:
    """How the login's contact looks after this resident (role, contact_id), or None if not linked."""
    return await fetch_one(
        db.table(RESIDENT_CONTACTS_TABLE)
        .select("role, contact_id, contacts!inner(user_id)")
        .eq("resident_id", resident_id)
        .eq("contacts.user_id", user_id)
    )


async def get_link_for_contact(db: AsyncClient, contact_id: str, resident_id: str) -> dict[str, Any] | None:
    """How the contact looks after this resident (role, contact_id, their full_name), or None if
    not linked."""
    return await fetch_one(
        db.table(RESIDENT_CONTACTS_TABLE)
        .select("role, contact_id, contacts!inner(full_name)")
        .eq("resident_id", resident_id)
        .eq("contact_id", contact_id)
    )


async def join_household(db: AsyncClient, user_id: str, full_name: str, resident_id: str) -> None:
    """Make the login a plain contact of the resident: its own contact row if it has none, then a
    link at the next free priority. Off call, so it never gets the real alerts. Already linked: no-op."""
    contact = await get_contact_for_user(db, user_id)
    if contact is None:
        row = {"full_name": full_name, "user_id": user_id, "on_call": False}
        contact = (await db.table(CONTACTS_TABLE).insert(row).execute()).data[0]
    if await get_link_for_contact(db, contact["id"], resident_id):
        return
    for attempt in range(JOIN_PRIORITY_TRIES):
        last = await (
            db.table(RESIDENT_CONTACTS_TABLE)
            .select("priority")
            .eq("resident_id", resident_id)
            .order("priority", desc=True)
            .limit(1)
            .execute()
        )
        priority = (last.data[0]["priority"] if last.data else 0) + 1
        link = {"resident_id": resident_id, "contact_id": contact["id"], "priority": priority}
        try:
            await db.table(RESIDENT_CONTACTS_TABLE).insert(link).execute()
            return
        except APIError:  # another sign-up took that priority first
            if attempt == JOIN_PRIORITY_TRIES - 1:
                raise
