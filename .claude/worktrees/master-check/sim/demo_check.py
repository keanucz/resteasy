# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "numpy>=1.26", "sounddevice>=0.4", "websockets>=14"]
# ///
"""Morning-of check before judging: everything the demo needs, one command, PASS/FAIL per step.

  1. server   GET /api/health through the tunnel, and the pillow's /state (Supabase answers)
  2. watch    Night Watch watches all day (quiet_start == quiet_end): judging is at 10:30, outside
              the usual 22:00-07:00, so otherwise the pillow ignores the demo
  3. tunnel   exactly one connector on calhacks-pillow, and it's the VPS (linux). Needs Keanu's
              cloudflared login; skipped elsewhere
  4. bridge   sim/audio_bridge.py is up on 127.0.0.1:8765
  5. chime    POST a `buzz` command to the server; the bridge picks it up and the voice unit plays
              it. You confirm you heard it
  6. speech   a Cartesia line spoken by the voice unit (voice/voice.py, PILLOW_AUDIO=pillow). You
              confirm you heard it

Start the bridge first, as for the demo:
  uv run sim/audio_bridge.py --serial /dev/ttyACM0 --server https://pillow.keanuc.net --pillow-id mum
then, with CARTESIA_API_KEY set:
  uv run sim/demo_check.py              # --yes: don't ask whether you heard it
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

os.environ["PILLOW_AUDIO"] = "pillow"  # before voice.py reads it: speak through the voice unit
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "voice"))
import voice

TUNNEL = "5a23a49f-52a1-426d-a08c-03c21a1a9be6"  # calhacks-pillow; by id, the name can resolve wrong
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12} ")
BRIDGE = ("127.0.0.1", 8765)
SPEECH = "Good morning. This is the pillow's check before the demo."
CHIME_WAIT_S = 4  # the bridge polls every 0.5 s; ~1.5 s from POST to sound through the VPS

results: list[tuple[str, bool | None, str]] = []  # (step, passed or None = skipped, detail)


def record(step: str, passed: bool | None, detail: str) -> None:
    results.append((step, passed, detail))
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}[passed]
    print(f"{mark}  {step:<7} {detail}", flush=True)


def heard(what: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return input(f"      heard the {what}? [Y/n] ").strip().lower() in ("", "y", "yes")


def check_server(server: str, pillow_id: str) -> bool:
    try:
        start = time.monotonic()
        r = httpx.get(f"{server}/api/health", timeout=10)
        ms = (time.monotonic() - start) * 1000
        r.raise_for_status()
        record("server", True, f"health {r.json().get('environment')} in {ms:.0f} ms")
        r = httpx.get(f"{server}/api/pillows/{pillow_id}/state", timeout=10)
        if r.status_code != 200:
            record("server", False, f"/api/pillows/{pillow_id}/state answered {r.status_code}: {r.text[:120]}")
            return False
        record("server", True, f"pillow {pillow_id} state readable (Supabase OK)")
        return True
    except (httpx.HTTPError, json.JSONDecodeError) as err:
        record("server", False, f"{server}: {err} (502 = the tunnel's backend is down: deploy/README.md)")
        return False


def check_watch(server: str, pillow_id: str) -> None:
    try:
        r = httpx.get(f"{server}/api/pillows/{pillow_id}/night", timeout=10)
        r.raise_for_status()
        settings = r.json()["settings"]
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as err:
        record("watch", False, f"GET /night: {err}")
        return
    start, end = settings.get("quiet_start"), settings.get("quiet_end")
    if start is None or end is None or start == end:
        record("watch", True, f"Night Watch on all day (check-in after {settings.get('checkin_timeout_min')} min)")
    else:
        record("watch", False, f"watched {start}-{end} only: set the resident's quiet_start = quiet_end")


def check_tunnel() -> None:
    if not shutil.which("cloudflared") or not (Path.home() / ".cloudflared" / "cert.pem").exists():
        record("tunnel", None, "no cloudflared login here (Keanu's laptop only)")
        return
    out = subprocess.run(["cloudflared", "tunnel", "info", TUNNEL],
                         capture_output=True, text=True, timeout=30, check=False)
    # connector rows: ID CREATED ARCHITECTURE VERSION ORIGIN-IP EDGE...
    connectors = [line.split() for line in out.stdout.splitlines() if UUID.match(line)]
    if len(connectors) == 1 and connectors[0][2].startswith("linux"):
        record("tunnel", True, f"one connector, the VPS ({connectors[0][2]} from {connectors[0][4]})")
    elif not connectors:
        record("tunnel", False, "no connector: the VPS tunnel container is down")
    else:
        rows = ", ".join(f"{c[0][:8]} {c[2]} from {c[4]}" for c in connectors)
        record("tunnel", False, f"{len(connectors)} connectors ({rows}): kill the laptop one (coord/TUNNEL.md)")


def check_bridge() -> bool:
    try:
        socket.create_connection(BRIDGE, timeout=2).close()
        record("bridge", True, f"audio_bridge on {BRIDGE[0]}:{BRIDGE[1]}")
        return True
    except OSError:
        record("bridge", False, "audio_bridge not running: start it (see the top of this file)")
        return False


def check_chime(server: str, pillow_id: str, assume_yes: bool) -> None:
    body = {"cmd": "buzz", "args": {"pattern": "chime", "repeat": 1}, "source": "routine"}
    try:
        r = httpx.post(f"{server}/api/pillows/{pillow_id}/commands", json=body, timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as err:
        record("chime", False, f"POST buzz: {err}")
        return
    print(f"      queued buzz #{r.json().get('id')}: listen...", flush=True)
    time.sleep(CHIME_WAIT_S)
    ok = heard("chime", assume_yes)
    record("chime", ok, "server -> bridge -> voice unit" if ok else
           "not heard: is the bridge running with --server and this --pillow-id?")


def check_speech(assume_yes: bool) -> None:
    if not os.environ.get("CARTESIA_API_KEY", "").strip():
        record("speech", False, "CARTESIA_API_KEY is not set")
        return
    try:
        start = time.monotonic()
        voice.speak(SPEECH)
        seconds = time.monotonic() - start
    except (httpx.HTTPError, OSError, RuntimeError) as err:
        record("speech", False, f"{err}")
        return
    ok = heard("voice", assume_yes)
    record("speech", ok, f"Cartesia + playback in {seconds:.1f} s" if ok else "not heard: check VOL / the speaker")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="https://pillow.keanuc.net")
    ap.add_argument("--pillow-id", default="mum")
    ap.add_argument("--yes", action="store_true", help="don't ask whether you heard the chime and voice")
    args = ap.parse_args()
    server = args.server.rstrip("/")

    server_ok = check_server(server, args.pillow_id)
    if server_ok:
        check_watch(server, args.pillow_id)
    check_tunnel()
    if check_bridge():
        if server_ok:
            check_chime(server, args.pillow_id, args.yes)
        check_speech(args.yes)

    failed = [step for step, passed, _ in results if passed is False]
    print("\nREADY FOR THE DEMO" if not failed else f"\nNOT READY: {', '.join(dict.fromkeys(failed))}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
