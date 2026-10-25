"""The per-minute sensor history: which `readings` rows a stream of state reports produces."""

from datetime import UTC, datetime

from app.schemas.pillow_state import DeviceState
from app.sensors.readings_recorder import ReadingsRecorder

PILLOW = "test-pillow"
# 23:00:00 UTC, the start of a minute
MINUTE = datetime(2026, 10, 24, 23, 0, tzinfo=UTC).timestamp()


def _state(seconds: float, **sensors: object) -> DeviceState:
    """A report `seconds` into the test minute; sensors not given are null (not wired)."""
    return DeviceState(ts=MINUTE + seconds, **sensors)


def test_first_report_writes_the_minute_at_once() -> None:
    """The app sees a new minute as soon as its first report lands."""
    rows = ReadingsRecorder().observe(PILLOW, _state(0.5, motion=0.2, sound_db=-50.0))
    assert rows == [
        {"pillow_id": PILLOW, "ts": "2026-10-24T23:00:00+00:00", "motion": 0.2, "sound_db": -50.0}
    ]


def test_minute_is_rewritten_every_flush_with_running_averages() -> None:
    """Reports between flushes only accumulate; the next flush writes their averages."""
    recorder = ReadingsRecorder(flush_s=5)
    recorder.observe(PILLOW, _state(0, motion=0.0))
    assert recorder.observe(PILLOW, _state(2, motion=0.3)) == []
    rows = recorder.observe(PILLOW, _state(5, motion=0.6))
    assert rows == [{"pillow_id": PILLOW, "ts": "2026-10-24T23:00:00+00:00", "motion": 0.3}]


def test_new_minute_finishes_the_previous_one_first() -> None:
    """Crossing into a new minute writes the old minute's final averages, then the new minute."""
    recorder = ReadingsRecorder(flush_s=5)
    recorder.observe(PILLOW, _state(57, motion=0.1))
    recorder.observe(PILLOW, _state(58, motion=0.3))
    old, new = recorder.observe(PILLOW, _state(61, motion=0.9))
    assert old == {"pillow_id": PILLOW, "ts": "2026-10-24T23:00:00+00:00", "motion": 0.2}
    assert new == {"pillow_id": PILLOW, "ts": "2026-10-24T23:01:00+00:00", "motion": 0.9}


def test_unwired_sensors_are_left_out_so_another_device_keeps_them() -> None:
    """The voice unit sends no temperature; its rows must not overwrite the pillow node's with null."""
    row = ReadingsRecorder().observe(PILLOW, _state(0, motion=0.1))[0]
    assert "temp_c" not in row
    assert "head_on" not in row


def test_head_counts_as_on_if_it_was_on_in_any_report() -> None:
    """A minute where she lay down part-way is a minute on the pillow."""
    recorder = ReadingsRecorder(flush_s=5)
    recorder.observe(PILLOW, _state(0, head_on=False, temp_c=20.0))
    row = recorder.observe(PILLOW, _state(10, head_on=True, temp_c=21.0))[0]
    assert row["head_on"] is True
    assert row["temp_c"] == 20.5


def test_keys_only_reports_write_nothing() -> None:
    """A report with every sensor null has nothing to chart."""
    assert ReadingsRecorder().observe(PILLOW, _state(0)) == []


def test_pillows_are_kept_apart() -> None:
    """Two pillows reporting in the same minute each get their own row."""
    recorder = ReadingsRecorder()
    recorder.observe(PILLOW, _state(0, motion=0.1))
    rows = recorder.observe("mum", _state(1, motion=0.5))
    assert rows == [{"pillow_id": "mum", "ts": "2026-10-24T23:00:00+00:00", "motion": 0.5}]
