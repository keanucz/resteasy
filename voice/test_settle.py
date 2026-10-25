"""Help me settle: calm music through the pillow's speaker, stoppable at once. No audio device, no
Cartesia, no Claude.  uv run --with pytest --with numpy pytest voice/test_settle.py"""

import threading
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

import settle
from judge import keyword_confirm_judge
from talk import Request, TalkSession, Voice, valid

RATE = 16000


def test_segments_are_16k_int16_and_cover_the_duration():
    parts = list(settle.segments(duration_s=6.0, segment_s=2.0, fade_s=1.0))
    assert len(parts) == 3
    assert all(p.dtype == np.int16 and len(p) == 2 * RATE for p in parts)


def test_music_is_quiet_and_fades_to_silence():
    parts = list(settle.segments(duration_s=20.0, segment_s=2.0, fade_s=10.0, seed=1))
    peaks = [int(np.abs(p.astype(np.int32)).max()) for p in parts]
    assert max(peaks) <= 0.35 * 32767  # a night-time level, never full scale
    assert peaks[0] > 500  # it is actually making a sound
    assert peaks[-1] < 0.15 * max(peaks)  # the last seconds are nearly silent


def test_each_segment_starts_and_ends_near_zero():
    """Segments are sent one PLAY at a time with a short gap between them: no clicks at the joins."""
    for p in settle.segments(duration_s=6.0, segment_s=2.0, fade_s=1.0, seed=2):
        assert abs(int(p[0])) < 400 and abs(int(p[-1])) < 400


class Played:
    def __init__(self, stop_after: int | None = None, fail: bool = False) -> None:
        self.parts, self.stop_after, self.fail = [], stop_after, fail
        self.player = None

    def __call__(self, audio: np.ndarray) -> None:
        if self.fail:
            raise RuntimeError("audio bridge: no answer")
        self.parts.append(audio)
        if self.stop_after is not None and len(self.parts) == self.stop_after:
            self.player.stop()  # the key pressed while this segment is on the speaker


def run(player: settle.Player, **kw) -> None:
    player.start(**kw)
    assert player.join(timeout=5.0), "the player did not finish"


def test_plays_every_segment_then_reports_done():
    played, done = Played(), threading.Event()
    player = settle.Player(played, on_done=done.set)
    played.player = player
    run(player, duration_s=6.0, segment_s=2.0, fade_s=1.0)
    assert len(played.parts) == 3
    assert done.is_set() and not player.playing


def test_stop_takes_effect_before_the_next_segment():
    played = Played(stop_after=2)
    player = settle.Player(played, on_done=lambda: None)
    played.player = player
    run(player, duration_s=60.0, segment_s=2.0, fade_s=10.0)
    assert len(played.parts) == 2  # nothing more was sent after the key
    assert not player.playing


def test_a_broken_speaker_ends_the_session_quietly():
    played, done = Played(fail=True), threading.Event()
    log = []
    player = settle.Player(played, on_done=done.set, log=log.append)
    played.player = player
    run(player, duration_s=6.0, segment_s=2.0, fade_s=1.0)
    assert done.is_set() and not player.playing
    assert any("audio bridge" in m for m in log)


def test_stop_when_nothing_is_playing_is_harmless():
    player = settle.Player(lambda a: None, on_done=lambda: None)
    player.stop()
    assert not player.playing


# ---------- the talk key: "I can't sleep" ----------


def voice_with(said: list, intent: Request, started: list) -> Voice:
    return Voice(say=said.append, beep=lambda: None, got_it=lambda: None,
                 listen=lambda **kw: SimpleNamespace(text="", spoke=False),
                 intent=lambda text, now: intent, confirm=keyword_confirm_judge,
                 pillow=None, on_distress=lambda r: None, log=lambda m: None,
                 settle=lambda: started.append(1))


def test_valid_accepts_a_settle_request():
    assert valid(Request("settle"))


def test_she_cant_sleep_starts_the_music_after_one_short_line():
    said, started = [], []
    TalkSession(voice_with(said, Request("settle"), started), None, ZoneInfo("America/Los_Angeles")) \
        .handle("I can't sleep, can you play something quiet")
    assert said == [settle.SETTLE_LINE]
    assert started == [1]


def test_no_speaker_path_says_so_instead_of_pretending():
    said = []
    v = voice_with(said, Request("settle"), [])
    v.settle = None
    TalkSession(v, None, ZoneInfo("America/Los_Angeles")).handle("play some music")
    assert said == [settle.NO_MUSIC]
