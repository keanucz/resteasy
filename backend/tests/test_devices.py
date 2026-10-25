"""Which of the pillow's boards answered a ping, from the latest state report."""

from datetime import UTC, datetime, timedelta

from app.schemas.pillow_state import PillowState
from app.sensors.devices import check_devices

PILLOW = "test-pillow"
SINCE = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)
NOW = SINCE + timedelta(seconds=1)


def _state(seen: datetime, link: str | None = "hotspot") -> PillowState:
    """The latest state, last reported at `seen` through `link`."""
    return PillowState(
        pillow_id=PILLOW,
        device_ts=seen,
        head_on=False,
        motion=0.1,
        room_motion=None,
        light=None,
        temp_c=21.0,
        humidity=40.0,
        key_talk=False,
        key_fine=False,
        key_family=False,
        knob=None,
        link=link,
        night_state="awake",
        state_since=SINCE,
        last_seen_at=seen,
    )


def test_fresh_report_through_the_voice_unit_is_active() -> None:
    """A report during the ping, with a link to the voice unit, means both boards answered."""
    ping = check_devices(PILLOW, _state(SINCE + timedelta(seconds=0.5)), SINCE, NOW)
    assert (ping.active, ping.node_alive, ping.voice_unit_alive, ping.link) == (True, True, True, "hotspot")


def test_report_just_before_the_ping_counts() -> None:
    """The bridge posts every ~0.5 s, so a report a moment before the ping is just as live."""
    assert check_devices(PILLOW, _state(SINCE - timedelta(seconds=1)), SINCE, NOW).active


def test_report_without_a_link_is_the_node_alone() -> None:
    """The node on a laptop's USB (uno_bridge) reports with no link: the voice unit isn't in the path."""
    ping = check_devices(PILLOW, _state(SINCE, link=None), SINCE, NOW)
    assert (ping.active, ping.node_alive, ping.voice_unit_alive) == (False, True, False)


def test_stale_report_is_silent() -> None:
    """Nothing fresh: neither board answered, and the last report time is still shown."""
    seen = SINCE - timedelta(minutes=5)
    ping = check_devices(PILLOW, _state(seen), SINCE, NOW)
    assert (ping.active, ping.node_alive, ping.voice_unit_alive, ping.link) == (False, False, False, None)
    assert ping.last_seen_at == seen


def test_future_report_is_seeded_data_not_a_board() -> None:
    """Demo seeds stamp last_seen_at days ahead; that's not a board answering."""
    assert not check_devices(PILLOW, _state(NOW + timedelta(days=2)), SINCE, NOW).node_alive


def test_pillow_that_never_reported_is_silent() -> None:
    """No state row at all: nothing answered."""
    ping = check_devices(PILLOW, None, SINCE, NOW)
    assert (ping.active, ping.last_seen_at) == (False, None)
