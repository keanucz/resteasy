"""Pillow router: the device pushes its state here and the app reads it back."""

import asyncio
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError

from app.core.dependencies import (
    NightWatchDep,
    PillowDep,
    ReadingsRecorderDep,
    SupabaseDep,
    require_checkin_token,
)
from app.crud.pillow_state import get_state, save_state
from app.crud.readings import upsert_reading
from app.schemas.checkin import Acknowledgement, CheckinResult, KeyPress, NightStatus
from app.schemas.pillow import Pillow
from app.schemas.pillow_state import DeviceState, PillowPing, PillowState
from app.sensors.devices import check_devices
from app.sensors.sensor_constants import PING_POLL_S, PING_WAIT_S

log = logging.getLogger(__name__)

router = APIRouter(prefix="/pillows/{pillow_id}", tags=["pillows"])


@router.get("")
async def read_pillow(pillow: PillowDep) -> Pillow:
    """Return a registered pillow."""
    return pillow


@router.post("/state")
async def report_state(
    pillow: PillowDep,
    state: DeviceState,
    db: SupabaseDep,
    night_watch: NightWatchDep,
    readings: ReadingsRecorderDep,
) -> PillowState:
    """Store the device's latest sensor report (CONTRACT.md section 1) and let Night Watch act on it.

    It also goes into the per-minute history the app's night charts draw; a failed history write
    is logged and never fails the report."""
    stored = await save_state(db, pillow.id, state)
    await night_watch.report_state(db, pillow, state)
    for row in readings.observe(pillow.id, state):
        try:
            await upsert_reading(db, row)
        except APIError:
            log.exception("Could not write the reading for pillow %s at %s", pillow.id, row["ts"])
    return stored


@router.get("/state")
async def read_state(pillow: PillowDep, db: SupabaseDep) -> PillowState:
    """Return the pillow's latest state for the app's live status card."""
    state = await get_state(db, pillow.id)
    if state is None:
        detail = f"Pillow {pillow.id} has no state yet"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return state


@router.post("/ping")
async def ping_pillow(pillow: PillowDep, db: SupabaseDep) -> PillowPing:
    """Check that both boards in the pillow are answering, for the app's "Connect pillow".

    The boards can't be reached directly (the bridge only forwards commands, it never answers them),
    so this waits up to `PING_WAIT_S` for a fresh state report and reads which boards it came
    through. `active` is true once the node and the voice unit both answered."""
    since = datetime.now(UTC)
    deadline = time.monotonic() + PING_WAIT_S
    while True:
        ping = check_devices(pillow.id, await get_state(db, pillow.id), since, datetime.now(UTC))
        if ping.active or time.monotonic() >= deadline:
            return ping
        await asyncio.sleep(PING_POLL_S)


@router.post("/checkin", dependencies=[Depends(require_checkin_token)])
async def report_checkin(
    pillow: PillowDep, result: CheckinResult, db: SupabaseDep, night_watch: NightWatchDep
) -> NightStatus:
    """The base laptop's voice check-in finished: escalate to family, or she said she's fine."""
    night_state = await night_watch.checkin_done(db, pillow, result.escalate, result.reason, result.distress)
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


@router.post("/keys", dependencies=[Depends(require_checkin_token)])
async def press_key(
    pillow: PillowDep, press: KeyPress, db: SupabaseDep, night_watch: NightWatchDep
) -> NightStatus:
    """A key on the bedside pad, from the base laptop: "fine" stops a check-in or an alert,
    "family" starts the alert ladder, "talk" is only logged (the laptop runs the conversation)."""
    return NightStatus(night_state=await night_watch.press_key(db, pillow, press.key))
