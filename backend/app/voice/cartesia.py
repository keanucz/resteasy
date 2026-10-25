"""Cartesia's REST API (docs.cartesia.ai): speak a short preview, clone a voice, remove a clone.

The API key never leaves the server and never goes into the logs. Every failure raises
VoiceServiceError with a plain sentence the app can show (the API answers it with a 502)."""

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.core.voice_constants import (
    CARTESIA_API,
    CARTESIA_TIMEOUT_S,
    CARTESIA_VERSION,
    CLONE_FAILED,
    DELETE_FAILED,
    PREVIEW_EMOTION,
    PREVIEW_FAILED,
    PREVIEW_FORMAT,
    PREVIEW_SPEED,
    TTS_MODEL,
)

log = logging.getLogger(__name__)


class VoiceServiceError(Exception):
    """Cartesia refused or could not be reached; the message is safe to show in the app."""


class Cartesia:
    """Client for the three Cartesia calls the family app needs."""

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        self.headers = {"Authorization": f"Bearer {api_key}", "Cartesia-Version": CARTESIA_VERSION}
        self.http = http or httpx.AsyncClient(timeout=CARTESIA_TIMEOUT_S)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Cartesia | None":
        return cls(settings.cartesia_api_key) if settings.cartesia_api_key else None

    async def speak(self, voice_id: str, text: str, language: str) -> bytes:
        """`text` in the voice, as MP3 bytes, spoken the way the pillow speaks."""
        body = {
            "model_id": TTS_MODEL,
            "transcript": text,
            "voice": {"id": voice_id},
            "language": language,
            "output_format": PREVIEW_FORMAT,
            "generation_config": {"speed": PREVIEW_SPEED, "emotion": PREVIEW_EMOTION},
        }
        response = await self._call("POST", "/tts/bytes", PREVIEW_FAILED, json=body)
        return response.content

    async def clone(
        self, clip: bytes, filename: str, content_type: str, name: str, language: str
    ) -> dict[str, Any]:
        """Make a private voice from the recording; Cartesia's voice (id, name, created_at, ...)."""
        base_language = language.replace("_", "-").partition("-")[0]  # a clone takes "en", not "en-GB"
        response = await self._call(
            "POST",
            "/voices/clone",
            CLONE_FAILED,
            data={"name": name, "language": base_language},
            files={"clip": (filename, clip, content_type)},
        )
        return response.json()

    async def delete(self, voice_id: str) -> None:
        """Remove a cloned voice; one Cartesia no longer has counts as removed."""
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
