"""Alert calls in the pillow's own voice: the script spoken by Cartesia and kept where Twilio can
fetch it, then deleted once the call is over (the script names her and what happened).

Making it is best effort: on any failure, or past CALL_AUDIO_BUDGET_S, the call goes out with
Twilio's voice reading the script instead."""

import asyncio
import logging
from uuid import uuid4

from supabase import AsyncClient

from app.core.voice_constants import DEFAULT_VOICE_ID, SAMPLE_EXTENSION
from app.crud.voice_samples import delete_sample, store_sample
from app.notify.notify_constants import (
    CALL_AUDIO_BUDGET_S,
    CALL_AUDIO_FOLDER,
    CALL_AUDIO_KEEP_S,
    CALL_AUDIO_LANGUAGE,
)
from app.voice.cartesia import Cartesia

log = logging.getLogger(__name__)


class CallAudio:
    """Speaks call scripts with Cartesia and stores them in Supabase Storage."""

    def __init__(self, cartesia: Cartesia, db: AsyncClient) -> None:
        self.cartesia = cartesia
        self.db = db

    async def make(self, text: str) -> tuple[str, str] | None:
        """The script spoken: (its path in the bucket, its public link), or None if it couldn't be
        made in time. Never raises."""
        path = f"{CALL_AUDIO_FOLDER}/{uuid4().hex}{SAMPLE_EXTENSION}"
        try:
            async with asyncio.timeout(CALL_AUDIO_BUDGET_S):
                mp3 = await self.cartesia.speak(DEFAULT_VOICE_ID, text, CALL_AUDIO_LANGUAGE)
                return path, await store_sample(self.db, path, mp3)
        except Exception as err:  # Cartesia, Storage or the budget: Twilio's voice reads it instead
            log.warning("Call audio not made (%s); Twilio's voice reads the script", type(err).__name__)
            return None

    async def forget_later(self, path: str) -> None:
        """Delete the MP3 once the call has had time to play it. Never raises."""
        await asyncio.sleep(CALL_AUDIO_KEEP_S)
        try:
            await delete_sample(self.db, path)
        except Exception as err:
            log.warning("Call audio %s not deleted (%s)", path, type(err).__name__)
