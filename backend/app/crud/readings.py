"""Data access for the per-minute sensor history (the `readings` table)."""

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.crud.crud_constants import MISSING_COLUMN, READINGS_KEY, READINGS_TABLE


async def upsert_reading(db: AsyncClient, row: dict) -> None:
    """Write one minute's reading, merging into the row already there.

    Only the columns in `row` change, so a sensor this device doesn't have (left out of `row`)
    keeps whatever another device wrote for that minute."""
    table = db.table(READINGS_TABLE)
    try:
        await table.upsert(row, on_conflict=READINGS_KEY).execute()
    except APIError as err:
        if err.code != MISSING_COLUMN or "sound_db" not in row:
            raise
        # The live_readings migration isn't applied yet: keep the minute, without its loudness
        without_loudness = {k: v for k, v in row.items() if k != "sound_db"}
        await table.upsert(without_loudness, on_conflict=READINGS_KEY).execute()
