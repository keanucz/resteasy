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

Nothing plays until she agrees. While a reminder's consent is pending, the tick makes a 'consent'
occurrence once a day (from 09:00 her time, held the same way) and the laptop asks her "<Sarah> would
like to remind you to <label> <when>. Is that alright?": yes agrees, no declines, no answer asks
again an hour later (twice a day at most), then tomorrow.
"""

import logging
import time as clock
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from supabase import AsyncClient

from app.agents.guardian import Guardian
from app.agents.night_watch import Command
from app.agents.reminder_schedule import (
    consent_line,
    day_bounds,
    due_at,
    expand,
    is_one_off,
    plays_on,
    spoken_line,
)
from app.agents.watch_service import WatchService
from app.core.app_constants import (
    CONSENT_AGREED,
    CONSENT_ASK_AT,
    CONSENT_ASK_WINDOW,
    CONSENT_DECLINED,
    CONSENT_PENDING,
    CONSENT_PURPOSE,
    CONSENT_RETRY_AFTER,
    REMIND_PURPOSE,
)
from app.crud.commands import queue_command
from app.crud.night_log import log_action
from app.crud.pillow_state import get_state
from app.crud.reminders import (
    claim_occurrence,
    get_occurrence,
    list_active_reminders,
    list_occurrences,
    list_open_occurrences,
    list_reminders,
    move_occurrence,
    set_consent,
)
from app.schemas.command import CommandCreate
from app.schemas.pillow import Pillow
from app.schemas.reminder import CalendarEntry, DueReminder, ReminderResult

log = logging.getLogger(__name__)

AGENT = "routine"
RETRY_AFTER = timedelta(minutes=10)  # "not yet" or no answer: ask again this much later
MAX_ASKS = 2  # a confirm reminder (or a consent question) is asked at most this often
MISS_AFTER = timedelta(hours=3)  # still not delivered or confirmed by then: missed
BUZZ = {"pattern": "chime", "repeat": 1}  # sounds just before the voice, so it doesn't startle her
HOLD_STATES = {"in_bed", "up", "check_in", "escalating"}  # night_state values that hold a reminder
# (retry after, miss after) for each purpose: a consent question waits longer and lasts the day
TIMING = {
    REMIND_PURPOSE: (RETRY_AFTER, MISS_AFTER),
    CONSENT_PURPOSE: (CONSENT_RETRY_AFTER, CONSENT_ASK_WINDOW),
}
# The agent log's words for a reported result
REMIND_RESULT_INTENTS = {
    "announced": "reminder reminded",
    "done": "reminder done",
    "waiting": "reminder not yet, will ask again",
    "missed": "reminder missed",
}
CONSENT_RESULT_INTENTS = {
    CONSENT_AGREED: "she agreed to a new reminder",
    CONSENT_DECLINED: "she declined a new reminder",
    None: "no answer about a new reminder",
}

_guardian = Guardian()


@dataclass(frozen=True)
class Step:
    """One change to an occurrence: its new status and fields, and whether to sound the buzzer."""

    status: str
    fields: dict[str, Any] = field(default_factory=dict)
    buzz: bool = False


# ---------- pure planning (no database) ----------


def slot_today(reminder: dict, timezone: str, now: datetime) -> datetime | None:
    """Today's due time for `reminder` in the resident's timezone, if it plays today, has passed,
    came after she agreed, and is still recent enough to deliver; else None."""
    today = now.astimezone(ZoneInfo(timezone)).date()
    if not plays_on(reminder, today, agreed_only=True):
        return None
    slot = due_at(reminder, today, timezone)
    if reminder["consent_at"] and slot < _ts(reminder["consent_at"]):
        return None  # she agreed after today's time: it starts next time
    return slot if slot <= now < slot + MISS_AFTER else None


def consent_slot_today(reminder: dict, timezone: str, now: datetime) -> datetime | None:
    """Today's time to ask her about a pending reminder (from CONSENT_ASK_AT, for the day, never at
    night), while it still has a time to play; else None."""
    if not reminder["active"] or reminder["consent"] != CONSENT_PENDING:
        return None
    if is_one_off(reminder) and due_at(reminder, date.fromisoformat(reminder["on_date"]), timezone) <= now:
        return None  # a one-off already past: nothing left to agree to
    tz = ZoneInfo(timezone)
    slot = datetime.combine(now.astimezone(tz).date(), CONSENT_ASK_AT, tz)
    return slot if slot <= now < slot + CONSENT_ASK_WINDOW else None


def asks_her(occ: dict, confirm: bool) -> bool:
    """Whether saying this occurrence waits for her answer: a consent question always does."""
    return confirm or occ["purpose"] == CONSENT_PURPOSE


def unanswered(attempts: int, confirm: bool) -> str:
    """After a try with no confirmation: wait for the retry, or give up."""
    return "waiting" if confirm and attempts < MAX_ASKS else "missed"


def next_step(occ: dict, confirm: bool, night_state: str | None, now: datetime) -> Step | None:
    """What the tick does with an open occurrence now, or None to leave it."""
    retry_after, miss_after = TIMING[occ["purpose"]]
    if now - _ts(occ["due_at"]) >= miss_after:
        return Step("missed", {"status": "missed"})
    asked = _ts(occ["last_asked_at"]) if occ["last_asked_at"] else None
    if occ["status"] == "waiting":
        if night_state in HOLD_STATES or (asked and now - asked < retry_after):
            return None
        fields = {"status": "due", "attempts": occ["attempts"] + 1, "last_asked_at": now.isoformat()}
        return Step("due", fields, buzz=True)
    if asked is None or now - asked >= RETRY_AFTER:  # due, but the laptop never reported back
        status = unanswered(occ["attempts"], asks_her(occ, confirm))
        return Step(status, {"status": status})
    return None


def result_status(outcome: str, attempts: int, confirm: bool) -> str:
    """The occurrence's status after the laptop reports `outcome`."""
    if outcome in ("announced", "done"):
        return outcome
    if outcome == "distress":
        return "missed"  # family are being alerted; don't keep asking her about the reminder
    return unanswered(attempts, confirm)


def consent_result(outcome: str, attempts: int, reply: str | None) -> tuple[str, str | None]:
    """After asking whether she agrees: the occurrence's status, and the reminder's new consent
    (None leaves it pending). Yes agrees and a heard no declines (both close it as "done": she
    answered); a mumble with no words, silence or a spoken-only report asks again later; distress
    closes it while Night Watch takes over."""
    if outcome == "done":
        return "done", CONSENT_AGREED
    if outcome == "not_done" and reply:
        return "done", CONSENT_DECLINED
    if outcome == "distress":
        return "missed", None
    return unanswered(attempts, True), None


def due_reminder(name: str, occ: dict) -> DueReminder:
    """What the laptop says for a due occurrence (its reminder embedded): the reminder, or the
    consent question."""
    r = occ["reminders"]
    if occ["purpose"] == CONSENT_PURPOSE:
        text = consent_line(r, (r["creator"] or {}).get("full_name"))
        return DueReminder(occurrence_id=occ["id"], text=text, confirm=True, purpose=CONSENT_PURPOSE)
    return DueReminder(occurrence_id=occ["id"], text=spoken_line(name, r["label"]), confirm=r["confirm"])


def calendar_entries(
    reminders: list[dict], occurrences: list[dict], start: date, end: date, timezone: str
) -> list[CalendarEntry]:
    """Every time the active `reminders` play from `start` to `end`, with how each went from its
    'remind' occurrence, earliest first."""
    statuses = {(o["reminder_id"], _ts(o["due_at"])): o["status"] for o in occurrences}
    entries = [
        CalendarEntry(
            reminder_id=r["id"],
            date=day,
            due_at=at,
            label=r["label"],
            kind=r["kind"],
            confirm=r["confirm"],
            consent=r["consent"],
            recurring=not is_one_off(r),
            status=statuses.get((r["id"], at)),
        )
        for r in reminders
        for day, at in expand(r, start, end, timezone)
    ]
    return sorted(entries, key=lambda e: (e.due_at, e.reminder_id))


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ---------- reads for the app and the laptop ----------


async def due_reminders(db: AsyncClient, resident: dict) -> list[DueReminder]:
    """What the laptop should say now (buzzer already queued), oldest first."""
    rows = await list_occurrences(db, resident["id"], status="due")
    return [due_reminder(resident["preferred_name"], row) for row in rows]


async def reminder_calendar(db: AsyncClient, resident: dict, start: date, end: date) -> list[CalendarEntry]:
    """The resident's active reminders laid out from `start` to `end` in her timezone."""
    timezone = resident["timezone"]
    since, until = day_bounds(start, end, timezone)
    reminders = await list_reminders(db, resident["id"], active_only=True)
    occurrences = await list_occurrences(
        db, resident["id"], since_iso=since.isoformat(), until_iso=until.isoformat(), purpose=REMIND_PURPOSE
    )
    return calendar_entries(reminders, occurrences, start, end, timezone)


# ---------- the service ----------


class ReminderService:
    """Runs the reminder schedule from the API's ticker and records what the laptop reports."""

    def __init__(self, night_watch: WatchService) -> None:
        self.night_watch = night_watch

    async def tick(self, db: AsyncClient, now: datetime | None = None) -> None:
        """Create today's occurrences whose time has passed (reminders she agreed to, questions
        about pending ones), then move every open one along."""
        now = now or datetime.now(UTC)
        reminders = {r["id"]: r for r in await list_active_reminders(db)}
        for r in reminders.values():
            timezone = r["residents"]["timezone"]
            slots = {
                REMIND_PURPOSE: slot_today(r, timezone, now),
                CONSENT_PURPOSE: consent_slot_today(r, timezone, now),
            }
            for purpose, slot in slots.items():
                if slot is not None:
                    await claim_occurrence(db, r["id"], slot.isoformat(), purpose)
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
        consent = occ["purpose"] == CONSENT_PURPOSE
        if step.status == "missed":
            missed = "no answer about a new reminder, will ask tomorrow" if consent else "reminder missed"
            for pid in pillow_ids:
                await log_action(
                    db,
                    pid,
                    AGENT,
                    intent=f"{missed}: {r['label']}",
                    tool="reminder",
                    args={"occurrence_id": occ["id"], "attempts": occ["attempts"]},
                )
            return
        if step.status != "due":
            return  # back to waiting for the retry: nothing to say yet
        for pid in pillow_ids:
            (screened,) = _guardian.screen([Command(pid, "buzz", dict(BUZZ))], clock.time())
            if screened.run is not None:
                await queue_command(
                    db, pid, CommandCreate(cmd=screened.run.cmd, args=screened.run.args, source=AGENT)
                )
            ask = step.fields["attempts"]
            verdict = screened.verdict
            what = "asking about a new reminder" if consent else "reminder"
            intent = f"{what}: {r['label']}" + (f" (ask {ask})" if ask > 1 else "")
            await log_action(
                db,
                pid,
                AGENT,
                intent=intent,
                tool="buzz",
                args={"occurrence_id": occ["id"], **BUZZ},
                guardian=verdict.label,
                reason=None if verdict.allowed else f"blocked: {verdict.reason}",
            )

    async def record_result(
        self, db: AsyncClient, pillow: Pillow, occurrence_id: int, result: ReminderResult
    ) -> str | None:
        """Store the laptop's report and return the occurrence's status; None if this pillow's
        resident has no such occurrence. Distress always reaches Night Watch, even if the report
        comes late; a repeated or late report changes nothing else. A consent answer is stored on
        the reminder."""
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
        now = datetime.now(UTC).isoformat()
        is_consent = occ["purpose"] == CONSENT_PURPOSE
        if is_consent:
            status, consent = consent_result(result.outcome, occ["attempts"], result.reply)
        else:
            status = result_status(result.outcome, occ["attempts"], occ["reminders"]["confirm"])
            consent = None
        fields: dict[str, Any] = {"status": status, "reply": result.reply}
        if status in ("announced", "done"):
            fields["answered_at"] = now
        if not await move_occurrence(db, occurrence_id, "due", fields):
            return (await get_occurrence(db, occurrence_id) or {}).get("status")
        if consent is not None:
            await set_consent(db, occ["reminder_id"], consent, now)
        intent = CONSENT_RESULT_INTENTS[consent] if is_consent else REMIND_RESULT_INTENTS[status]
        await log_action(
            db,
            pillow.id,
            AGENT,
            intent=f"{intent}: {label}",
            tool="reminder",
            args={"occurrence_id": occurrence_id, "outcome": result.outcome},
            reason=f'she said: "{result.reply}"' if result.reply else None,
        )
        return status
