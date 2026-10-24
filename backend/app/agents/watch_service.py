"""Runs Night Watch for each pillow inside the API (coord/AGENT_FLOW.md).

Loads each pillow's settings from its resident in Supabase, feeds Night Watch every state report,
and writes back what it decides: events, device commands, incidents and notifications, agent_log
(shown live in the family app) and `pillow_state.night_state`.

Family get alerts through the app (incidents + notifications) and acknowledge with the app's
"I'm on it" button (POST /api/pillows/{id}/ack). There is no family pillow.

Speech and the check-in run on the base laptop, not here: that laptop watches `night_state` (it
becomes `check_in`) and reports the result to POST /api/pillows/{id}/checkin. `Say` lines are only
logged until that laptop has a way to receive them.
"""

import asyncio
import logging
import time as clock
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from supabase import AsyncClient

from app.agents.night_watch import (
    Action,
    Alert,
    Command,
    Event,
    NightWatch,
    NightWatchConfig,
    State,
)
from app.crud.commands import queue_command
from app.crud.night_log import add_event, add_notification, log_action, open_incident, update_incident
from app.crud.pillow_state import get_state, set_night_state
from app.crud.pillows import get_pillow
from app.crud.residents import get_resident, list_contacts_in_order
from app.schemas.command import CommandCreate
from app.schemas.pillow import Pillow
from app.schemas.pillow_state import DeviceState

log = logging.getLogger(__name__)

AGENT = "night_watch"
CONFIG_REFRESH_S = 60  # re-read the resident's settings (pause, quiet hours) this often
# Night Watch's alert channels -> notifications.channel
CHANNELS = {"app": "app", "sms": "sms", "call": "call"}


@dataclass
class _Watch:
    """One pillow's Night Watch plus what the service tracks around it."""

    nw: NightWatch
    contact_ids: dict[str, str] = field(default_factory=dict)  # alert name -> contacts.id
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one report at a time, in order
    loaded_at: float = 0.0  # monotonic, last settings load
    last_ts: float = 0.0  # last device ts seen, the clock for check-in results
    incident_id: int | None = None
    incident_step: int = 0


class WatchService:
    """Holds a Night Watch per pillow for the life of the process."""

    def __init__(self) -> None:
        self._watches: dict[str, _Watch] = {}

    async def report_state(self, db: AsyncClient, pillow: Pillow, state: DeviceState) -> None:
        """Feed one state report to the pillow's Night Watch."""
        try:
            if pillow.resident_id is None or state.head_on is None:
                return  # nobody to watch, or no head sensor reading to watch with
            w = await self._watch(db, pillow)
            async with w.lock:
                w.last_ts = state.ts
                before = w.nw.state
                actions = w.nw.observe(state.model_dump())
                await self._apply(db, pillow.id, w, actions, before, state.ts)
        except Exception:  # the device's report is stored already; never fail it over an agent error
            log.exception("Night Watch failed on %s", pillow.id)

    async def acknowledge(self, db: AsyncClient, pillow: Pillow, contact_id: str) -> str | None:
        """A contact pressed "I'm on it" in the app: stop the alerts and return the night state.

        None if `contact_id` isn't one of this resident's contacts. Pressing it when nothing is
        being escalated, or twice, changes nothing.
        """
        w = await self._watch(db, pillow)
        async with w.lock:
            name = next((n for n, cid in w.contact_ids.items() if cid == contact_id), None)
            if name is None:
                return None
            before = w.nw.state
            actions = w.nw.family_acknowledged(w.last_ts, name)
            await self._apply(db, pillow.id, w, actions, before, w.last_ts)
            return str(w.nw.state)

    async def checkin_done(self, db: AsyncClient, pillow: Pillow, escalate: bool, reason: str) -> str:
        """Pass the base laptop's check-in result to Night Watch; return the new night state."""
        w = await self._watch(db, pillow)
        async with w.lock:
            before = w.nw.state
            actions = w.nw.checkin_done(w.last_ts, escalate, reason)
            await self._apply(db, pillow.id, w, actions, before, w.last_ts)
            return str(w.nw.state)

    # ---------- setup ----------

    async def _watch(self, db: AsyncClient, pillow: Pillow) -> _Watch:
        """The pillow's watch, created (and resumed from the database) on first use."""
        w = self._watches.get(pillow.id)
        if w is None:
            w = _Watch(NightWatch())
            await self._load_settings(db, pillow, w)
            saved = await get_state(db, pillow.id)
            if saved and saved.night_state != State.AWAKE:
                w.nw.resume(State(saved.night_state), saved.state_since.timestamp())
            self._watches[pillow.id] = w
        elif clock.monotonic() - w.loaded_at > CONFIG_REFRESH_S:
            await self._load_settings(db, pillow, w)
        return w

    async def _load_settings(self, db: AsyncClient, pillow: Pillow, w: _Watch) -> None:
        """Build the Night Watch config from the resident's row and contacts."""
        resident = await get_resident(db, str(pillow.resident_id))
        contacts = await list_contacts_in_order(db, str(pillow.resident_id))
        now = datetime.fromtimestamp(w.last_ts or clock.time(), ZoneInfo(resident["timezone"])).time()
        # Reachable contacts (on call, outside their own quiet hours) first, in priority order; the
        # rest after them, so nobody is ever left out of an alert.
        contacts.sort(key=lambda c: not _reachable(c, now))
        w.contact_ids = {c["full_name"].split()[0]: c["id"] for c in contacts}
        w.nw.cfg = NightWatchConfig(
            pillow_id=pillow.id,
            resident=resident["preferred_name"],
            contacts=tuple(w.contact_ids) or ("family",),
            checkin_timeout_min=resident["checkin_timeout_min"],
            timezone=resident["timezone"],
            quiet_hours=(time.fromisoformat(resident["quiet_start"]),
                         time.fromisoformat(resident["quiet_end"])),
            paused=resident["monitoring_paused"],
            step_wait_min=resident["step_wait_min"],
        )
        w.loaded_at = clock.monotonic()

    # ---------- writing decisions back ----------

    async def _apply(
        self, db: AsyncClient, pillow_id: str, w: _Watch, actions: list[Action], before: State, ts: float
    ) -> None:
        """Store and carry out Night Watch's actions, in order."""
        for a in actions:
            if isinstance(a, Event):
                await add_event(db, pillow_id, a.type, a.ts, a.data)
                await self._track_incident(db, pillow_id, w, a)
                continue
            reason = None
            if isinstance(a, Command):
                reason = await self._send_command(db, a)
            elif isinstance(a, Alert):
                reason = await self._notify(db, w, a)
            await log_action(db, pillow_id, AGENT, intent=_intent(a), tool=type(a).__name__,
                             args=asdict(a), incident_id=w.incident_id, reason=reason)
        if w.nw.state is not before:
            await set_night_state(db, pillow_id, str(w.nw.state), ts)
            await log_action(db, pillow_id, AGENT, intent=f"{before} -> {w.nw.state}",
                             incident_id=w.incident_id)
            if w.nw.state is not State.ESCALATING:
                w.incident_id, w.incident_step = None, 0

    async def _track_incident(self, db: AsyncClient, pillow_id: str, w: _Watch, e: Event) -> None:
        """Mirror the escalation into the incidents table the family app watches."""
        if e.type == "escalation_step":
            if w.incident_id is None:
                summary = f"{w.nw.cfg.resident} got up and hasn't come back to bed."
                w.incident_id = await open_incident(db, pillow_id, "no_return", summary)
            w.incident_step += 1
            await update_incident(db, w.incident_id, {"step": w.incident_step})
        elif w.incident_id is not None and e.type == "family_ack":
            await update_incident(db, w.incident_id, {
                "status": "acknowledged", "acked_by": w.contact_ids.get(e.data["contact"]),
                "acked_at": _now_iso()})
        elif w.incident_id is not None and e.type in ("bed_return", "key_fine"):
            await update_incident(db, w.incident_id, {"status": "resolved", "resolved_at": _now_iso()})

    async def _send_command(self, db: AsyncClient, c: Command) -> str | None:
        """Queue a device command; skip (and say why) if that pillow isn't registered."""
        if await get_pillow(db, c.pillow_id) is None:
            return f"pillow {c.pillow_id} is not registered, command not sent"
        await queue_command(db, c.pillow_id, CommandCreate(cmd=c.cmd, args=c.args, source=AGENT))
        return None

    async def _notify(self, db: AsyncClient, w: _Watch, a: Alert) -> str | None:
        """Record an alert as a queued notification for its incident."""
        contact_id = w.contact_ids.get(a.contact)
        if w.incident_id is None or contact_id is None:
            return "logged only: no open incident or no contact on record"
        await add_notification(db, w.incident_id, contact_id, CHANNELS[a.channel])
        return None


def _intent(a: Action) -> str:
    """A short human line for the family app's live log."""
    if isinstance(a, Command):
        return f"{a.cmd} on {a.pillow_id}"
    if isinstance(a, Alert):
        return f"alert {a.contact} by {a.channel}: {a.message}"
    return getattr(a, "text", None) or type(a).__name__


def _reachable(contact: dict, now: time) -> bool:
    """On call and not inside the contact's own quiet hours (times in the resident's timezone)."""
    if not contact.get("on_call", True):
        return False
    start, end = contact.get("quiet_start"), contact.get("quiet_end")
    if not start or not end:
        return True
    start, end = time.fromisoformat(start), time.fromisoformat(end)
    quiet = now >= start or now < end if start > end else start <= now < end
    return not quiet


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
