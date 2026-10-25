"""The base-laptop client's reaction to night_state changes (no network, no audio)."""

from checkin_client import Watcher


def test_first_state_is_only_remembered():
    w = Watcher()
    assert w.on_state("in_bed") == []
    assert w.on_state("in_bed") == []


def test_getting_up_at_night_speaks_the_path_light_line():
    w = Watcher()
    w.on_state("in_bed")
    assert w.on_state("up") == [("say", "The light's on. Take your time.")]


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


def test_back_in_bed_after_an_escalation_says_goodnight():
    w = Watcher()
    w.on_state("escalating")
    assert w.on_state("in_bed") == [("say", "You're back in bed. Goodnight.")]
    w.on_state("awake")
    assert w.on_state("in_bed") == [("goodnight",)]  # an ordinary lie-down only checks for a message


def test_lying_down_asks_for_a_goodnight_message():
    w = Watcher()
    w.on_state("awake")
    assert w.on_state("in_bed") == [("goodnight",)]
    assert w.on_state("in_bed") == []
