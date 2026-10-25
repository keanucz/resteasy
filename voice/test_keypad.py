"""The macro pad's press logic, no pad needed.  uv run --with pytest pytest voice"""

import pytest
from keypad import (
    FAMILY,
    FINE,
    HOLD_S,
    TALK_ARM,
    TALK_CANCEL,
    TALK_GO,
    TALK_READY,
    KeyPresses,
    parse_keymap,
)


def test_hold_two_seconds_then_let_go_starts_listening():
    p = KeyPresses()
    assert p.down("talk", 0.0) == [TALK_ARM]
    assert p.tick(1.0) == []
    assert p.tick(HOLD_S) == [TALK_READY]
    assert p.tick(HOLD_S + 0.5) == []  # ready only once
    assert p.up("talk", HOLD_S + 1.0) == [TALK_GO]


def test_a_short_press_does_nothing():
    p = KeyPresses()
    assert p.down("talk", 0.0) == [TALK_ARM]
    assert p.up("talk", 0.8) == [TALK_CANCEL]


def test_letting_go_at_the_threshold_without_a_tick_still_counts():
    p = KeyPresses()
    p.down("talk", 10.0)
    assert p.up("talk", 10.0 + HOLD_S) == [TALK_READY, TALK_GO]


def test_a_second_down_while_held_is_ignored_and_the_next_press_starts_fresh():
    p = KeyPresses()
    p.down("talk", 0.0)
    assert p.down("talk", 0.5) == []
    p.up("talk", 3.0)
    assert p.down("talk", 5.0) == [TALK_ARM]
    assert p.up("talk", 5.5) == [TALK_CANCEL]


def test_fine_and_family_act_on_key_down():
    p = KeyPresses()
    assert p.down("fine", 0.0) == [FINE]
    assert p.up("fine", 0.1) == []
    assert p.down("family", 1.0) == [FAMILY]


def test_keymap():
    assert parse_keymap("KEY_F13=talk, KEY_F14=fine,KEY_F15=family") == {
        "KEY_F13": "talk", "KEY_F14": "fine", "KEY_F15": "family"}
    with pytest.raises(ValueError):
        parse_keymap("KEY_A=dance")
