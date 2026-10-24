#!/usr/bin/env python3
"""End-to-end link test: a USB-plugged pillow <-> the public tunnel <-> FastAPI <-> Supabase.

Checks every hop in both directions and says which one broke:

  1. server   GET  {server}/api/health                  tunnel has a runner, FastAPI answers
  2. up       board STATE line -> POST /state -> GET /state reads the same report back
  3. down     POST /commands (vibrate) -> GET /commands?after= -> CMD line to the board ->
              the board prints "cmd <id> vibrate" (it ran it; the Waveshare flashes its screen)

The board reports its own pillow_id ("kid" on the Waveshare), which the server doesn't know, so
the test posts as --pillow-id (default test-pillow, the seeded pillow the tests own).

Stop sim/serial_bridge.py first: only one program can hold the serial port.

  python3 sim/link_test.py --port /dev/ttyACM0 --server https://pillow.keanuc.net
  python3 sim/link_test.py --no-board      # server hops only, with a made-up state report
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

HEADERS = {"Content-Type": "application/json", "User-Agent": "calhacks-link-test/1.0"}
BOARD_WAIT_S = 5


def http(url: str, body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode(errors="replace")[:200]


def step(name: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<8} {detail}", flush=True)
    if not ok:
        sys.exit(1)


def read_state(port) -> dict:
    """Wait for the board's next STATE line."""
    deadline = time.time() + BOARD_WAIT_S
    while time.time() < deadline:
        line = port.readline().decode(errors="replace").strip()
        if line.startswith("STATE "):
            return json.loads(line[6:])
    step("board", False, f"no STATE line from the board in {BOARD_WAIT_S} s (SERIAL_BRIDGE set?)")
    return {}


def wait_for_ack(port, command_id: int) -> float:
    """Wait for the board's "cmd <id> ..." print; returns seconds taken."""
    start = time.time()
    while time.time() - start < BOARD_WAIT_S:
        line = port.readline().decode(errors="replace").strip()
        if line.startswith(f"cmd {command_id} "):
            return time.time() - start
    step("down", False, f"board never printed 'cmd {command_id} ...' (command not run)")
    return 0.0


def check_server(api: str) -> None:
    t = time.time()
    code, body = http(f"{api}/health")
    hint = {530: "tunnel has no runner: start cloudflared next to FastAPI (coord/TUNNEL.md)",
            502: "tunnel runs but nothing listens on its port: start FastAPI",
            503: "FastAPI has no Supabase credentials (backend/.env)"}.get(code, str(body))
    step("server", code == 200, f"GET /api/health -> {code} in {time.time() - t:.2f} s"
         + ("" if code == 200 else f": {hint}"))


def check_up(api: str, pillow: str, report: dict) -> None:
    report = {**report, "pillow_id": pillow, "ts": round(time.time(), 2)}
    t = time.time()
    code, body = http(f"{api}/pillows/{pillow}/state", report)
    step("up", code == 200, f"POST /state -> {code} in {time.time() - t:.2f} s"
         + ("" if code == 200 else f": {body}"))
    code, body = http(f"{api}/pillows/{pillow}/state")
    seen = isinstance(body, dict) and body.get("motion") == report["motion"]
    step("up", code == 200 and seen, f"GET /state reads it back (motion {report['motion']}, "
         f"device_ts {body.get('device_ts') if isinstance(body, dict) else body})")


def check_down(api: str, pillow: str, port) -> None:
    code, queued = http(f"{api}/pillows/{pillow}/commands",
                        {"cmd": "vibrate", "args": {"pattern": "tap", "repeat": 1}, "source": "link_test"})
    step("down", code == 201, f"POST /commands -> {code}" + ("" if code == 201 else f": {queued}"))
    command_id = queued["id"]
    t = time.time()
    code, polled = http(f"{api}/pillows/{pillow}/commands?after={command_id - 1}")
    mine = [c for c in polled if c.get("id") == command_id] if isinstance(polled, list) else []
    step("down", code == 200 and bool(mine), f"GET /commands?after={command_id - 1} returns id "
         f"{command_id} in {time.time() - t:.2f} s")
    if port is None:
        return
    port.reset_input_buffer()
    port.write(f"CMD {json.dumps(mine[0], separators=(',', ':'))}\n".encode())
    step("down", True, f"board ran it: 'cmd {command_id} vibrate' after {wait_for_ack(port, command_id):.2f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--server", default="https://pillow.keanuc.net")
    parser.add_argument("--pillow-id", default="test-pillow", help="registered pillow to post as")
    parser.add_argument("--no-board", action="store_true", help="skip the serial hops")
    args = parser.parse_args()
    api = args.server.rstrip("/") + "/api"

    port = None
    if not args.no_board:
        import serial  # pyserial; only needed with a board
        port = serial.Serial(args.port, 115200, timeout=1)
    check_server(api)
    report = read_state(port) if port else {
        "ts": 0, "head_on": False, "motion": 0.123, "room_motion": False, "light": None,
        "temp_c": None, "humidity": None, "keys": {"talk": False, "fine": False, "family": False},
        "knob": None}
    if port:
        step("board", True, f"STATE from '{report.get('pillow_id')}', posting as '{args.pillow_id}'")
    check_up(api, args.pillow_id, report)
    check_down(api, args.pillow_id, port)
    print("ALL PASS: board <-> tunnel <-> FastAPI <-> Supabase works both ways", flush=True)


if __name__ == "__main__":
    main()
