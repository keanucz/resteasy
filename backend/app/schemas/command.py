"""Schemas for commands queued for a pillow (`coord/CONTRACT.md` section 3)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class CommandName(StrEnum):
    """Commands the device understands; mirrors the check constraint on `commands.cmd`."""

    SET_LIGHT = "set_light"
    PULSE = "pulse"
    VIBRATE = "vibrate"
    FAN = "fan"
    BUZZ = "buzz"
    STOP_ALL = "stop_all"


class CommandCreate(BaseModel):
    """Payload for queueing a command; `source` names the agent or screen that sent it."""

    cmd: CommandName
    args: dict[str, Any] = {}
    source: str | None = None


class Command(BaseModel):
    """A queued command in the shape the device polls for."""

    id: int
    cmd: CommandName
    args: dict[str, Any]
