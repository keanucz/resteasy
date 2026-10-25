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
PILLOW_SPEAKER=laptop then keeps the pillow's mic but plays through the laptop's default output.

The full check-in conversation lives in voice/checkin.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import threading
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
# Skylar, en-US, a stable voice Cartesia recommends for agents (Sonic 3.6 docs, "Voice selection"). Used
# until the family's choice arrives (checkin_client reads GET /pillows/{id}/voice and calls set_style),
# and whenever Cartesia refuses that voice (a clone deleted in the app). Jacqueline
# (9626c31c-bec5-4cca-baa8-f8ba9e84c8bc) is the en-US alternative.
FALLBACK_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"
VOICE_ID = os.environ.get("PILLOW_VOICE_ID", FALLBACK_VOICE_ID)
DEFAULT_SPEED = 0.85  # slower than Cartesia's default: she's older and may have just woken up
DEFAULT_EMOTION = "calm"
EMOTION_LANGUAGE = "en"  # Cartesia's emotions are English only
# "laptop": the laptop's speaker + mic. "pillow": the voice unit, via sim/audio_bridge.py.
AUDIO = os.environ.get("PILLOW_AUDIO", "laptop")
# Where she hears it, if not the same place: PILLOW_SPEAKER=laptop keeps the pillow's mic but plays
# through the laptop's default output, e.g. a Bluetooth speaker by the bed (the ESP32-S3 has no
# Classic Bluetooth, so it can't stream to one itself)
SPEAKER = os.environ.get("PILLOW_SPEAKER", AUDIO)
BRIDGE_HOST, _, BRIDGE_PORT = os.environ.get("PILLOW_AUDIO_BRIDGE", "127.0.0.1:8765").rpartition(":")
MIC_RATE = 16_000
# 16 kHz everywhere: the voice unit plays nothing else, and settle.py's music is 16 kHz too
TTS_RATE = MIC_RATE
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


@dataclass(frozen=True)
class Style:
    """The voice the family chose in the app and how it speaks (GET /api/pillows/{id}/voice)."""

    voice_id: str = VOICE_ID
    language: str = "en"
    speed: float = DEFAULT_SPEED
    volume: float = 1.0
    emotion: str = DEFAULT_EMOTION
    pronunciation_dict_id: str | None = None

    @classmethod
    def from_api(cls, body: dict) -> Style:
        """The backend's PillowVoice JSON; missing or null fields keep the defaults."""
        known = {k: v for k, v in body.items() if k in cls.__dataclass_fields__ and v is not None}
        return cls(**known)


_style = Style()
_style_lock = threading.Lock()
_on_change: list = []
_refused: set[str] = set()  # voices Cartesia refused this run: don't ask again for every line


def style() -> Style:
    """The voice in use now."""
    return _style


def set_style(new: Style) -> bool:
    """Use `new` from now on; True (and every on_style_change callback runs) if anything changed."""
    global _style
    with _style_lock:
        if new == _style:
            return False
        _style = new
        _refused.discard(new.voice_id)  # picked again in the app: give it another try
    for callback in list(_on_change):
        callback(new)
    return True


def on_style_change(callback) -> None:
    """Call `callback(style)` whenever set_style changes the voice, e.g. to re-render fixed lines."""
    _on_change.append(callback)


def speak(text: str, *, speed: float | None = None, emotion: str | None = None, volume: float = 1.0) -> None:
    """Say `text` through the speaker and block until it finishes.

    Slower than default and calm: the listener is likely older and just woken up. `volume` (0.5-2.0)
    is applied here, not by Cartesia: its own control barely changes loudness because speech already
    peaks near full scale. 1.0 plays 12 dB under full scale (gentle at night), 2.0 at full scale.
    """
    play(render(text, speed=speed, emotion=emotion, volume=volume))


def _language(language: str) -> str:
    """The bare language ("en" from "en-US" or "en_GB"), as Sonic takes it."""
    return language.replace("_", "-").partition("-")[0] or "en"


def tts_body(text: str, s: Style, *, speed: float | None = None, emotion: str | None = None) -> dict:
    """The /tts/bytes request for `text` in style `s`; `speed` and `emotion` override hers."""
    language = _language(s.language)
    config: dict = {"speed": s.speed if speed is None else speed}
    if language == EMOTION_LANGUAGE:
        config["emotion"] = s.emotion if emotion is None else emotion
    body = {
        "model_id": TTS_MODEL,
        "transcript": text,
        "voice": {"id": s.voice_id},
        "language": language,
        "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": TTS_RATE},
        "generation_config": config,
    }
    if s.pronunciation_dict_id:
        body["pronunciation_dict_id"] = s.pronunciation_dict_id
    return body


def gain_for(volume: float, style_volume: float = 1.0) -> float:
    """Linear gain for a line at `volume` (the caller's step, e.g. a louder second ask) scaled by the
    volume the family set: 1.0 -> -12 dB, 2.0 -> full scale, clamped to 0.5-2.0."""
    v = min(max(volume * style_volume, 0.5), 2.0)
    return 10 ** ((v - 2.0) * 12 / 20)


def render(text: str, *, speed: float | None = None, emotion: str | None = None, volume: float = 1.0) -> np.ndarray:
    """`text` as speech samples, ready for `play`: fixed lines can be rendered once at start-up and
    played instantly later (a Cartesia round trip is about a second).

    Spoken in the family's chosen voice. If Cartesia refuses it (a clone deleted in the app, a bad
    dictionary), the line is spoken in Skylar instead: she must never miss a line over the voice."""
    s = _style
    headers = {"Authorization": f"Bearer {_key()}", "Cartesia-Version": VERSION}
    if s.voice_id in _refused:
        s = Style(voice_id=FALLBACK_VOICE_ID, speed=s.speed, volume=s.volume, emotion=s.emotion)
    r = httpx.post(f"{API}/tts/bytes", headers=headers, json=tts_body(text, s, speed=speed, emotion=emotion),
                   timeout=30)
    if r.status_code in (400, 404, 422) and s.voice_id != FALLBACK_VOICE_ID:
        print(f"[voice] Cartesia refused voice {s.voice_id} ({r.status_code}: {r.text[:120]}); "
              "speaking in Skylar until the app picks another", file=sys.stderr, flush=True)
        _refused.add(s.voice_id)
        s = Style(voice_id=FALLBACK_VOICE_ID, speed=s.speed, volume=s.volume, emotion=s.emotion)
        r = httpx.post(f"{API}/tts/bytes", headers=headers, json=tts_body(text, s, speed=speed, emotion=emotion),
                       timeout=30)
    r.raise_for_status()
    return (np.frombuffer(r.content, dtype=np.int16) * gain_for(volume, s.volume)).astype(np.int16)


def tone(freq_hz: float = 660.0, ms: int = 160, volume: float = 0.15) -> np.ndarray:
    """A soft beep, made locally (no network): instant feedback that a key press was heard."""
    t = np.arange(int(TTS_RATE * ms / 1000)) / TTS_RATE
    fade = np.minimum(1.0, np.minimum(t, t[-1] - t) / 0.02)  # 20 ms fade in and out: no click
    return (np.sin(2 * np.pi * freq_hz * t) * fade * volume * 32767).astype(np.int16)


def play(audio: np.ndarray) -> None:
    """Play samples from `render` or `tone` and block until they finish."""
    if SPEAKER == "pillow":
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
    audio: AsyncIterator[bytes], *, no_answer_s: float, max_s: float, debug: bool = False,
    turn: dict | None = None, listen_from: threading.Event | None = None,
) -> Reply:
    """Stream `audio` to Ink-2 and return her first complete turn.

    `audio` must keep producing frames (silence included): the server waits for audio rather than
    assuming silence, so a turn only ends while frames keep arriving. `turn` overrides the turn
    settings (default: the Patient profile, `TURN`). With `listen_from`, the socket can be opened
    early (while she holds the talk key) and `no_answer_s` only starts counting once it is set.
    """
    params = urlencode({"model": STT_MODEL, "encoding": "pcm_s16le", "sample_rate": MIC_RATE,
                        "cartesia_version": VERSION, **(turn or TURN)})
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
                waiting = listen_from is not None and not listen_from.is_set() and not started
                if waiting:
                    deadline = loop.time() + no_answer_s  # the clock starts when we go live
                try:
                    timeout = 0.1 if waiting else max(0.0, deadline - loop.time())
                    msg = await asyncio.wait_for(ws.recv(), timeout)
                except TimeoutError:
                    if waiting:
                        continue
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
