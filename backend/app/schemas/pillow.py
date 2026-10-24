"""Schemas for registered pillows."""

from uuid import UUID

from pydantic import BaseModel


class Pillow(BaseModel):
    """A registered pillow and the resident it belongs to."""

    id: str
    resident_id: UUID | None
    location_label: str | None
