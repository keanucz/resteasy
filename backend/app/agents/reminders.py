"""The Routine agent: recurring reminders (tablets, calling family, walking the dog).

Plain code, like Night Watch: the schedule, the hold and the retries are decided here; the laptop
(voice/checkin_client.py) only speaks a due reminder, listens if asked to, and reports back.

    waiting --she is up for the day--> due (buzzer, then the laptop speaks it)
    due --"announced" / "done"--> closed
    due --"not yet" / no answer / no report in 10 min--> waiting again (confirm reminders, once)
                                                        or missed
    anything still open 3 h after its time --> missed

A reminder never wakes her or talks over a check-in: it waits while she is in bed, up at night,
being checked on or escalated. Anything she says that sounds like distress goes to Night Watch.
"""

import logging
import time as clock
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from supabase import AsyncClient

from app.agents.guardian import Guardian
from app.agents.night_watch import Command
from app.agents.watch_service import WatchService
from app.crud.commands import queue_command
from app.crud.night_log import log_action
from app.crud.pillow_state import get_state
from app.crud.reminders import (
    claim_occurrence,
    get_occurrence,
    list_active_reminders,
    list_open_occurrences,
    move_occurrence,
)
from app.schemas.command import CommandCreate
from app.schemas.pillow import Pillow
from app.schemas.reminder import ReminderResult

log = logging.getLogger(__name__)

AGENT = "routine"
RETRY_AFTER = timedelta(minutes=10)  # "not yet" or no answer: ask again this much later
MAX_ASKS = 2  # a confirm reminder is asked at most this often
MISS_AFTER = timedelta(hours=3)  # still not delivered or confirmed by then: missed
BUZZ = {"pattern": "chime", "repeat": 1}  # sounds just before the voice, so it doesn't startle her
HOLD_STATES = {"in_bed", "up", "check_in", "escalating"}  # night_state values that hold a reminder

_guardian = Guardian()


@dataclass(frozen=True)
class Step:
    """One change to an occurrence: its new status and fields, and whether to sound the buzzer."""

    status: str
    fields: dict[str, Any] = field(default_factory=dict)
    buzz: bool = False


# ---------- pure planning (no database) ----------


def slot_today(reminder: dict, timezone: str, now: datetime) -> datetime | None:
    """Today's due time for `reminder` in the resident's timezone, if it has passed and is still
    recent enough to deliver; else None."""
    local = now.astimezone(ZoneInfo(timezone))
    if local.isoweekday() not in reminder["days"]:
        return None
    slot = datetime.combine(local.date(), time.fromisoformat(reminder["time_of_day"]), ZoneInfo(timezone))
    return slot if slot <= now < slot + MISS_AFTER else None


def unanswered(attempts: int, confirm: bool) -> str:
    """After a try with no confirmation: wait for the retry, or give up."""
    return "waiting" if confirm and attempts < MAX_ASKS else "missed"


def next_step(occ: dict, confirm: bool, night_state: str | None, now: datetime) -> Step | None:
    """What the tick does with an open occurrence now, or None to leave it."""
    if now - _ts(occ["due_at"]) >= MISS_AFTER:
        return Step("missed", {"status": "missed"})
    asked = _ts(occ["last_asked_at"]) if occ["last_asked_at"] else None
    if occ["status"] == "waiting":
        if night_state in HOLD_STATES or (asked and now - asked < RETRY_AFTER):
            return None
        fields = {"status": "due", "attempts": occ["attempts"] + 1, "last_asked_at": now.isoformat()}
        return Step("due", fields, buzz=True)
    if asked is None or now - asked >= RETRY_AFTER:  # due, but the laptop never reported back
        status = unanswered(occ["attempts"], confirm)
        return Step(status, {"status": status})
    return None


def result_status(outcome: str, attempts: int, confirm: bool) -> str:
    """The occurrence's status after the laptop reports `outcome`."""
    if outcome in ("announced", "done"):
        return outcome
    if outcome == "distress":
        return "missed"  # family are being alerted; don't keep asking her about the reminder
    return unanswered(attempts, confirm)


def spoken_line(name: str, label: str) -> str:
    return f"{name}, it's time to {label}."


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ---------- the service ----------


class ReminderService:
    """Runs the reminder schedule from the API's ticker and records what the laptop reports."""

    def __init__(self, night_watch: WatchService) -> None:
        self.night_watch = night_watch

    async def tick(self, db: AsyncClient, now: datetime | None = None) -> None:
        """Create today's occurrences whose time has passed, then move every open one along."""
        now = now or datetime.now(UTC)
        reminders = {r["id"]: r for r in await list_active_reminders(db)}
        for r in reminders.values():
            slot = slot_today(r, r["residents"]["timezone"], now)
            if slot is not None:
                await claim_occurrence(db, r["id"], slot.isoformat())
        night_states: dict[str, str | None] = {}
        for occ in await list_open_occurrences(db, list(reminders)):
            r = reminders[occ["reminder_id"]]
            pillow_id = r["residents"]["pillows"][0]["id"]
            if pillow_id not in night_states:
                state = await get_state(db, pillow_id)
                night_states[pillow_id] = state.night_state if state else None
            step = next_step(occ, r["confirm"], night_states[pillow_id], now)
            if step is None or not await move_occurrence(db, occ["id"], occ["status"], step.fields):
                continue  # nothing to do, or a result moved it first
            await self._carry_out(db, r, occ, step)

    async def _carry_out(self, db: AsyncClient, r: dict, occ: dict, step: Step) -> None:
        pillow_ids = [p["id"] for p in r["residents"]["pillows"]]
        if step.status == "missed":
            for pid in pillow_ids:
                await log_action(db, pid, AGENT, intent=f"reminder missed: {r['label']}", tool="reminder",
                                 args={"occurrence_id": occ["id"], "attempts": occ["attempts"]})
            return
        if step.status != "due":
            return  # back to waiting for the retry: nothing to say yet
        for pid in pillow_ids:
            (screened,) = _guardian.screen([Command(pid, "buzz", dict(BUZZ))], clock.time())
            if screened.run is not None:
                await queue_command(db, pid, CommandCreate(cmd=screened.run.cmd, args=screened.run.args,
                                                           source=AGENT))
            ask = step.fields["attempts"]
            verdict = screened.verdict
            intent = f"reminder: {r['label']}" + (f" (ask {ask})" if ask > 1 else "")
            await log_action(db, pid, AGENT, intent=intent,
                             tool="buzz", args={"occurrence_id": occ["id"], **BUZZ}, guardian=verdict.label,
                             reason=None if verdict.allowed else f"blocked: {verdict.reason}")

    async def record_result(self, db: AsyncClient, pillow: Pillow, occurrence_id: int,
                            result: ReminderResult) -> str | None:
        """Store the laptop's report and return the occurrence's status; None if this pillow's
        resident has no such occurrence. Distress always reaches Night Watch, even if the report
        comes late; a repeated or late report changes nothing else."""
        occ = await get_occurrence(db, occurrence_id)
        if occ is None or occ["reminders"]["resident_id"] != str(pillow.resident_id):
            return None
        label = occ["reminders"]["label"]
        if result.outcome == "distress":
            heard = f'she said: "{result.reply}"' if result.reply else "she sounded in trouble"
            reason = f'Asked about her reminder ("{label}"), {heard}'
            await self.night_watch.report_distress(db, pillow, reason)
        if occ["status"] != "due":
            return occ["status"]
        status = result_status(result.outcome, occ["attempts"], occ["reminders"]["confirm"])
        fields: dict[str, Any] = {"status": status, "reply": result.reply}
        if status in ("announced", "done"):
            fields["answered_at"] = datetime.now(UTC).isoformat()
        if not await move_occurrence(db, occurrence_id, "due", fields):
            return (await get_occurrence(db, occurrence_id) or {}).get("status")
        intent = {"announced": "reminded", "done": "done", "waiting": "not yet, will ask again",
                  "missed": "missed"}[status]
        await log_action(db, pillow.id, AGENT, intent=f"reminder {intent}: {label}", tool="reminder",
                         args={"occurrence_id": occurrence_id, "outcome": result.outcome},
                         reason=f'she said: "{result.reply}"' if result.reply else None)
        return status
