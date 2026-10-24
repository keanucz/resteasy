"""Reminders router: the family app sets reminders up, the laptop speaks the due ones.

Reads and the app's writes are open like the rest of the app API (e.g. POST /goodnight). A label is
spoken to her, so it passes the Guardian's text check. Only the laptop, with the shared agent token,
may report how a reminder went.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.agents.guardian import Guardian
from app.agents.reminders import spoken_line
from app.core.dependencies import (
    PillowDep,
    ReminderServiceDep,
    ResidentDep,
    SupabaseDep,
    require_checkin_token,
)
from app.crud import reminders as crud
from app.schemas.reminder import (
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


@router.get("")
async def list_reminders(resident: ResidentDep, db: SupabaseDep) -> list[Reminder]:
    """Every reminder of the pillow's resident, earliest in the day first."""
    return [Reminder(**r) for r in await crud.list_reminders(db, resident["id"])]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_reminder(reminder: ReminderCreate, resident: ResidentDep, db: SupabaseDep) -> Reminder:
    """Set up a reminder: spoken as "<name>, it's time to <label>." on the chosen days."""
    _screen(reminder.label)
    return Reminder(**await crud.create_reminder(db, resident["id"], reminder.model_dump(mode="json")))


@router.patch("/{reminder_id}")
async def update_reminder(
    reminder_id: int, patch: ReminderUpdate, resident: ResidentDep, db: SupabaseDep
) -> Reminder:
    """Change a reminder; `active: false` pauses it."""
    _screen(patch.label)
    fields = patch.model_dump(mode="json", exclude_none=True)
    row = (await crud.update_reminder(db, resident["id"], reminder_id, fields) if fields
           else await crud.get_reminder(db, resident["id"], reminder_id))
    if row is None:
        raise _not_found(reminder_id)
    return Reminder(**row)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(reminder_id: int, resident: ResidentDep, db: SupabaseDep) -> Response:
    if not await crud.delete_reminder(db, resident["id"], reminder_id):
        raise _not_found(reminder_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/today")
async def list_today(resident: ResidentDep, db: SupabaseDep) -> list[Occurrence]:
    """Today's reminders that have fallen due so far, with how each went, for the app."""
    tz = ZoneInfo(resident["timezone"])
    midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await crud.list_occurrences(db, resident["id"], since_iso=midnight.isoformat())
    return [Occurrence(**row, **{k: row["reminders"][k] for k in ("label", "kind", "confirm")})
            for row in rows]


@router.get("/due")
async def list_due(resident: ResidentDep, db: SupabaseDep) -> list[DueReminder]:
    """What the laptop should say now (buzzer already queued), oldest first."""
    rows = await crud.list_occurrences(db, resident["id"], status="due")
    return [DueReminder(occurrence_id=row["id"], text=spoken_line(resident["preferred_name"],
                                                                  row["reminders"]["label"]),
                        confirm=row["reminders"]["confirm"]) for row in rows]


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
