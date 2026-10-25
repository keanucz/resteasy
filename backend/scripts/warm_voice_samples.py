"""Make the sample of every stock voice now, so the first Play in the app is already instant.

    uv run python -m scripts.warm_voice_samples [--again]

Each stock voice says the sample line once (Cartesia) and the MP3 is kept in Supabase Storage,
where the app plays it from. Voices that already have a sample are skipped unless --again is given.
Needs SUPABASE_URL, SUPABASE_SECRET_KEY and CARTESIA_API_KEY in backend/.env.
"""

import argparse
import asyncio

from supabase import acreate_client

from app.core.config import get_settings
from app.core.voice_constants import EMOTION_LANGUAGE, SAMPLE_EMOTION, SAMPLE_SPEED, SAMPLE_TEXT, VOICES
from app.crud.voice_samples import cached_samples, sample_path, store_sample
from app.voice.cartesia import Cartesia, Speech


async def warm(again: bool) -> None:
    """Speak and store each stock voice's sample that is missing (or all of them, `again`)."""
    settings = get_settings()
    cartesia = Cartesia.from_settings(settings)
    if cartesia is None:
        raise SystemExit("CARTESIA_API_KEY is not set")
    db = await acreate_client(settings.supabase_url, settings.supabase_secret_key)
    speech = Speech(speed=SAMPLE_SPEED, emotion=SAMPLE_EMOTION)
    try:
        # Stock samples ignore the resident, so any id works for the shared folder
        cached = await cached_samples(db, "")
        for voice_id, name, _ in VOICES:
            path = sample_path("", voice_id)
            if path in cached and not again:
                print(f"{name}: already made")
                continue
            mp3 = await cartesia.speak(voice_id, SAMPLE_TEXT, EMOTION_LANGUAGE, speech)
            print(f"{name}: {await store_sample(db, path, mp3)}")
    finally:
        await cartesia.aclose()


def main() -> None:
    """Parse arguments and make the samples."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--again", action="store_true", help="make every sample again, replacing the old ones"
    )
    asyncio.run(warm(parser.parse_args().again))


if __name__ == "__main__":
    main()
