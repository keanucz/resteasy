"""Family router: what the family app and the Fetch.ai agents read and write.

Reads of the night are open like the rest of the app API. A family member's own writes (settings,
a goodnight, the nights they're away) take the app's login of anyone in her care circle, or that
person's family agent with its own token (`FAMILY_AGENT_TOKENS`), the same way as reminders. The
watch roster takes the coordinator's (`COORDINATOR_TOKEN`). Every change lands in `agent_log`, so
the family app shows it live.
"""

import time as clock
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.agents.baseline import build_baseline, history_start
from app.agents.guardian import Guardian
from app.agents.night_summary import last_night_window, pending_goodnight, summarize_night
from app.core.app_constants import (
    AWAY_TOOL,
    FAMILY_APP_AGENT,
    GOODNIGHT_TOOL,
    SETTINGS_CHANGE_INTENT,
    SETTINGS_TOOL,
)
from app.core.dependencies import (
    CareActor,
    ContactActorDep,
    PillowDep,
    SupabaseDep,
    require_checkin_token,
    require_coordinator,
    require_roster_reader,
    resident_of,
)
from app.crud.night_log import (
    add_event,
    list_agent_log_between,
    list_events_between,
    list_recent_events_of_type,
    list_trips_between,
    log_action,
)
from app.crud.residents import (
    add_away,
    clear_away,
    list_away,
    list_contacts_in_order,
    set_contact_on_call,
    update_resident,
)
from app.schemas.family import (
    Away,
    AwayCreate,
    Goodnight,
    GoodnightCreate,
    NightReport,
    OnCallResult,
    OnCallUpdate,
    Roster,
    RosterContact,
    SettingsPatch,
    SettingsResult,
)

router = APIRouter(prefix="/pillows/{pillow_id}", tags=["family"])

ROSTER_AGENT = "watch_roster"  # the Fetch.ai coordinator
GOODNIGHT_TYPES = ["goodnight_queued", "goodnight_played"]
SETTINGS_KEYS = ("checkin_timeout_min", "quiet_start", "quiet_end")  # residents columns
_guardian = Guardian()  # text and roster checks need no per-resident settings


@router.get("/night")
async def read_night(
    pillow: PillowDep, db: SupabaseDep,
    night: Annotated[date | None, Query(description="The evening it started; default the latest")] = None,
) -> NightReport:
    """Last night: summary (trips, check-ins, alerts), events and the agent log.
    `night` reads an earlier one, e.g. yesterday's while tonight has only just begun."""
    resident = await resident_of(db, pillow)
    start, end = last_night_window(clock.time(), resident["timezone"], night)
    events = await list_events_between(db, pillow.id, start.isoformat(), end.isoformat())
    log = await list_agent_log_between(db, pillow.id, start.isoformat(), end.isoformat())
    trips = await list_trips_between(db, pillow.id, history_start(start).isoformat(), start.isoformat())
    baseline = build_baseline(trips, start, resident["timezone"], resident["checkin_timeout_min"])
    return NightReport(
        pillow_id=pillow.id, resident=resident["preferred_name"],
        window_start=start.isoformat(), window_end=end.isoformat(),
        summary=summarize_night(events, resident["timezone"], baseline), events=events, agent_log=log,
        settings={k: resident[k] for k in SETTINGS_KEYS},
    )


async def _log_for(
    db: SupabaseDep, pillow_id: str, actor: CareActor, intent: str, tool: str, args: dict
) -> None:
    """Note in agent_log what a family member did, through their agent or the app, and who."""
    who = f" for {actor.contact_name}" if actor.contact_name else ""
    await log_action(db, pillow_id, actor.agent or FAMILY_APP_AGENT, intent=intent + who, tool=tool,
                     args={"contact_id": actor.contact_id, **args}, guardian="allowed")


@router.patch("/settings")
async def patch_settings(
    pillow_id: str, patch: SettingsPatch, actor: ContactActorDep, db: SupabaseDep
) -> SettingsResult:
    """Anyone in her care circle (their login, or their family agent) changes when the pillow
    watches or the check-in wait, within the app's bounds (422 outside them)."""
    fields = patch.model_dump(mode="json", exclude_none=True)
    if fields:
        await update_resident(db, actor.resident["id"], fields)
        await _log_for(db, pillow_id, actor, SETTINGS_CHANGE_INTENT, SETTINGS_TOOL, {"applied": fields})
    return SettingsResult(applied=fields)


@router.post("/goodnight", status_code=status.HTTP_201_CREATED)
async def queue_goodnight(
    pillow_id: str, msg: GoodnightCreate, actor: ContactActorDep, db: SupabaseDep
) -> Goodnight:
    """Queue a goodnight message from someone in her care circle; the pillow plays it when she next
    lies down. The words pass the Guardian's text check (422 otherwise)."""
    verdict = _guardian.check_text(msg.message)
    if not verdict.allowed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=verdict.reason)
    data = {"message": msg.message, "from_name": msg.from_name}
    await add_event(db, pillow_id, "goodnight_queued", clock.time(), data)
    await _log_for(db, pillow_id, actor, f"goodnight from {msg.from_name}", GOODNIGHT_TOOL, data)
    return Goodnight(**data)


@router.get("/goodnight")
async def read_goodnight(pillow: PillowDep, db: SupabaseDep) -> Goodnight | None:
    """The goodnight message waiting to be played, or null."""
    events = await list_recent_events_of_type(db, pillow.id, GOODNIGHT_TYPES)
    pending = pending_goodnight(events)
    return Goodnight(**pending) if pending else None


@router.post("/goodnight/played", dependencies=[Depends(require_checkin_token)])
async def goodnight_played(pillow: PillowDep, db: SupabaseDep) -> Goodnight | None:
    """The base laptop played the pending message: mark it so it isn't played twice."""
    events = await list_recent_events_of_type(db, pillow.id, GOODNIGHT_TYPES)
    pending = pending_goodnight(events)
    if pending is None:
        return None
    await add_event(db, pillow.id, "goodnight_played", clock.time(), pending)
    return Goodnight(**pending)


@router.get("/roster", dependencies=[Depends(require_roster_reader)])
async def read_roster(pillow: PillowDep, db: SupabaseDep) -> Roster:
    """The resident's contacts in alert order, for the Fetch.ai coordinator's evening roster."""
    resident = await resident_of(db, pillow)
    contacts = await list_contacts_in_order(db, resident["id"])
    return Roster(
        resident=resident["preferred_name"], timezone=resident["timezone"],
        contacts=[RosterContact(contact_id=c["id"], name=(c.get("full_name") or "").strip() or c["id"],
                                on_call=c.get("on_call", True), quiet_start=c.get("quiet_start"),
                                quiet_end=c.get("quiet_end")) for c in contacts],
    )


@router.put("/roster/{contact_id}", dependencies=[Depends(require_coordinator)])
async def set_on_call(
    pillow: PillowDep, contact_id: str, update: OnCallUpdate, db: SupabaseDep
) -> OnCallResult:
    """Put a contact on or off call for tonight. Night Watch tries on-call contacts first but still
    alerts everyone, and the Guardian never lets the last on-call contact go off call."""
    resident = await resident_of(db, pillow)
    contacts = await list_contacts_in_order(db, resident["id"])
    contact = next((c for c in contacts if c["id"] == contact_id), None)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{contact_id} does not look after {pillow.id}")
    verdict = _guardian.check_on_call(contacts, contact_id, update.on_call)
    if verdict.allowed:
        await set_contact_on_call(db, contact_id, update.on_call)
    name = contact.get("full_name") or contact_id
    await log_action(db, pillow.id, ROSTER_AGENT,
                     intent=f"{name} {'on' if update.on_call else 'off'} call tonight: {update.reason}",
                     tool="on_call", args={"contact_id": contact_id, "on_call": update.on_call},
                     guardian=verdict.label, reason=verdict.reason or None)
    stored = update.on_call if verdict.allowed else contact.get("on_call", True)
    return OnCallResult(contact_id=contact_id, on_call=stored, guardian=verdict.label,
                        reason=verdict.reason or None)


def _today(actor: CareActor) -> str:
    return datetime.now(ZoneInfo(actor.resident["timezone"])).date().isoformat()


@router.get("/away")
async def read_away(actor: ContactActorDep, db: SupabaseDep) -> list[Away]:
    """The caller's own away nights from tonight on (her timezone), soonest first."""
    return [Away(**row) for row in await list_away(db, actor.contact_id, _today(actor))]


@router.post("/away", status_code=status.HTTP_201_CREATED)
async def create_away(pillow_id: str, away: AwayCreate, actor: ContactActorDep, db: SupabaseDep) -> Away:
    """Nights the caller can't be called first; on those nights the coordinator puts them off call."""
    row = await add_away(db, actor.contact_id, away.model_dump(mode="json"))
    when = f"{away.from_date.isoformat()} to {away.until_date.isoformat()}"
    await _log_for(db, pillow_id, actor, f"away {when} ({away.note})", AWAY_TOOL, row)
    return Away(**row)


@router.delete("/away", status_code=status.HTTP_204_NO_CONTENT)
async def delete_away(pillow_id: str, actor: ContactActorDep, db: SupabaseDep) -> Response:
    """Forget all of the caller's away nights."""
    await clear_away(db, actor.contact_id)
    await _log_for(db, pillow_id, actor, "cleared away dates", AWAY_TOOL, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
