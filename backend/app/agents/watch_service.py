"""Runs Night Watch for each pillow inside the API (coord/AGENT_FLOW.md).

Loads each pillow's settings from its resident in Supabase, feeds Night Watch every state report,
and writes back what it decides: events, device commands, incidents and notifications, agent_log
(shown live in the family app) and `pillow_state.night_state`.

Family get alerts through the app (incidents + notifications) and acknowledge with the app's
"I'm on it" button (POST /api/pillows/{id}/ack). There is no family pillow.

Speech and the check-in run on the base laptop, not here: that laptop watches `night_state` (it
becomes `check_in`) and reports the result to POST /api/pillows/{id}/checkin. `Say` lines are only
logged until that laptop has a way to receive them.

Alerts are worded by the Family Liaison (app/agents/liaison.py, Claude with tools; fixed text when it
can't), then every command, spoken line and alert passes the Guardian (app/agents/guardian.py); its
verdict lands in `agent_log.guardian`, and a blocked action runs its safe replacement or nothing.
"""

import asyncio
import logging
import re
import time as clock
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from supabase import AsyncClient

from app.agents.baseline import build_baseline, history_start
from app.agents.guardian import Guardian, GuardianConfig
from app.agents.liaison import Liaison, Situation
from app.agents.night_summary import last_night_window
from app.agents.night_watch import (
    DEMO_TIMINGS,
    Action,
    Alert,
    Command,
    Event,
    NightWatch,
    NightWatchConfig,
    State,
)
from app.agents.sleep_events import SleepTracker
from app.core.config import get_settings
from app.crud.commands import queue_command
from app.crud.night_log import (
    add_event,
    add_notification,
    clear_incident,
    clear_live_incidents,
    latest_log_row,
    list_trips_between,
    log_action,
    open_incident,
    update_incident,
)
from app.crud.pillow_state import get_state, set_night_state
from app.crud.pillows import get_pillow
from app.crud.residents import get_resident, list_contacts_in_order
from app.schemas.command import CommandCreate
from app.schemas.pillow import Pillow
from app.schemas.pillow_state import DeviceState

log = logging.getLogger(__name__)

AGENT = "night_watch"
BASELINE_TOOL = "baseline"  # agent_log tool of the check-in wait notes
CONFIG_REFRESH_S = 60  # re-read the resident's settings (pause, quiet hours) this often
# Night Watch's alert channels -> notifications.channel
CHANNELS = {"app": "app", "sms": "sms", "call": "call"}
# Each ladder channel and the contacts column that switches it on (Settings > Alerts in the app)
CHANNEL_SWITCHES = {"app": "app_alerts", "sms": "sms_consent", "call": "call_alerts"}
# The event that ended an alert -> incidents.resolved_reason, so the app can say "she's fine" or
# "she's back in bed". Another way for her to say she's fine adds its event here.
RESOLVED_REASONS = {"key_fine": "fine", "bed_return": "back_in_bed"}


@dataclass
class _Watch:
    """One pillow's Night Watch plus what the service tracks around it."""

    nw: NightWatch
    guardian: Guardian = field(default_factory=Guardian)
    sleep: SleepTracker = field(default_factory=SleepTracker)  # restless / asleep / key events
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=8))  # event types, for the Liaison
    heard: list[str] = field(default_factory=list)  # what she said at the last check-in
    contact_ids: dict[str, str] = field(default_factory=dict)  # alert name -> contacts.id
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one report at a time, in order
    loaded_at: float = 0.0  # monotonic, last settings load
    wait_note: str = ""  # the check-in wait as last logged, so a change shows in the app once
    last_ts: float = 0.0  # last device ts seen, the clock for check-in results
    last_seen: float = 0.0  # monotonic time of that report, to let device time run on without reports
    incident_id: int | None = None
    incident_step: int = 0


class WatchService:
    """Holds a Night Watch per pillow for the life of the process."""

    def __init__(self, liaison: Liaison | None = None) -> None:
        self.liaison = liaison or Liaison(None)
        self._watches: dict[str, _Watch] = {}
        self._create_lock = asyncio.Lock()  # two first reports after a restart make one watch

    async def report_state(self, db: AsyncClient, pillow: Pillow, state: DeviceState) -> None:
        """Feed one state report to the pillow's Night Watch (a null head reading still carries keys)."""
        try:
            if pillow.resident_id is None:
                return  # nobody to watch
            w = await self._watch(db, pillow, state.ts)
            async with w.lock:
                w.last_ts, w.last_seen = state.ts, clock.monotonic()
                before = w.nw.state
                report = state.model_dump()
                actions = [*w.sleep.observe(report), *w.nw.observe(report)]
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

    async def report_distress(self, db: AsyncClient, pillow: Pillow, reason: str) -> str:
        """She sounded in trouble outside a check-in (e.g. answering a reminder): escalate now.
        Return the new night state."""
        w = await self._watch(db, pillow)
        async with w.lock:
            before = w.nw.state
            ts = w.last_ts + (clock.monotonic() - w.last_seen) if w.last_seen else clock.time()
            actions = w.nw.distress_heard(ts, reason)
            await self._apply(db, pillow.id, w, actions, before, ts)
            return str(w.nw.state)

    async def press_key(self, db: AsyncClient, pillow: Pillow, key: str) -> str:
        """A key on the bedside pad (the laptop's POST /keys), which can't ride in POST /state:
        "fine" stops a check-in or an alert, "family" starts the alert ladder, "talk" is logged.
        Return the new night state."""
        w = await self._watch(db, pillow)
        async with w.lock:
            before = w.nw.state
            ts = w.last_ts + (clock.monotonic() - w.last_seen) if w.last_seen else clock.time()
            if key == "fine":
                actions = w.nw.fine_pressed(ts)
            elif key == "family":
                actions = w.nw.distress_heard(ts, f"{w.nw.cfg.resident} pressed the call-family key.")
            else:
                actions = [Event(ts, f"key_{key}", {"source": "pad"})]
            await self._apply(db, pillow.id, w, actions, before, ts)
            return str(w.nw.state)

    async def tick_all(self, db: AsyncClient) -> None:
        """Run every watch's due timers, so a silent pillow or a check-in that never reports back
        still moves the ladder. Device time is extrapolated from each pillow's last report."""
        for pillow_id, w in list(self._watches.items()):
            try:
                async with w.lock:
                    if not w.last_seen:
                        continue  # no report since start-up: no device clock to run on
                    ts = w.last_ts + (clock.monotonic() - w.last_seen)
                    before = w.nw.state
                    actions = w.nw.tick(ts)
                    await self._apply(db, pillow_id, w, actions, before, ts)
            except Exception:
                log.exception("Night Watch tick failed on %s", pillow_id)

    # ---------- setup ----------

    async def _watch(self, db: AsyncClient, pillow: Pillow, ts: float | None = None) -> _Watch:
        """The pillow's watch, created (and resumed from the database) on first use. `ts` is the
        reporting device's clock, if any, so settings follow the device's night, not the server's."""
        w = self._watches.get(pillow.id)
        if w is None:
            async with self._create_lock:
                w = self._watches.get(pillow.id)
                if w is None:
                    demo = get_settings().pillow_demo_timings
                    w = _Watch(NightWatch(timings=DEMO_TIMINGS if demo else None),
                               sleep=SleepTracker(demo=demo))
                    await self._load_settings(db, pillow, w, ts)
                    # Incidents left open by a previous run have lost their ladder: clear them, and
                    # a check-in or alert in flight restarts below and opens a fresh one if needed.
                    await clear_live_incidents(db, pillow.id)
                    saved = await get_state(db, pillow.id)
                    if saved and saved.night_state != State.AWAKE:
                        w.nw.resume(State(saved.night_state), saved.state_since.timestamp())
                    self._watches[pillow.id] = w
        elif clock.monotonic() - w.loaded_at > CONFIG_REFRESH_S:
            await self._load_settings(db, pillow, w, ts)
        return w

    async def _load_settings(
        self, db: AsyncClient, pillow: Pillow, w: _Watch, ts: float | None = None
    ) -> None:
        """Build the Night Watch config from the resident's row, contacts and her night baseline."""
        resident = await get_resident(db, str(pillow.resident_id))
        contacts = await list_contacts_in_order(db, str(pillow.resident_id))
        now_ts = ts or w.last_ts or clock.time()
        now = datetime.fromtimestamp(now_ts, ZoneInfo(resident["timezone"])).time()
        # The check-in wait: the owner's, or what the past week of trips says when that is shorter
        night_start, _ = last_night_window(now_ts, resident["timezone"])
        trips = await list_trips_between(db, pillow.id, history_start(night_start).isoformat(),
                                         night_start.isoformat())
        baseline = build_baseline(trips, night_start, resident["timezone"], resident["checkin_timeout_min"])
        # Reachable contacts (on call, outside their own quiet hours) first, in priority order; the
        # rest after them, so nobody is ever left out of an alert.
        contacts.sort(key=lambda c: not _reachable(c, now))
        # First name as spoken to her, but the full name when two share one (two Sarahs must stay two
        # contacts); a blank name falls back to the id.
        names = [(c.get("full_name") or "").strip() or c["id"] for c in contacts]
        firsts = [n.split()[0] for n in names]
        w.contact_ids = {(f if firsts.count(f) == 1 else n): c["id"]
                         for n, f, c in zip(names, firsts, contacts, strict=True)}
        quiet_hours = (time.fromisoformat(resident["quiet_start"]), time.fromisoformat(resident["quiet_end"]))
        w.nw.cfg = NightWatchConfig(
            pillow_id=pillow.id,
            resident=resident["preferred_name"],
            contacts=tuple(w.contact_ids) or ("family",),
            checkin_timeout_min=baseline.checkin_timeout_min,
            timezone=resident["timezone"],
            quiet_hours=quiet_hours,
            paused=resident["monitoring_paused"],
            step_wait_min=resident["step_wait_min"],
            channels={name: frozenset(ch for ch, column in CHANNEL_SWITCHES.items() if c.get(column, True))
                      for name, c in zip(w.contact_ids, contacts, strict=True)},
        )
        consent = {name: bool(c.get("sms_consent", True))
                   for name, c in zip(w.contact_ids, contacts, strict=True)}
        w.guardian.cfg = GuardianConfig(timezone=resident["timezone"], quiet_hours=quiet_hours,
                                        step_wait_min=resident["step_wait_min"], sms_consent=consent)
        w.loaded_at = clock.monotonic()
        if not w.wait_note:  # first load since the backend started: what was logged before it?
            last = await latest_log_row(db, pillow.id, AGENT, tool=BASELINE_TOOL)
            w.wait_note = last["intent"] if last else ""
        if baseline.note() != w.wait_note:
            w.wait_note = baseline.note()
            await log_action(db, pillow.id, AGENT, intent=w.wait_note, tool=BASELINE_TOOL,
                             args=baseline.as_dict())

    # ---------- writing decisions back ----------

    async def _apply(
        self, db: AsyncClient, pillow_id: str, w: _Watch, actions: list[Action], before: State, ts: float
    ) -> None:
        """Store the events, let the Liaison word the alerts, pass everything else through the
        Guardian, then carry it out, in order."""
        actions = await self._word(w, actions)
        for a in actions:
            if isinstance(a, Event):
                await add_event(db, pillow_id, a.type, a.ts, a.data)
                await self._track_incident(db, pillow_id, w, a)
                w.recent.append(a.type)
                if a.type == "checkin_result":
                    w.heard = _QUOTED.findall(a.data.get("reason") or "")
                continue
            (screened,) = w.guardian.screen([a], ts)
            run, verdict = screened.run, screened.verdict
            reason = None
            if isinstance(run, Command):
                reason = await self._send_command(db, run)
            elif isinstance(run, Alert):
                reason = await self._notify(db, w, run)
            if not verdict.allowed:
                instead = f"; ran instead: {_intent(run)}" if run is not None else "; dropped"
                reason = f"blocked: {verdict.reason}{instead}" + (f" ({reason})" if reason else "")
            await log_action(db, pillow_id, AGENT, intent=_intent(a), tool=type(a).__name__,
                             args=asdict(a), incident_id=w.incident_id, guardian=verdict.label, reason=reason)
        if w.nw.state is not before:
            await set_night_state(db, pillow_id, str(w.nw.state), ts)
            await log_action(db, pillow_id, AGENT, intent=f"{before} -> {w.nw.state}",
                             incident_id=w.incident_id)
            if w.nw.state is not State.ESCALATING:
                if w.incident_id is not None:  # ended another way (asleep, awake, distress -> check-in)
                    await clear_incident(db, w.incident_id)
                w.incident_id, w.incident_step = None, 0

    async def _word(self, w: _Watch, actions: list[Action]) -> list[Action]:
        """Replace the step's fixed alert texts with the Liaison's wording (same contacts and channels),
        and add the line it wants her to hear. Nothing else in the batch changes."""
        alerts = [a for a in actions if isinstance(a, Alert)]
        if not alerts:
            return actions
        events = [*w.recent, *(a.type for a in actions if isinstance(a, Event))]
        worded = await self.liaison.compose(Situation(w.nw.cfg.resident, alerts, events, w.heard))
        new_alerts = iter(a for a in worded if isinstance(a, Alert))
        out: list[Action] = [next(new_alerts, a) if isinstance(a, Alert) else a for a in actions]
        return out + [a for a in worded if not isinstance(a, Alert)]

    async def _track_incident(self, db: AsyncClient, pillow_id: str, w: _Watch, e: Event) -> None:
        """Mirror the escalation into the incidents table the family app watches."""
        if e.type == "escalation_step":
            if w.incident_id is None:
                kind = e.data.get("kind", "no_return")
                who = w.nw.cfg.resident
                summary = (f"{who} said something that sounds like she needs help." if kind == "distress"
                           else f"{who} got up and hasn't come back to bed.")
                await clear_live_incidents(db, pillow_id)  # one alert at a time in the app
                w.incident_id = await open_incident(db, pillow_id, kind, summary)
            w.incident_step += 1
            await update_incident(db, w.incident_id, {"step": w.incident_step})
        elif w.incident_id is not None and e.type == "family_ack":
            await update_incident(db, w.incident_id, {
                "status": "acknowledged", "acked_by": w.contact_ids.get(e.data["contact"]),
                "acked_at": _now_iso()})
        elif w.incident_id is not None and e.type in RESOLVED_REASONS:
            await update_incident(db, w.incident_id, {"status": "resolved", "resolved_at": _now_iso(),
                                                      "resolved_reason": RESOLVED_REASONS[e.type]})

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
        await add_notification(db, w.incident_id, contact_id, CHANNELS[a.channel], a.message)
        return None


_QUOTED = re.compile(r'"([^"]+)"')  # the check-in reason quotes her: She said: "..."


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
