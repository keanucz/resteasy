"""Data access for the latest state of each pillow."""

from datetime import UTC, datetime

from supabase import AsyncClient

from app.crud.crud_constants import PILLOW_STATE_KEY, PILLOW_STATE_TABLE
from app.crud.supabase_query import fetch_one
from app.schemas.pillow_state import DeviceState, PillowState


def _state_row(pillow_id: str, state: DeviceState) -> dict:
    """Flatten a device report into `pillow_state` columns; night_state stays with the agents."""
    return {
        "pillow_id": pillow_id,
        "device_ts": datetime.fromtimestamp(state.ts, UTC).isoformat(),
        "head_on": state.head_on,
        "motion": state.motion,
        "room_motion": state.room_motion,
        "light": state.light,
        "temp_c": state.temp_c,
        "humidity": state.humidity,
        "key_talk": state.keys.talk,
        "key_fine": state.keys.fine,
        "key_family": state.keys.family,
        "knob": state.knob,
        "last_seen_at": datetime.now(UTC).isoformat(),
    }


async def save_state(db: AsyncClient, pillow_id: str, state: DeviceState) -> PillowState:
    """Store a device report as the pillow's latest state and return the stored row."""
    row = _state_row(pillow_id, state)
    response = await db.table(PILLOW_STATE_TABLE).upsert(row, on_conflict=PILLOW_STATE_KEY).execute()
    return PillowState(**response.data[0])


async def get_state(db: AsyncClient, pillow_id: str) -> PillowState | None:
    """Return the pillow's latest state, or None if it has never reported."""
    row = await fetch_one(db.table(PILLOW_STATE_TABLE).select("*").eq("pillow_id", pillow_id))
    return PillowState(**row) if row else None
