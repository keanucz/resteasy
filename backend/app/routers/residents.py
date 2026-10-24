"""Residents router: the settings that live on the resident, so they work before any pillow exists.

"When it watches" is her quiet hours, "before telling family" is the check-in wait. Any login that
looks after her reads them; only the owner's login changes them, and each change shows in the
agent log of her pillows. Requests carry the app's Supabase access token, like the account router.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.app_constants import FAMILY_APP_AGENT, SETTINGS_CHANGE_INTENT
from app.core.dependencies import OwnedResidentDep, SupabaseDep, ViewedResidentDep
from app.crud.night_log import log_resident_action
from app.crud.residents import update_resident
from app.schemas.account import CheckinWait, CheckinWaitUpdate, WatchHours

router = APIRouter(prefix="/residents/{resident_id}", tags=["residents"])

WATCH_HOURS_TOOL = "watch_hours"
CHECKIN_WAIT_TOOL = "checkin_wait"


@router.get("/watch-hours")
async def read_watch_hours(resident: ViewedResidentDep) -> WatchHours:
    """When the pillow watches her: quiet_start to quiet_end in her timezone."""
    return WatchHours.model_validate(resident)


@router.put("/watch-hours")
async def update_watch_hours(resident: OwnedResidentDep, hours: WatchHours, db: SupabaseDep) -> WatchHours:
    """Set when the pillow watches her; equal start and end times watch all day. Owner only."""
    await _save(db, resident, WATCH_HOURS_TOOL, hours)
    return hours


@router.get("/checkin-wait")
async def read_checkin_wait(resident: ViewedResidentDep) -> CheckinWait:
    """How long she may be up before the pillow checks on her, then tells family."""
    return CheckinWait.model_validate(resident)


@router.put("/checkin-wait")
async def update_checkin_wait(
    resident: OwnedResidentDep, wait: CheckinWaitUpdate, db: SupabaseDep
) -> CheckinWait:
    """Set the check-in wait, within the Guardian's bounds (422 outside them). Owner only."""
    await _save(db, resident, CHECKIN_WAIT_TOOL, wait)
    return CheckinWait.model_validate(wait.model_dump())


async def _save(db: SupabaseDep, resident: dict[str, Any], tool: str, settings: BaseModel) -> None:
    """Write the settings to the resident's row and note the change in her pillows' agent log."""
    fields = settings.model_dump(mode="json")
    await update_resident(db, resident["id"], fields)
    await log_resident_action(
        db, resident["id"], FAMILY_APP_AGENT, SETTINGS_CHANGE_INTENT, tool=tool, args=fields
    )
