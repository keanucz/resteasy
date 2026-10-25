# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5"]
# ///
"""Bench bridge: the pillow board plugged straight into the laptop by USB, its lines posted as state.

For the bench, when the pillow node (firmware/pillow_node) is on the laptop's USB instead of talking
to the voice unit over ESP-NOW (then sim/audio_bridge.py --server does this job). Reads the board's
JSON lines (`UNO {...}` or bare `{...}`), stamps pillow_id + real time, nests them per
coord/CONTRACT.md and POSTs each one to the server. Also polls the pillow's commands: a `buzz` is
written back to the board as the USB line it already understands ("BUZZ chime 1"); anything else is
printed (the node has no light or motor to run it on).

  uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101 --baud 115200        # pillow_node, test-pillow
  uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101 --pillow-id mum --server http://localhost:8000
  uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101 --dry                # print, don't post
  (the retired Uno sketch, firmware/pillow_uno, printed the same lines at 9600 baud)
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


def command_to_line(cmd: dict) -> str | None:
    """The USB line that makes the pillow node run a server command, or None if it can't run it.

    Only `buzz` today ("BUZZ <chime|alert> <repeat>", the same text the voice unit sends it over
    ESP-NOW). The node clamps repeat to 1-3 and ignores unknown patterns.
    """
    if cmd.get("cmd") != "buzz":
        return None
    args = cmd.get("args") or {}
    return f"BUZZ {args.get('pattern', 'chime')} {int(args.get('repeat', 1))}"


def newest_state(lines: list[str], *, pillow_id: str, ts: float) -> tuple[dict | None, list[str]]:
    """The last state line in `lines` as a contract message (None if there is none), and the other
    lines (boot banner, link stats, buzz echoes) for printing.

    A POST to the server takes 1-3 s and the board prints a line every 500 ms, so the bridge
    drains what has queued up and posts only the newest: the server wants the current state, not
    a backlog that lags further behind every second.
    """
    state = None
    others = []
    for line in lines:
        parsed = uno_line_to_state(line, pillow_id=pillow_id, ts=ts)
        if parsed is None:
            others.append(line)
        else:
            state = parsed
    return state, others


class Board:
    """The board's serial port, shared by the reader (main loop) and the command writer (thread)."""

    def __init__(self) -> None:
        self.port: serial.Serial | None = None
        self.lock = threading.Lock()

    def write_line(self, line: str) -> bool:
        with self.lock:
            if self.port is None:
                return False
            self.port.write((line + "\n").encode())
            return True


def newest_id(cmds: list[dict]) -> int:
    """The highest command id in a poll result (0 if empty): where a fresh bridge starts polling, so
    a restart doesn't replay every command the pillow was ever sent."""
    return max((int(c.get("id", 0)) for c in cmds), default=0)


def poll_commands(base: str, interval: float, board: Board) -> None:
    last = None
    while last is None:  # skip what was queued before we started
        try:
            last = newest_id(http(f"{base}/commands?after=0") or [])
            print(f"commands: polling after id {last}", flush=True)
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"[uno_bridge] command poll failed: {err}", file=sys.stderr, flush=True)
            time.sleep(interval)
    while True:
        try:
            for cmd in http(f"{base}/commands?after={last}") or []:
                last = max(last, int(cmd.get("id", 0)))
                line = command_to_line(cmd)
                if line is None:
                    print(f"command (no actuator on the node): {json.dumps(cmd)}", flush=True)
                elif board.write_line(line):
                    print(f"command -> board: {line}  ({json.dumps(cmd)})", flush=True)
                else:
                    print(f"command dropped, board not open: {line}", flush=True)
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"[uno_bridge] command poll failed: {err}", file=sys.stderr, flush=True)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="the board's USB serial port")
    parser.add_argument("--baud", type=int, default=115200, help="pillow_node 115200; the old Uno sketch 9600")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--pillow-id", default="test-pillow", help="use 'mum' only for the real pillow")
    parser.add_argument("--dry", action="store_true", help="print the state messages instead of posting")
    args = parser.parse_args()
    base = f"{args.server.rstrip('/')}/api/pillows/{args.pillow_id}"
    board = Board()
    if not args.dry:
        threading.Thread(target=poll_commands, args=(base, 0.5, board), daemon=True).start()
    print(f"uno_bridge: {args.port} @ {args.baud} -> {base}/state", flush=True)
    while True:
        try:
            with serial.Serial(args.port, args.baud, timeout=2) as port:
                board.port = port
                while True:
                    lines = [port.readline().decode(errors="replace").strip()]
                    while port.in_waiting:  # drain what queued up during the last POST
                        lines.append(port.readline().decode(errors="replace").strip())
                    state, others = newest_state([ln for ln in lines if ln],
                                                 pillow_id=args.pillow_id, ts=round(time.time(), 2))
                    for other in others:
                        print(f"board: {other}", flush=True)
                    if state is None:
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
            board.port = None
            print(f"[uno_bridge] serial: {err}; retrying in 2 s", file=sys.stderr, flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
