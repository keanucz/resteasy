"""Cartesia's REST API (docs.cartesia.ai): speak a line, clone a voice, make an accent copy of one,
keep a pronunciation dictionary, and remove what the app made.

The API key never leaves the server and never goes into the logs. Every failure raises
VoiceServiceError with a plain sentence the app can show (the API answers it with a 502)."""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.voice_constants import (
    ACCENT_FAILED,
    ACCENTS_FAILED,
    CARTESIA_API,
    CARTESIA_TIMEOUT_S,
    CARTESIA_VERSION,
    CLONE_FAILED,
    DEFAULT_EMOTION,
    DEFAULT_SPEED,
    DEFAULT_VOLUME,
    DELETE_FAILED,
    EMOTION_LANGUAGE,
    PREVIEW_FAILED,
    PREVIEW_FORMAT,
    PRONUNCIATION_FAILED,
    TTS_MODEL,
)

log = logging.getLogger(__name__)


class VoiceServiceError(Exception):
    """Cartesia refused or could not be reached; the message is safe to show in the app."""


@dataclass(frozen=True)
class Speech:
    """How a line is spoken: Cartesia's generation_config, plus her pronunciation dictionary."""

    speed: float = DEFAULT_SPEED
    volume: float = DEFAULT_VOLUME
    emotion: str = DEFAULT_EMOTION
    pronunciation_dict_id: str | None = None


def base_language(language: str) -> str:
    """The bare language ("en" from "en-GB" or "en_GB"), which Cartesia's voice and accent calls take."""
    return language.replace("_", "-").partition("-")[0]


class Cartesia:
    """Client for the Cartesia calls the family app needs."""

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        self.headers = {"Authorization": f"Bearer {api_key}", "Cartesia-Version": CARTESIA_VERSION}
        self.http = http or httpx.AsyncClient(timeout=CARTESIA_TIMEOUT_S)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Cartesia | None":
        return cls(settings.cartesia_api_key) if settings.cartesia_api_key else None

    async def speak(self, voice_id: str, text: str, language: str, speech: Speech | None = None) -> bytes:
        """`text` in the voice, as MP3 bytes, spoken the way the pillow speaks (or as `speech` says).
        Cartesia's emotions are English only, so other languages are spoken without one."""
        speech = speech or Speech()
        config: dict[str, Any] = {"speed": speech.speed, "volume": speech.volume}
        if base_language(language) == EMOTION_LANGUAGE:
            config["emotion"] = speech.emotion
        body: dict[str, Any] = {
            "model_id": TTS_MODEL,
            "transcript": text,
            "voice": {"id": voice_id},
            "language": language,
            "output_format": PREVIEW_FORMAT,
            "generation_config": config,
        }
        if speech.pronunciation_dict_id:
            body["pronunciation_dict_id"] = speech.pronunciation_dict_id
        response = await self._call("POST", "/tts/bytes", PREVIEW_FAILED, json=body)
        return response.content

    async def clone(
        self,
        clip: bytes,
        filename: str,
        content_type: str,
        name: str,
        language: str,
        accent: str | None = None,
    ) -> dict[str, Any]:
        """Make a private voice from the recording, labelled with the speaker's own `accent` when
        known; Cartesia's voice (id, name, created_at, ...)."""
        data = {"name": name, "language": base_language(language)}  # a clone takes "en", not "en-GB"
        if accent:
            data["accent"] = accent
        response = await self._call(
            "POST",
            "/voices/clone",
            CLONE_FAILED,
            data=data,
            files={"clip": (filename, clip, content_type)},
        )
        return response.json()

    async def accents(self, language: str) -> list[dict[str, Any]]:
        """Accents Cartesia can give a voice in her language: id, name, locale, is_localizable."""
        response = await self._call(
            "GET", "/accents", ACCENTS_FAILED, params={"language": base_language(language)}
        )
        return response.json()["accents"]

    async def localize(self, voice_id: str, name: str, accent: str) -> dict[str, Any]:
        """A new private voice: `voice_id` speaking with `accent`; Cartesia's voice (id, name, ...)."""
        body = {"voice_id": voice_id, "name": name, "accent": accent}
        response = await self._call("POST", "/voices/localize", ACCENT_FAILED, json=body)
        return response.json()

    async def save_pronunciations(self, dict_id: str | None, name: str, items: list[dict[str, Any]]) -> str:
        """Put `items` ({text, pronunciation, case_sensitive}) in her dictionary, replacing what was
        there, and return its id; a new dictionary when she has none (or Cartesia lost hers)."""
        if dict_id:
            path = f"/pronunciation-dicts/{dict_id}"
            response = await self._call(
                "PATCH", path, PRONUNCIATION_FAILED, gone_ok=True, json={"items": items}
            )
            if response.status_code != httpx.codes.NOT_FOUND:
                return dict_id
        body = {"name": name, "items": items}
        response = await self._call("POST", "/pronunciation-dicts/", PRONUNCIATION_FAILED, json=body)
        return response.json()["id"]

    async def delete(self, voice_id: str) -> None:
        """Remove a cloned or localized voice; one Cartesia no longer has counts as removed."""
        await self._call("DELETE", f"/voices/{voice_id}", DELETE_FAILED, gone_ok=True)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _call(
        self, method: str, path: str, failed: str, *, gone_ok: bool = False, **request: Any
    ) -> httpx.Response:
        """One request; VoiceServiceError(`failed`) when it can't be sent or Cartesia refuses it."""
        try:
            response = await self.http.request(
                method, f"{CARTESIA_API}{path}", headers=self.headers, **request
            )
        except httpx.HTTPError as err:
            log.warning("Cartesia %s %s unreachable: %s", method, path, type(err).__name__)
            raise VoiceServiceError(failed) from err
        if response.is_success or (gone_ok and response.status_code == httpx.codes.NOT_FOUND):
            return response
        log.warning("Cartesia %s %s answered %s: %s", method, path, response.status_code, response.text[:200])
        raise VoiceServiceError(failed)
