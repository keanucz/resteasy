"""Help me settle: ten or twenty minutes of quiet sound through the pillow's speaker, stoppable at once.

She holds the talk key and says she can't sleep (talk.py hears a "settle" request); the pillow says
one short line and plays, fading to silence at the end:
  - "some quiet music" (default): soft plucked notes, like a music box far away, made here on the
    laptop: a slow random walk over a pentatonic scale, one or two notes every couple of seconds;
  - "rain": brown noise, lowpassed, with sparse soft drops, also generated;
  - a recorded track she names ("the flute music", "zen"): 16 kHz mono s16 WAV files in
    PILLOW_SETTLE_DIR (default ~/.cache/pillow/settle), named like mum_flute_a_16k.wav -> "flute".
    They are never in the repo; a missing dir or file falls back to the generated sounds, and the
    pillow says so rather than pretending.

It goes out through voice.play in short segments, so stopping (the talk or fine key, a check-in, a
reminder, or her head off the plate for 10 s: she got up) means not sending the next segment: the stop lands within one segment plus the bridge's
own tail (about 2 s). Each segment starts and ends at zero, so the small gap between PLAY requests
doesn't click. Everything here is plain code and timers; nothing listens while it plays.
"""

from __future__ import annotations

import functools
import os
import random
import re
import threading
import wave
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 16000  # voice.TTS_RATE: what the bridge and the laptop speaker expect
DURATION_S = 600.0  # the PRD's demo default: ten minutes
SEGMENT_S = 2.0  # one PLAY request each; also the worst-case stop latency
FADE_S = 10.0  # the last seconds fade to silence
LEVEL = 0.22  # peak, of full scale: a night-time level, well under the Guardian's cap
TRACK_GAIN = 0.6  # recorded tracks are mastered loud; keep them under the spoken lines
HEAD_OFF_S = 10.0  # head off the plate this long while the music plays = she got up, stop it
DEFAULT_LIBRARY = Path(os.environ.get("PILLOW_SETTLE_DIR", "~/.cache/pillow/settle")).expanduser()
NOTES_HZ = (196.0, 220.0, 261.63, 293.66, 329.63, 392.0, 440.0, 523.25)  # G3 .. C5, pentatonic

SETTLE_LINE = "Okay. Here's some quiet music for ten minutes. Hold the button any time to stop it."
_EDGE = np.linspace(0.0, 1.0, int(RATE * 0.02))  # 20 ms ramps: no click where segments join
NO_MUSIC = "I can't play music just now, but I'm here. Hold the button if you need anything."


def _pluck(freq_hz: float, seconds: float) -> np.ndarray:
    """One soft plucked note: 30 ms attack, about a second of decay, two quiet overtones."""
    t = np.arange(int(RATE * seconds)) / RATE
    env = np.exp(-t / 1.1) * np.minimum(1.0, t / 0.03)
    wave = (np.sin(2 * np.pi * freq_hz * t)
            + 0.35 * np.sin(4 * np.pi * freq_hz * t) * np.exp(-t / 0.5)
            + 0.15 * np.sin(6 * np.pi * freq_hz * t) * np.exp(-t / 0.3))
    return wave * env


def _finish(seg: np.ndarray, start_s: float, duration_s: float, fade_s: float, gain: float) -> np.ndarray:
    """Ramped edges, the final fade (gain falls to zero over the last fade_s, gently at first), int16."""
    seg = seg.copy()
    seg[: len(_EDGE)] *= _EDGE
    seg[-len(_EDGE):] *= _EDGE[::-1]
    t = start_s + np.arange(len(seg)) / RATE
    seg *= np.clip((duration_s - t) / fade_s, 0.0, 1.0) ** 2  # 1.0 until the fade begins
    return (np.clip(seg * gain, -1.0, 1.0) * 32767).astype(np.int16)


def _count(duration_s: float, segment_s: float) -> int:
    return max(1, int(round(duration_s / segment_s)))


def segments(duration_s: float = DURATION_S, segment_s: float = SEGMENT_S, fade_s: float = FADE_S,
             seed: int | None = None) -> Iterator[np.ndarray]:
    """The quiet music as 16 kHz mono int16 segments of `segment_s`, ready for voice.play one at a time."""
    rng = np.random.default_rng(seed)
    length = int(RATE * segment_s)
    note = len(NOTES_HZ) // 2
    for k in range(_count(duration_s, segment_s)):
        seg = np.zeros(length)
        for j in range(1 if rng.random() < 0.7 else 2):
            note = min(max(note + int(rng.integers(-2, 3)), 0), len(NOTES_HZ) - 1)
            at = int(RATE * (0.05 + j * 0.45 * segment_s + 0.2 * rng.random()))
            pluck = _pluck(NOTES_HZ[note], segment_s) * (0.7 + 0.3 * rng.random())
            end = min(length, at + len(pluck))
            seg[at:end] += pluck[: end - at]
        yield _finish(np.tanh(0.8 * seg), k * segment_s, duration_s, fade_s, LEVEL)  # two notes stay soft


def rain(duration_s: float = DURATION_S, segment_s: float = SEGMENT_S, fade_s: float = FADE_S,
         seed: int | None = None) -> Iterator[np.ndarray]:
    """Rain: brown noise through a one-pole lowpass, with a few soft drops a second. The filter state
    carries across segments, so the noise is continuous apart from the 20 ms edge ramps."""
    rng = np.random.default_rng(seed)
    length = int(RATE * segment_s)
    brown = low = 0.0
    for k in range(_count(duration_s, segment_s)):
        white = rng.standard_normal(length)
        seg = np.empty(length)
        for i in range(length):  # leaky integrator (brown), then lowpass: a soft, distant wash
            brown = 0.995 * brown + 0.02 * white[i]
            low = 0.9 * low + 0.1 * brown
            seg[i] = low
        seg *= 2.5
        for _ in range(int(rng.integers(2, 5))):  # the drops: short, quiet, high
            at = int(rng.integers(0, length - RATE // 10))
            t = np.arange(RATE // 10) / RATE
            seg[at: at + len(t)] += 0.08 * np.sin(2 * np.pi * float(rng.uniform(1800, 3200)) * t) * np.exp(-t / 0.012)
        yield _finish(np.tanh(seg), k * segment_s, duration_s, fade_s, LEVEL)


def track_segments(path: Path | str, duration_s: float = DURATION_S, segment_s: float = SEGMENT_S,
                   fade_s: float = FADE_S) -> Iterator[np.ndarray]:
    """A 16 kHz mono s16 WAV as segments, for up to `duration_s`, fading over the last `fade_s` of
    that. A track shorter than the duration ends when it ends (its tail padded to a whole segment)."""
    length = int(RATE * segment_s)
    with wave.open(str(path), "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
            raise ValueError(f"{path}: need 16 kHz mono s16, got {w.getnchannels()} ch, "
                             f"{w.getsampwidth() * 8} bit, {w.getframerate()} Hz")
        total = min(w.getnframes(), int(RATE * duration_s))
        played_s = total / RATE
        for k in range(_count(played_s, segment_s)):
            raw = w.readframes(length)
            if not raw:
                return
            seg = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32767
            if len(seg) < length:
                seg = np.concatenate([seg, np.zeros(length - len(seg))])
            yield _finish(seg, k * segment_s, played_s, fade_s, TRACK_GAIN)


# ---------- what she asked for: which sound, how long ----------


def library(directory: Path | str = DEFAULT_LIBRARY) -> dict[str, list[Path]]:
    """Recorded tracks by name: mum_flute_a_16k.wav and mum_flute_b_16k.wav -> "flute". {} if the
    directory isn't there (CI, another laptop): the generated sounds still work."""
    found: dict[str, list[Path]] = {}
    directory = Path(directory).expanduser()
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.wav")):
        name = re.sub(r"^mum_|_16k$", "", path.stem)
        name = re.sub(r"_16k$|_[a-z]$", "", name)
        found.setdefault(name, []).append(path)
    return found


@dataclass
class Plan:
    """What the pillow says, then what it starts: the line is spoken first, so the music never talks
    over it (one speaker owner at a time)."""

    line: str
    start: Callable[[], None]


def plan(player: "Player", sound: str, minutes: int, library_dir: Path | str = DEFAULT_LIBRARY) -> Plan:
    """Her request ("rain", "flute", "" ...; 20 or anything else) -> the spoken line and the music."""
    minutes = 20 if minutes == 20 else 10
    spoken_minutes = "twenty" if minutes == 20 else "ten"
    want = sound.strip().lower()
    sorry = ""
    if "rain" in want:
        source, name = rain, "some rain"
    elif want and want not in ("music", "quiet", "something quiet", "something", "company"):
        tracks = library(library_dir)
        matches = [key for key in tracks if want in key or key in want]
        if matches:
            key = matches[0]
            source = functools.partial(track_segments, random.choice(tracks[key]))
            name = f"the {key} music"
        else:
            source, name = segments, "some quiet music"
            sorry = f"I don't have the {want} tonight, so "
    else:
        source, name = segments, "some quiet music"
    body = f"here's {name} for {spoken_minutes} minutes. Hold the button any time to stop it."
    line = f"Okay. {body[0].upper()}{body[1:]}" if not sorry else f"{sorry[0].upper()}{sorry[1:]}{body}"
    return Plan(line=line, start=lambda: player.start(duration_s=minutes * 60.0, segment_s=SEGMENT_S,
                                                       fade_s=FADE_S, source=source))


class HeadOff:
    """Her head off the plate for `seconds` while the music plays means she got up: stop it, once per
    lift. An unknown reading (plate not wired, null) never fires."""

    def __init__(self, seconds: float = HEAD_OFF_S) -> None:
        self.seconds = seconds
        self._off_since: float | None = None
        self._fired = False

    def observe(self, head_on: bool | None, now: float) -> bool:
        if head_on is None or head_on:
            self._off_since, self._fired = None, False
            return False
        if self._off_since is None:
            self._off_since, self._fired = now, False
        if not self._fired and now - self._off_since >= self.seconds:
            self._fired = True
            return True
        return False


def warm_up() -> None:
    """numpy's first pass over these routines takes about 1.5 s on a laptop; the rest take 1 ms. Done
    once when the Player is made, so the music follows the spoken line without a pause."""
    for _ in segments(duration_s=0.2, segment_s=0.2, fade_s=0.1, seed=0):
        pass


class Player:
    """Plays the music on a background thread through `play` (voice.play), one segment at a time.
    `stop` is safe from any thread, including from inside `play`; `on_done` runs once per session,
    stopped or not. A speaker failure ends the session quietly: no music is never a crash."""

    def __init__(self, play: Callable[[np.ndarray], None], on_done: Callable[[], None] = lambda: None,
                 log: Callable[[str], None] = print) -> None:
        self._play, self._on_done, self._log = play, on_done, log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        warm_up()

    @property
    def playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, duration_s: float = DURATION_S, segment_s: float = SEGMENT_S, fade_s: float = FADE_S,
              source: Callable[..., Iterator[np.ndarray]] = segments) -> None:
        self.stop()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop, source, duration_s, segment_s, fade_s),
                                        name="settle", daemon=True)
        self._thread.start()

    def _run(self, stop: threading.Event, source: Callable[..., Iterator[np.ndarray]], duration_s: float,
             segment_s: float, fade_s: float) -> None:
        try:
            for part in source(duration_s=duration_s, segment_s=segment_s, fade_s=fade_s):
                if stop.is_set():
                    break
                self._play(part)
        except Exception as e:  # noqa: BLE001 - the speaker failing is "no music", never a crash
            self._log(f"settle: music stopped: {type(e).__name__}: {e}")
        finally:
            self._on_done()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> bool:
        """Wait for the current session to end; True if it has."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()
