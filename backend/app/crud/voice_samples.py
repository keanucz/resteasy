"""Data access for voice samples: one MP3 per voice saying the same line, in Supabase Storage.

A stock voice's sample is shared by everyone at `stock/<voice_id>.mp3`; a resident's own voices
(clones and accent copies) keep theirs at `<resident_id>/<voice_id>.mp3`. Only the backend writes
them; the app plays them straight from the public link.
"""

from supabase import AsyncClient

from app.core.voice_constants import (
    PREVIEW_CONTENT_TYPE,
    SAMPLE_EXTENSION,
    SAMPLES_BUCKET,
    SAMPLES_LIST_LIMIT,
    STOCK_SAMPLES_FOLDER,
    VOICE_IDS,
)


def _bucket(db: AsyncClient):
    """The voice-samples bucket's file API."""
    return db.storage.from_(SAMPLES_BUCKET)


def sample_folder(resident_id: str, voice_id: str) -> str:
    """The folder a voice's sample sits in: the shared one for stock voices, hers otherwise."""
    return STOCK_SAMPLES_FOLDER if voice_id in VOICE_IDS else resident_id


def sample_path(resident_id: str, voice_id: str) -> str:
    """Where a voice's sample sits in the bucket."""
    return f"{sample_folder(resident_id, voice_id)}/{voice_id}{SAMPLE_EXTENSION}"


async def cached_samples(db: AsyncClient, resident_id: str) -> set[str]:
    """The paths of every sample already made for the stock voices and for her own voices."""
    paths: set[str] = set()
    for folder in (STOCK_SAMPLES_FOLDER, resident_id):
        files = await _bucket(db).list(folder, {"limit": SAMPLES_LIST_LIMIT})
        paths.update(f"{folder}/{file['name']}" for file in files if file.get("id"))
    return paths


async def sample_url(db: AsyncClient, path: str) -> str:
    """The sample's public link (it need not exist yet)."""
    return await _bucket(db).get_public_url(path)


async def store_sample(db: AsyncClient, path: str, mp3: bytes) -> str:
    """Keep a sample in place of any old one and return its public link."""
    await _bucket(db).upload(path, mp3, {"content-type": PREVIEW_CONTENT_TYPE, "upsert": "true"})
    return await sample_url(db, path)


async def delete_sample(db: AsyncClient, path: str) -> None:
    """Forget a sample (its voice is gone)."""
    await _bucket(db).remove([path])
