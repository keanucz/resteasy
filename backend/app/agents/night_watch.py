"""Night Watch: turns one pillow's state stream into events and actions (coord/AGENT_FLOW.md 2 and 4).

Plain code by design: every timer and threshold lives here, and Claude only judges words (the
check-in conversation in voice/). Time comes from each state's `ts` (device or simulator clock),
never the wall clock, so a simulated night runs in seconds and tests are deterministic.

Feed it Mum's pillow states with `observe()`, the check-in result with `checkin_done()`, and a
family member's acknowledgement (the app's "I'm on it" button) with `family_acknowledged()`. Each
returns the actions to carry out, in order. Nothing here talks to Supabase, a device or a phone:
the caller stores the `Event`s, queues the `Command`s, speaks the `Say`s, runs the check-in and sends
the `Alert`s.
The Guardian (guardian.py) sits between these actions and the outside world.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

LAY_DOWN_S = 5  # head on this long = lying down (coord/CONTRACT.md 2)
# Head on this long = back in bed while she's up. Longer than LAY_DOWN_S: a brief reading from the
# slow warmth/humidity sensor must not end an incident mid-escalation.
BED_RETURN_S = 45
BED_EXIT_S = 10  # head off this long = out of bed (10 s so the demo reacts quickly; was 30)
CHECKIN_MAX_S = 180  # a check-in that hasn't reported back by now is treated as failed

PATH_LIGHT_ON = {"brightness_pct": 20, "color": "warm", "fade_s": 3}
PATH_LIGHT_OFF = {"brightness_pct": 0, "color": "off", "fade_s": 10}
# After this many "I'm fine" check-ins on one trip, family gets an informational heads-up (not an
# alarm). Provisional: the team still has to decide this (PR #21).
FINE_ROUNDS_BEFORE_HEADS_UP = 2


@dataclass(frozen=True)
class Timings:
    """How long the head reading must hold before the state changes, and how long she can be up
    before the check-in starts. The defaults are the product's; `DEMO_TIMINGS` is for judging."""

    lay_down_s: float = LAY_DOWN_S
    bed_return_s: float = BED_RETURN_S
    bed_exit_s: float = BED_EXIT_S
    checkin_after_s: float | None = None  # None: the owner's `checkin_timeout_min`
    recheck_after_fine_s: float | None = None  # after "I'm fine"; None: the same as checkin_after_s


# PILLOW_DEMO_TIMINGS=1 on the server: every state shows within seconds of pressing or lifting the
# head plate, so a five-minute judging slot sees them all. The check-in counts from the lift. After
# "I'm fine" it waits a minute, so a rehearsal can't run into the second-fine family heads-up.
DEMO_TIMINGS = Timings(lay_down_s=3, bed_return_s=3, bed_exit_s=5, checkin_after_s=15,
                       recheck_after_fine_s=60)


class State(StrEnum):
    AWAKE = "awake"  # daytime, or not in bed yet: nothing to watch
    IN_BED = "in_bed"
    UP = "up"  # out of bed at night, path light on, check-in timer running
    CHECK_IN = "check_in"  # the voice check-in is talking to her
    ESCALATING = "escalating"  # family are being alerted


@dataclass(frozen=True)
class NightWatchConfig:
    """The owner's settings (household row later). Defaults match the week-one plan."""

    pillow_id: str = "mum"
    resident: str = "Mum"
    contacts: tuple[str, ...] = ("Sarah",)  # alert order (the caller puts reachable contacts first)
    checkin_timeout_min: float = 20  # week one fixed; later the personal baseline (CONTEXT.md)
    timezone: str = "America/Los_Angeles"  # the resident's; decides what "night" means
    # Watched hours in her timezone. start == end, or None, watches all day (daytime demos).
    quiet_hours: tuple[time, time] | None = (time(22), time(7))
    paused: bool = False  # she (or the owner) paused monitoring: start no new watch
    path_light: dict = field(default_factory=lambda: dict(PATH_LIGHT_ON))
    step_wait_min: float = 2  # between escalation steps
    # The ladder channels ("app", "sms", "call") each contact allows (Settings > Alerts in the app);
    # a contact missing here allows every channel
    channels: Mapping[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    """A derived pillow event, for the events table (and the night baseline / night summary)."""

    ts: float
    type: str
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Command:
    """A device command to queue for a pillow (coord/CONTRACT.md 3)."""

    pillow_id: str
    cmd: str
    args: dict


@dataclass(frozen=True)
class Say:
    """A line for the base laptop's voice to speak to her."""

    text: str


@dataclass(frozen=True)
class StartCheckin:
    """Run the voice check-in (voice/checkin.py) and report back with `checkin_done()`."""


@dataclass(frozen=True)
class CancelCheckin:
    """Stop a running check-in: she's back in bed or tapped "I'm fine"."""


@dataclass(frozen=True)
class Alert:
    """A message to one family contact on one channel: "app" (in-app alert / push), "sms" or "call"."""

    contact: str
    channel: str
    message: str


Action = Event | Command | Say | StartCheckin | CancelCheckin | Alert


class NightWatch:
    """The state machine for one resident's pillow."""

    def __init__(self, config: NightWatchConfig | None = None, timings: Timings | None = None) -> None:
        self.cfg = config or NightWatchConfig()
        self.timings = timings or Timings()
        self.state = State.AWAKE
        self._head_on = False  # debounced
        self._head_raw: bool | None = None
        self._head_since = 0.0
        self._last_ts = -math.inf
        self._fine_held = False
        self._left_at = 0.0  # when her head left the pillow this trip
        self._checkin_due = math.inf
        self._checkin_deadline = math.inf  # when a running check-in counts as failed
        self._fine_rounds = 0  # check-ins this trip where she said she was fine
        self._ladder: list[list[tuple[str, str]]] = []  # steps still to run: [(channel, contact)]
        self._next_step_at = math.inf
        self._alerted: list[str] = []  # contacts told so far, to tell them when she's okay
        self._reason = ""  # why we escalated, repeated in every alert
        self._distress = False  # escalated on something she said, not a no-return
        self._acked = False  # a family member acknowledged this escalation

    # ---------- inputs ----------

    def resume(self, state: State, since: float) -> None:
        """Pick up after a server restart from `pillow_state.night_state` and `state_since`.

        A check-in or escalation in flight can't be resumed exactly: both become an immediate new
        check-in, because asking her again is safer than going quiet.
        """
        self._head_on = state is State.IN_BED
        if state in (State.AWAKE, State.IN_BED):
            self.state = state
            return
        self.state = State.UP
        self._left_at = since
        self._checkin_due = since + self._checkin_wait_s() if state is State.UP else -math.inf

    def observe(self, s: dict) -> list[Action]:
        """Take one state message from her pillow (coord/CONTRACT.md 1) and return what to do.

        A report with no head reading (`head_on` null) still counts for keys and timers.
        """
        ts = float(s["ts"])
        if ts < self._last_ts:
            return []  # out of order: time never goes backwards here
        self._last_ts = ts
        out: list[Action] = []
        head = s.get("head_on")
        if head is not None:
            head = bool(head)
            if head != self._head_raw:
                self._head_raw, self._head_since = head, ts
            held = ts - self._head_since
            t = self.timings
            lay_down_s = t.lay_down_s if self.state in (State.AWAKE, State.IN_BED) else t.bed_return_s
            if head and not self._head_on and held >= lay_down_s:
                self._head_on = True
                out += self._head_arrived(ts)
            elif not head and self._head_on and held >= t.bed_exit_s:
                self._head_on = False
                out += self._head_left(ts, left_at=self._head_since)
        fine = bool((s.get("keys") or {}).get("fine"))
        if fine and not self._fine_held:
            out += self._tapped_fine(ts)
        self._fine_held = fine
        return out + self._tick(ts)

    def tick(self, ts: float) -> list[Action]:
        """Let time pass with no report (board unplugged, check-in never answered): run due timers."""
        if ts < self._last_ts:
            return []
        self._last_ts = ts
        return self._tick(ts)

    def fine_pressed(self, ts: float) -> list[Action]:
        """The "I'm fine" key on the bedside pad (POST /keys): the same as the pillow's fine key."""
        return self._tapped_fine(ts)

    def checkin_done(self, ts: float, escalate: bool, reason: str) -> list[Action]:
        """Result of the voice check-in: escalate, or she said she's fine."""
        if self.state is not State.CHECK_IN:
            return []  # cancelled meanwhile (back in bed, or tapped)
        out: list[Action] = [Event(ts, "checkin_result", {"escalate": escalate, "reason": reason})]
        return out + (self._escalate(ts, reason) if escalate else self._said_fine(ts))

    def distress_heard(self, ts: float, reason: str) -> list[Action]:
        """She said something alarming outside a check-in (answering a reminder, say): escalate now,
        day or night. Never ignored, so it works in any state; an escalation already running goes on."""
        if self.state is State.ESCALATING:
            return []
        out: list[Action] = [Event(ts, "distress_heard", {"reason": reason, "state": str(self.state)})]
        if self.state is State.CHECK_IN:
            out.append(CancelCheckin())
        return out + self._escalate(ts, reason, distress=True)

    def family_acknowledged(self, ts: float, contact: str) -> list[Action]:
        """A family member pressed "I'm on it" in the app: stop alerting anyone else."""
        if self.state is not State.ESCALATING or self._acked:
            return []  # a held tap arrives twice a second; only the first one counts
        self._acked = True
        self._ladder, self._next_step_at = [], math.inf
        return [Event(ts, "family_ack", {"contact": contact}),
                Say(f"{contact} knows, and is checking on you.")]

    # ---------- transitions ----------

    def _checkin_wait_s(self) -> float:
        """How long she may be up before the check-in starts."""
        if self.timings.checkin_after_s is not None:
            return self.timings.checkin_after_s
        return self.cfg.checkin_timeout_min * 60

    def _head_arrived(self, ts: float) -> list[Action]:
        if self.state is State.AWAKE:
            if not self._is_night(ts):
                return [Event(ts, "lay_down", {"watching": False})]
            self.state = State.IN_BED
            return [Event(ts, "lay_down", {"watching": True})]
        if self.state is State.IN_BED:
            return []
        trip_min = round((ts - self._left_at) / 60, 1)
        out: list[Action] = [Event(ts, "bed_return", {"trip_min": trip_min}),
                             Command(self.cfg.pillow_id, "set_light", dict(PATH_LIGHT_OFF))]
        if self.state is State.CHECK_IN:
            out.append(CancelCheckin())
        out += self._tell_alerted(f"{self.cfg.resident} is back in bed.")
        self._reset_trip()
        self.state = State.IN_BED
        return out

    def _head_left(self, ts: float, left_at: float) -> list[Action]:
        if self.state is not State.IN_BED:
            return []
        if not self._is_night(left_at):
            self.state = State.AWAKE  # up for the day
            return [Event(ts, "got_up", {})]
        self.state = State.UP
        self._left_at = left_at
        self._checkin_due = left_at + self._checkin_wait_s()
        return [Event(ts, "bed_exit", {"left_at": left_at}),
                Command(self.cfg.pillow_id, "set_light", dict(self.cfg.path_light)),
                Say("The light's on. Take your time.")]

    def _tick(self, ts: float) -> list[Action]:
        if self.state is State.AWAKE and self._head_on and self._is_night(ts):
            # She lay down before quiet hours began: start watching now, not only at the next lay-down.
            self.state = State.IN_BED
            return [Event(ts, "lay_down", {"watching": True, "late_start": True})]
        if self.state is State.UP and ts >= self._checkin_due:
            # Every no-return goes through the voice check-in: it alone decides to escalate, so she
            # is always asked and warned (with a chance to cancel) before family are alarmed.
            away = round((ts - self._left_at) / 60)
            self.state = State.CHECK_IN
            self._checkin_due = math.inf
            self._checkin_deadline = ts + CHECKIN_MAX_S
            return [Event(ts, "no_return", {"away_min": away, "round": self._fine_rounds + 1}),
                    StartCheckin()]
        if self.state is State.CHECK_IN and ts >= self._checkin_deadline:
            reason = "The pillow's check-in didn't finish, so we couldn't ask her."
            return [Event(ts, "checkin_timeout", {}), CancelCheckin(), *self._escalate(ts, reason)]
        if self.state is State.ESCALATING and ts >= self._next_step_at:
            return self._next_step(ts)
        return []

    def _tapped_fine(self, ts: float) -> list[Action]:
        out: list[Action] = [Event(ts, "key_fine", {"state": str(self.state)})]
        if self.state is State.CHECK_IN:
            return out + [CancelCheckin(), *self._said_fine(ts)]
        if self.state is State.ESCALATING:
            self._ladder, self._next_step_at = [], math.inf
            out += self._tell_alerted(f"{self.cfg.resident} tapped her pillow to say she's okay.")
            self._alerted = []
            return out + self._said_fine(ts)
        return out

    def _said_fine(self, ts: float) -> list[Action]:
        self.state = State.UP
        self._fine_rounds += 1
        recheck_s = self.timings.recheck_after_fine_s
        self._checkin_due = ts + (recheck_s if recheck_s is not None else self._checkin_wait_s())
        if self._fine_rounds != FINE_ROUNDS_BEFORE_HEADS_UP:
            return []
        away = round((ts - self._left_at) / 60)
        contact = self.cfg.contacts[0]
        return [Event(ts, "heads_up", {"contact": contact, "away_min": away}),
                Alert(contact, "sms", f"Heads-up, no action needed: {self.cfg.resident} has been up "
                                      f"{away} min but says she's fine.")]

    def _escalate(self, ts: float, reason: str, distress: bool = False) -> list[Action]:
        self.state = State.ESCALATING
        self._acked = False
        self._distress = distress
        # Least intrusive first: an in-app alert to every contact at once, then SMS and a call to
        # each contact in turn, skipping the channels a contact turned off.
        ladder = [[("app", c) for c in self.cfg.contacts if self._allows(c, "app")]]
        for contact in self.cfg.contacts:
            ladder += [[(channel, contact)] for channel in ("sms", "call") if self._allows(contact, channel)]
        self._ladder = [step for step in ladder if step]
        self._reason = reason
        return self._next_step(ts)

    def _next_step(self, ts: float) -> list[Action]:
        if not self._ladder:
            self._next_step_at = math.inf
            return [Event(ts, "ladder_exhausted", {})]
        step = self._ladder.pop(0)
        self._next_step_at = ts + self.cfg.step_wait_min * 60
        if self._distress:
            message = f"{self.cfg.resident} may need help. {self._reason}"
        else:
            left = datetime.fromtimestamp(self._left_at, ZoneInfo(self.cfg.timezone)).strftime("%H:%M")
            away = round((ts - self._left_at) / 60)
            message = (f"{self.cfg.resident} got up at {left} and hasn't come back to bed ({away} min). "
                       f"{self._reason}")
        kind = "distress" if self._distress else "no_return"
        out: list[Action] = [Event(ts, "escalation_step", {"channel": step[0][0], "kind": kind,
                                                            "contacts": [c for _, c in step]})]
        for channel, contact in step:
            out.append(Alert(contact, channel, message))
            if contact not in self._alerted:
                self._alerted.append(contact)
        return out

    # ---------- helpers ----------

    def _allows(self, contact: str, channel: str) -> bool:
        """Whether `contact` takes alerts on `channel`."""
        allowed = self.cfg.channels.get(contact)
        return allowed is None or channel in allowed

    def _tell_alerted(self, message: str) -> list[Action]:
        return [Alert(c, "sms", message) for c in self._alerted]

    def _reset_trip(self) -> None:
        self._checkin_due = math.inf
        self._fine_rounds = 0
        self._ladder, self._next_step_at, self._alerted = [], math.inf, []

    def _is_night(self, ts: float) -> bool:
        """Whether a new watch may start at `ts`: inside her quiet hours and not paused."""
        if self.cfg.paused:
            return False
        if self.cfg.quiet_hours is None or self.cfg.quiet_hours[0] == self.cfg.quiet_hours[1]:
            return True
        start, end = self.cfg.quiet_hours
        now = datetime.fromtimestamp(ts, ZoneInfo(self.cfg.timezone)).time()
        return now >= start or now < end if start > end else start <= now < end
