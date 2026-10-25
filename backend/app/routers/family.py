"""Family router: what the Morning Brief droid and the Fetch.ai family agent read and write.

Reads are open like the rest of the app API. Writes that change settings or claim to be the
droid carry the shared agent token (`CHECKIN_TOKEN`), and every change goes through the Guardian
and into `agent_log`, so the family app shows it live.
"""

import time as clock
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.baseline import build_baseline, history_start
from app.agents.guardian import Guardian
from app.agents.night_summary import last_night_window, pending_goodnight, summarize_night
from app.core.app_constants import FAMILY_AGENT
from app.core.dependencies import PillowDep, SupabaseDep, require_checkin_token, resident_of
from app.crud.night_log import (
    add_event,
    latest_log_row,
    list_agent_log_between,
    list_events_between,
    list_recent_events_of_type,
    list_trips_between,
    log_action,
)
from app.crud.residents import list_contacts_in_order, set_contact_on_call, update_resident
from app.schemas.family import (
    Brief,
    BriefCreate,
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

BRIEF_AGENT = "morning_brief"
ROSTER_AGENT = "watch_roster"  # the Fetch.ai coordinator
GOODNIGHT_TYPES = ["goodnight_queued", "goodnight_played"]
SETTINGS_KEYS = ("checkin_timeout_min", "quiet_start", "quiet_end")  # residents columns
_guardian = Guardian()  # config checks need no per-resident settings


@router.get("/night")
async def read_night(pillow: PillowDep, db: SupabaseDep) -> NightReport:
    """Last night: summary (trips, check-ins, alerts), events and the agent log. The droid's input."""
    resident = await resident_of(db, pillow)
    start, end = last_night_window(clock.time(), resident["timezone"])
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


@router.get("/brief")
async def read_brief(pillow: PillowDep, db: SupabaseDep) -> Brief:
    """The latest Morning Brief, or 404 if none has been written yet."""
    row = await latest_log_row(db, pillow.id, BRIEF_AGENT)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No morning brief yet")
    return Brief(ts=row["ts"], guardian=row["guardian"] or "allowed", reason=row["reason"], **row["args"])


@router.post("/brief", dependencies=[Depends(require_checkin_token)], status_code=status.HTTP_201_CREATED)
async def write_brief(pillow: PillowDep, brief: BriefCreate, db: SupabaseDep) -> Brief:
    """Store the droid's note and apply its settings diff, limited to what the Guardian allows."""
    resident = await resident_of(db, pillow)
    verdict = _guardian.check_config(brief.config_diff)
    allowed = brief.config_diff if verdict.allowed else (verdict.replacement or {})
    await update_resident(db, resident["id"], {k: v for k, v in allowed.items() if k in SETTINGS_KEYS})
    args = {"note": brief.note, "proposed": brief.config_diff, "applied": allowed,
            "droid_session_id": brief.droid_session_id}
    await log_action(db, pillow.id, BRIEF_AGENT, intent="morning brief", tool="config_diff", args=args,
                     guardian=verdict.label, reason=verdict.reason or None)
    return Brief(ts=datetime.now(UTC).isoformat(), note=brief.note, proposed=brief.config_diff,
                 applied=allowed, guardian=verdict.label, reason=verdict.reason or None)


@router.patch("/settings", dependencies=[Depends(require_checkin_token)])
async def patch_settings(pillow: PillowDep, patch: SettingsPatch, db: SupabaseDep) -> SettingsResult:
    """The family agent changes quiet hours or the timeout; the Guardian bounds it."""
    resident = await resident_of(db, pillow)
    diff = patch.model_dump(exclude_none=True)
    verdict = _guardian.check_config(diff)
    allowed = diff if verdict.allowed else (verdict.replacement or {})
    await update_resident(db, resident["id"], {k: v for k, v in allowed.items() if k in SETTINGS_KEYS})
    await log_action(db, pillow.id, FAMILY_AGENT, intent="settings change", tool="settings",
                     args={"proposed": diff, "applied": allowed}, guardian=verdict.label,
                     reason=verdict.reason or None)
    return SettingsResult(applied=allowed, guardian=verdict.label, reason=verdict.reason or None)


@router.post("/goodnight", status_code=status.HTTP_201_CREATED)
async def queue_goodnight(pillow: PillowDep, msg: GoodnightCreate, db: SupabaseDep) -> Goodnight:
    """Queue a goodnight message from family; the pillow plays it when she next lies down."""
    verdict = _guardian.check_text(msg.message)
    if not verdict.allowed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=verdict.reason)
    data = {"message": msg.message, "from_name": msg.from_name}
    await add_event(db, pillow.id, "goodnight_queued", clock.time(), data)
    await log_action(db, pillow.id, FAMILY_AGENT, intent=f"goodnight from {msg.from_name}", tool="goodnight",
                     args=data, guardian="allowed")
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


@router.get("/roster", dependencies=[Depends(require_checkin_token)])
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


@router.put("/roster/{contact_id}", dependencies=[Depends(require_checkin_token)])
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
