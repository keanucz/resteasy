# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak>=0.22", "numpy>=1.26", "pyserial>=3.5"]
# ///
"""Audio bridge: the voice unit in the pillow (firmware/voice_unit) becomes a local speaker + mic.

The Waveshare ESP32-S3 streams its mic and plays speech over Bluetooth LE (default) or, plugged in,
USB serial; firmware/voice_unit/voice_unit.ino has both protocols. This script holds that link and
offers it to any program on the laptop over a localhost socket, one request per connection:

  PLAY\\n + raw audio, then close the write side   play 16 kHz mono s16le; the bridge answers DONE\\n
                                                 once it has finished playing
  LISTEN\\n                                       the bridge streams raw 16 kHz mono s16le mic audio
                                                 until the client hangs up
  EVENTS\\n                                       the bridge writes "talk\\n" each time someone
                                                 squeezes the pillow

voice/voice.py uses it when PILLOW_AUDIO=pillow. Clients see the same thing over either link.

  uv run sim/audio_bridge.py                          # Bluetooth: finds "pillow-voice"
  uv run sim/audio_bridge.py --serial /dev/ttyACM0    # USB serial instead
"""

import argparse
import asyncio
import base64
import queue
import socket
import socketserver
import sys
import threading
import time

import numpy as np

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
        """MIC ON / MIC OFF / VOL n / GAIN n. Raises OSError when the board isn't connected."""
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
        with self.lists_lock:
            for q in self.listeners:
                q.put(pcm)

    def _talk(self) -> None:
        print("audio_bridge: talk (pillow squeezed)", flush=True)
        with self.lists_lock:
            for q in self.watchers:
                q.put(b"talk\n")


class SerialBoard(Board):
    """USB serial: text lines, audio as base64 s16le."""

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
                self._read()
            except (serial.SerialException, OSError) as err:
                print(f"audio_bridge: {self.path}: {err}; retrying", file=sys.stderr, flush=True)
            self.port = None
            time.sleep(2)

    def _read(self) -> None:
        while True:
            line = self.port.readline().decode(errors="replace").strip()
            if line.startswith("MIC "):
                try:
                    self._mic(base64.b64decode(line[4:], validate=True))
                except ValueError:
                    continue
            elif line == "KEY talk":
                self._talk()
            elif line:
                print(f"board: {line}", flush=True)


class BleBoard(Board):
    """Bluetooth LE: one GATT service, audio as 16 kHz mu-law. Runs its own asyncio loop in a thread;
    command() and speak() hand work to it from the socket threads."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client = None

    def _call(self, make_coro) -> None:
        client, loop = self.client, self.loop
        if client is None or loop is None or not client.is_connected:
            raise OSError("voice unit not connected")
        try:
            asyncio.run_coroutine_threadsafe(make_coro(client), loop).result(BLE_CALL_TIMEOUT_S)
        except Exception as err:  # bleak raises its own error types; callers expect OSError
            raise OSError(f"bluetooth: {err}") from err

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
            try:
                device = await BleakScanner.find_device_by_name(self.name, timeout=BLE_SCAN_S)
                if device is None:
                    print(f"audio_bridge: no '{self.name}' in range; still looking", file=sys.stderr, flush=True)
                    continue
                gone = asyncio.Event()
                async with BleakClient(device, disconnected_callback=lambda _: gone.set()) as client:
                    await client.start_notify(MIC_UUID, lambda _, data: self._mic(ulaw_decode(data)))
                    await client.start_notify(EVENT_UUID, lambda _, data: data == b"talk" and self._talk())
                    self.client = client
                    print(f"audio_bridge: voice unit on bluetooth {device.address} (mtu {client.mtu_size})", flush=True)
                    if self.listeners:
                        await client.write_gatt_char(CTRL_UUID, b"MIC ON", response=True)
                    await gone.wait()
                print("audio_bridge: bluetooth link dropped; reconnecting", file=sys.stderr, flush=True)
            except (BleakError, OSError, asyncio.TimeoutError) as err:
                print(f"audio_bridge: bluetooth: {err}; retrying", file=sys.stderr, flush=True)
            self.client = None
            await asyncio.sleep(2)


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
    parser.add_argument("--serial", metavar="PORT", help="use USB serial (e.g. /dev/ttyACM0) instead of Bluetooth")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--listen", default="127.0.0.1:8765", help="host:port for local clients")
    args = parser.parse_args()
    host, _, port = args.listen.rpartition(":")
    board = SerialBoard(args.serial, args.baud) if args.serial else BleBoard(args.ble_name)
    threading.Thread(target=board.run, daemon=True).start()
    serve(board, host, int(port))


if __name__ == "__main__":
    main()
