"""The family's voice reaching the pillow's speech, with Cartesia faked.  uv run --with pytest pytest voice"""

import sys
import types

import numpy as np
import pytest

sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))  # no audio device in CI
import voice  # noqa: E402

CLONE = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def fresh_voice(monkeypatch):
    """Each test starts in Skylar with no callbacks and no refused voices."""
    monkeypatch.setenv("CARTESIA_API_KEY", "test-key")
    monkeypatch.setattr(voice, "_style", voice.Style(voice_id=voice.FALLBACK_VOICE_ID))
    monkeypatch.setattr(voice, "_on_change", [])
    monkeypatch.setattr(voice, "_refused", set())


class FakeCartesia:
    """Stands in for httpx.post to /tts/bytes: records each body, refuses the voices in `refuse`."""

    def __init__(self, refuse=()):
        self.bodies, self.refuse = [], set(refuse)

    def __call__(self, url, *, headers, json, timeout):
        self.bodies.append(json)
        status = 404 if json["voice"]["id"] in self.refuse else 200
        return types.SimpleNamespace(
            status_code=status, text="voice not found", content=np.full(160, 1000, np.int16).tobytes(),
            raise_for_status=lambda: None)


def test_style_from_the_backend_json_keeps_defaults_for_nulls():
    s = voice.Style.from_api({"voice_id": CLONE, "language": "en-US", "speed": 1.1, "volume": 1.5,
                              "emotion": "content", "pronunciation_dict_id": None, "extra": 1})
    assert (s.voice_id, s.language, s.speed, s.volume, s.emotion) == (CLONE, "en-US", 1.1, 1.5, "content")
    assert s.pronunciation_dict_id is None


def test_render_speaks_in_the_chosen_voice_and_style(monkeypatch):
    cartesia = FakeCartesia()
    monkeypatch.setattr(voice.httpx, "post", cartesia)
    voice.set_style(voice.Style(voice_id=CLONE, language="en-GB", speed=1.1, emotion="content",
                                pronunciation_dict_id="pd_1"))
    voice.render("Time for your tablets.")
    body = cartesia.bodies[-1]
    assert body["voice"] == {"id": CLONE}
    assert body["language"] == "en"
    assert body["generation_config"] == {"speed": 1.1, "emotion": "content"}
    assert body["pronunciation_dict_id"] == "pd_1"
    assert body["output_format"]["sample_rate"] == voice.TTS_RATE


def test_a_caller_can_still_override_speed_and_emotion(monkeypatch):
    cartesia = FakeCartesia()
    monkeypatch.setattr(voice.httpx, "post", cartesia)
    voice.render("Are you alright?", speed=0.7, emotion="sympathetic")
    assert cartesia.bodies[-1]["generation_config"] == {"speed": 0.7, "emotion": "sympathetic"}


def test_no_emotion_outside_english(monkeypatch):
    cartesia = FakeCartesia()
    monkeypatch.setattr(voice.httpx, "post", cartesia)
    voice.set_style(voice.Style(voice_id=CLONE, language="fr"))
    voice.render("Bonne nuit.")
    assert "emotion" not in cartesia.bodies[-1]["generation_config"]


def test_a_refused_clone_falls_back_to_skylar_and_is_not_asked_again(monkeypatch):
    cartesia = FakeCartesia(refuse={CLONE})
    monkeypatch.setattr(voice.httpx, "post", cartesia)
    voice.set_style(voice.Style(voice_id=CLONE))
    assert len(voice.render("Are you alright?")) == 160
    assert [b["voice"]["id"] for b in cartesia.bodies] == [CLONE, voice.FALLBACK_VOICE_ID]
    voice.render("Goodnight.")
    assert cartesia.bodies[-1]["voice"]["id"] == voice.FALLBACK_VOICE_ID
    assert len(cartesia.bodies) == 3


def test_picking_the_voice_again_in_the_app_retries_it(monkeypatch):
    voice._refused.add(CLONE)
    voice.set_style(voice.Style(voice_id=CLONE))
    assert CLONE not in voice._refused


def test_set_style_tells_listeners_only_on_a_change():
    seen = []
    voice.on_style_change(seen.append)
    new = voice.Style(voice_id=CLONE)
    assert voice.set_style(new) is True
    assert voice.set_style(voice.Style(voice_id=CLONE)) is False
    assert seen == [new]


def test_volume_is_her_setting_times_the_step():
    assert voice.gain_for(1.0) == pytest.approx(10 ** (-12 / 20))
    assert voice.gain_for(1.0, 2.0) == pytest.approx(1.0)
    assert voice.gain_for(2.0, 1.5) == pytest.approx(1.0)  # clamped at full scale
    assert voice.gain_for(0.1) == pytest.approx(10 ** (-18 / 20))  # never below 0.5
