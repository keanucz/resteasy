"""Data access for the voices cloned in the family app, each offered only for its resident."""

from typing import Any

from supabase import AsyncClient

from app.core.voice_constants import VOICE_IDS
from app.crud.crud_constants import VOICE_CLONE_COLUMNS, VOICE_CLONES_TABLE
from app.crud.supabase_query import fetch_one


async def list_voice_clones(db: AsyncClient, resident_id: str) -> list[dict[str, Any]]:
    """The resident's cloned voices, oldest first, each with the name of who recorded it."""
    response = await (
        db.table(VOICE_CLONES_TABLE)
        .select(VOICE_CLONE_COLUMNS)
        .eq("resident_id", resident_id)
        .order("created_at")
        .execute()
    )
    return response.data


async def get_voice_clone(db: AsyncClient, resident_id: str, voice_id: str) -> dict[str, Any] | None:
    """One of the resident's cloned voices with who recorded it, or None (also when it is someone
    else's)."""
    return await fetch_one(
        db.table(VOICE_CLONES_TABLE)
        .select(VOICE_CLONE_COLUMNS)
        .eq("voice_id", voice_id)
        .eq("resident_id", resident_id)
    )


async def create_voice_clone(
    db: AsyncClient, resident_id: str, voice_id: str, name: str, created_by: str
) -> dict[str, Any]:
    """Record a voice just cloned at Cartesia and return it as `get_voice_clone` does."""
    row = {"voice_id": voice_id, "resident_id": resident_id, "name": name, "created_by": created_by}
    await db.table(VOICE_CLONES_TABLE).insert(row).execute()
    return await get_voice_clone(db, resident_id, voice_id)


async def delete_voice_clone(db: AsyncClient, resident_id: str, voice_id: str) -> None:
    """Forget one of the resident's cloned voices."""
    await (
        db.table(VOICE_CLONES_TABLE)
        .delete()
        .eq("voice_id", voice_id)
        .eq("resident_id", resident_id)
        .execute()
    )


async def is_offered_voice(db: AsyncClient, resident_id: str, voice_id: str) -> bool:
    """Whether the pillow may speak to her in this voice: a stock voice or one of her clones."""
    return voice_id in VOICE_IDS or await get_voice_clone(db, resident_id, voice_id) is not None
