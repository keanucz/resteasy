"""Make every voice's sample in every preview language now, so Play in the app is always instant
and changing the preview language swaps the samples at once.

    uv run python -m scripts.warm_voice_samples [--again] [--language pl]

Each voice says the sample line once per language (Cartesia) and the MP3 is kept in Supabase
Storage, where the app plays it from: the stock voices once for everyone, and every resident's own
voices (clones and accent copies). Samples already made are skipped unless --again is given.
Needs SUPABASE_URL, SUPABASE_SECRET_KEY and CARTESIA_API_KEY in backend/.env.
"""

import argparse
import asyncio

from supabase import AsyncClient, acreate_client

from app.core.config import get_settings
from app.core.voice_constants import (
    EMOTION_LANGUAGE,
    PREVIEW_LANGUAGE,
    PREVIEW_LANGUAGES,
    SAMPLE_EMOTION,
    SAMPLE_SPEED,
    SAMPLE_TEXTS,
    VOICES,
)
from app.crud.crud_constants import VOICE_CLONES_TABLE
from app.crud.voice_samples import cached_samples, sample_path, store_sample
from app.voice.cartesia import Cartesia, Speech, VoiceServiceError


async def _own_voices(db: AsyncClient) -> list[tuple[str, str, str]]:
    """(resident id, voice id, name) of every resident's own voice."""
    rows = (await db.table(VOICE_CLONES_TABLE).select("resident_id, voice_id, name").execute()).data
    return [(row["resident_id"], row["voice_id"], row["name"]) for row in rows]


async def warm(again: bool, languages: list[str]) -> None:
    """Speak and store each missing sample (or all of them, `again`) in `languages`."""
    settings = get_settings()
    cartesia = Cartesia.from_settings(settings)
    if cartesia is None:
        raise SystemExit("CARTESIA_API_KEY is not set")
    db = await acreate_client(settings.supabase_url, settings.supabase_secret_key)
    speech = Speech(speed=SAMPLE_SPEED, emotion=SAMPLE_EMOTION)
    # Stock samples ignore the resident, so any id works for the shared folder
    voices = [("", voice_id, name) for voice_id, name, _ in VOICES] + await _own_voices(db)
    cached: dict[str, set[str]] = {}
    made = failed = 0
    try:
        for resident_id, voice_id, name in voices:
            if resident_id not in cached:
                cached[resident_id] = await cached_samples(db, resident_id)
            for language in languages:
                path = sample_path(resident_id, voice_id, language)
                if path in cached[resident_id] and not again:
                    continue
                spoken = EMOTION_LANGUAGE if language == PREVIEW_LANGUAGE else language
                try:
                    mp3 = await cartesia.speak(voice_id, SAMPLE_TEXTS[language], spoken, speech)
                except VoiceServiceError as err:
                    failed += 1
                    print(f"{name} ({language}): failed, {err}")
                    continue
                await store_sample(db, path, mp3)
                made += 1
                print(f"{name} ({language}): made")
    finally:
        await cartesia.aclose()
    print(f"{made} made, {failed} failed")


def main() -> None:
    """Parse arguments and make the samples."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--again", action="store_true", help="make every sample again, replacing the old ones"
    )
    codes = [code for code, _ in PREVIEW_LANGUAGES]
    parser.add_argument("--language", choices=codes, help="only this language (default: all)")
    args = parser.parse_args()
    asyncio.run(warm(args.again, [args.language] if args.language else codes))


if __name__ == "__main__":
    main()
