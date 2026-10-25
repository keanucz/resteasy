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
  4. bridge   sim/audio_bridge.py is up (--bridge, else PILLOW_AUDIO_BRIDGE, else 127.0.0.1:8765)
  5. hardware POST /ping: the pillow node and the voice unit both answer, and over which link
              (usb > hotspot > ble; ble works but its state updates are slow)
  6. sensors  temperature and humidity (the node's DHT11) are reported, not null
  7. plate    press the head plate: head_on goes true, then false when you let go. --yes skips it
  8. chime    POST a `buzz` command to the server; the bridge picks it up and the voice unit plays
              it. You confirm you heard it
  9. speech   a Cartesia line spoken by the voice unit (voice/voice.py, PILLOW_AUDIO=pillow). You
              confirm you heard it

Start the bridge first, as for the demo:
  uv run sim/audio_bridge.py --hotspot 10.42.0.1:47801 --serial /dev/ttyACM0 --listen 127.0.0.1:8799 \
      --server https://pillow.keanuc.net --pillow-id mum
then, with CARTESIA_API_KEY set:
  uv run sim/demo_check.py --bridge 127.0.0.1:8799   # --yes: don't ask whether you heard it
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
BRIDGE_DEFAULT = "127.0.0.1:8765"
SPEECH = "Good morning. This is the pillow's check before the demo."
PLATE_WAIT_S = 15  # to press, then to let go; state arrives every ~0.5-1.5 s over USB or the hotspot
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


def check_bridge(bridge: str) -> bool:
    host, _, port = bridge.rpartition(":")
    try:
        socket.create_connection((host, int(port)), timeout=2).close()
        record("bridge", True, f"audio_bridge on {bridge}")
        return True
    except OSError:
        record("bridge", False, "audio_bridge not running: start it (see the top of this file)")
        return False


def check_hardware(server: str, pillow_id: str) -> bool:
    try:
        r = httpx.post(f"{server}/api/pillows/{pillow_id}/ping", timeout=15)  # waits ~4 s for fresh state
        r.raise_for_status()
        ping = r.json()
    except (httpx.HTTPError, json.JSONDecodeError) as err:
        record("hardware", False, f"POST /ping: {err}")
        return False
    link = ping.get("link")
    if not ping.get("voice_unit_alive"):
        record("hardware", False, "no fresh state from the voice unit: is the bridge connected to it?")
        return False
    if not ping.get("node_alive"):
        record("hardware", False, f"voice unit on {link}, but the pillow node is silent: power it, it pairs by itself")
        return False
    note = " (slow state updates: plug the voice unit into USB)" if link == "ble" else ""
    record("hardware", True, f"pillow node and voice unit both answer, link {link}{note}")
    return True


def read_state(server: str, pillow_id: str) -> dict:
    r = httpx.get(f"{server}/api/pillows/{pillow_id}/state", timeout=10)
    r.raise_for_status()
    return r.json()


def check_sensors(server: str, pillow_id: str) -> None:
    try:
        state = read_state(server, pillow_id)
    except (httpx.HTTPError, json.JSONDecodeError) as err:
        record("sensors", False, f"GET /state: {err}")
        return
    t, h = state.get("temp_c"), state.get("humidity")
    if t is None or h is None:
        record("sensors", False, "temp/humidity null: DHT11 on GPIO7 unplugged, or the node runs older firmware")
    else:
        record("sensors", True, f"{t} C, {h}% humidity, motion {state.get('motion')}")


def wait_head(server: str, pillow_id: str, want: bool) -> bool:
    deadline = time.monotonic() + PLATE_WAIT_S
    while time.monotonic() < deadline:
        try:
            if read_state(server, pillow_id).get("head_on") is want:
                return True
        except (httpx.HTTPError, json.JSONDecodeError):
            pass
        time.sleep(0.5)
    return False


def check_plate(server: str, pillow_id: str, assume_yes: bool) -> None:
    if assume_yes:
        record("plate", None, "skipped with --yes (it needs a hand on the pillow)")
        return
    input("      press the head plate (a hand on the pillow), then press Enter ")
    if not wait_head(server, pillow_id, True):
        record("plate", False, f"head_on stayed false for {PLATE_WAIT_S} s: check the foil sheets and GPIO4/GND")
        return
    print("      head_on true. Now let go...", flush=True)
    ok = wait_head(server, pillow_id, False)
    record("plate", ok, "head_on went true, then false" if ok else "head_on stuck true: the foil sheets touch")


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
    ap.add_argument("--bridge", default=os.environ.get("PILLOW_AUDIO_BRIDGE") or BRIDGE_DEFAULT,
                    help="audio_bridge's --listen address (also where voice.py speaks)")
    ap.add_argument("--yes", action="store_true",
                    help="don't ask whether you heard the chime and voice; skip the plate press")
    args = ap.parse_args()
    server = args.server.rstrip("/")
    os.environ["PILLOW_AUDIO_BRIDGE"] = args.bridge  # voice.speak reads it per call

    server_ok = check_server(server, args.pillow_id)
    if server_ok:
        check_watch(server, args.pillow_id)
    check_tunnel()
    if check_bridge(args.bridge):
        if server_ok and check_hardware(server, args.pillow_id):
            check_sensors(server, args.pillow_id)
            check_plate(server, args.pillow_id, args.yes)
        if server_ok:
            check_chime(server, args.pillow_id, args.yes)
        check_speech(args.yes)

    failed = [step for step, passed, _ in results if passed is False]
    print("\nREADY FOR THE DEMO" if not failed else f"\nNOT READY: {', '.join(dict.fromkeys(failed))}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
