"""Data access for registered pillows."""

from uuid import UUID

from supabase import AsyncClient

from app.crud.crud_constants import PILLOWS_TABLE, RESIDENT_CONTACTS_TABLE
from app.crud.supabase_query import fetch_one
from app.schemas.pillow import Pillow


async def get_pillow(db: AsyncClient, pillow_id: str) -> Pillow | None:
    """Return the pillow with `pillow_id`, or None if it is not registered."""
    row = await fetch_one(db.table(PILLOWS_TABLE).select("*").eq("id", pillow_id))
    return Pillow(**row) if row else None


async def list_pillows_for_contact(db: AsyncClient, contact_id: UUID) -> list[Pillow]:
    """Return every pillow belonging to a resident that `contact_id` looks after."""
    links = await (
        db.table(RESIDENT_CONTACTS_TABLE).select("resident_id").eq("contact_id", str(contact_id)).execute()
    )
    resident_ids = [link["resident_id"] for link in links.data]
    if not resident_ids:
        return []
    pillows = await db.table(PILLOWS_TABLE).select("*").in_("resident_id", resident_ids).order("id").execute()
    return [Pillow(**row) for row in pillows.data]


async def list_pillow_ids_for_resident(db: AsyncClient, resident_id: str) -> list[str]:
    """Return the ids of the resident's pillows (none before a pillow is set up for them)."""
    response = await db.table(PILLOWS_TABLE).select("id").eq("resident_id", resident_id).order("id").execute()
    return [row["id"] for row in response.data]
