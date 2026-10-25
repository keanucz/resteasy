"""The notifications sender: delivers the "sms" and "call" rows Night Watch queues.

    sms   iMessage through the Photon sidecar; if that fails or isn't set up, Twilio SMS.
          Only to contacts who agreed to texts (contacts.sms_consent).
    call  a Twilio call that reads the alert aloud.

Night Watch's ladder never waits on this: it queues the row and moves on, and this ticker sends
what is queued. Only pillows in NOTIFY_PILLOW_IDS reach real phones (test pillows stay queued),
and nothing older than MAX_AGE_S is sent.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import AsyncClient

from app.core.config import Settings
from app.crud.night_log import finish_notification, list_sendable_notifications, log_action
from app.notify.notify_constants import AGENT, FALLBACK_TEXT, MAX_AGE_S, SENT_CHANNELS
from app.notify.transports import DeliveryError, IMessage, Twilio

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Delivery:
    """How one row went: sent (with the provider's reference) or failed, and why."""

    sent: bool
    via: str | None = None  # "imessage" / "sms" / "call"
    ref: str | None = None
    error: str | None = None


class NotificationSender:
    """Sends the queued rows; each provider is optional (None = not configured)."""

    def __init__(self, imessage: IMessage | None, twilio: Twilio | None, pillow_ids: list[str]) -> None:
        self.imessage = imessage
        self.twilio = twilio
        self.pillow_ids = pillow_ids

    @classmethod
    def from_settings(cls, settings: Settings) -> "NotificationSender":
        imessage, twilio = IMessage.from_settings(settings), Twilio.from_settings(settings)
        return cls(imessage, twilio, settings.notify_pillow_ids)

    @property
    def enabled(self) -> bool:
        return bool((self.imessage or self.twilio) and self.pillow_ids)

    async def tick(self, db: AsyncClient) -> None:
        """Send every queued row that is recent and on an enabled pillow, oldest first."""
        since = (datetime.now(UTC) - timedelta(seconds=MAX_AGE_S)).isoformat()
        for row in await list_sendable_notifications(db, list(SENT_CHANNELS), self.pillow_ids, since):
            result = await self.deliver(row)
            status = "sent" if result.sent else "failed"
            await finish_notification(db, row["id"], status, result.ref, result.error)
            await self._log(db, row, result)

    async def deliver(self, row: dict[str, Any]) -> Delivery:
        """Send one row; never raises."""
        contact = row.get("contacts") or {}
        phone = contact.get("phone")
        text = row.get("message") or (row.get("incidents") or {}).get("summary") or FALLBACK_TEXT
        if not phone:
            return Delivery(False, error="no phone number on record")
        if row["channel"] == "call":
            return await self._call(phone, text)
        if not contact.get("sms_consent"):
            return Delivery(False, error="has not agreed to texts (sms_consent)")
        return await self._text(phone, text)

    async def _text(self, phone: str, text: str) -> Delivery:
        failures = []
        if self.imessage is not None:
            try:
                return Delivery(True, "imessage", f"imessage:{await self.imessage.send(phone, text)}")
            except DeliveryError as err:
                failures.append(f"iMessage {err}")
        if self.twilio is not None:
            try:
                sid = await self.twilio.sms(phone, text)
                return Delivery(True, "sms", sid, "; ".join(failures) or None)  # say why not iMessage
            except DeliveryError as err:
                failures.append(f"SMS {err}")
        return Delivery(False, error="; ".join(failures) or "no iMessage or SMS sender configured")

    async def _call(self, phone: str, text: str) -> Delivery:
        if self.twilio is None:
            return Delivery(False, error="no Twilio configured for calls")
        try:
            return Delivery(True, "call", await self.twilio.call(phone, text))
        except DeliveryError as err:
            return Delivery(False, error=f"call {err}")

    async def _log(self, db: AsyncClient, row: dict[str, Any], result: Delivery) -> None:
        """A line in the family app's live log: who was reached, and how, or why not."""
        incident = row.get("incidents") or {}
        name = ((row.get("contacts") or {}).get("full_name") or "family").split()[0]
        how = {"imessage": "Texted (iMessage)", "sms": "Texted (SMS)", "call": "Called"}.get(result.via or "")
        intent = f"{how} {name}" if result.sent else f"Could not {row['channel']} {name}: {result.error}"
        if not result.sent:
            log.warning("Notification %s failed: %s", row["id"], result.error)
        await log_action(db, incident["pillow_id"], AGENT, intent=intent, tool=result.via or row["channel"],
                         args={"notification_id": row["id"]}, incident_id=row.get("incident_id"))
