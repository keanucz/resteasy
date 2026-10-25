"""Schemas for the device state the pillow pushes and the latest state the app reads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# How the bridge reaches the bedside voice unit right now
Link = Literal["ble", "hotspot", "usb"]


class Keys(BaseModel):
    """Keypad buttons, true while held."""

    talk: bool = False
    fine: bool = False
    family: bool = False


class DeviceState(BaseModel):
    """One state report from the device, exactly as `coord/CONTRACT.md` section 1 defines it.

    Sensors that are not wired arrive as null; the path's pillow id wins over the body's.
    """

    pillow_id: str | None = None
    ts: float
    head_on: bool | None = None
    motion: float | None = Field(default=None, ge=0, le=1)
    room_motion: bool | None = None
    light: float | None = Field(default=None, ge=0, le=1)
    temp_c: float | None = None
    humidity: float | None = Field(default=None, ge=0, le=100)
    keys: Keys = Keys()
    knob: int | None = Field(default=None, ge=0, le=10)
    sound_db: float | None = Field(default=None, ge=-120, le=0)
    link: Link | None = None


class PillowState(BaseModel):
    """The latest stored state of a pillow, including the night state the agents derive."""

    pillow_id: str
    device_ts: datetime | None
    head_on: bool | None
    motion: float | None
    room_motion: bool | None
    light: float | None
    temp_c: float | None
    humidity: float | None
    key_talk: bool | None
    key_fine: bool | None
    key_family: bool | None
    knob: int | None
    # Absent until the live_readings migration is applied
    sound_db: float | None = None
    link: Link | None = None
    night_state: str
    state_since: datetime
    last_seen_at: datetime


class PillowPing(BaseModel):
    """Whether both boards in the pillow answered a ping (POST /pillows/{id}/ping).

    The pillow node (sensors) sends its lines over ESP-NOW to the voice unit, which hands them to
    the bridge, which posts them as state. A fresh report means the node answered; a fresh report
    that also names the bridge's link to the voice unit means the voice unit answered too. When
    nothing arrives, the backend can't tell which hop broke, so both read false.
    """

    pillow_id: str
    active: bool
    node_alive: bool
    voice_unit_alive: bool
    link: Link | None
    last_seen_at: datetime | None
    checked_at: datetime
