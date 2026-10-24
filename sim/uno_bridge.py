# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5"]
# ///
"""Bench bridge: the Uno plugged straight into the laptop by USB, its lines posted as pillow state.

For the bench, before the Uno is wired into the voice unit (then sim/audio_bridge.py --server does
this job over the pillow's link). Reads firmware/pillow_uno's JSON lines at 9600 baud, stamps
pillow_id + real time, nests them per coord/CONTRACT.md and POSTs each one to the server. Also polls
the pillow's commands and prints them (the Uno has no light or motor to run them on).

  uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101                      # test-pillow on the tunnel
  uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101 --pillow-id mum --server http://localhost:8000
  uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101 --dry                # print, don't post
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import serial

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uno_state import uno_line_to_state  # noqa: E402

DEFAULT_SERVER = "https://pillow.keanuc.net"
HEADERS = {"Content-Type": "application/json", "User-Agent": "calhacks-uno-bridge/1.0"}


def http(url: str, body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def poll_commands(base: str, interval: float) -> None:
    last = 0
    while True:
        try:
            for cmd in http(f"{base}/commands?after={last}") or []:
                last = max(last, int(cmd.get("id", 0)))
                print(f"command (no actuator on the Uno): {json.dumps(cmd)}", flush=True)
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"[uno_bridge] command poll failed: {err}", file=sys.stderr, flush=True)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="the Uno's USB serial port")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--pillow-id", default="test-pillow", help="use 'mum' only for the real pillow")
    parser.add_argument("--dry", action="store_true", help="print the state messages instead of posting")
    args = parser.parse_args()
    base = f"{args.server.rstrip('/')}/api/pillows/{args.pillow_id}"
    if not args.dry:
        threading.Thread(target=poll_commands, args=(base, 0.5), daemon=True).start()
    print(f"uno_bridge: {args.port} @ {args.baud} -> {base}/state", flush=True)
    while True:
        try:
            with serial.Serial(args.port, args.baud, timeout=2) as port:
                while True:
                    line = port.readline().decode(errors="replace").strip()
                    if not line:
                        continue
                    state = uno_line_to_state(line, pillow_id=args.pillow_id, ts=round(time.time(), 2))
                    if state is None:
                        print(f"uno: {line}", flush=True)
                        continue
                    if args.dry:
                        print(json.dumps(state), flush=True)
                        continue
                    try:
                        http(f"{base}/state", state)
                        print(f"state head_on={state['head_on']}", end="\r", flush=True)
                    except (urllib.error.URLError, OSError, ValueError) as err:
                        print(f"\n[uno_bridge] POST failed: {err}", file=sys.stderr, flush=True)
        except serial.SerialException as err:
            print(f"[uno_bridge] serial: {err}; retrying in 2 s", file=sys.stderr, flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
