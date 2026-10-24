# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "numpy>=1.26", "sounddevice>=0.4"]
# ///
"""Pillow voice on the base laptop: Cartesia Sonic speaks, Cartesia Ink transcribes.

Plain REST (docs.cartesia.ai/calhacks, API version 2026-08-14). The agents decide what to say;
this module only turns text into speech and speech into text.

    export CARTESIA_API_KEY=sk_car_...          # never commit it
    uv run voice/voice.py                      # one check-in round trip: ask, listen, print
    uv run voice/voice.py --say "Light's on, take your time."
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import wave

import httpx
import numpy as np
import sounddevice as sd

API = "https://api.cartesia.ai"
VERSION = "2026-08-14"
TTS_MODEL = "sonic-3.6"
STT_MODEL = "ink-whisper"
# Gemma, en-GB, a stable voice Cartesia recommends for agents. Swap after a listen test.
VOICE_ID = os.environ.get("PILLOW_VOICE_ID", "62ae83ad-4f6a-430b-af41-a9bede9286ca")
TTS_RATE = 24_000
MIC_RATE = 16_000


def _headers() -> dict[str, str]:
    key = os.environ.get("CARTESIA_API_KEY", "").strip()
    if not key:
        sys.exit("CARTESIA_API_KEY is not set (play.cartesia.ai/keys). Never commit it.")
    return {"Authorization": f"Bearer {key}", "Cartesia-Version": VERSION}


def speak(text: str, *, speed: float = 0.85, emotion: str = "calm") -> None:
    """Say `text` through the laptop speaker and block until it finishes.

    Slower than default and calm: the listener is likely older and just woken up.
    """
    body = {
        "model_id": TTS_MODEL,
        "transcript": text,
        "voice": {"id": VOICE_ID},
        "language": "en",
        "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": TTS_RATE},
        "generation_config": {"speed": speed, "emotion": emotion},
    }
    r = httpx.post(f"{API}/tts/bytes", headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    sd.play(np.frombuffer(r.content, dtype=np.int16), TTS_RATE)
    sd.wait()


def listen(seconds: float = 6.0) -> str:
    """Record from the laptop mic for `seconds` and return the transcript ("" if silent)."""
    audio = sd.rec(int(seconds * MIC_RATE), samplerate=MIC_RATE, channels=1, dtype="int16")
    sd.wait()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MIC_RATE)
        w.writeframes(audio.tobytes())
    r = httpx.post(
        f"{API}/stt",
        headers=_headers(),
        data={"model": STT_MODEL, "language": "en"},
        files={"file": ("reply.wav", buf.getvalue(), "audio/wav")},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("text", "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--say", help="just speak this line and exit")
    parser.add_argument("--listen-s", type=float, default=6.0)
    args = parser.parse_args()

    if args.say:
        speak(args.say)
        return
    for attempt in (1, 2):
        speak("Are you alright?" if attempt == 1 else "I just want to check you're OK. Are you alright?")
        print(f"listening {args.listen_s:.0f} s ...", flush=True)
        reply = listen(args.listen_s)
        print(f"attempt {attempt}: {reply!r}")
        if reply:
            return
    print("no answer after 2 tries (Night Watch would escalate here)")


if __name__ == "__main__":
    main()
