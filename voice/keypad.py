# /// script
# requires-python = ">=3.12"
# dependencies = ["evdev>=1.7; sys_platform == 'linux'"]
# ///
"""The 3-key USB macro pad by the bed: talk, "I'm fine", call family.

On the base laptop (Fedora, GNOME on Wayland) a global hotkey can't see keys while another window has
focus, so the pad is read straight from its input device with python-evdev and grabbed (EVIOCGRAB),
so its keys stop typing into whatever window has focus. The user needs to be in the `input` group,
or have a udev rule for the pad.

    uv run voice/keypad.py --learn           # list input devices, then print every key the pad sends
    PILLOW_KEYPAD="<name part or /dev/input/eventN>" PILLOW_KEYMAP="KEY_F13=talk,KEY_F14=fine,KEY_F15=family" \
        uv run voice/keypad.py               # print the press events the client would act on

The keys:
    talk    hold 2 s, then let go, then she speaks. The hold gives the voice side time to start.
            A shorter press does nothing (a knock in the night must not start a conversation).
    fine    "I'm fine": stops a check-in or an alert, the moment it's pressed.
    family  "call my family": starts the alert ladder.

`KeyPresses` turns key-down / key-up into those press events and is plain code, tested without a pad.
`--keys stdin` reads t / f / c lines instead, for laptops without the pad and for rehearsals.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from collections.abc import Callable

HOLD_S = 2.0
KEYS = ("talk", "fine", "family")
DEFAULT_KEYMAP = "KEY_F13=talk,KEY_F14=fine,KEY_F15=family"

# Press events, in the order a talk press produces them
TALK_ARM = "talk_arm"  # talk key down: start the voice side (mic, Cartesia socket)
TALK_READY = "talk_ready"  # held long enough: tell her she can let go
TALK_GO = "talk_go"  # let go after the hold: listen now
TALK_CANCEL = "talk_cancel"  # let go too soon: stop, say nothing
FINE = "fine"
FAMILY = "family"

Emit = Callable[[str], None]


def parse_keymap(text: str) -> dict[str, str]:
    """ "KEY_F13=talk,KEY_F14=fine" -> {"KEY_F13": "talk", ...}; unknown roles are an error."""
    keymap: dict[str, str] = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        code, _, role = part.partition("=")
        if role.strip() not in KEYS:
            raise ValueError(f"{part!r}: the role must be one of {', '.join(KEYS)}")
        keymap[code.strip()] = role.strip()
    return keymap


class KeyPresses:
    """Key-down / key-up of the three roles in, press events out. Pure: the caller passes the time.

    Call `down(role, t)` and `up(role, t)` for each key edge (auto-repeat already dropped), and
    `tick(t)` often (every 50 ms or so) so the 2 s hold is noticed while the key is still held."""

    def __init__(self, hold_s: float = HOLD_S) -> None:
        self.hold_s = hold_s
        self._talk_since: float | None = None
        self._ready = False

    def down(self, role: str, t: float) -> list[str]:
        if role == "talk":
            if self._talk_since is not None:
                return []  # already held
            self._talk_since, self._ready = t, False
            return [TALK_ARM]
        return [FINE] if role == "fine" else [FAMILY] if role == "family" else []

    def tick(self, t: float) -> list[str]:
        if self._talk_since is not None and not self._ready and t - self._talk_since >= self.hold_s:
            self._ready = True
            return [TALK_READY]
        return []

    def up(self, role: str, t: float) -> list[str]:
        if role != "talk" or self._talk_since is None:
            return []
        out = self.tick(t)  # a release exactly at the threshold still counts as held
        ready, self._talk_since, self._ready = self._ready, None, False
        return out + [TALK_GO if ready else TALK_CANCEL]


# ---------- the pad (Linux, evdev) ----------


def find_device(want: str | None):
    """The pad's evdev device: `want` is a /dev/input path, "vid:pid" (hex) or part of its name."""
    import evdev

    devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
    if want and want.startswith("/dev/"):
        return evdev.InputDevice(want)
    for d in devices:
        vidpid = f"{d.info.vendor:04x}:{d.info.product:04x}"
        if want and (want.lower() == vidpid or want.lower() in d.name.lower()):
            return d
    names = "; ".join(f"{d.path} {d.name!r} {d.info.vendor:04x}:{d.info.product:04x}" for d in devices)
    raise SystemExit(f"keypad {want!r} not found. Devices: {names or 'none (are you in the input group?)'}")


def run_pad(emit: Emit, *, want: str | None, keymap: dict[str, str], grab: bool = True) -> None:
    """Read the pad forever, calling emit(event) for each press event. Blocks: run it in a thread."""
    import select

    import evdev

    dev = find_device(want)
    if grab:
        dev.grab()  # its keys stop typing into the focused window
    print(f"keypad: {dev.path} {dev.name!r}, keys {keymap}", file=sys.stderr, flush=True)
    presses = KeyPresses()
    try:
        while True:
            ready, _, _ = select.select([dev.fd], [], [], 0.05)
            now = time.monotonic()
            if ready:
                for ev in dev.read():
                    if ev.type != evdev.ecodes.EV_KEY or ev.value == 2:  # 2 = auto-repeat
                        continue
                    names = evdev.ecodes.KEY.get(ev.code, f"KEY_{ev.code}")
                    names = names if isinstance(names, list) else [names]
                    role = next((keymap[n] for n in names if n in keymap), None)
                    if role is not None:
                        for out in (presses.down if ev.value == 1 else presses.up)(role, now):
                            emit(out)
            for out in presses.tick(now):
                emit(out)
    finally:
        if grab:
            dev.ungrab()


def run_stdin(emit: Emit, *, hold_s: float = HOLD_S) -> None:
    """Rehearsal keys from stdin: t = a full talk press (held past 2 s), f = fine, c = call family."""
    for line in sys.stdin:
        key = line.strip().lower()[:1]
        if key == "t":
            for out in (TALK_ARM, TALK_READY, TALK_GO):
                emit(out)
                if out == TALK_ARM:
                    time.sleep(hold_s)
        elif key == "f":
            emit(FINE)
        elif key == "c":
            emit(FAMILY)


def start(emit: Emit, source: str) -> threading.Thread:
    """Run the keypad ("pad" or "stdin") in a daemon thread that calls emit for every press event."""
    if source == "stdin":
        target = lambda: run_stdin(emit)  # noqa: E731
    else:
        keymap = parse_keymap(os.environ.get("PILLOW_KEYMAP", DEFAULT_KEYMAP))
        target = lambda: run_pad(emit, want=os.environ.get("PILLOW_KEYPAD"), keymap=keymap)  # noqa: E731
    thread = threading.Thread(target=target, name="keypad", daemon=True)
    thread.start()
    return thread


def learn() -> None:
    """List input devices, then print every key event of the chosen one (Ctrl+C to stop)."""
    import evdev

    for p in evdev.list_devices():
        d = evdev.InputDevice(p)
        print(f"{d.path}  {d.info.vendor:04x}:{d.info.product:04x}  {d.name}")
    want = os.environ.get("PILLOW_KEYPAD") or input("device (path, vid:pid or name part): ").strip()
    dev = find_device(want)
    print(f"reading {dev.path} {dev.name!r}; press each key (Ctrl+C to stop)")
    for ev in dev.read_loop():
        if ev.type == evdev.ecodes.EV_KEY:
            state = {0: "up", 1: "down", 2: "repeat"}.get(ev.value, ev.value)
            print(f"  {evdev.ecodes.KEY.get(ev.code, ev.code)}  {state}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--learn", action="store_true", help="list devices and print the keys they send")
    parser.add_argument("--keys", choices=("pad", "stdin"), default="pad")
    args = parser.parse_args()
    if args.learn:
        learn()
        return
    thread = start(lambda e: print(f"{time.strftime('%H:%M:%S')}  {e}", flush=True), args.keys)
    thread.join()


if __name__ == "__main__":
    main()
