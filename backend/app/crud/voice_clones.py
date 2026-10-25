"""Data access for a resident's own voices: clones made in the family app and accent copies of a
voice, each offered only for its resident."""

from typing import Any

from supabase import AsyncClient

from app.core.voice_constants import ACCENT_SOURCE, CLONE_SOURCE, VOICE_IDS
from app.crud.crud_constants import VOICE_CLONE_COLUMNS, VOICE_CLONES_TABLE
from app.crud.supabase_query import fetch_one


async def list_voice_clones(db: AsyncClient, resident_id: str) -> list[dict[str, Any]]:
    """The resident's own voices, oldest first, each with the name of who made it."""
    response = await (
        db.table(VOICE_CLONES_TABLE)
        .select(VOICE_CLONE_COLUMNS)
        .eq("resident_id", resident_id)
        .order("created_at")
        .execute()
    )
    return response.data


async def get_voice_clone(db: AsyncClient, resident_id: str, voice_id: str) -> dict[str, Any] | None:
    """One of the resident's own voices with who made it, or None (also when it is someone else's)."""
    return await fetch_one(
        db.table(VOICE_CLONES_TABLE)
        .select(VOICE_CLONE_COLUMNS)
        .eq("voice_id", voice_id)
        .eq("resident_id", resident_id)
    )


async def find_accent_copy(
    db: AsyncClient, resident_id: str, base_voice_id: str, accent: str
) -> dict[str, Any] | None:
    """Her copy of `base_voice_id` with `accent`, if one was made already."""
    return await fetch_one(
        db.table(VOICE_CLONES_TABLE)
        .select(VOICE_CLONE_COLUMNS)
        .eq("resident_id", resident_id)
        .eq("kind", ACCENT_SOURCE)
        .eq("base_voice_id", base_voice_id)
        .eq("accent", accent)
        .limit(1)
    )


async def create_voice_clone(
    db: AsyncClient,
    resident_id: str,
    voice_id: str,
    name: str,
    created_by: str,
    *,
    kind: str = CLONE_SOURCE,
    base_voice_id: str | None = None,
    accent: str | None = None,
) -> dict[str, Any]:
    """Record a voice just made at Cartesia (a clone, or an accent copy of `base_voice_id`) and
    return it as `get_voice_clone` does."""
    row = {
        "voice_id": voice_id,
        "resident_id": resident_id,
        "name": name,
        "created_by": created_by,
        "kind": kind,
        "base_voice_id": base_voice_id,
        "accent": accent,
    }
    await db.table(VOICE_CLONES_TABLE).insert(row).execute()
    return await get_voice_clone(db, resident_id, voice_id)


async def delete_voice_clone(db: AsyncClient, resident_id: str, voice_id: str) -> None:
    """Forget one of the resident's own voices."""
    await (
        db.table(VOICE_CLONES_TABLE)
        .delete()
        .eq("voice_id", voice_id)
        .eq("resident_id", resident_id)
        .execute()
    )


async def is_offered_voice(db: AsyncClient, resident_id: str, voice_id: str) -> bool:
    """Whether the pillow may speak to her in this voice: a stock voice or one of her own."""
    return voice_id in VOICE_IDS or await get_voice_clone(db, resident_id, voice_id) is not None
