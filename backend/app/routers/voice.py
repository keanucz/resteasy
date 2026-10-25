"""Voice router: which voice the pillow speaks to her with and how, a sample and previews of each,
voices cloned from someone she knows, accent copies of a voice, and words it says her way.

Anyone who looks after her lists and hears voices, and may add a voice (a clone, with the consent
of the person recorded, or an accent copy) or a word; only the owner picks the voice she hears and
how it speaks. A voice or word is removed by whoever added it or by the owner. Cartesia is called
from here only, so its key never reaches the app; requests carry the app's Supabase access token,
like the residents router.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Response, status

from app.core.app_constants import FAMILY_APP_AGENT, SETTINGS_CHANGE_INTENT
from app.core.dependencies import (
    CartesiaDep,
    CloneUploadDep,
    OwnedResidentDep,
    ResidentLoginDep,
    SupabaseDep,
    ViewedResidentDep,
)
from app.core.voice_constants import (
    ACCENT_COPY_NAME,
    ACCENT_NAME_SUFFIX,
    ACCENT_SOURCE,
    CLONE_NAME_MAX,
    CLONE_SOURCE,
    DEFAULT_VOICE_ID,
    EMOTIONS,
    NOT_CLONE_CREATOR,
    NOT_PRONUNCIATION_CREATOR,
    PREVIEW_CONTENT_TYPE,
    PREVIEW_TEXT,
    PRONUNCIATION_DICT_NAME,
    PRONUNCIATION_EXISTS,
    PRONUNCIATIONS_FULL,
    PRONUNCIATIONS_MAX,
    SAMPLE_EMOTION,
    SAMPLE_SPEED,
    SAMPLE_TEXT,
    STYLE_COLUMNS,
    UNKNOWN_ACCENT,
    UNKNOWN_PRONUNCIATION,
    UNKNOWN_VOICE,
    VOICE_TOOL,
    VOICES,
)
from app.crud.night_log import log_resident_action
from app.crud.pronunciations import (
    create_pronunciation,
    delete_pronunciation,
    get_pronunciation,
    list_pronunciations,
)
from app.crud.residents import update_resident
from app.crud.voice_clones import (
    create_voice_clone,
    delete_voice_clone,
    find_accent_copy,
    get_voice_clone,
    is_offered_voice,
    list_voice_clones,
)
from app.crud.voice_samples import cached_samples, delete_sample, sample_path, sample_url, store_sample
from app.schemas.voice import (
    Accent,
    AccentRequest,
    CurrentVoice,
    Pronunciation,
    PronunciationRequest,
    ResidentVoice,
    ResidentVoices,
    SampleLink,
    VoiceChoice,
    VoicePreviewRequest,
    VoiceStyle,
)
from app.voice.cartesia import Cartesia, Speech, VoiceServiceError, base_language

log = logging.getLogger(__name__)

router = APIRouter(prefix="/residents/{resident_id}/voice", tags=["voice"])

# Cartesia's accents per language: they change rarely, so each is asked for once per process
_accents: dict[str, list[Accent]] = {}


@router.get("")
async def read_voices(resident: ViewedResidentDep, db: SupabaseDep) -> ResidentVoices:
    """The voice she hears now and how it speaks, then every voice the owner may pick: the stock
    voices, then her own (clones and accent copies), oldest first, each with its sample's link once
    one has been made."""
    stock = [ResidentVoice.stock(*voice) for voice in VOICES]
    own = [ResidentVoice.clone(row) for row in await list_voice_clones(db, resident["id"])]
    cached = await cached_samples(db, resident["id"])
    for voice in stock + own:
        path = sample_path(resident["id"], voice.id)
        if path in cached:
            voice.sample_url = await sample_url(db, path)
    return ResidentVoices(
        current=resident["voice_id"],
        style=VoiceStyle.of(resident),
        emotions=list(EMOTIONS),
        voices=stock + own,
    )


@router.get("/samples/{voice_id}")
async def read_sample(
    resident: ViewedResidentDep, voice_id: str, db: SupabaseDep, cartesia: CartesiaDep
) -> SampleLink:
    """Where to play the voice saying the sample line. Cartesia speaks it the first time only;
    after that it comes from Supabase Storage."""
    await _require_offered(db, resident, voice_id)
    path = sample_path(resident["id"], voice_id)
    if path in await cached_samples(db, resident["id"]):
        return SampleLink(url=await sample_url(db, path))
    return SampleLink(url=await _make_sample(db, cartesia, resident, voice_id))


@router.post("/preview", response_class=Response, responses={200: {"content": {PREVIEW_CONTENT_TYPE: {}}}})
async def preview_voice(
    resident: ViewedResidentDep, preview: VoicePreviewRequest, db: SupabaseDep, cartesia: CartesiaDep
) -> Response:
    """MP3 of the voice saying `text` (at most 200 characters), or a line with her name, spoken as
    she hears it (or in the `style` being tried) with her words said her way. Nothing is stored."""
    await _require_offered(db, resident, preview.voice_id)
    text = preview.text or PREVIEW_TEXT.format(name=resident["preferred_name"])
    style = preview.style or VoiceStyle.of(resident)
    speech = Speech(**style.model_dump(), pronunciation_dict_id=resident["pronunciation_dict_id"])
    audio = await cartesia.speak(preview.voice_id, text, resident["language"], speech)
    return Response(content=audio, media_type=PREVIEW_CONTENT_TYPE)


@router.put("")
async def choose_voice(resident: OwnedResidentDep, choice: VoiceChoice, db: SupabaseDep) -> CurrentVoice:
    """Set the voice the pillow speaks to her with: a stock voice or one of her own. Owner only."""
    await _require_offered(db, resident, choice.voice_id)
    await _set_voice(db, resident, choice.voice_id)
    return CurrentVoice(current=choice.voice_id)


@router.put("/style")
async def save_style(resident: OwnedResidentDep, style: VoiceStyle, db: SupabaseDep) -> VoiceStyle:
    """Set how the pillow speaks to her: speed, volume and tone. Owner only."""
    fields = dict(zip(STYLE_COLUMNS, (style.speed, style.volume, style.emotion), strict=True))
    await _change(db, resident, fields)
    return style


@router.get("/accents")
async def read_accents(resident: ViewedResidentDep, cartesia: CartesiaDep) -> list[Accent]:
    """The accents a voice can be copied into, for her language."""
    return await _accents_for(cartesia, resident["language"])


@router.post("/accents", status_code=status.HTTP_201_CREATED)
async def copy_with_accent(
    login: ResidentLoginDep, request: AccentRequest, db: SupabaseDep, cartesia: CartesiaDep
) -> ResidentVoice:
    """A copy of one of her voices speaking with another accent (Cartesia's localize); it joins her
    picker with its sample made. A copy she already has is returned rather than made again."""
    resident = login.resident
    await _require_offered(db, resident, request.voice_id)
    accent = next(
        (a for a in await _accents_for(cartesia, resident["language"]) if a.id == request.accent), None
    )
    if accent is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=UNKNOWN_ACCENT)
    base_id, base_name = await _original(db, resident, request.voice_id)
    row = await find_accent_copy(db, resident["id"], base_id, accent.id)
    if row is None:
        name = ACCENT_COPY_NAME.format(name=base_name, accent=accent.name)[:CLONE_NAME_MAX]
        voice = await cartesia.localize(base_id, name, accent.id)
        row = await _keep_voice(
            db,
            cartesia,
            resident,
            voice["id"],
            name,
            login.contact_id,
            base_voice_id=base_id,
            accent=accent.id,
        )
    copy = ResidentVoice.clone(row)
    copy.sample_url = await _sample_or_none(db, cartesia, resident, copy.id)
    return copy


@router.post("/clones", status_code=status.HTTP_201_CREATED)
async def clone_voice(
    login: ResidentLoginDep,
    upload: CloneUploadDep,
    db: SupabaseDep,
    cartesia: CartesiaDep,
    accent: Annotated[str | None, Form()] = None,
) -> ResidentVoice:
    """Clone a voice from the multipart `clip` (10 to 60 seconds of one person, at most 10 MB),
    named `name`, with `consent` "true" from the person recorded and, optionally, the speaker's own
    `accent` (an accent id). It joins her picker with its sample made."""
    resident = login.resident
    accent = accent or None
    if accent and accent not in {a.id for a in await _accents_for(cartesia, resident["language"])}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=UNKNOWN_ACCENT)
    voice = await cartesia.clone(
        upload.clip, upload.filename, upload.content_type, upload.name, resident["language"], accent
    )
    row = await _keep_voice(db, cartesia, resident, voice["id"], upload.name, login.contact_id, accent=accent)
    clone = ResidentVoice.clone(row)
    clone.sample_url = await _sample_or_none(db, cartesia, resident, clone.id)
    return clone


@router.delete("/clones/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_clone(
    login: ResidentLoginDep, voice_id: str, db: SupabaseDep, cartesia: CartesiaDep
) -> None:
    """Remove one of her own voices (a clone or an accent copy), at Cartesia too; if she hears it
    now, she goes back to the default voice. Only whoever made it, or the owner."""
    resident = login.resident
    clone = await get_voice_clone(db, resident["id"], voice_id)
    if clone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=UNKNOWN_VOICE)
    if not (login.is_owner or clone["created_by"] == login.contact_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_CLONE_CREATOR)
    await cartesia.delete(voice_id)
    if resident["voice_id"] == voice_id:
        await _set_voice(db, resident, DEFAULT_VOICE_ID)
    await delete_voice_clone(db, resident["id"], voice_id)
    await delete_sample(db, sample_path(resident["id"], voice_id))


@router.get("/pronunciations")
async def read_pronunciations(resident: ViewedResidentDep, db: SupabaseDep) -> list[Pronunciation]:
    """The words the pillow says her way, oldest first."""
    return [Pronunciation.of(row) for row in await list_pronunciations(db, resident["id"])]


@router.post("/pronunciations", status_code=status.HTTP_201_CREATED)
async def add_pronunciation(
    login: ResidentLoginDep, request: PronunciationRequest, db: SupabaseDep, cartesia: CartesiaDep
) -> Pronunciation:
    """Teach the pillow how to say a word (a name, a place, a medicine). Her Cartesia dictionary is
    updated first, so a word is only listed once the pillow will say it."""
    resident = login.resident
    rows = await list_pronunciations(db, resident["id"])
    if any(row["word"].lower() == request.word.lower() for row in rows):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=PRONUNCIATION_EXISTS)
    if len(rows) >= PRONUNCIATIONS_MAX:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=PRONUNCIATIONS_FULL)
    await _sync_dictionary(db, cartesia, resident, [*rows, request.model_dump()])
    row = await create_pronunciation(db, resident["id"], request.word, request.sounds_like, login.contact_id)
    return Pronunciation.of(row)


@router.delete("/pronunciations/{pronunciation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_pronunciation(
    login: ResidentLoginDep, pronunciation_id: str, db: SupabaseDep, cartesia: CartesiaDep
) -> None:
    """Forget a word. Only whoever added it, or the owner."""
    resident = login.resident
    row = await get_pronunciation(db, resident["id"], pronunciation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=UNKNOWN_PRONUNCIATION)
    if not (login.is_owner or row["created_by"] == login.contact_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_PRONUNCIATION_CREATOR)
    rest = [other for other in await list_pronunciations(db, resident["id"]) if other["id"] != row["id"]]
    await _sync_dictionary(db, cartesia, resident, rest)
    await delete_pronunciation(db, resident["id"], pronunciation_id)


async def _require_offered(db: SupabaseDep, resident: dict[str, Any], voice_id: str) -> None:
    """404 unless the voice is a stock voice or one of her own."""
    if not await is_offered_voice(db, resident["id"], voice_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=UNKNOWN_VOICE)


async def _set_voice(db: SupabaseDep, resident: dict[str, Any], voice_id: str) -> None:
    """Make it the voice she hears and note the change in her pillows' agent log."""
    await _change(db, resident, {"voice_id": voice_id})


async def _change(db: SupabaseDep, resident: dict[str, Any], fields: dict[str, Any]) -> None:
    """Save how the pillow speaks to her and note it in her pillows' agent log."""
    await update_resident(db, resident["id"], fields)
    await log_resident_action(
        db, resident["id"], FAMILY_APP_AGENT, SETTINGS_CHANGE_INTENT, tool=VOICE_TOOL, args=fields
    )


async def _accents_for(cartesia: Cartesia, language: str) -> list[Accent]:
    """The accents a voice can be copied into for `language`, with short names ("British")."""
    key = base_language(language)
    if key not in _accents:
        _accents[key] = [
            Accent(id=a["id"], name=a["name"].removesuffix(ACCENT_NAME_SUFFIX), locale=a["locale"])
            for a in await cartesia.accents(key)
            if a.get("is_localizable")
        ]
    return _accents[key]


async def _original(db: SupabaseDep, resident: dict[str, Any], voice_id: str) -> tuple[str, str]:
    """The voice an accent copy starts from, and its name: the voice itself, or for a copy the
    voice it was copied from (so a copy of a copy is never made)."""
    stock = next((name for vid, name, _ in VOICES if vid == voice_id), None)
    if stock:
        return voice_id, stock
    row = await get_voice_clone(db, resident["id"], voice_id)
    if row["kind"] == ACCENT_SOURCE and row["base_voice_id"]:
        return await _original(db, resident, row["base_voice_id"])
    return voice_id, row["name"]


async def _keep_voice(
    db: SupabaseDep,
    cartesia: Cartesia,
    resident: dict[str, Any],
    voice_id: str,
    name: str,
    created_by: str,
    *,
    base_voice_id: str | None = None,
    accent: str | None = None,
) -> dict[str, Any]:
    """Record a voice just made at Cartesia as hers; if that fails, remove it there too, so no
    voice is left at Cartesia that no picker shows."""
    kind = ACCENT_SOURCE if base_voice_id else CLONE_SOURCE
    try:
        return await create_voice_clone(
            db,
            resident["id"],
            voice_id,
            name,
            created_by,
            kind=kind,
            base_voice_id=base_voice_id,
            accent=accent,
        )
    except Exception:
        await cartesia.delete(voice_id)
        raise


async def _make_sample(db: SupabaseDep, cartesia: Cartesia, resident: dict[str, Any], voice_id: str) -> str:
    """Have the voice say the sample line once, keep it, and return its link."""
    speech = Speech(speed=SAMPLE_SPEED, emotion=SAMPLE_EMOTION)
    mp3 = await cartesia.speak(voice_id, SAMPLE_TEXT, resident["language"], speech)
    return await store_sample(db, sample_path(resident["id"], voice_id), mp3)


async def _sample_or_none(
    db: SupabaseDep, cartesia: Cartesia, resident: dict[str, Any], voice_id: str
) -> str | None:
    """A new voice's sample link; None if Cartesia can't say it right now (Play makes it later)."""
    try:
        return await _make_sample(db, cartesia, resident, voice_id)
    except VoiceServiceError:
        log.warning("No sample yet for a new voice of resident %s", resident["id"])
        return None


async def _sync_dictionary(
    db: SupabaseDep, cartesia: Cartesia, resident: dict[str, Any], words: list[dict[str, Any]]
) -> None:
    """Make her Cartesia dictionary hold exactly `words`, and remember its id if it is new."""
    items = [{"text": w["word"], "pronunciation": w["sounds_like"], "case_sensitive": False} for w in words]
    name = PRONUNCIATION_DICT_NAME.format(resident_id=resident["id"])
    dict_id = await cartesia.save_pronunciations(resident["pronunciation_dict_id"], name, items)
    if dict_id != resident["pronunciation_dict_id"]:
        await update_resident(db, resident["id"], {"pronunciation_dict_id": dict_id})
