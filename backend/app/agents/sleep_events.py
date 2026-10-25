"""The events of coord/CONTRACT.md section 2 that aren't about leaving the bed: `restless`, `asleep`
and the `key_talk` / `key_family` presses (Night Watch owns lay_down, bed_exit, bed_return,
no_return and key_fine).

Plain code, like Night Watch: thresholds and windows live here, time comes from each report's
`ts`, and nothing here talks to a database. `observe()` returns the events to store. `settled`
(not in the contract) is the end of a restless spell, so a Settle agent can tell its loop worked.
"""

from __future__ import annotations

import math
from collections import deque

from app.agents.night_watch import Event

RESTLESS_MOTION = 0.35  # average motion above this ...
RESTLESS_S = 10 * 60  # ... over this long, head on the pillow = restless
ASLEEP_MOTION = 0.08  # motion below this ...
ASLEEP_S = 15 * 60  # ... continuously for this long, head on the pillow = asleep
# Head off for less than this (rolling over, turning the pillow) is still the same sleep session
HEAD_OFF_GRACE_S = 3 * 60
EDGE_KEYS = ("talk", "family")  # key_fine is Night Watch's (it cancels alerts)

# PILLOW_DEMO_TIMINGS=1 on the server (with Night Watch's DEMO_TIMINGS): restless the moment she
# moves, settled the moment she stops, so judges see both in seconds. Two reports in a row (one
# second) either way, so a single bump of the bedside unit doesn't flip it.
DEMO_RESTLESS_MOTION = 0.15
DEMO_MOTION_REPORTS = 2
DEMO_ASLEEP_S = 3
DEMO_HEAD_OFF_GRACE_S = 5  # Night Watch's demo bed exit: off this long ends the bed session


class SleepTracker:
    """Derives restless / asleep / key events from one pillow's state stream."""

    def __init__(self, demo: bool = False) -> None:
        self._demo = demo
        self._asleep_s = DEMO_ASLEEP_S if demo else ASLEEP_S
        self._grace_s = DEMO_HEAD_OFF_GRACE_S if demo else HEAD_OFF_GRACE_S
        self._streak = 0  # demo: reports in a row on the other side of DEMO_RESTLESS_MOTION
        self._last_ts = -math.inf
        self._window: deque[tuple[float, float]] = deque()  # (ts, motion) over the last RESTLESS_S
        self._quiet_since: float | None = None  # first ts of the current run of motion < ASLEEP_MOTION
        self._off_since: float | None = None  # when her head left the pillow, until the grace runs out
        self._asleep = False  # reported asleep this bed session
        self._restless = False  # a restless spell is open
        self._keys_held = dict.fromkeys(EDGE_KEYS, False)

    def observe(self, s: dict) -> list[Event]:
        ts = float(s["ts"])
        if ts < self._last_ts:
            return []
        self._last_ts = ts
        out = self._keys(ts, s.get("keys") or {})
        head, motion = s.get("head_on"), s.get("motion")
        if head is None or motion is None:
            return out  # a sensor that isn't wired can't say anything about sleep
        if not head:
            if self._off_since is None:
                self._off_since = ts
            elif ts - self._off_since >= self._grace_s:
                out += self._leave_bed(ts)  # really up, not just rolled over
            return out
        self._off_since = None
        return out + self._motion(ts, float(motion))

    # ---------- pieces ----------

    def _keys(self, ts: float, keys: dict) -> list[Event]:
        out = []
        for key in EDGE_KEYS:
            held = bool(keys.get(key))
            if held and not self._keys_held[key]:
                out.append(Event(ts, f"key_{key}", {}))
            self._keys_held[key] = held
        return out

    def _leave_bed(self, ts: float) -> list[Event]:
        # In the demo a restless spell left open would still show "restless" when she lies down again
        out = [Event(ts, "settled", {"left_bed": True})] if self._demo and self._restless else []
        self._window.clear()
        self._quiet_since = None
        self._asleep = False
        self._restless = False
        self._streak = 0
        return out

    def _motion(self, ts: float, motion: float) -> list[Event]:
        out = self._demo_restless(ts, motion) if self._demo else self._restless_window(ts, motion)
        # asleep: continuously quiet for the asleep time
        if motion < ASLEEP_MOTION:
            if self._quiet_since is None:
                self._quiet_since = ts
            if not self._asleep and ts - self._quiet_since >= self._asleep_s:
                self._asleep = True
                quiet = {"quiet_s": self._asleep_s} if self._demo else {"quiet_min": ASLEEP_S // 60}
                out.append(Event(ts, "asleep", quiet))
        else:
            self._quiet_since = None
        return out

    def _demo_restless(self, ts: float, motion: float) -> list[Event]:
        moving = motion >= DEMO_RESTLESS_MOTION
        self._streak = self._streak + 1 if moving != self._restless else 0
        if self._streak < DEMO_MOTION_REPORTS:
            return []
        self._streak = 0
        self._restless = moving
        if moving:
            return [Event(ts, "restless", {"motion": round(motion, 3)})]
        return [Event(ts, "settled", {"motion": round(motion, 3)})]

    def _restless_window(self, ts: float, motion: float) -> list[Event]:
        """Restless: the average motion over a full RESTLESS_S window."""
        out = []
        self._window.append((ts, motion))
        while self._window and self._window[0][0] < ts - RESTLESS_S:
            self._window.popleft()
        if ts - self._window[0][0] >= RESTLESS_S:
            avg = sum(m for _, m in self._window) / len(self._window)
            if avg > RESTLESS_MOTION and not self._restless:
                self._restless = True
                data = {"motion_avg": round(avg, 3), "window_min": RESTLESS_S // 60}
                out.append(Event(ts, "restless", data))
            elif avg <= RESTLESS_MOTION and self._restless:
                self._restless = False
                out.append(Event(ts, "settled", {"motion_avg": round(avg, 3)}))
        return out
