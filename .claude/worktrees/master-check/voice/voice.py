# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "numpy>=1.26", "sounddevice>=0.4", "websockets>=14"]
# ///
"""Pillow voice on the base laptop: Cartesia Sonic speaks, Cartesia Ink-2 listens.

docs.cartesia.ai/calhacks, API version 2026-08-14. The agents decide what to say; this module only
turns text into speech and speech into text.

Listening streams the mic to Ink-2's turn-detection socket, so a reply ends when she has finished
talking (not after a fixed window): a quick "I'm fine" returns at once, a slow sleepy answer is not
cut off, and silence is recognised as no answer.

    export CARTESIA_API_KEY=sk_car_...          # never commit it
    uv run voice/voice.py --say "Light's on, take your time."
    uv run voice/voice.py --debug              # listen once, print the reply + mic level and events

Audio goes through the laptop's own speaker and mic by default. PILLOW_AUDIO=pillow uses the voice
unit inside the pillow instead (firmware/voice_unit, reached through sim/audio_bridge.py).

The full check-in conversation lives in voice/checkin.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import numpy as np
import sounddevice as sd
import websockets

API = "https://api.cartesia.ai"
STT_WS = "wss://api.cartesia.ai/stt/turns/websocket"
VERSION = "2026-08-14"
TTS_MODEL = "sonic-3.6"
STT_MODEL = "ink-2"
# Skylar, en-US, a stable voice Cartesia recommends for agents (Sonic 3.6 docs, "Voice selection"); a
# placeholder, we're in SF. Jacqueline (9626c31c-bec5-4cca-baa8-f8ba9e84c8bc) is the en-US fallback.
# TODO(app): let the owner pick her voice in the family app. `residents.voice_id` already exists (still
# defaulting to Gemma, en-GB) but nothing reads it yet: pass it here per pillow instead of this constant.
VOICE_ID = os.environ.get("PILLOW_VOICE_ID", "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4")
# "laptop": the laptop's speaker + mic. "pillow": the voice unit, via sim/audio_bridge.py.
AUDIO = os.environ.get("PILLOW_AUDIO", "laptop")
BRIDGE_HOST, _, BRIDGE_PORT = os.environ.get("PILLOW_AUDIO_BRIDGE", "127.0.0.1:8765").rpartition(":")
MIC_RATE = 16_000
TTS_RATE = MIC_RATE if AUDIO == "pillow" else 24_000  # the voice unit plays 16 kHz only
CHUNK = MIC_RATE // 10  # 100 ms of audio per frame, as the docs recommend
# Cartesia's "Patient" turn profile: tolerates pauses mid-sentence from someone half asleep.
TURN = {
    "turn_start_threshold": 0.8,
    "turn_eager_end_threshold": 0.3,
    "turn_end_threshold": 0.1,
    "turn_end_timeout_ms": 8000,
}


def _key() -> str:
    key = os.environ.get("CARTESIA_API_KEY", "").strip()
    if not key:
        sys.exit("CARTESIA_API_KEY is not set (play.cartesia.ai/keys). Never commit it.")
    return key


def speak(text: str, *, speed: float = 0.85, emotion: str = "calm", volume: float = 1.0) -> None:
    """Say `text` through the laptop speaker and block until it finishes.

    Slower than default and calm: the listener is likely older and just woken up. `volume` (0.5-2.0)
    is applied here, not by Cartesia: its own control barely changes loudness because speech already
    peaks near full scale. 1.0 plays 12 dB under full scale (gentle at night), 2.0 at full scale.
    """
    body = {
        "model_id": TTS_MODEL,
        "transcript": text,
        "voice": {"id": VOICE_ID},
        "language": "en",
        "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": TTS_RATE},
        "generation_config": {"speed": speed, "emotion": emotion},
    }
    headers = {"Authorization": f"Bearer {_key()}", "Cartesia-Version": VERSION}
    r = httpx.post(f"{API}/tts/bytes", headers=headers, json=body, timeout=30)
    r.raise_for_status()
    gain = 10 ** ((min(max(volume, 0.5), 2.0) - 2.0) * 12 / 20)  # 1.0 -> -12 dB, 2.0 -> 0 dB
    audio = (np.frombuffer(r.content, dtype=np.int16) * gain).astype(np.int16)
    if AUDIO == "pillow":
        _play_on_pillow(audio.tobytes())
        return
    sd.play(audio, TTS_RATE)
    sd.wait()


def _play_on_pillow(pcm: bytes) -> None:
    """Send speech to the voice unit through the audio bridge and block until it has played."""
    with socket.create_connection((BRIDGE_HOST, int(BRIDGE_PORT)), timeout=5) as conn:
        conn.sendall(b"PLAY\n" + pcm)
        conn.shutdown(socket.SHUT_WR)
        conn.settimeout(len(pcm) / (TTS_RATE * 2) + 10)
        answer = conn.makefile("rb").readline().strip()
    if answer != b"DONE":
        raise RuntimeError(f"audio bridge: {answer.decode(errors='replace') or 'no answer'}")


async def _mic() -> AsyncIterator[bytes]:
    """Yield 100 ms frames of 16 kHz mono s16le from the default mic, forever."""
    if AUDIO == "pillow":
        async for frame in _pillow_mic():
            yield frame
        return
    loop = asyncio.get_running_loop()
    frames: asyncio.Queue[bytes] = asyncio.Queue()

    def on_audio(data, _frames, _time, _status) -> None:
        loop.call_soon_threadsafe(frames.put_nowait, bytes(data))

    with sd.RawInputStream(samplerate=MIC_RATE, channels=1, dtype="int16", blocksize=CHUNK, callback=on_audio):
        while True:
            yield await frames.get()


async def _pillow_mic() -> AsyncIterator[bytes]:
    """The voice unit's mic, through the audio bridge, in the same 100 ms frames."""
    reader, writer = await asyncio.open_connection(BRIDGE_HOST, int(BRIDGE_PORT))
    try:
        writer.write(b"LISTEN\n")
        await writer.drain()
        while True:
            yield await reader.readexactly(CHUNK * 2)
    finally:
        writer.close()


@dataclass
class Reply:
    """One reply. `spoke` without `text` means she said something we couldn't make out (a mumble,
    a groan): not the same as silence, and worth treating as a possible problem."""

    text: str
    spoke: bool


async def transcribe_turn(
    audio: AsyncIterator[bytes], *, no_answer_s: float, max_s: float, debug: bool = False
) -> Reply:
    """Stream `audio` to Ink-2 and return her first complete turn.

    `audio` must keep producing frames (silence included): the server waits for audio rather than
    assuming silence, so a turn only ends while frames keep arriving.
    """
    params = urlencode({"model": STT_MODEL, "encoding": "pcm_s16le", "sample_rate": MIC_RATE,
                        "cartesia_version": VERSION, **TURN})
    async with websockets.connect(f"{STT_WS}?{params}", additional_headers={"X-API-Key": _key()}) as ws:

        async def send() -> None:
            peak, n = 0.0, 0
            async for frame in audio:
                await ws.send(frame)
                if debug:  # mic level once a second: is a mumble even reaching the mic?
                    rms = float(np.sqrt(np.mean(np.frombuffer(frame, dtype=np.int16).astype(np.float32) ** 2)))
                    peak, n = max(peak, rms), n + 1
                    if n == 10:
                        print(f"  mic peak {20 * np.log10(max(peak, 1) / 32768):6.1f} dBFS", file=sys.stderr)
                        peak, n = 0.0, 0

        async def receive() -> Reply:
            heard = ""  # latest cumulative text, returned if we hit max_s mid-turn
            started = False
            loop = asyncio.get_running_loop()
            deadline = loop.time() + no_answer_s
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), max(0.0, deadline - loop.time()))
                except TimeoutError:
                    return Reply(heard.strip(), started)
                event = json.loads(msg)
                kind = event["type"]
                if debug:
                    print(f"  {kind} {event.get('transcript', '')!r}", file=sys.stderr)
                if kind == "error":
                    raise RuntimeError(f"Cartesia STT: {event.get('title')}: {event.get('message')}")
                if kind == "turn.start" and not started:
                    started = True
                    deadline = loop.time() + max_s
                elif kind in ("turn.update", "turn.eager_end"):
                    heard = event.get("transcript", heard)
                elif kind == "turn.end":
                    return Reply(event.get("transcript", "").strip(), True)

        sender = asyncio.create_task(send())
        try:
            return await receive()
        finally:
            sender.cancel()


def listen(*, no_answer_s: float = 8.0, max_s: float = 30.0, debug: bool = False) -> Reply:
    """Listen on the laptop mic until she finishes one reply, or `no_answer_s` of silence."""
    return asyncio.run(transcribe_turn(_mic(), no_answer_s=no_answer_s, max_s=max_s, debug=debug))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--say", help="just speak this line and exit")
    parser.add_argument("--no-answer-s", type=float, default=8.0, help="silence before counting it as no answer")
    parser.add_argument("--debug", action="store_true", help="print mic level and Cartesia turn events")
    args = parser.parse_args()

    if args.say:
        speak(args.say)
        return
    print(f"listening once (no answer after {args.no_answer_s:.0f} s of silence) ...", flush=True)
    print(listen(no_answer_s=args.no_answer_s, debug=args.debug))


if __name__ == "__main__":
    main()
