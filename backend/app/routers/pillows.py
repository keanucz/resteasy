"""Pillow router: the device pushes its state here and the app reads it back."""

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import NightWatchDep, PillowDep, SupabaseDep
from app.crud.pillow_state import get_state, save_state
from app.schemas.checkin import Acknowledgement, CheckinResult, NightStatus
from app.schemas.pillow import Pillow
from app.schemas.pillow_state import DeviceState, PillowState

router = APIRouter(prefix="/pillows/{pillow_id}", tags=["pillows"])


@router.get("")
async def read_pillow(pillow: PillowDep) -> Pillow:
    """Return a registered pillow."""
    return pillow


@router.post("/state")
async def report_state(
    pillow: PillowDep, state: DeviceState, db: SupabaseDep, night_watch: NightWatchDep
) -> PillowState:
    """Store the device's latest sensor report (CONTRACT.md section 1) and let Night Watch act on it."""
    stored = await save_state(db, pillow.id, state)
    await night_watch.report_state(db, pillow, state)
    return stored


@router.get("/state")
async def read_state(pillow: PillowDep, db: SupabaseDep) -> PillowState:
    """Return the pillow's latest state for the app's live status card."""
    state = await get_state(db, pillow.id)
    if state is None:
        detail = f"Pillow {pillow.id} has no state yet"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return state


@router.post("/checkin")
async def report_checkin(
    pillow: PillowDep, result: CheckinResult, db: SupabaseDep, night_watch: NightWatchDep
) -> NightStatus:
    """The base laptop's voice check-in finished: escalate to family, or she said she's fine."""
    night_state = await night_watch.checkin_done(db, pillow, result.escalate, result.reason)
    return NightStatus(night_state=night_state)


@router.post("/ack")
async def acknowledge_alert(
    pillow: PillowDep, ack: Acknowledgement, db: SupabaseDep, night_watch: NightWatchDep
) -> NightStatus:
    """The app's "I'm on it": stop alerting other contacts and tell Mum who is coming."""
    night_state = await night_watch.acknowledge(db, pillow, str(ack.contact_id))
    if night_state is None:
        detail = f"Contact {ack.contact_id} does not look after pillow {pillow.id}"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return NightStatus(night_state=night_state)
