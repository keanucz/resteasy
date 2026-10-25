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
    def plan(sound: str, minutes: int):
        return SimpleNamespace(line=f"line for {sound or 'music'} {minutes}",
                               start=lambda: started.append((sound, minutes, len(said))))

    return Voice(say=said.append, beep=lambda: None, got_it=lambda: None,
                 listen=lambda **kw: SimpleNamespace(text="", spoke=False),
                 intent=lambda text, now: intent, confirm=keyword_confirm_judge,
                 pillow=None, on_distress=lambda r: None, log=lambda m: None, settle=plan)


def test_valid_accepts_a_settle_request():
    assert valid(Request("settle"))
    assert valid(Request("settle", sound="rain", minutes=20))


def test_she_cant_sleep_starts_the_music_after_one_short_line():
    said, started = [], []
    TalkSession(voice_with(said, Request("settle", sound="rain", minutes=20), started), None,
                ZoneInfo("America/Los_Angeles")).handle("I can't sleep, can I have the rain for twenty minutes")
    assert said == ["line for rain 20"]
    assert started == [("rain", 20, 1)]  # the music starts after the line has been said, not during


def test_no_speaker_path_says_so_instead_of_pretending():
    said = []
    v = voice_with(said, Request("settle"), [])
    v.settle = None
    TalkSession(v, None, ZoneInfo("America/Los_Angeles")).handle("play some music")
    assert said == [settle.NO_MUSIC]


# ---------- rain, recorded tracks, the plan, and head off the plate ----------

import wave
from pathlib import Path


def write_wav(path: Path, seconds: float, freq: float = 220.0) -> None:
    t = np.arange(int(RATE * seconds)) / RATE
    pcm = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def test_rain_segments_are_quiet_seamless_and_fade_out():
    parts = list(settle.rain(duration_s=20.0, segment_s=2.0, fade_s=10.0, seed=3))
    assert len(parts) == 10 and all(p.dtype == np.int16 and len(p) == 2 * RATE for p in parts)
    peaks = [int(np.abs(p.astype(np.int32)).max()) for p in parts]
    assert 500 < max(peaks) <= 0.35 * 32767
    assert peaks[-1] < 0.15 * max(peaks)
    assert all(abs(int(p[0])) < 400 and abs(int(p[-1])) < 400 for p in parts)


def test_a_track_is_streamed_in_segments_and_fades_at_the_end(tmp_path):
    write_wav(tmp_path / "zen_16k.wav", 6.0)
    parts = list(settle.track_segments(tmp_path / "zen_16k.wav", duration_s=4.0, segment_s=2.0, fade_s=1.0))
    assert len(parts) == 2 and all(p.dtype == np.int16 and len(p) == 2 * RATE for p in parts)
    assert abs(int(parts[0][0])) < 400 and abs(int(parts[1][-1])) < 400  # ramped joins, silent end
    assert int(np.abs(parts[1][-RATE // 4:].astype(np.int32)).max()) < int(np.abs(parts[0].astype(np.int32)).max()) / 4


def test_a_short_track_ends_with_the_track(tmp_path):
    write_wav(tmp_path / "short_16k.wav", 3.0)
    parts = list(settle.track_segments(tmp_path / "short_16k.wav", duration_s=20.0, segment_s=2.0, fade_s=1.0))
    assert len(parts) == 2 and len(parts[1]) == 2 * RATE  # the tail is padded to a whole segment


def test_library_names_tracks_from_their_filenames(tmp_path):
    for name in ("mum_flute_a_16k.wav", "mum_flute_b_16k.wav", "zen_16k.wav", "notes.txt"):
        (tmp_path / name).write_bytes(b"")
    lib = settle.library(tmp_path)
    assert set(lib) == {"flute", "zen"}
    assert len(lib["flute"]) == 2 and len(lib["zen"]) == 1


def test_library_of_a_missing_dir_is_empty(tmp_path):
    assert settle.library(tmp_path / "nowhere") == {}


class FakePlayer:
    def __init__(self) -> None:
        self.started = None

    def start(self, **kw) -> None:
        self.started = kw


def test_plan_defaults_to_ten_minutes_of_quiet_music(tmp_path):
    player = FakePlayer()
    plan = settle.plan(player, "", 0, library_dir=tmp_path)
    assert plan.line == settle.SETTLE_LINE
    plan.start()
    assert player.started["duration_s"] == 600.0 and player.started["source"] is settle.segments


def test_plan_gives_rain_for_twenty_minutes_when_asked(tmp_path):
    player = FakePlayer()
    plan = settle.plan(player, "rain", 20, library_dir=tmp_path)
    assert "rain" in plan.line and "twenty minutes" in plan.line
    plan.start()
    assert player.started["duration_s"] == 1200.0 and player.started["source"] is settle.rain


def test_plan_plays_a_named_track_when_it_exists(tmp_path):
    write_wav(tmp_path / "mum_flute_a_16k.wav", 3.0)
    player = FakePlayer()
    plan = settle.plan(player, "flute", 0, library_dir=tmp_path)
    assert "flute" in plan.line and "ten minutes" in plan.line
    plan.start()
    first = next(player.started["source"](duration_s=2.0, segment_s=2.0, fade_s=1.0))
    assert first.dtype == np.int16 and len(first) == 2 * RATE


def test_plan_says_so_and_falls_back_when_the_track_is_missing(tmp_path):
    player = FakePlayer()
    plan = settle.plan(player, "flute", 0, library_dir=tmp_path)
    assert "flute" in plan.line and "quiet music" in plan.line  # no pretending she gets the flute
    plan.start()
    assert player.started["source"] is settle.segments


def test_head_off_the_plate_for_ten_seconds_fires_once():
    off = settle.HeadOff(seconds=10.0)
    assert not off.observe(True, 0.0)
    assert not off.observe(False, 1.0)
    assert not off.observe(False, 10.5)
    assert off.observe(False, 11.5)
    assert not off.observe(False, 12.0)  # fires once per lift
    assert not off.observe(True, 13.0)
    assert not off.observe(False, 14.0)
    assert off.observe(False, 24.5)  # a new lift fires again


def test_an_unwired_plate_never_stops_the_music():
    off = settle.HeadOff(seconds=10.0)
    assert not off.observe(None, 0.0) and not off.observe(None, 100.0)
