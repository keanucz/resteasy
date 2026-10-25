"""The two ways out to a phone: Photon's iMessage sidecar (deploy/imessage) and Twilio's REST API.

Each send returns the provider's reference for the message or call, or raises DeliveryError with a
short reason the notifications row can store. Phone numbers never go into the logs."""

from xml.sax.saxutils import escape

import httpx

from app.core.config import Settings
from app.notify.notify_constants import (
    CALL_RING_S,
    HTTP_TIMEOUT_S,
    MACHINE_DETECTION,
    MACHINE_DETECTION_SILENCE_MS,
    TWILIO_API,
    TWILIO_VOICE,
)


class DeliveryError(Exception):
    """A provider refused or failed to deliver; the message is safe to store and show."""


def _reason(response: httpx.Response) -> str:
    """The provider's error text, trimmed, for the notifications row."""
    try:
        body = response.json()
        detail = body.get("error") or body.get("message") or response.text
    except ValueError:
        detail = response.text
    return f"{response.status_code}: {str(detail)[:200]}"


class IMessage:
    """Client for the iMessage sidecar on the compose network."""

    def __init__(self, url: str, http: httpx.AsyncClient | None = None) -> None:
        self.url = url.rstrip("/")
        self.http = http or httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)

    @classmethod
    def from_settings(cls, settings: Settings) -> "IMessage | None":
        return cls(settings.imessage_url) if settings.imessage_url else None

    async def send(self, to: str, text: str) -> str:
        try:
            response = await self.http.post(f"{self.url}/send", json={"to": to, "text": text})
        except httpx.HTTPError as err:
            raise DeliveryError(f"sidecar unreachable ({type(err).__name__})") from err
        if response.status_code != 200:
            raise DeliveryError(_reason(response))
        return str(response.json().get("id") or "sent")


class Twilio:
    """Twilio's REST API: an SMS, or a call that reads the alert aloud."""

    def __init__(self, sid: str, token: str, from_number: str, http: httpx.AsyncClient | None = None) -> None:
        self.base = f"{TWILIO_API}/Accounts/{sid}"
        self.from_number = from_number
        self.http = http or httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, auth=(sid, token))

    @classmethod
    def from_settings(cls, settings: Settings) -> "Twilio | None":
        s = settings
        if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number):
            return None
        return cls(s.twilio_account_sid, s.twilio_auth_token, s.twilio_from_number)

    async def sms(self, to: str, body: str) -> str:
        return await self._create("Messages.json", {"To": to, "From": self.from_number, "Body": body})

    async def call(self, to: str, say: str, audio_url: str | None = None) -> str:
        """Call `to` and play `audio_url` (the script in the pillow's voice) once, or have Twilio's
        voice read `say` when there is none. It starts after they answer with "Hello?", once
        answering-machine detection hears them stop, so nothing is lost while the phone is lifted."""
        line = (f"<Play>{escape(audio_url)}</Play>" if audio_url
                else f'<Say voice="{TWILIO_VOICE}">{escape(say)}</Say>')
        form = {"To": to, "From": self.from_number, "Twiml": f"<Response>{line}</Response>",
                "Timeout": str(CALL_RING_S), "MachineDetection": MACHINE_DETECTION,
                "MachineDetectionSilenceTimeout": str(MACHINE_DETECTION_SILENCE_MS)}
        return await self._create("Calls.json", form)

    async def call_status(self, sid: str) -> tuple[str, str | None]:
        """How call `sid` is going: Twilio's status ("ringing", "in-progress", "completed", "busy",
        "no-answer", ...) and who answered ("human", "machine_start", ..., None until known)."""
        try:
            response = await self.http.get(f"{self.base}/Calls/{sid}.json")
        except httpx.HTTPError as err:
            raise DeliveryError(f"Twilio unreachable ({type(err).__name__})") from err
        if response.status_code != 200:
            raise DeliveryError(_reason(response))
        call = response.json()
        return call["status"], call.get("answered_by")

    async def _create(self, resource: str, form: dict[str, str]) -> str:
        try:
            response = await self.http.post(f"{self.base}/{resource}", data=form)
        except httpx.HTTPError as err:
            raise DeliveryError(f"Twilio unreachable ({type(err).__name__})") from err
        if response.status_code not in (200, 201):
            raise DeliveryError(_reason(response))
        return response.json()["sid"]
