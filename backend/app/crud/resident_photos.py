"""Data access for a resident's profile photo: one per resident in Supabase Storage.

It lives at `<resident_id>/photo.jpg` in the public resident-photos bucket, where the app also
uploads it directly, so the link and its version match what the app builds itself.
"""

from datetime import datetime

from supabase import AsyncClient

from app.crud.crud_constants import PHOTO_FILE, PHOTO_VERSION_PARAM, RESIDENT_PHOTOS_BUCKET


def _bucket(db: AsyncClient):
    """The resident-photos bucket's file API."""
    return db.storage.from_(RESIDENT_PHOTOS_BUCKET)


def _path(resident_id: str) -> str:
    """Where the resident's photo sits in the bucket."""
    return f"{resident_id}/{PHOTO_FILE}"


def _version(changed_at: str | None) -> int:
    """When the photo last changed, in ms since epoch (0 if unknown), like the app's `Date.parse`."""
    return int(datetime.fromisoformat(changed_at).timestamp() * 1000) if changed_at else 0


async def get_resident_photo_url(db: AsyncClient, resident_id: str) -> str | None:
    """The photo's public link with `?v=<when it last changed>`, or None when she has no photo."""
    files = await _bucket(db).list(resident_id, {"search": PHOTO_FILE, "limit": 1})
    photo = next((file for file in files if file["name"] == PHOTO_FILE), None)
    if photo is None:
        return None
    url = await _bucket(db).get_public_url(_path(resident_id))
    version = _version(photo.get("updated_at") or photo.get("created_at"))
    return f"{url}?{PHOTO_VERSION_PARAM}={version}"


async def upload_resident_photo(db: AsyncClient, resident_id: str, content: bytes, content_type: str) -> None:
    """Store the photo in place of any old one, with its real content type."""
    await _bucket(db).upload(_path(resident_id), content, {"content-type": content_type, "upsert": "true"})


async def delete_resident_photo(db: AsyncClient, resident_id: str) -> bool:
    """Remove the photo; True when there was one to remove."""
    return bool(await _bucket(db).remove([_path(resident_id)]))
