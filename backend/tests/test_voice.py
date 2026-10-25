"""Voice API: the Cartesia client against a mock transport, then the routes against live Supabase.

Cartesia is never called for real here (no clones, no credits): the routes get a fake client. The
live tests only touch the test resident (the owner of `test-pillow`), never `mum`'s household; her
voice is put back by the login fixtures and every clone row a test makes is removed.
"""

import asyncio
import json
import secrets
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.core.dependencies import get_cartesia
from app.core.voice_constants import (
    CARTESIA_VERSION,
    CLIP_MAX_BYTES,
    CLONE_FAILED,
    DEFAULT_VOICE_ID,
    PREVIEW_CONTENT_TYPE,
    PREVIEW_FAILED,
    TTS_MODEL,
    VOICE_IDS,
    VOICE_NOT_CONFIGURED,
    VOICES,
)
from app.crud.crud_constants import RESIDENTS_TABLE, VOICE_CLONES_TABLE
from app.main import app
from app.voice.cartesia import Cartesia, VoiceServiceError
from tests.seed_constants import TEST_RESIDENT_ID, UNKNOWN_RESIDENT_ID

VOICE_URL = f"/api/residents/{TEST_RESIDENT_ID}/voice"
PREVIEW_URL = f"{VOICE_URL}/preview"
CLONES_URL = f"{VOICE_URL}/clones"
# Every clone the fake makes has this prefix, so cleanup can never remove a real one
FAKE_CLONE_PREFIX = "test-clone-"
FAKE_MP3 = b"ID3fake-mp3"
GEMMA = "62ae83ad-4f6a-430b-af41-a9bede9286ca"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _clip(content: bytes = b"\0" * 2048, content_type: str = "audio/mp4") -> dict:
    """The multipart file of a clone upload."""
    return {"clip": ("sarah.m4a", content, content_type)}


def _form(name: str = "Sarah", consent: str = "true") -> dict[str, str]:
    return {"name": name, "consent": consent}


class FakeCartesia:
    """Stands in for app.voice.cartesia.Cartesia and records what it was asked."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.spoken: list[tuple[str, str, str]] = []
        self.cloned: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    async def speak(self, voice_id: str, text: str, language: str) -> bytes:
        if self.fail:
            raise VoiceServiceError(PREVIEW_FAILED)
        self.spoken.append((voice_id, text, language))
        return FAKE_MP3

    async def clone(
        self, clip: bytes, filename: str, content_type: str, name: str, language: str
    ) -> dict[str, Any]:
        if self.fail:
            raise VoiceServiceError(CLONE_FAILED)
        voice = {"id": f"{FAKE_CLONE_PREFIX}{secrets.token_hex(4)}", "name": name, "language": language}
        self.cloned.append(voice | {"bytes": len(clip), "content_type": content_type})
        return voice

    async def delete(self, voice_id: str) -> None:
        self.deleted.append(voice_id)


@pytest.fixture
def cartesia(client: TestClient) -> FakeCartesia:
    """The fake Cartesia the routes use for this test."""
    fake = FakeCartesia()
    app.dependency_overrides[get_cartesia] = lambda: fake
    return fake


@pytest.fixture
def clones_removed(db: Client) -> Iterator[None]:
    """Remove every clone row a test made for the test resident."""
    yield
    db.table(VOICE_CLONES_TABLE).delete().eq("resident_id", TEST_RESIDENT_ID).like(
        "voice_id", f"{FAKE_CLONE_PREFIX}%"
    ).execute()


def _current_voice(db: Client) -> str:
    return (
        db.table(RESIDENTS_TABLE)
        .select("voice_id")
        .eq("id", TEST_RESIDENT_ID)
        .single()
        .execute()
        .data["voice_id"]
    )


# ---------- the Cartesia client (mock transport, offline) ----------


def _client_with(handler) -> tuple[Cartesia, list[httpx.Request]]:
    """A Cartesia client whose requests go to `handler`, and the requests it saw."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return Cartesia("sk_car_test", http=httpx.AsyncClient(transport=httpx.MockTransport(record))), seen


def test_speak_sends_the_pillow_model_version_and_mp3_format():
    cartesia, seen = _client_with(lambda _: httpx.Response(200, content=FAKE_MP3))
    assert asyncio.run(cartesia.speak(GEMMA, "Hello Margaret", "en-GB")) == FAKE_MP3
    request = seen[0]
    assert request.url == "https://api.cartesia.ai/tts/bytes"
    assert request.headers["Cartesia-Version"] == CARTESIA_VERSION
    assert request.headers["Authorization"] == "Bearer sk_car_test"
    body = json.loads(request.content)
    assert body["model_id"] == TTS_MODEL and body["voice"] == {"id": GEMMA}
    assert body["transcript"] == "Hello Margaret" and body["language"] == "en-GB"
    assert body["output_format"]["container"] == "mp3"


def test_clone_posts_the_clip_with_a_base_language():
    voice = {"id": "v1", "name": "Sarah", "created_at": "2026-10-25T10:00:00Z"}
    cartesia, seen = _client_with(lambda _: httpx.Response(200, json=voice))
    assert asyncio.run(cartesia.clone(b"audio", "sarah.m4a", "audio/mp4", "Sarah", "en-GB")) == voice
    request = seen[0]
    assert request.method == "POST" and request.url.path == "/voices/clone"
    body = request.content
    assert b'name="clip"; filename="sarah.m4a"' in body and b"audio/mp4" in body
    assert b'name="language"\r\n\r\nen\r\n' in body and b'name="name"\r\n\r\nSarah\r\n' in body


def test_delete_treats_a_voice_cartesia_no_longer_has_as_removed():
    cartesia, seen = _client_with(lambda _: httpx.Response(404))
    asyncio.run(cartesia.delete("gone"))
    assert seen[0].method == "DELETE" and seen[0].url.path == "/voices/gone"


@pytest.mark.parametrize(
    "handler",
    [lambda _: httpx.Response(500, json={"error": "boom"}), lambda _: httpx.Response(401)],
    ids=["server-error", "bad-key"],
)
def test_a_cartesia_refusal_is_a_voice_service_error(handler):
    cartesia, _ = _client_with(handler)
    with pytest.raises(VoiceServiceError, match="could not make this preview"):
        asyncio.run(cartesia.speak(GEMMA, "Hi", "en"))


def test_an_unreachable_cartesia_is_a_voice_service_error():
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    cartesia, _ = _client_with(unreachable)
    with pytest.raises(VoiceServiceError, match="could not clone"):
        asyncio.run(cartesia.clone(b"audio", "a.wav", "audio/wav", "Sarah", "en"))


def test_the_stock_voices_are_a_short_list_with_the_default_and_gemma():
    assert 4 <= len(VOICES) <= 6
    assert {DEFAULT_VOICE_ID, GEMMA} <= VOICE_IDS


# ---------- routes, offline ----------


def test_voice_routes_need_a_valid_login(offline_client: TestClient):
    bad = _bearer("not-a-real-token")
    assert offline_client.get(VOICE_URL).status_code == 401
    assert offline_client.put(VOICE_URL, json={"voice_id": GEMMA}, headers=bad).status_code == 401
    assert offline_client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=bad).status_code == 401
    assert offline_client.delete(f"{CLONES_URL}/x", headers=bad).status_code == 401


# ---------- live Supabase (test resident only), fake Cartesia ----------


def test_anyone_in_her_circle_lists_the_stock_voices_and_her_current_one(
    client: TestClient, db: Client, contact_token: str
):
    listed = client.get(VOICE_URL, headers=_bearer(contact_token)).json()
    assert listed["current"] == _current_voice(db)
    stock = [v for v in listed["voices"] if v["source"] == "stock"]
    assert [v["id"] for v in stock] == [voice_id for voice_id, _, _ in VOICES]
    assert stock[0] == {
        "id": DEFAULT_VOICE_ID,
        "name": "Skylar",
        "description": VOICES[0][2],
        "source": "stock",
        "created_by_name": None,
        "created_at": None,
    }


def test_preview_says_a_line_with_her_name_by_default(
    client: TestClient, db: Client, contact_token: str, cartesia: FakeCartesia
):
    resident = db.table(RESIDENTS_TABLE).select("*").eq("id", TEST_RESIDENT_ID).single().execute().data
    response = client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=_bearer(contact_token))
    assert response.status_code == 200
    assert response.content == FAKE_MP3 and response.headers["content-type"] == PREVIEW_CONTENT_TYPE
    voice_id, text, language = cartesia.spoken[0]
    assert voice_id == GEMMA and language == resident["language"]
    assert text == f"Hello {resident['preferred_name']}, it's time to take your heart tablets."

    custom = client.post(
        PREVIEW_URL, json={"voice_id": GEMMA, "text": "  Goodnight.  "}, headers=_bearer(contact_token)
    )
    assert custom.status_code == 200 and cartesia.spoken[1][1] == "Goodnight."


def test_preview_refuses_unknown_voices_and_long_text(
    client: TestClient, owner_token: str, cartesia: FakeCartesia
):
    auth = _bearer(owner_token)
    assert client.post(PREVIEW_URL, json={"voice_id": "not-a-voice"}, headers=auth).status_code == 404
    too_long = {"voice_id": GEMMA, "text": "a" * 201}
    assert client.post(PREVIEW_URL, json=too_long, headers=auth).status_code == 422
    assert cartesia.spoken == []


def test_a_cartesia_failure_is_a_502_with_a_sentence(client: TestClient, owner_token: str):
    app.dependency_overrides[get_cartesia] = lambda: FakeCartesia(fail=True)
    response = client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=_bearer(owner_token))
    assert response.status_code == 502 and response.json() == {"detail": PREVIEW_FAILED}


def test_no_cartesia_key_is_a_503(client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app.state, "cartesia", None)
    response = client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=_bearer(owner_token))
    assert response.status_code == 503 and response.json() == {"detail": VOICE_NOT_CONFIGURED}


def test_owner_picks_a_stock_voice(client: TestClient, db: Client, owner_token: str):
    auth = _bearer(owner_token)
    voice = next(v for v in VOICE_IDS if v != _current_voice(db))
    assert client.put(VOICE_URL, json={"voice_id": voice}, headers=auth).json() == {"current": voice}
    assert _current_voice(db) == voice
    assert client.get(VOICE_URL, headers=auth).json()["current"] == voice
    assert client.put(VOICE_URL, json={"voice_id": "not-a-voice"}, headers=auth).status_code == 404


def test_only_the_owner_picks_the_voice(client: TestClient, contact_token: str, stranger_token: str):
    assert client.put(VOICE_URL, json={"voice_id": GEMMA}, headers=_bearer(contact_token)).status_code == 403
    assert client.get(VOICE_URL, headers=_bearer(stranger_token)).status_code == 403
    preview = client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=_bearer(stranger_token))
    assert preview.status_code == 403


@pytest.mark.usefixtures("clones_removed")
def test_a_contact_clones_a_voice_the_owner_picks_and_the_creator_removes(
    client: TestClient, db: Client, owner_token: str, contact_token: str, cartesia: FakeCartesia
):
    helper, owner = _bearer(contact_token), _bearer(owner_token)
    made = client.post(CLONES_URL, files=_clip(), data=_form(" Sarah "), headers=helper)
    assert made.status_code == 201
    voice = made.json()
    assert voice["id"].startswith(FAKE_CLONE_PREFIX) and voice["name"] == "Sarah"
    assert voice["source"] == "clone" and voice["created_by_name"] == "Test Helper"
    assert voice["description"] is None and voice["created_at"]
    assert cartesia.cloned[0]["content_type"] == "audio/mp4" and cartesia.cloned[0]["bytes"] == 2048
    assert client.get(VOICE_URL, headers=owner).json()["voices"][-1] == voice

    assert client.post(PREVIEW_URL, json={"voice_id": voice["id"]}, headers=helper).status_code == 200
    assert client.put(VOICE_URL, json={"voice_id": voice["id"]}, headers=owner).json() == {
        "current": voice["id"]
    }

    assert client.delete(f"{CLONES_URL}/{voice['id']}", headers=helper).status_code == 204
    assert cartesia.deleted == [voice["id"]]
    assert _current_voice(db) == DEFAULT_VOICE_ID  # she heard it, so she is back on the default
    assert all(v["id"] != voice["id"] for v in client.get(VOICE_URL, headers=owner).json()["voices"])
    assert client.delete(f"{CLONES_URL}/{voice['id']}", headers=helper).status_code == 404


@pytest.mark.usefixtures("clones_removed")
def test_only_the_creator_or_the_owner_removes_a_clone(
    client: TestClient, db: Client, owner_token: str, contact_token: str, cartesia: FakeCartesia
):
    current = _current_voice(db)
    voice = client.post(CLONES_URL, files=_clip(), data=_form(), headers=_bearer(owner_token)).json()
    assert client.delete(f"{CLONES_URL}/{voice['id']}", headers=_bearer(contact_token)).status_code == 403
    assert cartesia.deleted == []
    assert client.delete(f"{CLONES_URL}/{voice['id']}", headers=_bearer(owner_token)).status_code == 204
    assert _current_voice(db) == current  # not her voice, so it stays


@pytest.mark.usefixtures("clones_removed")
@pytest.mark.parametrize(
    ("files", "data", "expected"),
    [
        (_clip(), _form(consent="false"), 422),
        (_clip(), {"name": "Sarah"}, 422),
        (_clip(), _form(name="x" * 41), 422),
        (_clip(), _form(name="   "), 422),
        (_clip(content_type="text/plain"), _form(), 422),
        (_clip(content=b""), _form(), 422),
        (_clip(content=b"\0" * (CLIP_MAX_BYTES + 1)), _form(), 413),
        (None, _form(), 422),
    ],
    ids=[
        "no-consent",
        "consent-missing",
        "long-name",
        "blank-name",
        "text",
        "empty",
        "over-10-mb",
        "no-clip",
    ],
)
def test_a_bad_clone_upload_is_refused_before_cartesia(
    client: TestClient, owner_token: str, cartesia: FakeCartesia, files, data, expected
):
    response = client.post(CLONES_URL, files=files, data=data, headers=_bearer(owner_token))
    assert response.status_code == expected
    assert cartesia.cloned == []


@pytest.mark.usefixtures("clones_removed")
def test_a_failed_clone_stores_nothing(client: TestClient, db: Client, owner_token: str):
    app.dependency_overrides[get_cartesia] = lambda: FakeCartesia(fail=True)
    response = client.post(CLONES_URL, files=_clip(), data=_form(), headers=_bearer(owner_token))
    assert response.status_code == 502 and response.json() == {"detail": CLONE_FAILED}
    assert (
        db.table(VOICE_CLONES_TABLE).select("voice_id").eq("resident_id", TEST_RESIDENT_ID).execute().data
        == []
    )


def test_unknown_resident_is_404(client: TestClient, owner_token: str):
    assert (
        client.get(f"/api/residents/{UNKNOWN_RESIDENT_ID}/voice", headers=_bearer(owner_token)).status_code
        == 404
    )
