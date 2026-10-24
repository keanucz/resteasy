"""Plain-code parts of the Morning Brief (no Droid, no network).

    uv run --with pytest --with httpx --with pydantic --with tzdata pytest droid
"""

import json

import morning_brief as mb

NIGHT = {
    "pillow_id": "mum", "resident": "Margaret",
    "window_start": "2026-10-24T18:00:00-07:00", "window_end": "2026-10-25T06:00:00-07:00",
    "summary": {"lay_down": "22:40", "asleep": "22:55", "got_up": "06:50",
                "trips": [{"left": "03:10", "back": "03:41", "min": 31}], "trip_count": 1,
                "longest_trip_min": 31,
                "checkins": 1, "escalations": 0, "acknowledged_by": [], "restless_spells": 0,
                "unusual": ["a 31-minute trip at 03:10"]},
    "events": [{"event_type": "lay_down", "device_ts": "2026-10-24T22:40:00-07:00", "data": {}}],
    "agent_log": [{"ts": "x", "agent": "night_watch", "intent": "set_light on mum", "guardian": "allowed"}],
    "settings": {"checkin_timeout_min": 20, "quiet_start": "22:00:00", "quiet_end": "07:00:00"},
}


def test_plain_brief_states_the_facts_and_proposes_nothing():
    brief = mb.plain_brief(NIGHT)
    assert "got up 1 time" in brief.note and "31 min" in brief.note and "checked in 1 time" in brief.note
    assert "Worth knowing: a 31-minute trip at 03:10" in brief.note
    assert brief.config_diff == {}


def test_plain_brief_for_a_quiet_night():
    quiet = {**NIGHT, "summary": {**NIGHT["summary"], "trips": [], "trip_count": 0, "longest_trip_min": 0,
                                  "checkins": 0, "unusual": []}}
    assert mb.plain_brief(quiet).note == "Margaret had a quiet night: in bed from 22:40, up at 06:50."


def test_workspace_holds_only_the_night(tmp_path, monkeypatch):
    monkeypatch.setattr(mb, "WORKSPACE", tmp_path / "ws")
    ws = mb.write_workspace(NIGHT)
    names = sorted(p.name for p in ws.iterdir())
    assert names == ["SETTINGS.md", "SUMMARY.md", "agent_log.json", "events.json"]
    assert "left 03:10, back 03:41, 31 min" in (ws / "SUMMARY.md").read_text()
    settings = (ws / "SETTINGS.md").read_text()
    assert "checkin_timeout_min: 20" in settings and "path_light_pct: 0-40" in settings
    assert json.loads((ws / "events.json").read_text()) == NIGHT["events"]


def test_seconds_until_is_within_a_day():
    assert 0 < mb.seconds_until("06:00", "America/Los_Angeles") <= 24 * 3600
