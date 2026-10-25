"""Account router: what the signed-in family app asks about itself, and the owner's settings.

Every request here carries the app's Supabase access token (`Authorization: Bearer ...`), never
the agents' shared token, which must not ship inside the app.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.app_constants import (
    DEMO_PILLOW_ID,
    DEMO_PILLOW_MISSING,
    FAMILY_APP_AGENT,
    NEW_HELPER_NAME,
    OWNER_ROLE,
    PILLOW_TAKEN,
    REAL_PILLOW_ID,
    SETTINGS_CHANGE_INTENT,
)
from app.core.dependencies import PillowDep, SupabaseDep, UserIdDep, require_role, resident_of
from app.core.voice_constants import VOICES
from app.crud.accounts import (
    create_household,
    get_contact_for_user,
    get_link_for_user,
    join_household,
    list_account_pillows,
)
from app.crud.night_log import log_action
from app.crud.pillows import get_pillow
from app.crud.residents import update_resident
from app.schemas.account import Account, AccountPillow, NewPillow, Preferences, PreferencesPatch, Voice

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


@router.post("/me/join-demo")
async def join_demo(user_id: UserIdDep, db: SupabaseDep) -> Account:
    """Pair a fresh sign-up with the demo pillow: they become a plain, off-call contact of its
    resident, named from their email. Safe to repeat; a login already linked is left as it is."""
    pillow = await get_pillow(db, DEMO_PILLOW_ID)
    if pillow is None or pillow.resident_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=DEMO_PILLOW_MISSING)
    await join_household(db, user_id, await _name_from_email(db, user_id), str(pillow.resident_id))
    return await read_account(user_id, db)


@router.post("/me/pillows")
async def create_pillow(user_id: UserIdDep, new: NewPillow, db: SupabaseDep) -> Account:
    """"Connect pillow" on a login that looks after nobody: set the real pillow up for the person it
    names, with the login as their owner. It starts empty: only what the boards send from now on.
    Safe to repeat for the same owner (the name is updated); 409 once another login has set it up."""
    pillow = await get_pillow(db, REAL_PILLOW_ID)
    if pillow is not None:
        link = await get_link_for_user(db, user_id, str(pillow.resident_id)) if pillow.resident_id else None
        if link is None or link["role"] != OWNER_ROLE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=PILLOW_TAKEN)
        names = {"full_name": new.name, "preferred_name": new.name}
        await update_resident(db, str(pillow.resident_id), names)
        return await read_account(user_id, db)
    contact_name = await _name_from_email(db, user_id)
    if not await create_household(db, user_id, contact_name, new.name, REAL_PILLOW_ID):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=PILLOW_TAKEN)
    return await read_account(user_id, db)


async def _name_from_email(db: SupabaseDep, user_id: str) -> str:
    """A new contact's name, borrowed from the login's email."""
    user = (await db.auth.admin.get_user_by_id(user_id)).user
    return (user.email or "").split("@")[0].strip() or NEW_HELPER_NAME


@router.get("/voices")
async def list_voices() -> list[Voice]:
    """The voices the pillow can speak with, for the app's voice picker."""
    return [Voice(id=voice_id, name=name, description=description) for voice_id, name, description in VOICES]


@router.get("/pillows/{pillow_id}/preferences")
async def read_preferences(user_id: UserIdDep, pillow: PillowDep, db: SupabaseDep) -> Preferences:
    """The settings the app shows: voice, quiet hours, check-in timeout and whether watching is paused."""
    resident = await resident_of(db, pillow)
    await require_role(db, user_id, resident["id"], owner=False)
    return Preferences(**{key: resident[key] for key in PREFERENCE_KEYS})


@router.patch("/pillows/{pillow_id}/preferences")
async def update_preferences(
    user_id: UserIdDep, pillow: PillowDep, patch: PreferencesPatch, db: SupabaseDep
) -> Preferences:
    """Change any of the preferences. Owner only; the change shows in the app's live agent log."""
    resident = await resident_of(db, pillow)
    await require_role(db, user_id, resident["id"], owner=True)
    fields = patch.model_dump(exclude_none=True, mode="json")
    await update_resident(db, resident["id"], fields)
    if fields:
        await log_action(
            db, pillow.id, FAMILY_APP_AGENT, SETTINGS_CHANGE_INTENT, tool="preferences", args=fields
        )
    return Preferences(**{key: resident[key] for key in PREFERENCE_KEYS} | fields)
