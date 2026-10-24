"""Schemas for the example `items` resource."""

from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    """Fields shared by every item representation."""

    name: str = Field(min_length=1)
    description: str | None = None


class ItemCreate(ItemBase):
    """Payload for creating an item."""


class ItemUpdate(BaseModel):
    """Payload for a partial item update; omitted fields stay unchanged."""

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class Item(ItemBase):
    """An item as stored and returned by the API."""

    id: int
