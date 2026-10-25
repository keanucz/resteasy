"""Schemas for the voice the pillow speaks to her with: the picker, samples and previews, how it
speaks, accent copies, clones, and the words it says her way."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.core.voice_constants import (
    ACCENT_SOURCE,
    CLONE_SOURCE,
    DEFAULT_EMOTION,
    DEFAULT_SPEED,
    DEFAULT_VOLUME,
    EMOTIONS,
    PREVIEW_LANGUAGE_CODES,
    PREVIEW_TEXT_MAX,
    PRONUNCIATION_WORD_MAX,
    SOUNDS_LIKE_MAX,
    SPEED_MAX,
    SPEED_MIN,
    STOCK_SOURCE,
    UNKNOWN_EMOTION,
    UNKNOWN_LANGUAGE,
    VOLUME_MAX,
    VOLUME_MIN,
)


class ResidentVoice(BaseModel):
    """One voice in her picker: a stock voice, a clone made in the app (with who recorded it), or
    an accent copy of either; with the link to its sample once one has been made."""

    id: str
    name: str
    description: str | None
    source: Literal["stock", "clone", "accent"]
    created_by_name: str | None
    created_at: datetime | None
    # Cartesia's accent id: a clone's own accent, or the accent of a copy
    accent: str | None = None
    # The voice an accent copy was made from
    base_voice_id: str | None = None
    # Its sample in the preview language, once made
    sample_url: str | None = None
    # Its sample in every preview language made so far (code -> link), so the app swaps at once
    samples: dict[str, str] = Field(default_factory=dict)

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
        """A voice_clones row (a clone or an accent copy) with its maker, as the app shows it."""
        creator = row.get("creator") or {}
        return cls(
            id=row["voice_id"],
            name=row["name"],
            description=None,
            source=ACCENT_SOURCE if row.get("kind") == ACCENT_SOURCE else CLONE_SOURCE,
            created_by_name=creator.get("full_name"),
            created_at=row["created_at"],
            accent=row.get("accent"),
            base_voice_id=row.get("base_voice_id"),
        )


Speed = Annotated[float, Field(ge=SPEED_MIN, le=SPEED_MAX)]
Volume = Annotated[float, Field(ge=VOLUME_MIN, le=VOLUME_MAX)]


class VoiceStyle(BaseModel):
    """How the pillow speaks: Cartesia's speed and volume, and one of the gentle tones offered."""

    speed: Speed = DEFAULT_SPEED
    volume: Volume = DEFAULT_VOLUME
    emotion: str = DEFAULT_EMOTION

    @field_validator("emotion")
    @classmethod
    def offered_emotion(cls, emotion: str) -> str:
        if emotion not in EMOTIONS:
            raise ValueError(UNKNOWN_EMOTION)
        return emotion

    @classmethod
    def of(cls, resident: dict[str, Any]) -> "VoiceStyle":
        """Her saved style (numeric columns arrive as numbers or strings)."""
        return cls(
            speed=float(resident["voice_speed"]),
            volume=float(resident["voice_volume"]),
            emotion=resident["voice_emotion"],
        )


def _offered_language(language: str) -> str:
    if language not in PREVIEW_LANGUAGE_CODES:
        raise ValueError(UNKNOWN_LANGUAGE)
    return language


class PreviewLanguage(BaseModel):
    """A language the previews can speak in: its code and its own name ("Polski")."""

    code: str
    name: str


class PreviewLanguageChoice(BaseModel):
    """The language the app's previews speak in."""

    language: str

    @field_validator("language")
    @classmethod
    def offered_language(cls, language: str) -> str:
        return _offered_language(language)


class ResidentVoices(BaseModel):
    """The voice she hears now and how it speaks, every voice the owner may pick for her, and the
    language the previews speak in."""

    current: str
    style: VoiceStyle
    emotions: list[str]
    voices: list[ResidentVoice]
    language: str
    languages: list[PreviewLanguage]


class VoiceChoice(BaseModel):
    """The voice the owner picks: a stock voice or one of her own."""

    voice_id: str


class CurrentVoice(BaseModel):
    """The voice she hears now."""

    current: str


class VoicePreviewRequest(BaseModel):
    """A voice to hear, and what it says; no text (or only spaces) says a line with her name. A
    `style` tries how it would sound before saving; without one it speaks as she hears it."""

    voice_id: str
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=PREVIEW_TEXT_MAX)] | None = None
    style: VoiceStyle | None = None
    # The language to speak in (a typed line is translated first); None = the preview language
    language: str | None = None

    @field_validator("language")
    @classmethod
    def offered_language(cls, language: str | None) -> str | None:
        return None if language is None else _offered_language(language)


class SampleLink(BaseModel):
    """Where to play a voice's sample from."""

    url: str


class Accent(BaseModel):
    """An accent Cartesia can give a voice: its id, a short name ("British") and locale."""

    id: str
    name: str
    locale: str


class AccentRequest(BaseModel):
    """Make a copy of one of her voices that speaks with `accent` (an Accent id)."""

    voice_id: str
    accent: str


class PronunciationRequest(BaseModel):
    """A word and how to say it: plain "sounds like" spelling, or Cartesia IPA in <<...>>."""

    word: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PRONUNCIATION_WORD_MAX)
    ]
    sounds_like: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SOUNDS_LIKE_MAX)
    ]


class Pronunciation(BaseModel):
    """One of her words, with who added it."""

    id: str
    word: str
    sounds_like: str
    created_by_name: str | None
    created_at: datetime

    @classmethod
    def of(cls, row: dict[str, Any]) -> "Pronunciation":
        creator = row.get("creator") or {}
        return cls(
            id=row["id"],
            word=row["word"],
            sounds_like=row["sounds_like"],
            created_by_name=creator.get("full_name"),
            created_at=row["created_at"],
        )


class PillowVoice(BaseModel):
    """Everything the pillow needs to speak to her the way the family set it up."""

    voice_id: str
    language: str
    speed: float
    volume: float
    emotion: str
    pronunciation_dict_id: str | None


class CloneUpload(BaseModel):
    """A checked recording to clone, of someone who agreed: an audio file within the size limit,
    and the speaker's own accent when the family gave it."""

    clip: bytes
    filename: str
    content_type: str
    name: str
    accent: str | None = None
