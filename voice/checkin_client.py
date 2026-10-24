# /// script
# requires-python = ">=3.12"
# dependencies = ["anthropic>=2.3", "httpx>=0.27", "numpy>=1.26", "sounddevice>=0.4", "websockets>=14"]
# ///
"""The base laptop's side of Night Watch: watch the pillow's night state, speak, run the check-in.

Night Watch runs on the server and can't talk; this laptop (next to the pillow, with the speaker
and mic) can. It polls GET /api/pillows/{id}/state about once a second and reacts to `night_state`:

    in_bed      -> play a queued goodnight message from family, if there is one (GET /goodnight)
    up          -> "The light's on. Take your time."
    check_in    -> run voice/checkin.py, then POST /api/pillows/{id}/checkin with the result
    in_bed      -> "You're back in bed. Goodnight." (only after an alert)

    export CARTESIA_API_KEY=sk_car_...  ANTHROPIC_API_KEY=sk-ant-...  CHECKIN_TOKEN=<same as the server>
    uv run voice/checkin_client.py                                # mum on https://pillow.keanuc.net
    uv run voice/checkin_client.py --server http://localhost:8000 --pillow-id test-pillow --contact Sarah
    uv run voice/checkin_client.py --keywords                     # judge replies by keywords, not Claude
    uv run voice/checkin_client.py --text                         # type her replies instead of mic + speaker

The check-in itself (tries, timings, when to escalate) is in checkin.py; this file only decides when
to run it and reports the outcome. If the server can't be reached the client keeps polling; if the
result can't be posted it retries, because the server escalates on its own once the check-in times out.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

DEFAULT_SERVER = "https://pillow.keanuc.net"
POLL_S = 1.0
PATH_LIGHT_LINE = "The light's on. Take your time."
GOODNIGHT_LINE = "You're back in bed. Goodnight."
ALERTED = {"check_in", "escalating"}

Action = tuple  # ("say", text) | ("checkin",) | ("goodnight",)


class Watcher:
    """Turns the stream of night states into the laptop's actions. Pure; no I/O."""

    def __init__(self) -> None:
        self.state: str | None = None
        self._alerted = False  # an alert was in flight since she got up

    def on_state(self, state: str) -> list[Action]:
        prev, self.state = self.state, state
        if state == prev:
            return []
        if state in ALERTED:
            self._alerted = True
        if state == "check_in":
            return [("checkin",)]
        if prev is None:
            return []  # just started: don't narrate a state we didn't see begin
        if state == "up" and prev == "in_bed":
            return [("say", PATH_LIGHT_LINE)]
        if state == "in_bed" and self._alerted:
            self._alerted = False
            return [("say", GOODNIGHT_LINE)]
        if state == "in_bed":
            return [("goodnight",)]  # she's lying down for the night: any message from family?
        if state == "awake":
            self._alerted = False
        return []


def _headers() -> dict[str, str]:
    return {"User-Agent": "calhacks-checkin-client/1.0"}


def main() -> None:
    import httpx  # only the live client needs it; the Watcher is tested without

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default=os.environ.get("PILLOW_SERVER", DEFAULT_SERVER))
    parser.add_argument("--pillow-id", default="mum")
    parser.add_argument("--contact", default="your family", help="who she's told will be alerted, e.g. Sarah")
    parser.add_argument("--keywords", action="store_true", help="judge replies by keywords, not Claude")
    parser.add_argument("--text", action="store_true", help="type replies and print speech (no audio needed)")
    args = parser.parse_args()

    token = os.environ.get("CHECKIN_TOKEN", "").strip()
    if not token:
        sys.exit("CHECKIN_TOKEN is not set (same value as backend/.env). Never commit it.")

    import checkin
    import judge

    if args.text:
        def speak(text: str, volume: float = 1.0) -> None:
            print(f"  pillow says ({volume:.1f}): {text}", flush=True)

        def listen(no_answer_s: float = 8.0):
            from types import SimpleNamespace
            reply = input("  she says (enter = silence, ... = mumble): ").strip()
            spoke = bool(reply)
            return SimpleNamespace(text="" if reply == "..." else reply, spoke=spoke)
    else:
        import voice
        voice._key()  # exit now, not mid check-in, if CARTESIA_API_KEY is missing
        speak, listen = voice.speak, voice.listen

    if args.keywords:
        judge_fn = judge.keyword_judge
    else:
        judge.warm_up_in_background()
        judge_fn = judge.claude_judge

    base = f"{args.server.rstrip('/')}/api/pillows/{args.pillow_id}"
    watcher = Watcher()
    print(f"watching {base}/state (night_state) ...", flush=True)
    with httpx.Client(timeout=10, headers=_headers()) as http:
        while True:
            try:
                r = http.get(f"{base}/state")
                r.raise_for_status()
                state = r.json()["night_state"]
            except (httpx.HTTPError, KeyError, ValueError) as err:
                print(f"[client] state poll failed: {err}", file=sys.stderr, flush=True)
                time.sleep(POLL_S * 3)
                continue
            for action in watcher.on_state(state):
                stamp = time.strftime("%H:%M:%S")
                if action[0] == "say":
                    print(f"{stamp}  say      {action[1]!r}", flush=True)
                    speak(action[1])
                elif action[0] == "goodnight":
                    try:
                        pending = http.get(f"{base}/goodnight").json()
                    except (httpx.HTTPError, ValueError) as err:
                        print(f"[client] goodnight check failed: {err}", file=sys.stderr, flush=True)
                        pending = None
                    if pending:
                        line = f"A goodnight message from {pending['from_name']}: {pending['message']}"
                        print(f"{stamp}  say      {line!r}", flush=True)
                        speak(line)
                        try:
                            http.post(f"{base}/goodnight/played",
                                      headers={"Authorization": f"Bearer {token}"})
                        except httpx.HTTPError as err:
                            print(f"[client] could not mark it played: {err}", file=sys.stderr, flush=True)
                else:
                    print(f"{stamp}  check-in starting", flush=True)
                    judge.warm_up_in_background()
                    out = checkin.run_checkin(speak, listen, judge=judge_fn, contact=args.contact,
                                              log=lambda m: print(f"          {m}", flush=True))
                    body = {"escalate": out.escalate, "reason": out.reason[:300]}
                    for attempt in range(5):
                        try:
                            resp = http.post(f"{base}/checkin", json=body,
                                             headers={"Authorization": f"Bearer {token}"})
                            resp.raise_for_status()
                            print(f"{stamp}  check-in {'ESCALATE' if out.escalate else 'STAND DOWN'}: "
                                  f"{out.reason} -> {resp.json()}", flush=True)
                            break
                        except httpx.HTTPError as err:
                            print(f"[client] posting the result failed ({err}); retry {attempt + 1}/5",
                                  file=sys.stderr, flush=True)
                            time.sleep(2)
            time.sleep(POLL_S)


if __name__ == "__main__":
    main()
