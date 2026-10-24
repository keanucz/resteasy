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
EDGE_KEYS = ("talk", "family")  # key_fine is Night Watch's (it cancels alerts)


class SleepTracker:
    """Derives restless / asleep / key events from one pillow's state stream."""

    def __init__(self) -> None:
        self._last_ts = -math.inf
        self._window: deque[tuple[float, float]] = deque()  # (ts, motion) over the last RESTLESS_S
        self._quiet_since: float | None = None  # first ts of the current run of motion < ASLEEP_MOTION
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
            self._leave_bed()
            return out
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

    def _leave_bed(self) -> None:
        self._window.clear()
        self._quiet_since = None
        self._asleep = False
        self._restless = False

    def _motion(self, ts: float, motion: float) -> list[Event]:
        out = []
        # restless: average over a full RESTLESS_S window
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
        # asleep: continuously quiet for ASLEEP_S
        if motion < ASLEEP_MOTION:
            if self._quiet_since is None:
                self._quiet_since = ts
            if not self._asleep and ts - self._quiet_since >= ASLEEP_S:
                self._asleep = True
                out.append(Event(ts, "asleep", {"quiet_min": ASLEEP_S // 60}))
        else:
            self._quiet_since = None
        return out
