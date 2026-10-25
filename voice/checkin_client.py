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
    awake       -> every 10 s, say any due reminder (GET /reminders/due, voice/reminder.py), then
                   POST /reminders/{occurrence_id}/result

With --keys pad (the 3-key macro pad, voice/keypad.py) or --keys stdin (t / f / c lines):
    talk    hold 2 s, let go, then she speaks: set or hear her reminders (voice/talk.py), or
            "I can't sleep": ten minutes of quiet music (voice/settle.py)
    fine    POST /keys "fine" at once: stops a check-in or an alert (and the music)
    family  POST /keys "family" at once: starts the alert ladder
The pillow never needs a key to hear her: whenever it asks something, it listens straight away.

    export CARTESIA_API_KEY=sk_car_...  ANTHROPIC_API_KEY=sk-ant-...  CHECKIN_TOKEN=<same as the server>
    uv run voice/checkin_client.py                                # mum on https://pillow.keanuc.net
    uv run voice/checkin_client.py --server http://localhost:8000 --pillow-id test-pillow --contact Sarah
    uv run voice/checkin_client.py --keywords                     # judge replies by keywords, not Claude
    uv run voice/checkin_client.py --text                         # type her replies instead of mic + speaker
    uv run voice/checkin_client.py --keys pad                     # the macro pad (Linux, evdev)

The check-in itself (tries, timings, when to escalate) is in checkin.py; this file only decides when
to run it and reports the outcome. If the server can't be reached the client keeps polling; if the
result can't be posted it retries, because the server escalates on its own once the check-in times out.
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
from zoneinfo import ZoneInfo

DEFAULT_SERVER = "https://pillow.keanuc.net"
POLL_S = 1.0
PATH_LIGHT_LINE = "The light's on. Take your time."
GOODNIGHT_LINE = "You're back in bed. Goodnight."
ALERTED = {"check_in", "escalating"}
REMINDER_CHECK_S = 10.0  # the server only marks reminders due while she's awake

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


def reminders_due(state: str | None, now: float, last_check: float) -> bool:
    """Whether to ask the server for due reminders now: only by day, and not every poll."""
    return state == "awake" and now - last_check >= REMINDER_CHECK_S


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
    parser.add_argument("--keys", choices=("none", "pad", "stdin"), default=os.environ.get("PILLOW_KEYS", "none"),
                        help="the bedside keys: the macro pad, or t/f/c lines on stdin")
    parser.add_argument("--tz", default=os.environ.get("PILLOW_TZ", "America/Los_Angeles"), help="her timezone")
    args = parser.parse_args()

    token = os.environ.get("CHECKIN_TOKEN", "").strip()
    if not token:
        sys.exit("CHECKIN_TOKEN is not set (same value as backend/.env). Never commit it.")

    import checkin
    import judge
    import reminder

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
        judge_fn, reminder_judge = judge.keyword_judge, judge.keyword_reminder_judge
    else:
        judge.warm_up_in_background()
        judge_fn, reminder_judge = judge.claude_judge, judge.claude_reminder_judge

    base = f"{args.server.rstrip('/')}/api/pillows/{args.pillow_id}"
    watcher = Watcher()
    auth = {"Authorization": f"Bearer {token}"}
    last_reminder_check = 0.0

    def post_result(http, url: str, body: dict) -> object | None:
        """POST a result with retries; the server's own timers cover a result that never arrives."""
        for attempt in range(5):
            try:
                resp = http.post(url, json=body, headers=auth)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as err:
                print(f"[client] posting to {url} failed ({err}); retry {attempt + 1}/5",
                      file=sys.stderr, flush=True)
                time.sleep(2)
        return None

    events: queue.Queue[str] = queue.Queue()
    stop_checkin = threading.Event()
    talk_session = None
    music = None  # settle.Player: the lowest priority sound; any key, check-in or reminder stops it

    def post_key(key: str) -> None:
        """POST /keys now, from the keypad thread: "I'm fine" must not wait behind speech."""
        try:
            with httpx.Client(timeout=10, headers=_headers()) as h:
                r = h.post(f"{base}/keys", json={"key": key}, headers=auth)
                r.raise_for_status()
                print(f"{time.strftime('%H:%M:%S')}  key      {key} -> {r.json()}", flush=True)
        except httpx.HTTPError as err:
            print(f"[client] key {key} failed: {err}", file=sys.stderr, flush=True)

    if args.keys != "none":
        import keypad
        import settle
        import talk

        if args.text:
            sys.exit("--keys needs real audio: rehearse talking with voice/talk.py --text instead")
        music = settle.Player(voice.play, log=lambda m: print(f"          {m}", flush=True))

        def on_key(event: str) -> None:
            if event in (keypad.FINE, keypad.FAMILY, keypad.TALK_ARM):
                music.stop()  # from the keypad thread: the music must not wait behind speech
            if event in (keypad.FINE, keypad.FAMILY):
                if event == keypad.FINE:
                    stop_checkin.set()
                threading.Thread(target=post_key, args=(event,), daemon=True).start()
            events.put(event)

        talk_session = talk.TalkSession(
            talk.live_voice(talk.Pillow(args.server, args.pillow_id, token), lambda _reason: post_key("family"),
                            keywords=args.keywords, player=music),
            talk.Ears(), ZoneInfo(args.tz))
        keypad.start(on_key, args.keys)

    def handle_key(event: str) -> None:
        """Talk events, on the main thread (one conversation at a time; never during a check-in)."""
        import keypad

        if talk_session is None or event in (keypad.FINE, keypad.FAMILY):
            return
        if watcher.state == "check_in":
            talk_session.cancel()  # the check-in is already listening to her
            return
        if event == keypad.TALK_ARM:
            talk_session.arm()
        elif event == keypad.TALK_READY:
            talk_session.ready()
        elif event == keypad.TALK_CANCEL:
            talk_session.cancel()
        elif event == keypad.TALK_GO:
            threading.Thread(target=post_key, args=("talk",), daemon=True).start()
            print(f"{time.strftime('%H:%M:%S')}  talk     listening", flush=True)
            talk_session.go()

    def wait_for_keys(seconds: float) -> None:
        """Sleep between polls, but act on a key press the moment it comes."""
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            try:
                event = events.get(timeout=left)
            except queue.Empty:
                return
            handle_key(event)

    def drop_stale_talk() -> None:
        """Talk presses made while the pillow was busy (a check-in, a reminder) are dropped."""
        while not events.empty():
            events.get_nowait()
        if talk_session is not None:
            talk_session.cancel()

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
                            http.post(f"{base}/goodnight/played", headers=auth)
                        except httpx.HTTPError as err:
                            print(f"[client] could not mark it played: {err}", file=sys.stderr, flush=True)
                else:
                    print(f"{stamp}  check-in starting", flush=True)
                    if music is not None:
                        music.stop()  # the check-in owns the speaker and the mic now
                    judge.warm_up_in_background()
                    stop_checkin.clear()
                    out = checkin.run_checkin(speak, listen, judge=judge_fn, contact=args.contact,
                                              log=lambda m: print(f"          {m}", flush=True),
                                              should_stop=stop_checkin.is_set)
                    drop_stale_talk()
                    if out.reason == checkin.STOPPED_REASON:
                        print(f"{stamp}  check-in stopped: she pressed I'm fine (the server knows)", flush=True)
                        continue
                    body = {"escalate": out.escalate, "reason": out.reason[:300]}
                    resp = post_result(http, f"{base}/checkin", body)
                    print(f"{stamp}  check-in {'ESCALATE' if out.escalate else 'STAND DOWN'}: "
                          f"{out.reason} -> {resp}", flush=True)
            if reminders_due(watcher.state, time.monotonic(), last_reminder_check):
                last_reminder_check = time.monotonic()
                try:
                    due = http.get(f"{base}/reminders/due").json()
                except (httpx.HTTPError, ValueError) as err:
                    print(f"[client] reminder check failed: {err}", file=sys.stderr, flush=True)
                    due = []
                if due and music is not None:
                    music.stop()
                for item in due:
                    stamp = time.strftime("%H:%M:%S")
                    print(f"{stamp}  reminder {item['text']!r}", flush=True)
                    out = reminder.run_reminder(speak, listen, text=item["text"], confirm=item["confirm"],
                                                judge=reminder_judge,
                                                log=lambda m: print(f"          {m}", flush=True))
                    resp = post_result(http, f"{base}/reminders/{item['occurrence_id']}/result",
                                       {"outcome": out.outcome, "reply": out.reply})
                    print(f"{stamp}  reminder {out.outcome} -> {resp}", flush=True)
                if due:
                    drop_stale_talk()
            wait_for_keys(POLL_S)


if __name__ == "__main__":
    main()
