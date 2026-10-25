"""Help me settle: ten minutes of quiet music through the pillow's speaker, stoppable at once.

She holds the talk key and says she can't sleep (talk.py hears a "settle" request); the pillow says
one short line and plays soft plucked notes, like a music box far away, fading to silence at the
end. The music is made here, on the laptop (no licensed track, no streaming account): a slow random
walk over a pentatonic scale, one or two notes every couple of seconds.

It goes out through voice.play in short segments, so stopping (the talk or fine key, a check-in, a
reminder) means not sending the next segment: the stop lands within one segment plus the bridge's
own tail (about 2 s). Each segment starts and ends at zero, so the small gap between PLAY requests
doesn't click. Everything here is plain code and timers; nothing listens while it plays.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator

import numpy as np

RATE = 16000  # voice.TTS_RATE: what the bridge and the laptop speaker expect
DURATION_S = 600.0  # the PRD's demo default: ten minutes
SEGMENT_S = 2.0  # one PLAY request each; also the worst-case stop latency
FADE_S = 10.0  # the last seconds fade to silence
LEVEL = 0.22  # peak, of full scale: a night-time level, well under the Guardian's cap
NOTES_HZ = (196.0, 220.0, 261.63, 293.66, 329.63, 392.0, 440.0, 523.25)  # G3 .. C5, pentatonic

SETTLE_LINE = "Okay. Here's some quiet music for ten minutes. Hold the button any time to stop it."
NO_MUSIC = "I can't play music just now, but I'm here. Hold the button if you need anything."


def _pluck(freq_hz: float, seconds: float) -> np.ndarray:
    """One soft plucked note: 30 ms attack, about a second of decay, two quiet overtones."""
    t = np.arange(int(RATE * seconds)) / RATE
    env = np.exp(-t / 1.1) * np.minimum(1.0, t / 0.03)
    wave = (np.sin(2 * np.pi * freq_hz * t)
            + 0.35 * np.sin(4 * np.pi * freq_hz * t) * np.exp(-t / 0.5)
            + 0.15 * np.sin(6 * np.pi * freq_hz * t) * np.exp(-t / 0.3))
    return wave * env


def segments(duration_s: float = DURATION_S, segment_s: float = SEGMENT_S, fade_s: float = FADE_S,
             seed: int | None = None) -> Iterator[np.ndarray]:
    """The music as 16 kHz mono int16 segments of `segment_s`, ready for voice.play one at a time."""
    rng = np.random.default_rng(seed)
    count = max(1, int(round(duration_s / segment_s)))
    length = int(RATE * segment_s)
    edge = np.linspace(0.0, 1.0, int(RATE * 0.02))  # 20 ms ramps: no click where segments join
    note = len(NOTES_HZ) // 2
    for k in range(count):
        start_s = k * segment_s
        seg = np.zeros(length)
        for j in range(1 if rng.random() < 0.7 else 2):
            note = min(max(note + int(rng.integers(-2, 3)), 0), len(NOTES_HZ) - 1)
            at = int(RATE * (0.05 + j * 0.45 * segment_s + 0.2 * rng.random()))
            pluck = _pluck(NOTES_HZ[note], segment_s) * (0.7 + 0.3 * rng.random())
            end = min(length, at + len(pluck))
            seg[at:end] += pluck[: end - at]
        seg = np.tanh(0.8 * seg)  # two notes together stay soft, never clip
        seg[: len(edge)] *= edge
        seg[-len(edge):] *= edge[::-1]
        if duration_s - start_s <= fade_s:  # the last fade_s: gain falls to zero, gently at first
            t = start_s + np.arange(length) / RATE
            seg *= np.clip((duration_s - t) / fade_s, 0.0, 1.0) ** 2
        yield (seg * LEVEL * 32767).astype(np.int16)


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

    def start(self, duration_s: float = DURATION_S, segment_s: float = SEGMENT_S, fade_s: float = FADE_S) -> None:
        self.stop()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop, duration_s, segment_s, fade_s),
                                        name="settle", daemon=True)
        self._thread.start()

    def _run(self, stop: threading.Event, duration_s: float, segment_s: float, fade_s: float) -> None:
        try:
            for part in segments(duration_s, segment_s, fade_s):
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
