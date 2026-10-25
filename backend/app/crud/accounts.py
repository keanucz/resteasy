"""Data access for app logins: the contact behind a login, and the pillows they look after."""

from typing import Any

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.core.app_constants import NEW_PILLOW_QUIET_HOURS, OWNER_ROLE
from app.crud.crud_constants import (
    CONTACTS_TABLE,
    JOIN_PRIORITY_TRIES,
    PILLOWS_TABLE,
    RESIDENT_CONTACTS_TABLE,
    RESIDENTS_TABLE,
    UNIQUE_VIOLATION,
)
from app.crud.supabase_query import fetch_one


async def get_contact_for_user(db: AsyncClient, user_id: str) -> dict[str, Any] | None:
    """Return the contact linked to Supabase Auth user `user_id` (id, full_name), or None."""
    return await fetch_one(db.table(CONTACTS_TABLE).select("id, full_name").eq("user_id", user_id))


async def get_alert_contact(db: AsyncClient, user_id: str) -> dict[str, Any] | None:
    """Return the login's contact with its mobile number, alert switches, on-call and quiet hours,
    and test flag, or None."""
    return await fetch_one(
        db.table(CONTACTS_TABLE)
        .select(
            "id, full_name, phone, sms_consent, call_alerts, app_alerts, restless_alerts, on_call, "
            "quiet_start, quiet_end, is_test"
        )
        .eq("user_id", user_id)
    )


async def list_contact_resident_ids(db: AsyncClient, contact_id: str) -> list[str]:
    """Every resident this contact looks after."""
    response = (
        await db.table(RESIDENT_CONTACTS_TABLE).select("resident_id").eq("contact_id", contact_id).execute()
    )
    return [row["resident_id"] for row in response.data]


async def update_contact(db: AsyncClient, contact_id: str, fields: dict[str, Any]) -> bool:
    """Change the contact's own fields; False when the new phone number belongs to another contact."""
    if not fields:
        return True
    try:
        await db.table(CONTACTS_TABLE).update(fields).eq("id", contact_id).execute()
    except APIError as err:
        if err.code == UNIQUE_VIOLATION:
            return False
        raise
    return True


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
    """Make the login an owner of the resident (for the demo, everyone may change her settings): its
    own contact row if it has none, then a link at the next free priority. Off call, so it never gets
    the real alerts. Already linked: no-op."""
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
        link = {
            "resident_id": resident_id,
            "contact_id": contact["id"],
            "priority": priority,
            "role": OWNER_ROLE,
        }
        try:
            await db.table(RESIDENT_CONTACTS_TABLE).insert(link).execute()
            return
        except APIError:  # another sign-up took that priority first
            if attempt == JOIN_PRIORITY_TRIES - 1:
                raise


async def create_household(
    db: AsyncClient, user_id: str, contact_name: str, resident_name: str, pillow_id: str
) -> bool:
    """Set up pillow `pillow_id` for a new resident called `resident_name`, with the login as their
    owner and first contact (its own contact row if it has none). False, with nothing left behind,
    when that pillow is already registered."""
    names = {"full_name": resident_name, "preferred_name": resident_name}
    row = {**names, **NEW_PILLOW_QUIET_HOURS}
    resident = (await db.table(RESIDENTS_TABLE).insert(row).execute()).data[0]
    try:
        await db.table(PILLOWS_TABLE).insert({"id": pillow_id, "resident_id": resident["id"]}).execute()
    except APIError as err:
        await db.table(RESIDENTS_TABLE).delete().eq("id", resident["id"]).execute()
        if err.code == UNIQUE_VIOLATION:
            return False
        raise
    contact = await get_contact_for_user(db, user_id)
    if contact is None:
        row = {"full_name": contact_name, "user_id": user_id, "on_call": False}
        contact = (await db.table(CONTACTS_TABLE).insert(row).execute()).data[0]
    link = {"resident_id": resident["id"], "contact_id": contact["id"], "priority": 1, "role": OWNER_ROLE}
    await db.table(RESIDENT_CONTACTS_TABLE).insert(link).execute()
    return True
