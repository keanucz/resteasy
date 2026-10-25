"""Turn a line from the Uno (firmware/pillow_uno) into a CONTRACT.md section 1 state message.

The Uno prints `{"head_on":1,"motion":null,...,"fine":0,"talk":0,"family":0}` at 9600 baud; the
voice unit forwards it as `UNO <line>`. The laptop adds `pillow_id` and real Unix `ts` (the boards
have no clock) and nests the keys. Anything that isn't a state line (boot banner, noise) is None.
Stdlib only, so both bridges can import it.
"""

from __future__ import annotations

import json

SENSORS = ("head_on", "motion", "room_motion", "light", "temp_c", "humidity")
KEYS = ("talk", "fine", "family")
BOOLS = ("head_on", "room_motion")


def uno_line_to_state(line: str, *, pillow_id: str, ts: float) -> dict | None:
    """The contract message for a `UNO {...}` (or bare `{...}`) line, or None if it isn't one."""
    text = line.strip()
    if text.startswith("UNO "):
        text = text[4:].strip()
    if not text.startswith("{"):
        return None
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if not isinstance(raw, dict) or "head_on" not in raw:
        return None  # the boot banner, or not ours
    state: dict = {"pillow_id": pillow_id, "ts": ts}
    for name in SENSORS:
        value = raw.get(name)
        state[name] = None if value is None else (bool(value) if name in BOOLS else value)
    state["keys"] = {k: bool(raw.get(k, 0)) for k in KEYS}
    state["knob"] = raw.get("knob")
    return state
