# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak>=0.22", "numpy>=1.26", "pyserial>=3.5"]
# ///
"""Audio bridge: the voice unit in the pillow (firmware/voice_unit) becomes a local speaker + mic.

The Waveshare ESP32-S3 streams its mic and plays speech over Bluetooth LE (default), plugged in,
USB serial, or over the laptop's Wi-Fi hotspot (TCP, the USB lines) with Bluetooth as the fallback;
firmware/voice_unit/voice_unit.ino has all three. This script holds that link and
offers it to any program on the laptop over a localhost socket, one request per connection:

  PLAY\\n + raw audio, then close the write side   play 16 kHz mono s16le; the bridge answers DONE\\n
                                                 once it has finished playing
  LISTEN\\n                                       the bridge streams raw 16 kHz mono s16le mic audio
                                                 until the client hangs up
  EVENTS\\n                                       the bridge writes "talk\\n" each time someone
                                                 squeezes the pillow

voice/voice.py uses it when PILLOW_AUDIO=pillow. Clients see the same thing over either link.

While any program listens, the bridge repeats MIC ON every 2 s: the ESP-NOW relay turns the mic
off by itself when those stop (the bridge died), instead of streaming forever.

  uv run sim/audio_bridge.py                          # Bluetooth: finds "pillow-voice"
  uv run sim/audio_bridge.py --serial /dev/ttyACM0    # USB serial instead, or the ESP-NOW relay
                                                      # (firmware/espnow_relay) on that port
  uv run sim/audio_bridge.py --hotspot 10.42.0.1:47801   # the hotspot (voice_unit PILLOW_HOTSPOT=1),
                                                      # Bluetooth while it's down
  uv run sim/audio_bridge.py --hotspot 10.42.0.1:47801 --serial /dev/ttyACM0
                                                      # hotspot, then USB if it's plugged in, then
                                                      # Bluetooth
  uv run sim/audio_bridge.py --server https://pillow.keanuc.net --pillow-id mum
                                                      # also forward the pillow's lines ("UNO {...}",
                                                      # firmware/pillow_node) as pillow state, and
                                                      # pass `buzz` and `set_light` commands on to
                                                      # the voice unit (its screen is the light)

The voice unit's IMU lines ("IMU {...}", firmware/voice_unit) fill the state's motion while the
pillow node's is null.
"""

import argparse
import asyncio
import base64
import contextlib
import json
import queue
import socket
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uno_state import imu_line_motion, uno_line_to_state  # noqa: E402

RATE = 16_000
CHUNK = RATE // 10 * 2  # 100 ms of s16le, sent to the board at a time
LEAD_S = 0.3  # how far ahead of real time to send speech: enough to ride out link jitter, well
#               under the board's 2 s buffer
BLE_NAME = "pillow-voice"
BLE_SCAN_S = 10
BLE_CALL_TIMEOUT_S = 5
# GATT UUIDs: shared with firmware/voice_unit/voice_unit.ino
MIC_UUID = "6e9d0002-5a1c-4c5e-9b7e-70696c6c6f77"
SPK_UUID = "6e9d0003-5a1c-4c5e-9b7e-70696c6c6f77"
CTRL_UUID = "6e9d0004-5a1c-4c5e-9b7e-70696c6c6f77"
EVENT_UUID = "6e9d0005-5a1c-4c5e-9b7e-70696c6c6f77"
HOTSPOT_SILENCE_S = 5  # the board sends a line (at least "HB") every second: 5 s of silence = dead link
IMU_FRESH_S = 3  # an IMU motion this old no longer fills the state's motion
MIC_KEEPALIVE_S = 2  # the relay gives up on the mic after 6 s without MIC ON
COMMAND_POLL_S = 0.5  # coord/CONTRACT.md 3
BUZZ_PATTERNS = ("chime", "alert")
BUZZ_REPEAT_MAX = 3
LIGHT_COLORS = ("warm", "amber", "off")
LIGHT_FADE_MAX_S = 60


def ulaw_encode(pcm: bytes) -> bytes:
    """G.711 mu-law, the same as ulawEncode() in the firmware."""
    x = np.frombuffer(pcm, "<i2").astype(np.int32)
    sign = np.where(x < 0, 0x80, 0)
    v = np.minimum(np.abs(x), 32635) + 0x84
    exponent = np.clip(np.floor(np.log2(v)).astype(np.int32) - 7, 0, 7)
    mantissa = (v >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8).tobytes()


def ulaw_decode(data: bytes) -> bytes:
    u = ~np.frombuffer(data, np.uint8).astype(np.int32) & 0xFF
    t = (((u & 0x0F) << 3) + 0x84) << ((u >> 4) & 7)
    return np.where(u & 0x80, 0x84 - t, t - 0x84).astype("<i2").tobytes()


class Board:
    """The link to the voice unit, shared by every client. Subclasses reconnect when it drops."""

    def __init__(self) -> None:
        self.subs_lock = threading.Lock()  # serialises (un)subscribing, held across MIC ON/OFF
        self.lists_lock = threading.Lock()  # guards the lists; never held while talking to the board,
        #                                     so mic audio keeps flowing while a command is in flight
        self.listeners: list[queue.Queue] = []
        self.watchers: list[queue.Queue] = []

    def command(self, cmd: str) -> None:
        """MIC ON / MIC OFF / VOL n / GAIN n / BUZZ pattern n / LIGHT pct colour fade_s. Raises OSError when the board isn't
        connected."""
        raise NotImplementedError

    def speak(self, pcm: bytes) -> None:
        """Queue up to 100 ms of 16 kHz mono s16le on the board's speaker."""
        raise NotImplementedError

    def run(self) -> None:
        raise NotImplementedError

    def subscribe(self, kind: list, q: queue.Queue) -> None:
        with self.subs_lock:
            if kind is self.listeners and not kind:
                self.command("MIC ON")
            with self.lists_lock:
                kind.append(q)

    def unsubscribe(self, kind: list, q: queue.Queue) -> None:
        with self.subs_lock:
            with self.lists_lock:
                kind.remove(q)
            if kind is self.listeners and not kind:
                try:
                    self.command("MIC OFF")
                except OSError:
                    pass

    def _mic(self, pcm: bytes) -> None:
        if self.mic_gate is not None and not self.mic_gate():
            return
        with self.lists_lock:
            for q in self.listeners:
                q.put(pcm)

    def keep_mic_alive(self) -> None:
        """Repeat MIC ON while anyone listens (see the module docstring)."""
        while True:
            time.sleep(MIC_KEEPALIVE_S)
            with self.subs_lock:
                if not self.listeners:
                    continue
                try:
                    self.command("MIC ON")
                except OSError:
                    pass  # not connected: run() sends MIC ON again on reconnect

    def _talk(self) -> None:
        print("audio_bridge: talk (pillow squeezed)", flush=True)
        with self.lists_lock:
            for q in self.watchers:
                q.put(b"talk\n")

    poster: "StatePoster | None" = None  # set by main() with --server
    link: str | None = None  # CONTRACT 1 state.link: which way the voice unit is connected
    mic_gate = None  # FailoverBoard: a callable saying whether this is the active link (its mic and state count)

    def _line(self, line: str) -> None:
        """Any other text line from the board: the Uno's state ("UNO {...}") goes to the server, the
        voice unit's IMU ("IMU {...}", twice a second) feeds it."""
        if line == "HB":  # the hotspot link's heartbeat
            return
        if line.startswith("IMU "):
            if self.poster is not None:
                self.poster.imu(line)
            return
        if self.poster is not None and line.startswith("UNO "):
            if self.mic_gate is not None and not self.mic_gate():
                return  # a late line from the link on its way out: the active one posts
            if self.poster.post(line, self.link):
                return
        print(f"board: {line}", flush=True)


class SerialBoard(Board):
    """USB serial: text lines, audio as base64 s16le."""

    link = "usb"

    def __init__(self, path: str, baud: int) -> None:
        super().__init__()
        self.path, self.baud = path, baud
        self.port = None
        self.write_lock = threading.Lock()

    def _write(self, line: str) -> None:
        with self.write_lock:
            if self.port is None:
                raise OSError("voice unit not connected")
            self.port.write(line.encode() + b"\n")

    def connected(self) -> bool:
        return self.port is not None

    def command(self, cmd: str) -> None:
        self._write(cmd)

    def speak(self, pcm: bytes) -> None:
        self._write("SPK " + base64.b64encode(pcm).decode())

    def run(self) -> None:
        import serial  # pyserial

        while True:
            try:
                self.port = serial.Serial(self.path, self.baud, timeout=1)
                print(f"audio_bridge: voice unit on {self.path}", flush=True)
                if self.listeners:
                    self.command("MIC ON")  # the board forgets after a reset
                self._read(self.port)
            except (serial.SerialException, OSError) as err:
                print(f"audio_bridge: {self.path}: {err}; retrying", file=sys.stderr, flush=True)
            self.port = None
            time.sleep(2)

    def _read(self, port) -> None:
        while True:
            line = port.readline().decode(errors="replace").strip()
            if line.startswith("MIC "):
                try:
                    self._mic(base64.b64decode(line[4:], validate=True))
                except ValueError:
                    continue
            elif line == "KEY talk":
                self._talk()
            elif line:
                self._line(line)


class _SocketPort:
    """A connected socket with the two calls SerialBoard uses on its port."""

    def __init__(self, conn: socket.socket) -> None:
        self.conn = conn
        self.reader = conn.makefile("rb")

    def readline(self) -> bytes:
        line = self.reader.readline()
        if not line:
            raise OSError("hotspot: the voice unit hung up")
        return line

    def write(self, data: bytes) -> None:
        self.conn.sendall(data)


class HotspotBoard(SerialBoard):
    """The laptop's hotspot: the voice unit dials this TCP port and speaks the USB serial lines.
    One connection at a time; a newer one (the board rebooted) replaces the old."""

    link = "hotspot"

    def __init__(self, host: str, port: int) -> None:
        super().__init__(f"{host}:{port}", 0)
        self.addr = (host, port)
        self.conn: socket.socket | None = None

    def run(self) -> None:
        while True:
            try:
                with socket.create_server(self.addr) as server:
                    print(f"audio_bridge: waiting for the voice unit on {self.path}", flush=True)
                    while True:
                        conn, peer = server.accept()
                        if self.conn is not None:
                            with contextlib.suppress(OSError):
                                self.conn.shutdown(socket.SHUT_RDWR)  # wakes the old reader
                        threading.Thread(target=self._serve, args=(conn, peer), daemon=True).start()
            except OSError as err:  # no hotspot yet: the address isn't there to bind
                print(f"audio_bridge: hotspot {self.path}: {err}; retrying", file=sys.stderr, flush=True)
                time.sleep(2)

    def _serve(self, conn: socket.socket, peer: tuple) -> None:
        with conn:
            conn.settimeout(HOTSPOT_SILENCE_S)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            port = _SocketPort(conn)
            with self.write_lock:
                self.conn, self.port = conn, port
            print(f"audio_bridge: voice unit on the hotspot from {peer[0]}", flush=True)
            try:
                if self.listeners:
                    self.command("MIC ON")  # the board forgets after a reset
                self._read(port)
            except OSError as err:
                print(f"audio_bridge: hotspot link dropped ({err})", file=sys.stderr, flush=True)
            finally:
                with self.write_lock:
                    if self.conn is conn:
                        self.conn = self.port = None


class BleBoard(Board):
    """Bluetooth LE: one GATT service, audio as 16 kHz mu-law. Runs its own asyncio loop in a thread;
    command() and speak() hand work to it from the socket threads."""

    link = "ble"

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client = None
        # True while a better link is up (FailoverBoard sets it): stay off the air, since a held
        # Bluetooth connection shares the board's radio with Wi-Fi and chops the hotspot's audio
        self.standby = lambda: False

    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    def _call(self, make_coro) -> None:
        client, loop = self.client, self.loop
        if client is None or loop is None or not client.is_connected:
            raise OSError("voice unit not connected")
        try:
            asyncio.run_coroutine_threadsafe(make_coro(client), loop).result(BLE_CALL_TIMEOUT_S)
        except Exception as err:  # bleak raises its own error types; callers expect OSError
            raise OSError(f"bluetooth: {err}") from err

    def _event(self, data: bytes) -> None:
        """EVENT notify: "talk", or a line from the Uno ("UNO ...")."""
        if data == b"talk":
            self._talk()
        else:
            self._line(data.decode(errors="replace").strip())

    def command(self, cmd: str) -> None:
        self._call(lambda c: c.write_gatt_char(CTRL_UUID, cmd.encode(), response=True))

    def speak(self, pcm: bytes) -> None:
        ulaw = ulaw_encode(pcm)

        async def send(client) -> None:
            size = client.mtu_size - 3
            for i in range(0, len(ulaw), size):
                await client.write_gatt_char(SPK_UUID, ulaw[i:i + size], response=False)

        self._call(send)

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        from bleak import BleakClient, BleakScanner
        from bleak.exc import BleakError

        self.loop = asyncio.get_running_loop()
        while True:
            if self.standby():
                await asyncio.sleep(1)
                continue
            try:
                device = await BleakScanner.find_device_by_name(self.name, timeout=BLE_SCAN_S)
                if device is None:
                    print(f"audio_bridge: no '{self.name}' in range; still looking", file=sys.stderr, flush=True)
                    continue
                gone = asyncio.Event()
                async with BleakClient(device, disconnected_callback=lambda _: gone.set()) as client:
                    if hasattr(client._backend, "_acquire_mtu"):  # BlueZ reports 23 until asked
                        await client._backend._acquire_mtu()
                    await client.start_notify(MIC_UUID, lambda _, data: self._mic(ulaw_decode(data)))
                    await client.start_notify(EVENT_UUID, lambda _, data: self._event(data))
                    self.client = client
                    print(f"audio_bridge: voice unit on bluetooth {device.address} (mtu {client.mtu_size})", flush=True)
                    if self.listeners:
                        await client.write_gatt_char(CTRL_UUID, b"MIC ON", response=True)
                    while not gone.is_set() and not self.standby():
                        with contextlib.suppress(asyncio.TimeoutError):
                            await asyncio.wait_for(gone.wait(), 1)
                    self.client = None
                if self.standby():
                    print("audio_bridge: a better link is up; bluetooth on standby", flush=True)
                    continue
                print("audio_bridge: bluetooth link dropped; reconnecting", file=sys.stderr, flush=True)
            except (BleakError, OSError, asyncio.TimeoutError) as err:
                print(f"audio_bridge: bluetooth: {err}; retrying", file=sys.stderr, flush=True)
            self.client = None
            await asyncio.sleep(2)


class FailoverBoard(Board):
    """Several links to one voice unit, best first (the hotspot, USB if given, then Bluetooth). Clients and commands
    use the first one that's connected; mic audio counts only from that one. Each MIC ON (repeated
    every 2 s while anyone listens) also turns the mic off on the others, so a switch heals itself.
    Bluetooth only connects while every better link is down (see BleBoard.standby)."""

    def __init__(self, links: list) -> None:
        super().__init__()
        self.links = links
        for link in links:  # one set of clients, whichever link carries them
            link.listeners, link.watchers, link.lists_lock = self.listeners, self.watchers, self.lists_lock
            link.mic_gate = lambda link=link: self.active() is link
        for i, link in enumerate(links[1:], 1):
            if hasattr(link, "standby"):
                link.standby = lambda better=links[:i]: any(b.connected() for b in better)

    @property
    def poster(self) -> "StatePoster | None":
        return self.links[0].poster

    @poster.setter
    def poster(self, value: "StatePoster | None") -> None:
        for link in self.links:
            link.poster = value

    def active(self) -> "Board | None":
        return next((link for link in self.links if link.connected()), None)

    def _link(self) -> Board:
        link = self.active()
        if link is None:
            raise OSError("voice unit not connected")
        return link

    def command(self, cmd: str) -> None:
        link = self._link()
        link.command(cmd)
        if cmd == "MIC ON":
            for other in self.links:
                if other is not link and other.connected():
                    with contextlib.suppress(OSError):
                        other.command("MIC OFF")

    def speak(self, pcm: bytes) -> None:
        self._link().speak(pcm)

    def run(self) -> None:
        threads = [threading.Thread(target=link.run, daemon=True) for link in self.links]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()


class StatePoster:
    """Forwards the Uno's lines to POST /api/pillows/{id}/state (coord/CONTRACT.md 1), stamping the
    laptop's time, from a worker thread so the link never waits on the network. Keeps only the
    newest line if the server is slow."""

    def __init__(self, server: str, pillow_id: str) -> None:
        self.url = f"{server.rstrip('/')}/api/pillows/{pillow_id}/state"
        self.pillow_id = pillow_id
        self.latest: queue.Queue = queue.Queue(maxsize=1)
        self.failures = 0
        self.imu_motion: float | None = None
        self.imu_at = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def imu(self, line: str) -> None:
        motion = imu_line_motion(line)
        if motion is not None:
            self.imu_motion, self.imu_at = motion, time.monotonic()

    def post(self, line: str, link: str | None = None) -> bool:
        state = uno_line_to_state(line, pillow_id=self.pillow_id, ts=round(time.time(), 2))
        if state is None:
            return False
        if link is not None:
            state["link"] = link
        if state["motion"] is None and time.monotonic() - self.imu_at < IMU_FRESH_S:
            state["motion"] = self.imu_motion  # the pillow node has no IMU: the voice unit's
        with contextlib.suppress(queue.Empty):
            self.latest.get_nowait()  # drop an unsent older one
        self.latest.put(state)
        return True

    def _run(self) -> None:
        while True:
            state = self.latest.get()
            req = urllib.request.Request(self.url, data=json.dumps(state).encode(), method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "calhacks-audio-bridge/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=5):
                    pass
                if self.failures:
                    print("audio_bridge: state posting recovered", flush=True)
                self.failures = 0
            except (urllib.error.URLError, OSError) as err:
                self.failures += 1
                if self.failures in (1, 10, 100):
                    print(f"audio_bridge: POST state failed ({err}), will keep trying", flush=True)


def play(board: Board, conn: socket.socket, first: bytes) -> None:
    audio = bytearray(first)
    while chunk := conn.recv(65536):
        audio += chunk
    start = time.monotonic()
    for i in range(0, len(audio) - 1, CHUNK):
        wait = start + i / (RATE * 2) - LEAD_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        board.speak(bytes(audio[i:i + CHUNK]))
    remaining = start + len(audio) / (RATE * 2) - time.monotonic()
    time.sleep(max(0.0, remaining) + 0.15)  # + the board's own I2S buffering
    conn.sendall(b"DONE\n")


def http_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "calhacks-audio-bridge/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def buzz_line(args: object) -> str | None:
    """A buzz command's args ({"pattern": "chime", "repeat": 1}) as the voice unit's "BUZZ chime 1",
    or None if they aren't a buzz it can play."""
    if not isinstance(args, dict) or args.get("pattern") not in BUZZ_PATTERNS:
        return None
    try:
        repeat = int(args.get("repeat", 1))
    except (TypeError, ValueError):
        repeat = 1
    return f"BUZZ {args['pattern']} {min(max(repeat, 1), BUZZ_REPEAT_MAX)}"


def _clamped_int(value: object, lo: int, hi: int) -> int:
    try:
        return min(max(int(value), lo), hi)
    except (TypeError, ValueError):
        return lo


def light_line(args: object) -> str | None:
    """A set_light command's args ({"brightness_pct": 20, "color": "warm", "fade_s": 3}) as the voice
    unit's "LIGHT 20 warm 3", or None if they aren't a light it can show. Colour "off" is dark."""
    if not isinstance(args, dict) or args.get("color", "warm") not in LIGHT_COLORS:
        return None
    color = args.get("color", "warm")
    pct = 0 if color == "off" else _clamped_int(args.get("brightness_pct", 0), 0, 100)
    return f"LIGHT {pct} {color} {_clamped_int(args.get('fade_s', 0), 0, LIGHT_FADE_MAX_S)}"


DEVICE_LINES = {"buzz": buzz_line, "set_light": light_line}  # server command -> voice unit line


def poll_commands(board: Board, server: str, pillow_id: str) -> None:
    """GET /api/pillows/{id}/commands (coord/CONTRACT.md 3) and pass `buzz` and `set_light` on to the
    voice unit, which makes the sound itself (firmware/libraries/PillowBuzz: on the pillow's buzzer,
    or its speaker) and shows the light on its screen. The other commands are for the pillow's motor,
    which nothing here drives: ignored.
    Like sim/serial_bridge.py, skips the backlog on start so a restart doesn't replay old buzzes."""
    url = f"{server.rstrip('/')}/api/pillows/{pillow_id}/commands?after="
    last_id = None
    failures = 0
    while True:
        time.sleep(COMMAND_POLL_S)
        try:
            commands = http_json(url + str(last_id or 0)) or []
            if failures:
                print("audio_bridge: command polling recovered", flush=True)
            failures = 0
        except (urllib.error.URLError, OSError, ValueError) as err:
            failures += 1
            if failures in (1, 10, 100):
                print(f"audio_bridge: GET commands failed ({err}), will keep trying", flush=True)
            continue
        if not isinstance(commands, list):
            continue
        if last_id is None:
            last_id = max((int(cmd.get("id", 0)) for cmd in commands), default=0)
            print(f"audio_bridge: skipped {len(commands)} old commands (up to id {last_id})", flush=True)
            continue
        for cmd in commands:
            last_id = max(last_id, int(cmd.get("id", 0)))
            to_line = DEVICE_LINES.get(cmd.get("cmd"))
            if to_line is None:
                continue
            line = to_line(cmd.get("args"))
            if line is None:
                print(f"audio_bridge: {cmd.get('cmd')} with bad args {cmd.get('args')!r}; skipped", flush=True)
                continue
            print(f"audio_bridge: {line}", flush=True)
            try:
                board.command(line)
            except OSError as err:
                print(f"audio_bridge: {cmd.get('cmd')}: {err}", file=sys.stderr, flush=True)


def stream(board: Board, kind: list, conn: socket.socket) -> None:
    q: queue.Queue = queue.Queue()
    board.subscribe(kind, q)
    try:
        while True:
            conn.sendall(q.get())
    except OSError:
        pass  # client hung up
    finally:
        board.unsubscribe(kind, q)


def serve(board: Board, host: str, port: int) -> None:
    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            conn: socket.socket = self.request
            data = b""
            while b"\n" not in data and len(data) < 64:
                if not (chunk := conn.recv(64)):
                    return
                data += chunk
            request, _, rest = data.partition(b"\n")
            try:
                if request == b"PLAY":
                    play(board, conn, rest)
                elif request == b"LISTEN":
                    stream(board, board.listeners, conn)
                elif request == b"EVENTS":
                    stream(board, board.watchers, conn)
                else:
                    conn.sendall(b"ERR unknown request\n")
            except OSError as err:
                print(f"audio_bridge: {request.decode(errors='replace')}: {err}", file=sys.stderr, flush=True)
                try:
                    conn.sendall(f"ERR {err}\n".encode())
                except OSError:
                    pass

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    with socketserver.ThreadingTCPServer((host, port), Handler) as server:
        print(f"audio_bridge: listening on {host}:{port}", flush=True)
        server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ble-name", default=BLE_NAME, help="the voice unit's Bluetooth name")
    parser.add_argument("--serial", metavar="PORT", help="use USB serial (e.g. /dev/ttyACM0) instead of Bluetooth; "
                        "with --hotspot, the fallback before Bluetooth")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--hotspot", metavar="HOST:PORT", help="take the voice unit over the laptop's "
                        "hotspot (e.g. 10.42.0.1:47801), with Bluetooth as the fallback")
    parser.add_argument("--listen", default="127.0.0.1:8765", help="host:port for local clients")
    parser.add_argument("--server", help="also POST the pillow's lines as state to this server and pass "
                        "its buzz commands to the voice unit")
    parser.add_argument("--pillow-id", default="mum", help="pillow id for state posts and commands")
    args = parser.parse_args()
    host, _, port = args.listen.rpartition(":")
    if args.hotspot:
        hotspot_host, _, hotspot_port = args.hotspot.rpartition(":")
        usb = [SerialBoard(args.serial, args.baud)] if args.serial else []
        board = FailoverBoard([HotspotBoard(hotspot_host, int(hotspot_port)), *usb, BleBoard(args.ble_name)])
    elif args.serial:
        board = SerialBoard(args.serial, args.baud)
    else:
        board = BleBoard(args.ble_name)
    if args.server:
        board.poster = StatePoster(args.server, args.pillow_id)
        print(f"audio_bridge: Uno lines -> {board.poster.url}", flush=True)
        threading.Thread(target=poll_commands, args=(board, args.server, args.pillow_id), daemon=True).start()
    threading.Thread(target=board.run, daemon=True).start()
    threading.Thread(target=board.keep_mic_alive, daemon=True).start()
    serve(board, host, int(port))


if __name__ == "__main__":
    main()
