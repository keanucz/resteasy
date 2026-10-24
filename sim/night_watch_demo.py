# /// script
# requires-python = ">=3.12"
# dependencies = ["anthropic", "httpx>=0.27", "numpy>=1.26", "sounddevice>=0.4", "websockets>=14"]
# ///
"""Play a simulated night through Night Watch on one laptop, no server or pillow needed.

Night Watch (backend/app/agents/night_watch.py) watches the fake pillow; when she doesn't come back
it starts the check-in, then walks the family alert ladder. Prints a timeline of everything it does.

  uv run sim/night_watch_demo.py --scenario no_return                  # nobody answers the check-in
  uv run sim/night_watch_demo.py --scenario no_return --checkin voice  # YOU answer, via the laptop
  uv run sim/night_watch_demo.py --scenario no_return --ack-after-min 1  # Sarah taps her pillow
  uv run sim/night_watch_demo.py --list

--checkin voice speaks through the laptop (needs CARTESIA_API_KEY and ANTHROPIC_API_KEY); the
simulated clock pauses while you talk. Commands and alerts are only printed: nothing is sent.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "backend"), str(ROOT / "voice")]

import pillow_sim  # noqa: E402
from app.agents.night_watch import (  # noqa: E402
    Alert,
    CancelCheckin,
    Command,
    Event,
    NightWatch,
    NightWatchConfig,
    Say,
    StartCheckin,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", default="no_return", choices=sorted(pillow_sim.SCENARIOS))
    parser.add_argument("--checkin", default="silent", choices=["silent", "fine", "voice"],
                        help="how the check-in goes: nobody answers, she says fine, or you answer live")
    parser.add_argument("--contact", default="Sarah")
    parser.add_argument("--start", default="23:00", help="simulated clock at the start, HH:MM")
    parser.add_argument("--speed", type=float, default=120, help="simulated seconds per real second")
    parser.add_argument("--ack-after-min", type=float, help="Sarah taps her pillow this long after alerts start")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for name, (desc, _) in sorted(pillow_sim.SCENARIOS.items()):
            print(f"{name:16} {desc}")
        return

    voice = None
    if args.checkin == "voice":
        import checkin
        import judge
        import voice

        judge.warm_up_in_background()  # SDK import is slow: pay it now, not when she first answers

    hh, mm = map(int, args.start.split(":"))
    start = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp()
    _, phases = pillow_sim.SCENARIOS[args.scenario]
    nw = NightWatch(NightWatchConfig(contacts=(args.contact,)))
    escalated_at = None

    def show(ts: float, acts: list) -> None:
        for a in acts:
            clock = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            if isinstance(a, Event):
                print(f"{clock}  event    {a.type} {a.data or ''}")
            elif isinstance(a, Command):
                print(f"{clock}  command  {a.pillow_id}: {a.cmd} {a.args}")
            elif isinstance(a, Say):
                print(f"{clock}  say      {a.text!r}")
                if voice:
                    voice.speak(a.text)
            elif isinstance(a, Alert):
                print(f"{clock}  ALERT    {a.contact} by {a.channel}: {a.message}")
            elif isinstance(a, (StartCheckin, CancelCheckin)):
                print(f"{clock}  {type(a).__name__}")

    print(f"{args.scenario}: {pillow_sim.SCENARIOS[args.scenario][0]}  [state: {nw.state}]")
    for second in range(int(phases[-1][0] * 60) + 1):
        ts = start + second
        acts = nw.observe({"ts": ts, **pillow_sim.state_at(phases, second / 60)})
        show(ts, acts)
        if any(isinstance(a, StartCheckin) for a in acts):
            if args.checkin == "voice":
                judge.warm_up_in_background()  # reopen the connection while the first question plays
                out = checkin.run_checkin(voice.speak, voice.listen, judge=judge.claude_judge,
                                          contact=args.contact, log=lambda m: print(f"          check-in {m}"))
                escalate, reason = out.escalate, out.reason
            else:
                escalate = args.checkin == "silent"
                reason = "She didn't answer." if escalate else "She said she was fine."
            show(ts, nw.checkin_done(ts, escalate, reason))
        if escalated_at is None and str(nw.state) == "escalating":
            escalated_at = second
        if args.ack_after_min is not None and escalated_at is not None \
                and second == escalated_at + int(args.ack_after_min * 60):
            show(ts, nw.family_acknowledged(ts, args.contact))
        if args.speed > 0:
            time.sleep(1 / args.speed)
    print(f"end of night  [state: {nw.state}]")


if __name__ == "__main__":
    main()
