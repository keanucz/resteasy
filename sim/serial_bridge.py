#!/usr/bin/env python3
"""USB serial bridge: a pillow plugged into a laptop reaches the server without Wi-Fi.

The venue's 2.4 GHz Wi-Fi is too weak for the ESP32s (they can't use 5/6 GHz), and hotspots are
banned. With SERIAL_BRIDGE set in the firmware's secrets.h, the board prints one line per state
message and reads command lines:

  board -> laptop:  STATE {"pillow_id": "kid", ...}      (coord/CONTRACT.md section 1)
  laptop -> board:  CMD {"id": 41, "cmd": "set_light", "args": {...}}
  laptop -> board:  LINK OK   (after each successful state POST; boards fall back to local
                             behaviour, e.g. the path light, when these stop)

This script forwards STATE to POST {server}/api/pillows/{id}/state and polls
GET {server}/api/pillows/{id}/commands?after=N every 500 ms, writing each command back as CMD.

  pip install pyserial
  python3 sim/serial_bridge.py --port /dev/ttyACM0 --server https://pillow.keanuc.net

Other lines from the board (boot log, debug prints) are echoed with a "board:" prefix.
"""

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request

import serial  # pyserial

HEADERS = {"Content-Type": "application/json", "User-Agent": "calhacks-pillow-bridge/1.0"}


def http(url: str, body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def read_board(port: serial.Serial, server: str, state: dict) -> None:
    """Forward STATE lines; remember which pillow is on the other end."""
    while True:
        line = port.readline().decode(errors="replace").strip()
        if not line:
            continue
        if not line.startswith("STATE "):
            print(f"board: {line}", flush=True)
            continue
        try:
            msg = json.loads(line[6:])
        except json.JSONDecodeError:
            print(f"bridge: bad STATE line: {line[:120]}", file=sys.stderr, flush=True)
            continue
        state["pillow_id"] = msg.get("pillow_id", state.get("pillow_id"))
        # The boards have no clock (ts = seconds since boot). Night Watch reads quiet hours and
        # trip times from ts, so stamp real Unix time from the laptop before forwarding.
        msg["device_uptime_s"] = msg.get("ts")
        msg["ts"] = round(time.time(), 2)
        try:
            http(f"{server}/api/pillows/{state['pillow_id']}/state", msg)
            port.write(b"LINK OK\n")  # tells the board the server is reachable (offline fallback)
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"bridge: state POST failed: {err}", file=sys.stderr, flush=True)


def poll_commands(port: serial.Serial, server: str, state: dict, interval: float) -> None:
    last_id = 0
    while True:
        time.sleep(interval)
        pillow = state.get("pillow_id")
        if not pillow:
            continue  # wait until the board has told us who it is
        try:
            commands = http(f"{server}/api/pillows/{pillow}/commands?after={last_id}") or []
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"bridge: commands GET failed: {err}", file=sys.stderr, flush=True)
            continue
        for cmd in commands:
            last_id = max(last_id, int(cmd.get("id", 0)))
            port.write(f"CMD {json.dumps(cmd, separators=(',', ':'))}\n".encode())
            print(f"bridge: -> {cmd.get('cmd')} {json.dumps(cmd.get('args', {}))}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="/dev/ttyACM0", help="e.g. /dev/ttyACM0, /dev/ttyUSB0, COM5")
    parser.add_argument("--server", default="https://pillow.keanuc.net")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--interval", type=float, default=0.5, help="command poll seconds")
    args = parser.parse_args()

    port = serial.Serial(args.port, args.baud, timeout=1)
    state: dict = {}
    server = args.server.rstrip("/")
    print(f"bridge: {args.port} <-> {server}", flush=True)
    threading.Thread(target=poll_commands, args=(port, server, state, args.interval), daemon=True).start()
    read_board(port, server, state)


if __name__ == "__main__":
    main()
