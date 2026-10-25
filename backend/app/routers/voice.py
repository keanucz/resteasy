"""Voice router: which voice the pillow speaks to her with, previews of each, and voices cloned
from someone she knows.

Anyone who looks after her lists and previews voices, and may clone a voice (with the consent of
the person recorded); only the owner picks the voice she hears. A clone is removed by whoever made
it or by the owner. Cartesia is called from here only, so its key never reaches the app; requests
carry the app's Supabase access token, like the residents router.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

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
    DEFAULT_VOICE_ID,
    NOT_CLONE_CREATOR,
    PREVIEW_CONTENT_TYPE,
    PREVIEW_TEXT,
    UNKNOWN_VOICE,
    VOICE_TOOL,
    VOICES,
)
from app.crud.night_log import log_resident_action
from app.crud.residents import update_resident
from app.crud.voice_clones import (
    create_voice_clone,
    delete_voice_clone,
    get_voice_clone,
    is_offered_voice,
    list_voice_clones,
)
from app.schemas.voice import CurrentVoice, ResidentVoice, ResidentVoices, VoiceChoice, VoicePreviewRequest

router = APIRouter(prefix="/residents/{resident_id}/voice", tags=["voice"])


@router.get("")
async def read_voices(resident: ViewedResidentDep, db: SupabaseDep) -> ResidentVoices:
    """The voice she hears now, then every voice the owner may pick: the stock voices, then her
    clones, oldest first."""
    stock = [ResidentVoice.stock(*voice) for voice in VOICES]
    clones = [ResidentVoice.clone(row) for row in await list_voice_clones(db, resident["id"])]
    return ResidentVoices(current=resident["voice_id"], voices=stock + clones)


@router.post("/preview", response_class=Response, responses={200: {"content": {PREVIEW_CONTENT_TYPE: {}}}})
async def preview_voice(
    resident: ViewedResidentDep, preview: VoicePreviewRequest, db: SupabaseDep, cartesia: CartesiaDep
) -> Response:
    """MP3 of the voice saying `text` (at most 200 characters), or a line with her name. Nothing is
    stored."""
    await _require_offered(db, resident, preview.voice_id)
    text = preview.text or PREVIEW_TEXT.format(name=resident["preferred_name"])
    audio = await cartesia.speak(preview.voice_id, text, resident["language"])
    return Response(content=audio, media_type=PREVIEW_CONTENT_TYPE)


@router.put("")
async def choose_voice(resident: OwnedResidentDep, choice: VoiceChoice, db: SupabaseDep) -> CurrentVoice:
    """Set the voice the pillow speaks to her with: a stock voice or one of her clones. Owner only."""
    await _require_offered(db, resident, choice.voice_id)
    await _set_voice(db, resident, choice.voice_id)
    return CurrentVoice(current=choice.voice_id)


@router.post("/clones", status_code=status.HTTP_201_CREATED)
async def clone_voice(
    login: ResidentLoginDep, upload: CloneUploadDep, db: SupabaseDep, cartesia: CartesiaDep
) -> ResidentVoice:
    """Clone a voice from the multipart `clip` (10 to 60 seconds of one person, at most 10 MB),
    named `name`, with `consent` "true" from the person recorded. It joins her picker."""
    resident = login.resident
    voice = await cartesia.clone(
        upload.clip, upload.filename, upload.content_type, upload.name, resident["language"]
    )
    try:
        row = await create_voice_clone(db, resident["id"], voice["id"], upload.name, login.contact_id)
    except Exception:
        await cartesia.delete(voice["id"])  # no voice left at Cartesia that no picker shows
        raise
    return ResidentVoice.clone(row)


@router.delete("/clones/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_clone(
    login: ResidentLoginDep, voice_id: str, db: SupabaseDep, cartesia: CartesiaDep
) -> None:
    """Remove one of her clones, at Cartesia too; if she hears it now, she goes back to the default
    voice. Only whoever made it, or the owner."""
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


async def _require_offered(db: SupabaseDep, resident: dict[str, Any], voice_id: str) -> None:
    """404 unless the voice is a stock voice or one of her clones."""
    if not await is_offered_voice(db, resident["id"], voice_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=UNKNOWN_VOICE)


async def _set_voice(db: SupabaseDep, resident: dict[str, Any], voice_id: str) -> None:
    """Make it the voice she hears and note the change in her pillows' agent log."""
    fields = {"voice_id": voice_id}
    await update_resident(db, resident["id"], fields)
    await log_resident_action(
        db, resident["id"], FAMILY_APP_AGENT, SETTINGS_CHANGE_INTENT, tool=VOICE_TOOL, args=fields
    )
