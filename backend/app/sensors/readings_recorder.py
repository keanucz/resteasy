"""Averages each pillow's state reports into one `readings` row per minute.

Plain code with no I/O: `observe` says which rows to write, the router writes them."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.schemas.pillow_state import DeviceState
from app.sensors.sensor_constants import READING_DECIMALS, READING_PERIOD_S, READINGS_FLUSH_S

# The columns that identify a readings row (its primary key); the rest are sensor values
_ROW_KEY = ("pillow_id", "ts")


def _mean(values: list[float]) -> float | None:
    """The average of `values` rounded for storage, or None when there are none."""
    return round(sum(values) / len(values), READING_DECIMALS) if values else None


@dataclass
class _Minute:
    """The reports seen so far in one pillow's current minute."""

    start: int  # Unix seconds at the start of the minute (device clock)
    motion: list[float] = field(default_factory=list)
    temp_c: list[float] = field(default_factory=list)
    sound_db: list[float] = field(default_factory=list)
    head_on: list[bool] = field(default_factory=list)
    flushed_at: float | None = None  # device ts of the last write, None before the first

    def add(self, state: DeviceState) -> None:
        """Count one report's sensors; null ones (not wired) are skipped."""
        for name, values in (("motion", self.motion), ("temp_c", self.temp_c), ("sound_db", self.sound_db)):
            value = getattr(state, name)
            if value is not None:
                values.append(value)
        if state.head_on is not None:
            self.head_on.append(state.head_on)

    def row(self, pillow_id: str) -> dict:
        """The minute as a `readings` row, leaving out sensors that never reported.

        A head counts as on for the minute if it was on in any report."""
        row: dict = {"pillow_id": pillow_id, "ts": datetime.fromtimestamp(self.start, UTC).isoformat()}
        for name, values in (("motion", self.motion), ("temp_c", self.temp_c), ("sound_db", self.sound_db)):
            mean = _mean(values)
            if mean is not None:
                row[name] = mean
        if self.head_on:
            row["head_on"] = any(self.head_on)
        return row


class ReadingsRecorder:
    """Keeps each pillow's current minute in memory (like Night Watch's timers)."""

    def __init__(self, flush_s: float = READINGS_FLUSH_S) -> None:
        self._flush_s = flush_s
        self._minutes: dict[str, _Minute] = {}

    def observe(self, pillow_id: str, state: DeviceState) -> list[dict]:
        """Add a report and return the rows to upsert now, oldest first.

        A new minute first finishes the previous one (its final averages). The current minute is
        written on its first report and then every `flush_s` device seconds."""
        start = int(state.ts // READING_PERIOD_S * READING_PERIOD_S)
        rows: list[dict] = []
        minute = self._minutes.get(pillow_id)
        if minute is not None and minute.start != start:
            rows.append(minute.row(pillow_id))
            minute = None
        if minute is None:
            minute = self._minutes[pillow_id] = _Minute(start)
        minute.add(state)
        if minute.flushed_at is None or state.ts - minute.flushed_at >= self._flush_s:
            minute.flushed_at = state.ts
            rows.append(minute.row(pillow_id))
        # A minute where no sensor reported (keys only) has nothing to chart
        return [row for row in rows if len(row) > len(_ROW_KEY)]
