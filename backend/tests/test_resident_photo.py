"""Resident photo API: offline checks, then live Supabase Storage.

The live tests only touch the test resident's folder (the owner of `test-pillow`), never `mum`'s
household, and put back whatever photo was there before.
"""

import base64
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.core.app_constants import FAMILY_APP_AGENT, PHOTO_MAX_BYTES
from app.crud.crud_constants import AGENT_LOG_TABLE, PHOTO_FILE, RESIDENT_PHOTOS_BUCKET
from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID, UNKNOWN_RESIDENT_ID

PHOTO_URL = f"/api/residents/{TEST_RESIDENT_ID}/photo"
PHOTO_PATH = f"{TEST_RESIDENT_ID}/{PHOTO_FILE}"
# A 1x1 PNG, so the stored object is a real image
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _file(content: bytes = PNG, content_type: str = "image/png") -> dict:
    """The multipart body of a photo upload."""
    return {"file": ("photo.png", content, content_type)}


def _latest_app_log(db: Client) -> dict:
    """The newest agent_log row the family app wrote on the test pillow."""
    rows = (
        db.table(AGENT_LOG_TABLE)
        .select("intent, tool, args")
        .eq("pillow_id", TEST_PILLOW_ID)
        .eq("agent", FAMILY_APP_AGENT)
        .order("ts", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0]


@pytest.fixture
def photo_restored(db: Client) -> Iterator[None]:
    """Put the test resident's photo back as it was (or remove it) after the test."""
    bucket = db.storage.from_(RESIDENT_PHOTOS_BUCKET)
    before = bucket.list(TEST_RESIDENT_ID, {"search": PHOTO_FILE, "limit": 1})
    saved = next((file for file in before if file["name"] == PHOTO_FILE), None)
    original = bucket.download(PHOTO_PATH) if saved else None
    try:
        yield
    finally:
        bucket.remove([PHOTO_PATH])
        if original is not None:
            content_type = saved["metadata"]["mimetype"]
            bucket.upload(PHOTO_PATH, original, {"content-type": content_type, "upsert": "true"})


# ---------- offline ----------


def test_photo_needs_a_valid_login(offline_client: TestClient):
    bad = _bearer("not-a-real-token")
    assert offline_client.get(PHOTO_URL).status_code == 401
    assert offline_client.put(PHOTO_URL, files=_file(), headers=bad).status_code == 401
    assert offline_client.delete(PHOTO_URL, headers=bad).status_code == 401


# ---------- live Supabase (test resident only) ----------


@pytest.mark.usefixtures("photo_restored")
def test_owner_uploads_reads_and_removes_the_photo(client: TestClient, db: Client, owner_token: str):
    auth = _bearer(owner_token)
    uploaded = client.put(PHOTO_URL, files=_file(), headers=auth)
    assert uploaded.status_code == 200
    url = uploaded.json()["url"]
    link, _, version = url.partition("?v=")
    assert link.endswith(f"/{RESIDENT_PHOTOS_BUCKET}/{PHOTO_PATH}") and int(version) > 0
    assert client.get(PHOTO_URL, headers=auth).json() == {"url": url}
    served = httpx.get(url)
    assert served.content == PNG and served.headers["content-type"] == "image/png"
    assert _latest_app_log(db) == {
        "intent": "change settings",
        "tool": "photo",
        "args": {"photo": "updated", "content_type": "image/png"},
    }

    assert client.delete(PHOTO_URL, headers=auth).status_code == 204
    assert client.get(PHOTO_URL, headers=auth).json() == {"url": None}
    assert _latest_app_log(db)["args"] == {"photo": "removed"}
    assert client.delete(PHOTO_URL, headers=auth).status_code == 204  # nothing left to remove


@pytest.mark.usefixtures("photo_restored")
@pytest.mark.parametrize(
    ("content", "content_type", "expected"),
    [
        (PNG, "image/gif", 422),
        (PNG, "text/plain", 422),
        (b"", "image/png", 422),
        (b"\0" * (PHOTO_MAX_BYTES + 1), "image/jpeg", 413),
    ],
    ids=["gif", "text", "empty", "over-5-mb"],
)
def test_a_bad_photo_is_refused_and_nothing_changes(
    client: TestClient, owner_token: str, content: bytes, content_type: str, expected: int
):
    auth = _bearer(owner_token)
    before = client.get(PHOTO_URL, headers=auth).json()
    response = client.put(PHOTO_URL, files=_file(content, content_type), headers=auth)
    assert response.status_code == expected
    assert client.get(PHOTO_URL, headers=auth).json() == before


def test_an_upload_without_a_file_is_422(client: TestClient, owner_token: str):
    assert client.put(PHOTO_URL, headers=_bearer(owner_token)).status_code == 422


@pytest.mark.usefixtures("photo_restored")
def test_a_plain_contact_sees_but_cannot_change_the_photo(client: TestClient, contact_token: str):
    auth = _bearer(contact_token)
    assert client.get(PHOTO_URL, headers=auth).status_code == 200
    assert client.put(PHOTO_URL, files=_file(), headers=auth).status_code == 403
    assert client.delete(PHOTO_URL, headers=auth).status_code == 403


@pytest.mark.usefixtures("photo_restored")
def test_a_login_that_does_not_look_after_her_gets_403(client: TestClient, stranger_token: str):
    auth = _bearer(stranger_token)
    assert client.get(PHOTO_URL, headers=auth).status_code == 403
    assert client.put(PHOTO_URL, files=_file(), headers=auth).status_code == 403
    assert client.delete(PHOTO_URL, headers=auth).status_code == 403


def test_unknown_resident_is_404_and_a_malformed_id_422(client: TestClient, owner_token: str):
    auth = _bearer(owner_token)
    assert client.get(f"/api/residents/{UNKNOWN_RESIDENT_ID}/photo", headers=auth).status_code == 404
    assert client.get("/api/residents/not-a-uuid/photo", headers=auth).status_code == 422
