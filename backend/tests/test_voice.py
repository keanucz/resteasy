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

from app.core.config import get_settings
from app.core.dependencies import get_cartesia, get_translator
from app.core.voice_constants import (
    CARTESIA_VERSION,
    CLIP_MAX_BYTES,
    CLONE_FAILED,
    DEFAULT_VOICE_ID,
    EMOTIONS,
    PREVIEW_CONTENT_TYPE,
    PREVIEW_FAILED,
    PREVIEW_LANGUAGES,
    PRONUNCIATION_FAILED,
    PRONUNCIATIONS_TABLE,
    SAMPLE_EMOTION,
    SAMPLE_TEXT,
    SAMPLE_TEXTS,
    STYLE_COLUMNS,
    TTS_MODEL,
    VOICE_IDS,
    VOICE_NOT_CONFIGURED,
    VOICES,
)
from app.crud.crud_constants import RESIDENTS_TABLE, VOICE_CLONES_TABLE
from app.main import app
from app.routers import voice as voice_router
from app.voice.cartesia import Cartesia, Speech, VoiceServiceError
from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID, UNKNOWN_RESIDENT_ID

VOICE_URL = f"/api/residents/{TEST_RESIDENT_ID}/voice"
PREVIEW_URL = f"{VOICE_URL}/preview"
CLONES_URL = f"{VOICE_URL}/clones"
STYLE_URL = f"{VOICE_URL}/style"
ACCENTS_URL = f"{VOICE_URL}/accents"
WORDS_URL = f"{VOICE_URL}/pronunciations"
PILLOW_VOICE_URL = f"/api/pillows/{TEST_PILLOW_ID}/voice"
SAMPLE_URL_BASE = "https://samples.test/"
FAKE_DICT_ID = "pdict_test"
SKYLAR = DEFAULT_VOICE_ID
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


FAKE_ACCENTS = [
    {"id": "british", "name": "British English", "locale": "en-GB", "is_localizable": True},
    {"id": "australian", "name": "Australian English", "locale": "en-AU", "is_localizable": True},
    {"id": "scouse", "name": "Scouse English", "locale": "en-GB", "is_localizable": False},
]


class FakeCartesia:
    """Stands in for app.voice.cartesia.Cartesia and records what it was asked."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.spoken: list[tuple[str, str, str]] = []
        self.speech: list[Speech | None] = []
        self.cloned: list[dict[str, Any]] = []
        self.localized: list[tuple[str, str, str]] = []
        self.dictionaries: list[tuple[str | None, list[dict[str, Any]]]] = []
        self.deleted: list[str] = []

    async def speak(self, voice_id: str, text: str, language: str, speech: Speech | None = None) -> bytes:
        if self.fail:
            raise VoiceServiceError(PREVIEW_FAILED)
        self.spoken.append((voice_id, text, language))
        self.speech.append(speech)
        return FAKE_MP3

    async def clone(
        self,
        clip: bytes,
        filename: str,
        content_type: str,
        name: str,
        language: str,
        accent: str | None = None,
    ) -> dict[str, Any]:
        if self.fail:
            raise VoiceServiceError(CLONE_FAILED)
        voice = {"id": f"{FAKE_CLONE_PREFIX}{secrets.token_hex(4)}", "name": name, "language": language}
        self.cloned.append(voice | {"bytes": len(clip), "content_type": content_type, "accent": accent})
        return voice

    async def accents(self, language: str) -> list[dict[str, Any]]:
        return FAKE_ACCENTS

    async def localize(self, voice_id: str, name: str, accent: str) -> dict[str, Any]:
        self.localized.append((voice_id, name, accent))
        return {"id": f"{FAKE_CLONE_PREFIX}{secrets.token_hex(4)}", "name": name}

    async def save_pronunciations(self, dict_id: str | None, name: str, items: list[dict[str, Any]]) -> str:
        if self.fail:
            raise VoiceServiceError(PRONUNCIATION_FAILED)
        self.dictionaries.append((dict_id, items))
        return dict_id or FAKE_DICT_ID

    async def delete(self, voice_id: str) -> None:
        self.deleted.append(voice_id)


@pytest.fixture
def cartesia(client: TestClient) -> FakeCartesia:
    """The fake Cartesia the routes use for this test."""
    fake = FakeCartesia()
    app.dependency_overrides[get_cartesia] = lambda: fake
    return fake


@pytest.fixture(autouse=True)
def samples(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Samples kept in memory instead of Supabase Storage, so a fake MP3 never lands in the shared
    stock folder; and Cartesia's accents asked for afresh in every test."""
    store: dict[str, bytes] = {}

    async def cached(db, resident_id: str) -> set[str]:
        return set(store)

    async def url(db, path: str) -> str:
        return f"{SAMPLE_URL_BASE}{path}"

    async def keep(db, path: str, mp3: bytes) -> str:
        store[path] = mp3
        return f"{SAMPLE_URL_BASE}{path}"

    async def forget(db, path: str) -> None:
        store.pop(path, None)

    for name, fake in {
        "cached_samples": cached,
        "sample_url": url,
        "store_sample": keep,
        "delete_sample": forget,
    }.items():
        monkeypatch.setattr(voice_router, name, fake)
    monkeypatch.setattr(voice_router, "_accents", {})
    return store


@pytest.fixture
def voice_settings_restored(db: Client) -> Iterator[None]:
    """Put back the test resident's voice, style and dictionary, and remove the words a test added."""
    resident = db.table(RESIDENTS_TABLE).select("*").eq("id", TEST_RESIDENT_ID).single().execute().data
    yield
    restore = {key: resident[key] for key in ("voice_id", *STYLE_COLUMNS, "pronunciation_dict_id")}
    db.table(RESIDENTS_TABLE).update(restore).eq("id", TEST_RESIDENT_ID).execute()
    db.table(PRONUNCIATIONS_TABLE).delete().eq("resident_id", TEST_RESIDENT_ID).execute()


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
        "accent": None,
        "base_voice_id": None,
        "sample_url": None,
        "samples": {},
    }
    assert listed["emotions"] == list(EMOTIONS)
    assert listed["language"] == "en"
    assert [lang["code"] for lang in listed["languages"]] == [code for code, _ in PREVIEW_LANGUAGES]
    assert set(listed["style"]) == {"speed", "volume", "emotion"}


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
    # The samples (one per preview language) are made just after the reply, so only the listing
    # has their links.
    listed = client.get(VOICE_URL, headers=owner).json()["voices"][-1]
    assert voice["sample_url"] is None and listed["sample_url"]
    assert set(listed["samples"]) == {code for code, _ in PREVIEW_LANGUAGES}
    assert listed | {"sample_url": None, "samples": {}} == voice

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
def test_a_browser_recording_with_a_codec_is_cloned(
    client: TestClient, owner_token: str, cartesia: FakeCartesia
):
    files = _clip(content_type="audio/webm;codecs=opus")
    made = client.post(CLONES_URL, files=files, data=_form(), headers=_bearer(owner_token))
    assert made.status_code == 201
    assert cartesia.cloned[0]["content_type"] == "audio/webm"


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


# ---------- the studio's Cartesia calls (mock transport, offline) ----------


def test_speak_sends_her_style_and_dictionary_and_drops_emotion_outside_english():
    cartesia, seen = _client_with(lambda _: httpx.Response(200, content=FAKE_MP3))
    speech = Speech(speed=1.1, volume=1.3, emotion="peaceful", pronunciation_dict_id="pdict_1")
    asyncio.run(cartesia.speak(GEMMA, "Hi", "en", speech))
    body = json.loads(seen[0].content)
    assert body["generation_config"] == {"speed": 1.1, "volume": 1.3, "emotion": "peaceful"}
    assert body["pronunciation_dict_id"] == "pdict_1"

    asyncio.run(cartesia.speak(GEMMA, "Hola", "es", speech))
    body = json.loads(seen[1].content)
    assert "emotion" not in body["generation_config"] and body["language"] == "es"


def test_speak_without_a_dictionary_sends_none():
    cartesia, seen = _client_with(lambda _: httpx.Response(200, content=FAKE_MP3))
    asyncio.run(cartesia.speak(GEMMA, "Hi", "en"))
    body = json.loads(seen[0].content)
    assert "pronunciation_dict_id" not in body and body["generation_config"]["emotion"] == "calm"


def test_clone_sends_the_speakers_accent_when_given():
    cartesia, seen = _client_with(lambda _: httpx.Response(200, json={"id": "v1"}))
    asyncio.run(cartesia.clone(b"audio", "a.wav", "audio/wav", "Sarah", "en", "british"))
    assert b'name="accent"\r\n\r\nbritish\r\n' in seen[0].content


def test_accents_and_localize_use_cartesias_paths():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/accents":
            return httpx.Response(200, json={"accents": FAKE_ACCENTS})
        return httpx.Response(200, json={"id": "v2", "name": "Skylar, British"})

    cartesia, seen = _client_with(handler)
    assert asyncio.run(cartesia.accents("en-GB")) == FAKE_ACCENTS
    assert seen[0].url.params["language"] == "en"
    assert asyncio.run(cartesia.localize(SKYLAR, "Skylar, British", "british"))["id"] == "v2"
    assert seen[1].method == "POST" and seen[1].url.path == "/voices/localize"
    assert json.loads(seen[1].content) == {"voice_id": SKYLAR, "name": "Skylar, British", "accent": "british"}


def test_pronunciations_patch_her_dictionary_or_make_one():
    items = [{"text": "Margaret", "pronunciation": "MAR-gret", "case_sensitive": False}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH" and request.url.path.endswith("/gone"):
            return httpx.Response(404)
        return httpx.Response(200, json={"id": "pdict_new"})

    cartesia, seen = _client_with(handler)
    assert asyncio.run(cartesia.save_pronunciations("pdict_1", "pillow-x", items)) == "pdict_1"
    assert seen[0].method == "PATCH" and json.loads(seen[0].content) == {"items": items}
    assert asyncio.run(cartesia.save_pronunciations(None, "pillow-x", items)) == "pdict_new"
    assert seen[1].method == "POST" and json.loads(seen[1].content) == {"name": "pillow-x", "items": items}
    assert asyncio.run(cartesia.save_pronunciations("gone", "pillow-x", items)) == "pdict_new"
    assert [r.method for r in seen[2:]] == ["PATCH", "POST"]


# ---------- the studio's routes, offline ----------


def test_studio_routes_need_a_valid_login(offline_client: TestClient):
    bad = _bearer("not-a-real-token")
    assert offline_client.get(f"{VOICE_URL}/samples/{GEMMA}", headers=bad).status_code == 401
    assert offline_client.put(STYLE_URL, json={"speed": 1}, headers=bad).status_code == 401
    assert offline_client.get(ACCENTS_URL, headers=bad).status_code == 401
    word = {"word": "a", "sounds_like": "b"}
    assert offline_client.post(WORDS_URL, json=word, headers=bad).status_code == 401


def test_the_pillow_needs_the_checkin_token(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "checkin_token", "pillow-secret")
    assert client.get(PILLOW_VOICE_URL).status_code == 401
    assert client.get(PILLOW_VOICE_URL, headers=_bearer("wrong")).status_code == 401


# ---------- the studio's routes, live Supabase (test resident only), fake Cartesia ----------


def test_a_sample_is_spoken_once_then_served_from_storage(
    client: TestClient, contact_token: str, cartesia: FakeCartesia, samples: dict[str, bytes]
):
    auth = _bearer(contact_token)
    first = client.get(f"{VOICE_URL}/samples/{GEMMA}", headers=auth)
    assert first.status_code == 200 and first.json() == {"url": f"{SAMPLE_URL_BASE}stock/{GEMMA}.mp3"}
    assert cartesia.spoken[0][:2] == (GEMMA, SAMPLE_TEXT) and cartesia.speech[0].emotion == SAMPLE_EMOTION
    assert samples == {f"stock/{GEMMA}.mp3": FAKE_MP3}

    again = client.get(f"{VOICE_URL}/samples/{GEMMA}", headers=auth)
    assert again.json() == first.json() and len(cartesia.spoken) == 1
    listed = client.get(VOICE_URL, headers=auth).json()["voices"]
    assert next(v for v in listed if v["id"] == GEMMA)["sample_url"] == first.json()["url"]
    assert client.get(f"{VOICE_URL}/samples/not-a-voice", headers=auth).status_code == 404


@pytest.mark.usefixtures("voice_settings_restored")
def test_the_owner_sets_how_it_speaks_and_previews_use_it(
    client: TestClient, owner_token: str, contact_token: str, cartesia: FakeCartesia
):
    owner = _bearer(owner_token)
    style = {"speed": 1.1, "volume": 1.3, "emotion": "peaceful"}
    assert client.put(STYLE_URL, json=style, headers=owner).json() == style
    assert client.get(VOICE_URL, headers=owner).json()["style"] == style

    assert client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=owner).status_code == 200
    assert cartesia.speech[-1] == Speech(
        speed=1.1, volume=1.3, emotion="peaceful", pronunciation_dict_id=None
    )
    draft = {"voice_id": GEMMA, "style": {"speed": 0.7, "volume": 1.0, "emotion": "calm"}}
    assert client.post(PREVIEW_URL, json=draft, headers=owner).status_code == 200
    assert cartesia.speech[-1].speed == 0.7

    assert client.put(STYLE_URL, json=style, headers=_bearer(contact_token)).status_code == 403
    for bad in ({"speed": 3}, {"volume": 0.1}, {"emotion": "angry"}):
        assert client.put(STYLE_URL, json=bad, headers=owner).status_code == 422


def test_the_pillow_reads_her_voice_with_the_token(
    client: TestClient, db: Client, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(get_settings(), "checkin_token", "pillow-secret")
    resident = db.table(RESIDENTS_TABLE).select("*").eq("id", TEST_RESIDENT_ID).single().execute().data
    voice = client.get(PILLOW_VOICE_URL, headers=_bearer("pillow-secret")).json()
    assert voice == {
        "voice_id": resident["voice_id"],
        "language": resident["language"],
        "speed": float(resident["voice_speed"]),
        "volume": float(resident["voice_volume"]),
        "emotion": resident["voice_emotion"],
        "pronunciation_dict_id": resident["pronunciation_dict_id"],
    }


def test_accents_are_the_localizable_ones_with_short_names(
    client: TestClient, contact_token: str, cartesia: FakeCartesia
):
    accents = client.get(ACCENTS_URL, headers=_bearer(contact_token)).json()
    assert accents == [
        {"id": "british", "name": "British", "locale": "en-GB"},
        {"id": "australian", "name": "Australian", "locale": "en-AU"},
    ]


@pytest.mark.usefixtures("clones_removed", "voice_settings_restored")
def test_an_accent_copy_joins_her_voices_once_with_its_sample(
    client: TestClient,
    owner_token: str,
    contact_token: str,
    cartesia: FakeCartesia,
    samples: dict[str, bytes],
):
    helper = _bearer(contact_token)
    made = client.post(ACCENTS_URL, json={"voice_id": SKYLAR, "accent": "british"}, headers=helper)
    assert made.status_code == 201
    copy = made.json()
    assert copy["name"] == "Skylar, British" and copy["source"] == "accent"
    assert copy["accent"] == "british" and copy["base_voice_id"] == SKYLAR
    assert cartesia.localized == [(SKYLAR, "Skylar, British", "british")]
    assert copy["sample_url"] == f"{SAMPLE_URL_BASE}{TEST_RESIDENT_ID}/{copy['id']}.mp3"

    again = client.post(ACCENTS_URL, json={"voice_id": SKYLAR, "accent": "british"}, headers=helper)
    assert again.json()["id"] == copy["id"] and len(cartesia.localized) == 1
    # A copy of a copy starts from the original voice
    aussie = client.post(ACCENTS_URL, json={"voice_id": copy["id"], "accent": "australian"}, headers=helper)
    assert aussie.json()["base_voice_id"] == SKYLAR and cartesia.localized[-1][1] == "Skylar, Australian"

    bad = client.post(ACCENTS_URL, json={"voice_id": SKYLAR, "accent": "scouse"}, headers=helper)
    assert bad.status_code == 422
    assert (
        client.put(VOICE_URL, json={"voice_id": copy["id"]}, headers=_bearer(owner_token)).status_code == 200
    )
    assert client.delete(f"{CLONES_URL}/{copy['id']}", headers=helper).status_code == 204
    assert f"{TEST_RESIDENT_ID}/{copy['id']}.mp3" not in samples


@pytest.mark.usefixtures("clones_removed")
def test_a_clone_keeps_the_speakers_accent(
    client: TestClient, owner_token: str, cartesia: FakeCartesia, samples: dict[str, bytes]
):
    owner = _bearer(owner_token)
    made = client.post(CLONES_URL, files=_clip(), data=_form() | {"accent": "british"}, headers=owner).json()
    assert made["accent"] == "british" and cartesia.cloned[0]["accent"] == "british"
    # The reply doesn't wait for the sample; it is made just after (TestClient runs it before returning).
    assert made["sample_url"] is None
    assert f"{TEST_RESIDENT_ID}/{made['id']}.mp3" in samples
    bad = client.post(CLONES_URL, files=_clip(), data=_form() | {"accent": "martian"}, headers=owner)
    assert bad.status_code == 422


@pytest.mark.usefixtures("voice_settings_restored")
def test_words_sync_her_dictionary_and_previews_use_it(
    client: TestClient, db: Client, owner_token: str, contact_token: str, cartesia: FakeCartesia
):
    helper, owner = _bearer(contact_token), _bearer(owner_token)
    db.table(RESIDENTS_TABLE).update({"pronunciation_dict_id": None}).eq("id", TEST_RESIDENT_ID).execute()
    db.table(PRONUNCIATIONS_TABLE).delete().eq("resident_id", TEST_RESIDENT_ID).execute()

    added = client.post(WORDS_URL, json={"word": " Margaret ", "sounds_like": "MAR-gret"}, headers=helper)
    assert added.status_code == 201
    word = added.json()
    assert word["word"] == "Margaret" and word["created_by_name"] == "Test Helper"
    assert cartesia.dictionaries[-1] == (
        None,
        [{"text": "Margaret", "pronunciation": "MAR-gret", "case_sensitive": False}],
    )
    assert client.get(WORDS_URL, headers=owner).json() == [word]

    twice = client.post(WORDS_URL, json={"word": "margaret", "sounds_like": "x"}, headers=owner)
    assert twice.status_code == 409
    client.post(WORDS_URL, json={"word": "Warfarin", "sounds_like": "WAR-fuh-rin"}, headers=owner)
    assert cartesia.dictionaries[-1][0] == FAKE_DICT_ID and len(cartesia.dictionaries[-1][1]) == 2

    client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=owner)
    assert cartesia.speech[-1].pronunciation_dict_id == FAKE_DICT_ID

    warfarin = next(w for w in client.get(WORDS_URL, headers=owner).json() if w["word"] == "Warfarin")
    assert client.delete(f"{WORDS_URL}/{warfarin['id']}", headers=helper).status_code == 403
    assert client.delete(f"{WORDS_URL}/{word['id']}", headers=helper).status_code == 204
    assert [i["text"] for i in cartesia.dictionaries[-1][1]] == ["Warfarin"]
    assert client.delete(f"{WORDS_URL}/{word['id']}", headers=helper).status_code == 404


@pytest.mark.usefixtures("voice_settings_restored")
def test_a_word_cartesia_refuses_is_not_listed(client: TestClient, db: Client, owner_token: str):
    db.table(PRONUNCIATIONS_TABLE).delete().eq("resident_id", TEST_RESIDENT_ID).execute()
    app.dependency_overrides[get_cartesia] = lambda: FakeCartesia(fail=True)
    owner = _bearer(owner_token)
    response = client.post(WORDS_URL, json={"word": "Margaret", "sounds_like": "x"}, headers=owner)
    assert response.status_code == 502 and response.json() == {"detail": PRONUNCIATION_FAILED}
    assert client.get(WORDS_URL, headers=owner).json() == []


# ---------- preview languages ----------


class FakeTranslator:
    """Stands in for app.voice.translate.Translator: marks the line with the language."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    async def translate(self, text: str, language: str) -> str:
        self.asked.append((text, language))
        return text if language == "en" else f"[{language}] {text}"


@pytest.fixture
def preview_language_restored(db: Client) -> Iterator[None]:
    """Put the test resident's preview language back to English."""
    yield
    db.table(RESIDENTS_TABLE).update({"preview_language": "en"}).eq("id", TEST_RESIDENT_ID).execute()


@pytest.mark.usefixtures("preview_language_restored")
def test_a_sample_in_another_language_is_kept_beside_the_english_one(
    client: TestClient, contact_token: str, cartesia: FakeCartesia, samples: dict[str, bytes]
):
    auth = _bearer(contact_token)
    polish = client.get(f"{VOICE_URL}/samples/{GEMMA}", params={"language": "pl"}, headers=auth)
    assert polish.json() == {"url": f"{SAMPLE_URL_BASE}stock/{GEMMA}.pl.mp3"}
    assert cartesia.spoken[0] == (GEMMA, SAMPLE_TEXTS["pl"], "pl")
    english = client.get(f"{VOICE_URL}/samples/{GEMMA}", headers=auth)
    assert english.json() == {"url": f"{SAMPLE_URL_BASE}stock/{GEMMA}.mp3"}
    listed = next(v for v in client.get(VOICE_URL, headers=auth).json()["voices"] if v["id"] == GEMMA)
    assert listed["samples"] == {"en": english.json()["url"], "pl": polish.json()["url"]}
    unknown = client.get(f"{VOICE_URL}/samples/{GEMMA}", params={"language": "xx"}, headers=auth)
    assert unknown.status_code == 422


@pytest.mark.usefixtures("preview_language_restored")
def test_choosing_a_language_swaps_the_samples_and_makes_the_missing_ones(
    client: TestClient, db: Client, owner_token: str, cartesia: FakeCartesia, samples: dict[str, bytes]
):
    auth = _bearer(owner_token)
    chosen = client.put(f"{VOICE_URL}/language", json={"language": "es"}, headers=auth)
    assert chosen.json() == {"language": "es"}
    stored = db.table(RESIDENTS_TABLE).select("preview_language").eq("id", TEST_RESIDENT_ID).single()
    assert stored.execute().data["preview_language"] == "es"
    # every voice she may pick now has its Spanish sample (made after the reply)
    assert {f"stock/{voice_id}.es.mp3" for voice_id, _, _ in VOICES} <= set(samples)
    listed = client.get(VOICE_URL, headers=auth).json()
    assert listed["language"] == "es"
    gemma = next(v for v in listed["voices"] if v["id"] == GEMMA)
    assert gemma["sample_url"] == f"{SAMPLE_URL_BASE}stock/{GEMMA}.es.mp3"
    bad = client.put(f"{VOICE_URL}/language", json={"language": "klingon"}, headers=auth)
    assert bad.status_code == 422


@pytest.mark.usefixtures("preview_language_restored")
def test_previews_speak_the_preview_language_and_translate_a_typed_line(
    client: TestClient, db: Client, owner_token: str, cartesia: FakeCartesia
):
    translator = FakeTranslator()
    app.dependency_overrides[get_translator] = lambda: translator
    auth = _bearer(owner_token)
    resident = db.table(RESIDENTS_TABLE).select("*").eq("id", TEST_RESIDENT_ID).single().execute().data
    client.put(f"{VOICE_URL}/language", json={"language": "fr"}, headers=auth)
    cartesia.spoken.clear()
    assert client.post(PREVIEW_URL, json={"voice_id": GEMMA}, headers=auth).status_code == 200
    assert cartesia.spoken[-1] == (
        GEMMA,
        f"Bonjour {resident['preferred_name']}, c'est l'heure de prendre tes comprimés pour le cœur.",
        "fr",
    )
    typed = {"voice_id": GEMMA, "text": "Goodnight."}
    assert client.post(PREVIEW_URL, json=typed, headers=auth).status_code == 200
    assert cartesia.spoken[-1] == (GEMMA, "[fr] Goodnight.", "fr")
    asked = {"voice_id": GEMMA, "text": "Goodnight.", "language": "de"}
    client.post(PREVIEW_URL, json=asked, headers=auth)
    assert cartesia.spoken[-1] == (GEMMA, "[de] Goodnight.", "de")
