# /// script
# requires-python = ">=3.12"
# dependencies = ["evdev>=1.7; sys_platform == 'linux'"]
# ///
"""The 3-key USB macro pad by the bed: talk, "I'm fine", call family.

On Linux (Fedora, GNOME on Wayland) a global hotkey can't see keys while another window has focus,
so the pad is read straight from its input device with python-evdev and grabbed (EVIOCGRAB), so its
keys stop typing into whatever window has focus. The user needs to be in the `input` group, or have
a udev rule for the pad.

On Windows a low-level keyboard hook (ctypes, nothing to install) sees the mapped keys whichever
window has focus and swallows them, so they don't type anywhere either. A hook can't tell keyboards
apart, so map keys no other keyboard sends (F13-F15: voice/pillow-pad.yaml flashes our pad);
PILLOW_KEYPAD is ignored. Key names are evdev's on both (KEY_F13, KEY_A, KEY_VOLUMEUP...).

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


class PadKeys:
    """The pad's raw key edges in, press events out: drops auto-repeat and keys outside the keymap."""

    def __init__(self, keymap: dict[str, str], emit: Emit) -> None:
        self.keymap, self.emit = keymap, emit
        self.presses = KeyPresses()
        self._held: set[str] = set()

    def edge(self, names: list[str], down: bool, t: float) -> bool:
        """One key down or up (`names`: the key's names). True if it is one of the pad's keys."""
        name = next((n for n in names if n in self.keymap), None)
        if name is None:
            return False
        if down == (name in self._held):
            return True  # auto-repeat (a down while held), or an up whose down we never saw
        (self._held.add if down else self._held.discard)(name)
        for out in (self.presses.down if down else self.presses.up)(self.keymap[name], t):
            self.emit(out)
        return True

    def tick(self, t: float) -> None:
        for out in self.presses.tick(t):
            self.emit(out)


# ---------- the pad on Linux (evdev) ----------


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
    pad = PadKeys(keymap, emit)
    try:
        while True:
            ready, _, _ = select.select([dev.fd], [], [], 0.05)
            now = time.monotonic()
            if ready:
                for ev in dev.read():
                    if ev.type != evdev.ecodes.EV_KEY or ev.value == 2:  # 2 = auto-repeat
                        continue
                    names = evdev.ecodes.KEY.get(ev.code, f"KEY_{ev.code}")
                    pad.edge(names if isinstance(names, list) else [names], ev.value == 1, now)
            pad.tick(now)
    finally:
        if grab:
            dev.ungrab()


# ---------- the pad on Windows (low-level keyboard hook) ----------

# Windows virtual-key codes under evdev's names, so one PILLOW_KEYMAP works on both
VK_CODES = {
    **{f"KEY_F{n}": 0x6F + n for n in range(1, 25)},
    **{f"KEY_{c}": ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
    "KEY_SPACE": 0x20, "KEY_ENTER": 0x0D, "KEY_ESC": 0x1B, "KEY_TAB": 0x09, "KEY_BACKSPACE": 0x08,
    "KEY_LEFTSHIFT": 0xA0, "KEY_RIGHTSHIFT": 0xA1, "KEY_LEFTCTRL": 0xA2, "KEY_RIGHTCTRL": 0xA3,
    "KEY_LEFTALT": 0xA4, "KEY_RIGHTALT": 0xA5, "KEY_LEFTMETA": 0x5B,
    "KEY_LEFT": 0x25, "KEY_UP": 0x26, "KEY_RIGHT": 0x27, "KEY_DOWN": 0x28,
    "KEY_MUTE": 0xAD, "KEY_VOLUMEDOWN": 0xAE, "KEY_VOLUMEUP": 0xAF,
    "KEY_NEXTSONG": 0xB0, "KEY_PREVIOUSSONG": 0xB1, "KEY_STOPCD": 0xB2, "KEY_PLAYPAUSE": 0xB3,
}
_VK_NAMES = {vk: name for name, vk in VK_CODES.items()}


def vk_name(vk: int) -> str:
    """A virtual-key code as its evdev key name, or VK_<n> if it has none here."""
    return _VK_NAMES.get(vk, f"VK_{vk}")


def run_pad_windows(emit: Emit, *, keymap: dict[str, str], learn: bool = False) -> None:
    """Hook the keyboard, calling emit(event) for each press event. Blocks: run it in a thread.

    The pad's keys are swallowed; every other key goes on as usual. learn=True prints every key
    (from every keyboard) and swallows none."""
    import ctypes
    from ctypes import wintypes

    unknown = [n for n in keymap if n not in VK_CODES and not n.startswith("VK_")]
    if unknown:
        raise SystemExit(f"keypad: no Windows key for {unknown}; `uv run voice/keypad.py --learn` names the pad's keys")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    user32.SetTimer.argtypes = (wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p)
    user32.SetTimer.restype = ctypes.c_size_t
    user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    WH_KEYBOARD_LL, HC_ACTION, LLKHF_UP = 13, 0, 0x80

    pad = PadKeys(keymap, emit)

    @HOOKPROC
    def on_key(code: int, wparam: int, lparam: int) -> int:
        # Windows drops a hook that takes too long (~1 s): emit must return fast (it only queues)
        if code == HC_ACTION:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            name, down = vk_name(kb.vkCode), not kb.flags & LLKHF_UP
            if learn:
                print(f"  {name}  {'down' if down else 'up'}", flush=True)
            elif pad.edge([name], down, time.monotonic()):
                return 1  # the pad's key: it must not type into the focused window
        return user32.CallNextHookEx(None, code, wparam, lparam)

    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, on_key, kernel32.GetModuleHandleW(None), 0)
    if not hook:
        raise SystemExit(f"keypad: couldn't hook the keyboard (error {ctypes.get_last_error()})")
    user32.SetTimer(None, 0, 50, None)  # a WM_TIMER every 50 ms, so the 2 s hold is noticed while held
    print(f"keypad: Windows keyboard hook, keys {keymap}", file=sys.stderr, flush=True)
    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:  # the hook runs inside this loop
            pad.tick(time.monotonic())
    finally:
        user32.UnhookWindowsHookEx(hook)


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
        if sys.platform == "win32":
            target = lambda: run_pad_windows(emit, keymap=keymap)  # noqa: E731
        else:
            target = lambda: run_pad(emit, want=os.environ.get("PILLOW_KEYPAD"), keymap=keymap)  # noqa: E731
    thread = threading.Thread(target=target, name="keypad", daemon=True)
    thread.start()
    return thread


def learn() -> None:
    """List input devices, then print every key event of the chosen one (Ctrl+C to stop)."""
    if sys.platform == "win32":
        print("printing every key from every keyboard: press each key on the pad (Ctrl+C to stop)", flush=True)
        run_pad_windows(lambda _event: None, keymap={}, learn=True)
        return
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
