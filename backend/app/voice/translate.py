"""Claude, to translate a typed preview line before Cartesia speaks it in another language.

Only the app's previews use it. Anything that goes wrong (no key, a timeout, a refusal) gives back
the line as typed, so a preview is always spoken.
"""

import asyncio
import logging
from typing import Any

from app.core.voice_constants import (
    LANGUAGE_ENGLISH_NAMES,
    PREVIEW_LANGUAGE,
    TRANSLATE_MAX_TOKENS,
    TRANSLATE_MODEL,
    TRANSLATE_SYSTEM,
    TRANSLATE_TIMEOUT_S,
)

log = logging.getLogger(__name__)


class Translator:
    """Translates short lines with Claude; `client` is an AsyncAnthropic (None = never translates).
    Each (line, language) is asked for once per process."""

    def __init__(self, client: Any = None, *, model: str = TRANSLATE_MODEL) -> None:
        self.client, self.model = client, model
        self._done: dict[tuple[str, str], str] = {}

    @classmethod
    def from_api_key(cls, api_key: str) -> "Translator":
        if not api_key:
            return cls(None)
        import anthropic  # slow import, paid once at start-up

        return cls(anthropic.AsyncAnthropic(api_key=api_key, max_retries=0))

    async def translate(self, text: str, language: str) -> str:
        """`text` in `language` (a preview language code), or `text` itself when it can't be."""
        target = LANGUAGE_ENGLISH_NAMES.get(language)
        if self.client is None or target is None or language == PREVIEW_LANGUAGE or not text.strip():
            return text
        key = (text, language)
        if key in self._done:
            return self._done[key]
        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=TRANSLATE_MAX_TOKENS,
                    system=TRANSLATE_SYSTEM.format(language=target),
                    messages=[{"role": "user", "content": text}],
                ),
                TRANSLATE_TIMEOUT_S,
            )
        except Exception as e:  # noqa: BLE001 - key, network, timeout: the typed line is spoken
            log.warning("Preview translation failed: %s", type(e).__name__)
            return text
        if getattr(response, "stop_reason", None) == "refusal":
            return text
        out = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
        if out:
            self._done[key] = out
        return out or text
