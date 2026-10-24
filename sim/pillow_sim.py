#!/usr/bin/env python3
"""Fake pillow: plays a scripted night as device state messages (coord/CONTRACT.md section 1).

Lets the agents and backend run end to end before the hardware arrives.

  python3 sim/pillow_sim.py --scenario no_return                 # JSON lines to stdout
  python3 sim/pillow_sim.py --scenario no_return --post http://localhost:8000
  python3 sim/pillow_sim.py --list

--speed is simulated seconds per real second (default 60: a night in about 9 minutes).
--post also polls GET /api/pillows/{id}/commands and prints each command it receives.
Stdlib only.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# (minutes from start, field updates). Each phase holds until the next one starts.
Phase = tuple[float, dict]

AWAKE_BED = {"head_on": True, "motion": 0.25, "room_motion": False, "light": 0.05}
ASLEEP = {"head_on": True, "motion": 0.03, "room_motion": False, "light": 0.02}
OUT_OF_BED = {"head_on": False, "motion": 0.0, "room_motion": True, "light": 0.02}
EMPTY_ROOM = {"head_on": False, "motion": 0.0, "room_motion": False, "light": 0.02}

SCENARIOS: dict[str, tuple[str, list[Phase]]] = {
    "good_night": ("lies down, settles, sleeps, 6-min bathroom trip, back to sleep", [
        (0, {**EMPTY_ROOM, "light": 0.6}), (1, {**AWAKE_BED, "light": 0.6}), (3, AWAKE_BED),
        (15, ASLEEP), (120, OUT_OF_BED), (126, AWAKE_BED), (135, ASLEEP), (180, ASLEEP),
    ]),
    "no_return": ("asleep, gets up at 3am, never comes back (Night Watch should escalate)", [
        (0, AWAKE_BED), (10, ASLEEP), (60, OUT_OF_BED), (62, EMPTY_ROOM), (100, EMPTY_ROOM),
    ]),
    "restless": ("in bed but restless for 40 min, then settles (Settle agent)", [
        (0, AWAKE_BED), (2, {**AWAKE_BED, "motion": 0.55}), (42, {**AWAKE_BED, "motion": 0.2}),
        (50, ASLEEP), (70, ASLEEP),
    ]),
    "talk_then_fine": ("gets up, check-in starts, presses the 'I'm fine' key in bed", [
        (0, ASLEEP), (5, OUT_OF_BED), (30, {**AWAKE_BED, "keys": {"fine": True}}),
        (30.2, AWAKE_BED), (40, ASLEEP),
    ]),
}

NO_KEYS = {"talk": False, "fine": False, "family": False}


@dataclass(frozen=True)
class Options:
    scenario: str
    pillow_id: str
    speed: float
    rate_hz: float
    post: str | None


def state_at(phases: list[Phase], minute: float) -> dict:
    current = phases[0][1]
    for start, fields in phases:
        if minute >= start:
            current = fields
    jitter = random.uniform(-0.03, 0.03) if current.get("head_on") else 0.0
    return {
        "head_on": current.get("head_on", False),
        "motion": round(max(0.0, current.get("motion", 0.0) + jitter), 3),
        "room_motion": current.get("room_motion", False),
        "light": current.get("light", 0.02),
        "temp_c": round(19.5 - minute / 120, 1),
        "humidity": 48,
        "keys": {**NO_KEYS, **current.get("keys", {})},
        "knob": None,
    }


def http(url: str, body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def run(opts: Options) -> None:
    _, phases = SCENARIOS[opts.scenario]
    end_min = phases[-1][0]
    sim_start = time.time()
    real_start = time.monotonic()
    last_cmd = 0
    while True:
        sim_elapsed = (time.monotonic() - real_start) * opts.speed
        minute = sim_elapsed / 60
        if minute > end_min:
            break
        msg = {"pillow_id": opts.pillow_id, "ts": round(sim_start + sim_elapsed, 2), **state_at(phases, minute)}
        if opts.post:
            base = f"{opts.post.rstrip('/')}/api/pillows/{opts.pillow_id}"
            try:
                http(f"{base}/state", msg)
                for cmd in http(f"{base}/commands?after={last_cmd}") or []:
                    last_cmd = max(last_cmd, int(cmd.get("id", 0)))
                    print(f"[sim t+{minute:5.1f}min] command: {json.dumps(cmd)}", flush=True)
            except (urllib.error.URLError, OSError, ValueError) as err:
                print(f"[sim] server error: {err}", file=sys.stderr, flush=True)
        else:
            print(json.dumps(msg), flush=True)
        time.sleep(1 / opts.rate_hz)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", default="no_return", choices=sorted(SCENARIOS))
    parser.add_argument("--pillow-id", default="mum")
    parser.add_argument("--speed", type=float, default=60.0, help="simulated seconds per real second")
    parser.add_argument("--rate-hz", type=float, default=2.0, help="state messages per real second")
    parser.add_argument("--post", help="server base URL, e.g. http://localhost:8000")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args()
    if args.list:
        for name, (desc, _) in sorted(SCENARIOS.items()):
            print(f"{name:16} {desc}")
        return
    run(Options(args.scenario, args.pillow_id, args.speed, args.rate_hz, args.post))


if __name__ == "__main__":
    main()
