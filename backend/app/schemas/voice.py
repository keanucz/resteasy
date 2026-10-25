"""Schemas for the voice the pillow speaks to her with: the picker, previews and clones."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, StringConstraints

from app.core.voice_constants import CLONE_SOURCE, PREVIEW_TEXT_MAX, STOCK_SOURCE


class ResidentVoice(BaseModel):
    """One voice in her picker: a stock voice, or a clone made in the app (with who recorded it)."""

    id: str
    name: str
    description: str | None
    source: Literal["stock", "clone"]
    created_by_name: str | None
    created_at: datetime | None

    @classmethod
    def stock(cls, voice_id: str, name: str, description: str) -> "ResidentVoice":
        return cls(
            id=voice_id,
            name=name,
            description=description,
            source=STOCK_SOURCE,
            created_by_name=None,
            created_at=None,
        )

    @classmethod
    def clone(cls, row: dict[str, Any]) -> "ResidentVoice":
        """A voice_clones row with its creator, as the app shows it."""
        creator = row.get("creator") or {}
        return cls(
            id=row["voice_id"],
            name=row["name"],
            description=None,
            source=CLONE_SOURCE,
            created_by_name=creator.get("full_name"),
            created_at=row["created_at"],
        )


class ResidentVoices(BaseModel):
    """The voice she hears now, and every voice the owner may pick for her."""

    current: str
    voices: list[ResidentVoice]


class VoiceChoice(BaseModel):
    """The voice the owner picks: a stock voice or one of her clones."""

    voice_id: str


class CurrentVoice(BaseModel):
    """The voice she hears now."""

    current: str


class VoicePreviewRequest(BaseModel):
    """A voice to hear, and what it says; no text (or only spaces) says a line with her name."""

    voice_id: str
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=PREVIEW_TEXT_MAX)] | None = None


class CloneUpload(BaseModel):
    """A checked recording to clone, of someone who agreed: an audio file within the size limit."""

    clip: bytes
    filename: str
    content_type: str
    name: str
