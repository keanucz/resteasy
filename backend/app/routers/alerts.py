"""Alerts router: how the signed-in app user is reached when someone they look after needs help.

Settings > Alerts in the app reads and changes the switches on the login's own contact row: the
in-app alert (app_alerts), texts (sms_consent) and calls (call_alerts), and the mobile number they
go to. Night Watch's ladder skips a channel the contact turned off. The test buttons send one text
or call to that number now. Every request carries the app's Supabase access token.
"""

import logging
import time as clock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status

from app.agents.guardian import Guardian
from app.core.app_constants import (
    ALERT_DEBUG_NOT_TEST,
    ALERT_DEBUG_REASON,
    ALERT_SWITCH_COLUMNS,
    ALERT_TEST_GAP_S,
    ALERT_TEST_MESSAGES,
    ALERT_TEST_NO_PHONE,
    ALERT_TEST_NOT_CONFIGURED,
    ALERT_TEST_TOO_SOON,
    CONSENT_AGREED,
    DEMO_REMINDER,
    KEEP_ONE_CHANNEL,
    LAST_ON_CALL,
    NO_ALERT_CONTACT,
    PHONE_TAKEN,
)
from app.core.dependencies import (
    NightWatchDep,
    NotifierDep,
    PillowDep,
    SupabaseDep,
    UserIdDep,
    require_role,
    resident_of,
)
from app.crud.accounts import get_alert_contact, list_contact_resident_ids, update_contact
from app.crud.pillow_state import get_state
from app.crud.reminders import create_reminder
from app.crud.residents import list_contacts_in_order
from app.notify.sender import NotificationSender
from app.schemas.account import AlertSettings, AlertSettingsPatch, AlertTest, AlertTestResult
from app.schemas.checkin import NightStatus
from app.schemas.pillow import Pillow

log = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])
_guardian = Guardian()  # the roster check needs no per-resident settings

# When each (contact, channel) last had a test sent, so a double tap can't text twice
_last_test: dict[tuple[str, str], float] = {}


async def _own_contact(db: SupabaseDep, user_id: str) -> dict:
    """The login's contact row, or 404 for a fresh sign-up that looks after nobody yet."""
    contact = await get_alert_contact(db, user_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_ALERT_CONTACT)
    return contact


def _settings(contact: dict, notifier: NotificationSender) -> AlertSettings:
    """The contact row as the app's alert settings."""
    return AlertSettings(
        phone=contact["phone"],
        app=contact["app_alerts"],
        sms=contact["sms_consent"],
        call=contact["call_alerts"],
        restless=contact["restless_alerts"],
        on_call=contact["on_call"],
        quiet_start=contact["quiet_start"],
        quiet_end=contact["quiet_end"],
        twilio_ready=notifier.twilio is not None,
    )


async def _others_on_call(db: SupabaseDep, contact_id: str) -> bool:
    """Whether every resident this contact looks after keeps someone else on call (the Guardian's
    roster rule, as for an agent taking someone off call)."""
    for resident_id in await list_contact_resident_ids(db, contact_id):
        contacts = await list_contacts_in_order(db, resident_id)
        if not _guardian.check_on_call(contacts, contact_id, on_call=False).allowed:
            return False
    return True


@router.get("/me/alerts")
async def read_alerts(user_id: UserIdDep, db: SupabaseDep, notifier: NotifierDep) -> AlertSettings:
    """How the signed-in person is alerted, for Settings > Alerts."""
    return _settings(await _own_contact(db, user_id), notifier)


@router.patch("/me/alerts")
async def update_alerts(
    user_id: UserIdDep, patch: AlertSettingsPatch, db: SupabaseDep, notifier: NotifierDep
) -> AlertSettings:
    """Change any of the alert settings or the mobile number. One channel always stays on (422), the
    last contact on call stays on call (422), and a number another contact uses is refused (409)."""
    contact = await _own_contact(db, user_id)
    fields = patch.columns()
    merged = contact | fields
    if not any(merged[column] for column in ALERT_SWITCH_COLUMNS.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=KEEP_ONE_CHANNEL)
    if fields.get("on_call") is False and contact["on_call"] and not await _others_on_call(db, contact["id"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=LAST_ON_CALL)
    if not await update_contact(db, contact["id"], fields):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=PHONE_TAKEN)
    return _settings(merged, notifier)


@router.post("/me/alerts/test")
async def send_test_alert(
    user_id: UserIdDep, test: AlertTest, db: SupabaseDep, notifier: NotifierDep
) -> AlertTestResult:
    """Send one test text or call to the person's own number now, whatever the switches say: it
    checks the number and the providers work. At most one per channel every ALERT_TEST_GAP_S."""
    contact = await _own_contact(db, user_id)
    if notifier.twilio is None and (test.channel == "call" or notifier.imessage is None):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=ALERT_TEST_NOT_CONFIGURED)
    if not contact["phone"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=ALERT_TEST_NO_PHONE)
    key, now = (contact["id"], test.channel), clock.monotonic()
    if now - _last_test.get(key, -ALERT_TEST_GAP_S) < ALERT_TEST_GAP_S:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=ALERT_TEST_TOO_SOON)
    _last_test[key] = now
    result = await notifier.send_test(test.channel, contact["phone"], ALERT_TEST_MESSAGES[test.channel])
    if not result.sent:
        log.warning("Test %s for contact %s failed: %s", test.channel, contact["id"], result.error)
    return AlertTestResult(sent=result.sent, via=result.via, error=result.error)


async def _debug_caller(db: SupabaseDep, user_id: str, pillow: Pillow) -> None:
    """403 unless the login is a test account in this pillow's care circle."""
    contact = await _own_contact(db, user_id)
    if not contact.get("is_test"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=ALERT_DEBUG_NOT_TEST)
    await require_role(db, user_id, (await resident_of(db, pillow))["id"], owner=False)


@router.post("/pillows/{pillow_id}/alert-debug/start")
async def start_debug_alert(
    user_id: UserIdDep, pillow: PillowDep, db: SupabaseDep, night_watch: NightWatchDep
) -> NightStatus:
    """Test accounts: start a real alert now, through Night Watch. The app goes red and the gentle
    ladder runs (in-app first, then texts and calls to the care circle in turn), and "I'm on it" and
    her "I'm fine" work on it like on any alert."""
    await _debug_caller(db, user_id, pillow)
    night_state = await night_watch.report_distress(db, pillow, ALERT_DEBUG_REASON, urgent=False)
    return NightStatus(night_state=night_state)


@router.post("/pillows/{pillow_id}/alert-debug/stop")
async def stop_debug_alert(
    user_id: UserIdDep, pillow: PillowDep, db: SupabaseDep, night_watch: NightWatchDep
) -> NightStatus:
    """Test accounts: end the alert as if she pressed "I'm fine" (the fine key)."""
    await _debug_caller(db, user_id, pillow)
    return NightStatus(night_state=await night_watch.press_key(db, pillow, "fine"))


@router.post("/pillows/{pillow_id}/alert-debug/reminder")
async def start_debug_reminder(user_id: UserIdDep, pillow: PillowDep, db: SupabaseDep) -> NightStatus:
    """Test accounts: a one-off reminder due this minute that she has already agreed to, so the
    Routine agent marks it due on its next tick and the bedside voice says it. Like any reminder it
    waits while she's in bed or being checked on, so the answer says what the pillow is doing."""
    await _debug_caller(db, user_id, pillow)
    resident = await resident_of(db, pillow)
    slot = datetime.now(ZoneInfo(resident["timezone"])).replace(second=0, microsecond=0)
    fields = DEMO_REMINDER | {
        "time_of_day": slot.strftime("%H:%M"),
        "on_date": slot.date().isoformat(),
        "consent": CONSENT_AGREED,
        "consent_at": (slot - timedelta(minutes=1)).isoformat(),  # before the slot, or it never plays
        "created_by": (await _own_contact(db, user_id))["id"],
    }
    await create_reminder(db, resident["id"], fields)
    state = await get_state(db, pillow.id)
    return NightStatus(night_state=state.night_state if state else "awake")
