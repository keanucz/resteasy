"""The base-laptop client's reaction to night_state changes (no network, no audio)."""

from checkin_client import Watcher


def test_first_state_is_only_remembered():
    w = Watcher()
    assert w.on_state("in_bed") == []
    assert w.on_state("in_bed") == []


def test_check_in_runs_once_per_entry():
    w = Watcher()
    w.on_state("up")
    assert w.on_state("check_in") == [("checkin",)]
    assert w.on_state("check_in") == []  # still talking: don't start a second one
    assert w.on_state("up") == []  # she said fine: back to up, nothing to say (the check-in did)
    assert w.on_state("check_in") == [("checkin",)]  # a later no-return asks again


def test_starting_mid_check_in_runs_it():
    """The laptop was (re)started while the server already wanted a check-in."""
    assert Watcher().on_state("check_in") == [("checkin",)]


def test_the_pillow_says_nothing_for_ordinary_moves_through_the_night():
    """Getting up, lying down, back in bed after an alert, restless, asleep, awake: no words."""
    w = Watcher()
    for state in ("awake", "in_bed", "restless", "asleep", "up", "in_bed", "escalating", "in_bed", "awake"):
        assert w.on_state(state) == []
