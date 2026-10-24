"""Uno JSON line -> CONTRACT.md state message.  uv run --with pytest pytest sim/test_uno_state.py"""

from uno_state import uno_line_to_state

LINE = ('{"head_on":1,"motion":null,"room_motion":null,"light":null,"temp_c":null,"humidity":null,'
        '"fine":0,"talk":0,"family":0}')


def test_a_plate_line_becomes_a_contract_state():
    state = uno_line_to_state("UNO " + LINE, pillow_id="mum", ts=1792815000.25)
    assert state == {
        "pillow_id": "mum", "ts": 1792815000.25, "head_on": True, "motion": None, "room_motion": None,
        "light": None, "temp_c": None, "humidity": None,
        "keys": {"talk": False, "fine": False, "family": False}, "knob": None,
    }


def test_missing_fields_are_null_and_keys_default_false():
    state = uno_line_to_state('{"head_on":0,"fine":1}', pillow_id="mum", ts=1.0)
    assert state["head_on"] is False and state["temp_c"] is None
    assert state["keys"] == {"talk": False, "fine": True, "family": False}


def test_non_state_lines_are_ignored():
    assert uno_line_to_state('UNO {"boot":"pillow_uno","plate_pin":2}', pillow_id="mum", ts=1.0) is None
    assert uno_line_to_state("UNO garbage", pillow_id="mum", ts=1.0) is None
    assert uno_line_to_state("talk", pillow_id="mum", ts=1.0) is None
