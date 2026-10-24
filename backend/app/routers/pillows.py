"""Pillow router: the device pushes its state here and the app reads it back."""

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import PillowDep, SupabaseDep
from app.crud.pillow_state import get_state, save_state
from app.schemas.pillow import Pillow
from app.schemas.pillow_state import DeviceState, PillowState

router = APIRouter(prefix="/pillows/{pillow_id}", tags=["pillows"])


@router.get("")
async def read_pillow(pillow: PillowDep) -> Pillow:
    """Return a registered pillow."""
    return pillow


@router.post("/state")
async def report_state(pillow: PillowDep, state: DeviceState, db: SupabaseDep) -> PillowState:
    """Store the device's latest sensor report (CONTRACT.md section 1)."""
    return await save_state(db, pillow.id, state)


@router.get("/state")
async def read_state(pillow: PillowDep, db: SupabaseDep) -> PillowState:
    """Return the pillow's latest state for the app's live status card."""
    state = await get_state(db, pillow.id)
    if state is None:
        detail = f"Pillow {pillow.id} has no state yet"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return state
