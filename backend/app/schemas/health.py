"""Schemas for the health router."""

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """A single human-readable message."""

    message: str


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: str
    environment: str
