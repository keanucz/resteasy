"""Guardian: the last check before anything leaves the agents (coord/AGENT_FLOW.md section 5).

Plain code, no model: every device command, spoken line, family message and config change goes
through `check()` / `check_config()` and gets a `Verdict`. A blocked action may come with a safe
`replacement` (a capped brightness, a message with the medical claim removed), because at 3 am a
blocked alert must still reach someone. The caller logs every verdict to `agent_log.guardian`,
which the family app shows live.

Rules (defaults, all in config):
- device commands: only the contract's commands and argument ranges; brightness <= 40 % at night.
- words: no diagnosis or medical claim in anything spoken or sent ("may have had a stroke").
- alerts: at most N per contact per night; no repeat on one channel inside the step wait; SMS only
  to contacts who opted in.
- config: the Morning Brief may only change whitelisted keys, within bounds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.agents.night_watch import Action, Alert, Command, Say

NIGHT_BRIGHTNESS_MAX = 40
CONFIG_BOUNDS: dict[str, tuple[int, int]] = {"checkin_timeout_min": (10, 30), "path_light_pct": (0, 40)}
CONFIG_TIMES = ("quiet_start", "quiet_end")
CONFIG_WHITELIST = (*CONFIG_BOUNDS, *CONFIG_TIMES)

_COMMANDS: dict[str, dict[str, tuple]] = {  # cmd -> arg -> (lo, hi) or allowed values
    "set_light": {"brightness_pct": (0, 100), "color": ("warm", "amber", "off"), "fade_s": (0, 60)},
    "pulse": {"start_bpm": (4, 14), "end_bpm": (4, 14), "duration_min": (1, 30)},
    "vibrate": {"pattern": ("tap", "double", "long"), "repeat": (1, 5)},
    "fan": {"speed_pct": (0, 100)},
    "buzz": {"pattern": ("chime", "alert"), "repeat": (1, 3)},
    "stop_all": {},
}
_CLAMPABLE = {("set_light", "brightness_pct"), ("set_light", "fade_s"), ("vibrate", "repeat"),
              ("fan", "speed_pct"), ("buzz", "repeat")}

MEDICAL = re.compile(
    r"\b(strokes?|heart attack|cardiac|seizures?|dementia|alzheimer'?s?|delirium|concussion|"
    r"fractured?|broken? (?:her |his |a )?(?:hip|leg|arm|bone)|infection|sepsis|pneumonia|"
    r"hypoglyc\w*|overdose|diagnos\w*|symptoms? of|"
    r"take (?:another|more|an extra|a second) (?:pill|tablet|dose))\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_QUOTED = re.compile(r'"[^"]*"|“[^”]*”')  # her own words, quoted: reported, not claimed


def _claim(text: str) -> re.Match | None:
    """A medical word the AGENT uses; what she said in quotes is hers to say."""
    return MEDICAL.search(_QUOTED.sub("", text))


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = ""
    replacement: Any = None  # a safe version to carry out instead, when there is one

    @property
    def label(self) -> str:
        return "allowed" if self.allowed else "blocked"


@dataclass(frozen=True)
class Screened:
    """One action after the Guardian: `run` is what to carry out (None = dropped)."""

    original: Action
    verdict: Verdict
    run: Action | None


@dataclass(frozen=True)
class GuardianConfig:
    timezone: str = "America/Los_Angeles"
    quiet_hours: tuple[time, time] | None = (time(22), time(7))  # when the brightness cap applies
    night_brightness_max: int = NIGHT_BRIGHTNESS_MAX
    max_alerts_per_contact: int = 6  # per night, all channels together
    step_wait_min: float = 2  # no repeat to one contact on one channel inside this
    sms_consent: dict[str, bool] = field(default_factory=dict)  # contact -> opted in (missing = yes)


class Guardian:
    SAFE_SAY = "I'm here with you. Help is on its way."
    SAFE_ALERT = "Please check on her, or call her now; if you can't reach her, go round or call for help."

    def __init__(self, config: GuardianConfig | None = None) -> None:
        self.cfg = config or GuardianConfig()
        self._sent: dict[tuple[str, str], int] = {}  # (night, contact) -> alerts allowed
        self._last: dict[tuple[str, str], float] = {}  # (contact, channel) -> ts of last allowed alert

    # ---------- actions ----------

    def screen(self, actions: list[Action], ts: float) -> list[Screened]:
        """Check a batch in order: allowed actions run as they are, blocked ones run their safe
        replacement if there is one, otherwise they are dropped."""
        out = []
        for a in actions:
            v = self.check(a, ts)
            out.append(Screened(a, v, a if v.allowed else v.replacement))
        return out

    def check(self, action: Action, ts: float) -> Verdict:
        """Judge one action about to be carried out at device time `ts`; record allowed alerts."""
        if isinstance(action, Command):
            return self._command(action, ts)
        if isinstance(action, Say):
            return self._say(action)
        if isinstance(action, Alert):
            v = self._alert(action, ts)
            if v.allowed or isinstance(v.replacement, Alert):
                self._count(action, ts)
            return v
        return Verdict(True)

    def _command(self, c: Command, ts: float) -> Verdict:
        spec = _COMMANDS.get(c.cmd)
        if spec is None:
            return Verdict(False, f"{c.cmd} is not a pillow command")
        args, reasons = dict(c.args), []
        for name, rule in spec.items():
            if name not in args:
                return Verdict(False, f"{c.cmd} needs {name}")
            value = args[name]
            if isinstance(rule[0], str):
                if value not in rule:
                    return Verdict(False, f"{c.cmd}: {name} {value!r} is not one of {', '.join(rule)}")
                continue
            lo, hi = rule
            if c.cmd == "set_light" and name == "brightness_pct" and self._is_night(ts):
                hi = self.cfg.night_brightness_max
            if not isinstance(value, int | float) or isinstance(value, bool):
                return Verdict(False, f"{c.cmd}: {name} must be a number")
            if not lo <= value <= hi:
                if (c.cmd, name) not in _CLAMPABLE:
                    return Verdict(False, f"{c.cmd}: {name} {value} is outside {lo}-{hi}")
                args[name] = min(max(value, lo), hi)
                unit = "%" if name.endswith("_pct") else ""
                when = " at night" if name == "brightness_pct" and hi != 100 else ""
                reasons.append(f"{name} {value}{unit} capped to {args[name]}{unit}{when}")
        if reasons:
            return Verdict(False, "; ".join(reasons), replace(c, args=args))
        return Verdict(True)

    def check_text(self, text: str) -> Verdict:
        """Free text that will be spoken to her (a family goodnight message): no medical claims."""
        hit = MEDICAL.search(text)
        return Verdict(False, f"medical claim blocked: {hit.group(0)!r}") if hit else Verdict(True)

    def _say(self, s: Say) -> Verdict:
        hit = _claim(s.text)
        if hit:
            return Verdict(False, f"medical claim blocked: {hit.group(0)!r}", Say(self.SAFE_SAY))
        return Verdict(True)

    def _alert(self, a: Alert, ts: float) -> Verdict:
        if a.channel == "sms" and not self.cfg.sms_consent.get(a.contact, True):
            return Verdict(False, f"{a.contact} has not given SMS consent")
        night = self._night_key(ts)
        n = self._sent.get((night, a.contact), 0)
        if n >= self.cfg.max_alerts_per_contact:
            cap = self.cfg.max_alerts_per_contact
            return Verdict(False, f"{a.contact} already had {n} alerts tonight (max {cap})")
        last = self._last.get((a.contact, a.channel))
        wait = self.cfg.step_wait_min * 60
        if last is not None and ts - last < wait:
            return Verdict(False, f"{a.channel} to {a.contact} repeated inside the "
                                  f"{self.cfg.step_wait_min:g} min step wait")
        hit = _claim(a.message)
        if hit:
            kept = [p for p in _SENTENCE.split(a.message) if not _claim(p)]
            safe = " ".join(kept).strip() or self.SAFE_ALERT
            return Verdict(False, f"medical claim blocked: {hit.group(0)!r}", replace(a, message=safe))
        return Verdict(True)

    def _count(self, a: Alert, ts: float) -> None:
        key = (self._night_key(ts), a.contact)
        self._sent[key] = self._sent.get(key, 0) + 1
        self._last[(a.contact, a.channel)] = ts

    # ---------- config (Morning Brief) ----------

    def check_config(self, diff: dict[str, Any]) -> Verdict:
        """Keep only whitelisted keys, clamp numbers to their bounds, validate times."""
        clean, reasons = {}, []
        for key, value in diff.items():
            if key not in CONFIG_WHITELIST:
                reasons.append(f"{key} is not a key the agents may change")
            elif key in CONFIG_BOUNDS:
                lo, hi = CONFIG_BOUNDS[key]
                if not isinstance(value, int | float) or isinstance(value, bool):
                    reasons.append(f"{key} must be a number")
                    continue
                clean[key] = min(max(value, lo), hi)
                if clean[key] != value:
                    reasons.append(f"{key} {value} clamped to {clean[key]} ({lo}-{hi})")
            else:
                try:
                    time.fromisoformat(str(value))
                    clean[key] = value
                except ValueError:
                    reasons.append(f"{key} {value!r} is not a time")
        if reasons:
            return Verdict(False, "; ".join(reasons), clean)
        return Verdict(True)

    # ---------- helpers ----------

    def _local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts, ZoneInfo(self.cfg.timezone))

    def _is_night(self, ts: float) -> bool:
        if self.cfg.quiet_hours is None or self.cfg.quiet_hours[0] == self.cfg.quiet_hours[1]:
            return True
        start, end = self.cfg.quiet_hours
        now = self._local(ts).time()
        return now >= start or now < end if start > end else start <= now < end

    def _night_key(self, ts: float) -> str:
        """One bucket per night: the date 12 hours earlier, so 22:00 and 03:00 share it."""
        return (self._local(ts) - timedelta(hours=12)).date().isoformat()
