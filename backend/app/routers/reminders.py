"""Reminders router: the family app sets reminders up, the laptop speaks the due ones.

Setting a reminder up, changing or deleting it, and the calendar take the app's Supabase login of
anyone who looks after her (owner or contact), or the shared agent token of the Fetch.ai family
agents with the `contact_id` of the family member they act for, or that token with `as=resident`
when she asks the pillow herself (the talk key on the base laptop); each agent write lands in
`agent_log`. The lists the laptop and the app already poll stay open like the rest of the pillow
API. A label is spoken to her, so it passes the Guardian's text check. Only the laptop, with the
shared agent token, may report how a reminder went.
"""

from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from supabase import AsyncClient

from app.agents.guardian import Guardian
from app.agents.reminders import due_reminders, reminder_calendar
from app.core.app_constants import CONSENT_AGREED, REMIND_PURPOSE, REMINDERS_TOOL
from app.core.dependencies import (
    CareActor,
    CareActorDep,
    ContactActorDep,
    PillowDep,
    ReminderServiceDep,
    ResidentDep,
    SupabaseDep,
    require_checkin_token,
)
from app.crud import reminders as crud
from app.crud.night_log import log_action
from app.schemas.reminder import (
    CalendarEntry,
    CalendarRange,
    DueReminder,
    Occurrence,
    Reminder,
    ReminderCreate,
    ReminderResult,
    ReminderStatus,
    ReminderUpdate,
)

router = APIRouter(prefix="/pillows/{pillow_id}/reminders", tags=["reminders"])

_guardian = Guardian()


def _screen(label: str | None) -> None:
    verdict = _guardian.check_text(label) if label else None
    if verdict is not None and not verdict.allowed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"label: {verdict.reason}")


def _not_found(reminder_id: int) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Reminder {reminder_id} not found")


async def _log_agent(
    db: AsyncClient, pillow_id: str, actor: CareActor, done: str, row: dict, fields: dict | None = None
) -> None:
    """Note in agent_log what an agent did for a family member; a login's own change isn't logged."""
    if actor.agent is None:
        return
    args = {"contact_id": actor.contact_id, "reminder_id": row["id"], "fields": fields or {}}
    if actor.contact_id is None:  # she asked the pillow herself
        intent = f"{actor.contact_name} {done} by voice: {row['label']}"
    else:
        intent = f"{done} for {actor.contact_name}: {row['label']}"
    await log_action(db, pillow_id, actor.agent, intent, tool=REMINDERS_TOOL, args=args)


@router.get("")
async def list_reminders(resident: ResidentDep, db: SupabaseDep) -> list[Reminder]:
    """Every reminder of the pillow's resident, earliest in the day first."""
    return [Reminder.from_row(r) for r in await crud.list_reminders(db, resident["id"])]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_reminder(
    pillow_id: str, reminder: ReminderCreate, actor: CareActorDep, db: SupabaseDep
) -> Reminder:
    """Set up a reminder, spoken as "<name>, it's time to <label>." on `on_date` or on the chosen
    days, once she agrees: the pillow asks her first (consent "pending"). When she asked for it
    herself (`as=resident`) and said yes to the pillow's read-back, that is her consent."""
    _screen(reminder.label)
    fields = reminder.to_fields(created_by=actor.contact_id)
    if actor.contact_id is None:
        fields |= {"consent": CONSENT_AGREED, "consent_at": datetime.now(UTC).isoformat()}
    row = await crud.create_reminder(db, actor.resident["id"], fields)
    await _log_agent(db, pillow_id, actor, "set up a reminder", row, fields)
    return Reminder.from_row(row)


@router.get("/calendar")
async def read_calendar(
    days: Annotated[CalendarRange, Query()], actor: CareActorDep, db: SupabaseDep
) -> list[CalendarEntry]:
    """Every time an active reminder plays from `start` to `end` (inclusive, at most 62 days, her
    timezone), with how each went, earliest first."""
    return await reminder_calendar(db, actor.resident, days.start, days.end)


@router.patch("/{reminder_id}")
async def update_reminder(
    pillow_id: str, reminder_id: int, patch: ReminderUpdate, actor: ContactActorDep, db: SupabaseDep
) -> Reminder:
    """Change a reminder; `active: false` pauses it. Changing what is said or when asks her again."""
    _screen(patch.label)
    resident_id = actor.resident["id"]
    current = await crud.get_reminder(db, resident_id, reminder_id)
    if current is None:
        raise _not_found(reminder_id)
    fields = patch.to_fields(Reminder.from_row(current))
    if not fields:
        return Reminder.from_row(current)
    row = await crud.update_reminder(db, resident_id, reminder_id, fields)
    if row is None:  # deleted meanwhile
        raise _not_found(reminder_id)
    await _log_agent(db, pillow_id, actor, "changed a reminder", row, fields)
    return Reminder.from_row(row)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    pillow_id: str, reminder_id: int, actor: ContactActorDep, db: SupabaseDep
) -> Response:
    row = await crud.delete_reminder(db, actor.resident["id"], reminder_id)
    if row is None:
        raise _not_found(reminder_id)
    await _log_agent(db, pillow_id, actor, "deleted a reminder", row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/today")
async def list_today(resident: ResidentDep, db: SupabaseDep) -> list[Occurrence]:
    """Today's reminders that have fallen due so far, with how each went, for the app."""
    tz = ZoneInfo(resident["timezone"])
    midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await crud.list_occurrences(
        db, resident["id"], since_iso=midnight.isoformat(), purpose=REMIND_PURPOSE
    )
    return [
        Occurrence(**row, **{k: row["reminders"][k] for k in ("label", "kind", "confirm")}) for row in rows
    ]


@router.get("/due")
async def list_due(resident: ResidentDep, db: SupabaseDep) -> list[DueReminder]:
    """What the laptop should say now (buzzer already queued), oldest first: reminders, and the
    question whether she agrees to a new one."""
    return await due_reminders(db, resident)


@router.post("/{occurrence_id}/result", dependencies=[Depends(require_checkin_token)])
async def report_result(
    occurrence_id: int,
    result: ReminderResult,
    pillow: PillowDep,
    db: SupabaseDep,
    service: ReminderServiceDep,
) -> ReminderStatus:
    """The laptop said a due reminder: how it went. Distress goes straight to Night Watch."""
    new_status = await service.record_result(db, pillow, occurrence_id, result)
    if new_status is None:
        detail = f"Reminder occurrence {occurrence_id} not found for pillow {pillow.id}"
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=detail)
    return ReminderStatus(status=new_status)
