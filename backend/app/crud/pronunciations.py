"""Data access for the words the pillow says her way: names, places, medicines, each with how to say it."""

from typing import Any

from supabase import AsyncClient

from app.core.voice_constants import PRONUNCIATION_COLUMNS, PRONUNCIATIONS_TABLE
from app.crud.supabase_query import fetch_one


async def list_pronunciations(db: AsyncClient, resident_id: str) -> list[dict[str, Any]]:
    """Her words, oldest first, each with the name of who added it."""
    response = await (
        db.table(PRONUNCIATIONS_TABLE)
        .select(PRONUNCIATION_COLUMNS)
        .eq("resident_id", resident_id)
        .order("created_at")
        .execute()
    )
    return response.data


async def get_pronunciation(
    db: AsyncClient, resident_id: str, pronunciation_id: str
) -> dict[str, Any] | None:
    """One of her words with who added it, or None (also when it is someone else's)."""
    return await fetch_one(
        db.table(PRONUNCIATIONS_TABLE)
        .select(PRONUNCIATION_COLUMNS)
        .eq("id", pronunciation_id)
        .eq("resident_id", resident_id)
    )


async def create_pronunciation(
    db: AsyncClient, resident_id: str, word: str, sounds_like: str, created_by: str
) -> dict[str, Any]:
    """Add a word and return it as `get_pronunciation` does; raises on a word she already has."""
    row = {"resident_id": resident_id, "word": word, "sounds_like": sounds_like, "created_by": created_by}
    response = await db.table(PRONUNCIATIONS_TABLE).insert(row).execute()
    return await get_pronunciation(db, resident_id, response.data[0]["id"])


async def delete_pronunciation(db: AsyncClient, resident_id: str, pronunciation_id: str) -> None:
    """Forget one of her words."""
    await (
        db.table(PRONUNCIATIONS_TABLE)
        .delete()
        .eq("id", pronunciation_id)
        .eq("resident_id", resident_id)
        .execute()
    )
