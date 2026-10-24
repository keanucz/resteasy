"""Account router: what the signed-in family app asks about itself, and the owner's settings.

Every request here carries the app's Supabase access token (`Authorization: Bearer ...`), never
the agents' shared token, which must not ship inside the app.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.app_constants import FAMILY_APP_AGENT, NOT_LINKED, NOT_OWNER
from app.core.dependencies import PillowDep, SupabaseDep, UserIdDep, resident_of
from app.core.voice_constants import VOICES
from app.crud.accounts import get_contact_for_user, get_role, list_account_pillows
from app.crud.night_log import log_action
from app.crud.residents import update_resident
from app.schemas.account import Account, AccountPillow, Preferences, PreferencesPatch, Voice

router = APIRouter(tags=["account"])

PREFERENCE_KEYS = tuple(Preferences.model_fields)


@router.get("/me")
async def read_account(user_id: UserIdDep, db: SupabaseDep) -> Account:
    """Who is signed in, and the pillows they look after (none yet after a fresh sign-up)."""
    contact = await get_contact_for_user(db, user_id)
    if contact is None:
        return Account(contact_id=None, full_name=None, pillows=[])
    pillows = await list_account_pillows(db, contact["id"])
    return Account(
        contact_id=contact["id"],
        full_name=contact["full_name"],
        pillows=[AccountPillow(**p) for p in pillows],
    )


@router.get("/voices")
async def list_voices() -> list[Voice]:
    """The voices the pillow can speak with, for the app's voice picker."""
    return [Voice(id=voice_id, name=name, description=description) for voice_id, name, description in VOICES]


@router.get("/pillows/{pillow_id}/preferences")
async def read_preferences(user_id: UserIdDep, pillow: PillowDep, db: SupabaseDep) -> Preferences:
    """The settings the app shows: voice, quiet hours, check-in timeout and whether watching is paused."""
    resident = await resident_of(db, pillow)
    await _require_role(db, user_id, resident["id"], owner=False)
    return Preferences(**{key: resident[key] for key in PREFERENCE_KEYS})


@router.patch("/pillows/{pillow_id}/preferences")
async def update_preferences(
    user_id: UserIdDep, pillow: PillowDep, patch: PreferencesPatch, db: SupabaseDep
) -> Preferences:
    """Change any of the preferences. Owner only; the change shows in the app's live agent log."""
    resident = await resident_of(db, pillow)
    await _require_role(db, user_id, resident["id"], owner=True)
    fields = patch.model_dump(exclude_none=True, mode="json")
    await update_resident(db, resident["id"], fields)
    if fields:
        await log_action(db, pillow.id, FAMILY_APP_AGENT, "change settings", tool="preferences", args=fields)
    return Preferences(**{key: resident[key] for key in PREFERENCE_KEYS} | fields)


async def _require_role(db: SupabaseDep, user_id: str, resident_id: str, *, owner: bool) -> None:
    """403 unless the user's contact looks after this resident (as the owner, when `owner`)."""
    contact = await get_contact_for_user(db, user_id)
    role = await get_role(db, contact["id"], resident_id) if contact else None
    if role is None or (owner and role != "owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_OWNER if role else NOT_LINKED)
