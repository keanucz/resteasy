"""Alerts router: how the signed-in app user is reached when someone they look after needs help.

Settings > Alerts in the app reads and changes the switches on the login's own contact row: the
in-app alert (app_alerts), texts (sms_consent) and calls (call_alerts), and the mobile number they
go to. Night Watch's ladder skips a channel the contact turned off. The test buttons send one text
or call to that number now. Every request carries the app's Supabase access token.
"""

import logging
import time as clock

from fastapi import APIRouter, HTTPException, status

from app.core.app_constants import (
    ALERT_SWITCH_COLUMNS,
    ALERT_TEST_GAP_S,
    ALERT_TEST_MESSAGES,
    ALERT_TEST_NO_PHONE,
    ALERT_TEST_NOT_CONFIGURED,
    ALERT_TEST_TOO_SOON,
    KEEP_ONE_CHANNEL,
    NO_ALERT_CONTACT,
    PHONE_TAKEN,
)
from app.core.dependencies import NotifierDep, SupabaseDep, UserIdDep
from app.crud.accounts import get_alert_contact, update_contact
from app.notify.sender import NotificationSender
from app.schemas.account import AlertSettings, AlertSettingsPatch, AlertTest, AlertTestResult

log = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])

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
        twilio_ready=notifier.twilio is not None,
    )


@router.get("/me/alerts")
async def read_alerts(user_id: UserIdDep, db: SupabaseDep, notifier: NotifierDep) -> AlertSettings:
    """How the signed-in person is alerted, for Settings > Alerts."""
    return _settings(await _own_contact(db, user_id), notifier)


@router.patch("/me/alerts")
async def update_alerts(
    user_id: UserIdDep, patch: AlertSettingsPatch, db: SupabaseDep, notifier: NotifierDep
) -> AlertSettings:
    """Change any of the alert switches or the mobile number. One switch always stays on (422), and
    a number another contact uses is refused (409)."""
    contact = await _own_contact(db, user_id)
    fields = patch.columns()
    merged = contact | fields
    if not any(merged[column] for column in ALERT_SWITCH_COLUMNS.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=KEEP_ONE_CHANNEL)
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
