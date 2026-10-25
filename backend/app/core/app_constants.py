"""App-wide constants that are not environment specific."""

from datetime import time, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"

DEFAULT_APP_NAME = "Pillow API"
DEFAULT_ENVIRONMENT = "development"
DEFAULT_CORS_ORIGINS = ["*"]

# HTTP methods the CORS middleware allows; tighten to e.g. ["GET", "POST"] for production
CORS_ALLOW_METHODS = ["*"]
# Request headers the CORS middleware allows; tighten for production
CORS_ALLOW_HEADERS = ["*"]

# Message returned by the root endpoint to confirm the API was reached
HELLO_MESSAGE = "Hello World"

API_PREFIX = "/api"

# Message returned by GET /api/test so the app can show it reached the backend
CONNECTION_TEST_MESSAGE = "Frontend reached the backend"

# Detail returned with a 503 when SUPABASE_URL / SUPABASE_SECRET_KEY are not set
SUPABASE_NOT_CONFIGURED = "Supabase is not configured on this server"

# Seconds between Night Watch timer runs when no pillow reports
NIGHT_WATCH_TICK_S = 5

# Seconds between runs of the reminder schedule (the Routine agent)
REMINDERS_TICK_S = 15

# Seconds between runs of the notifications sender (app/notify)
NOTIFY_TICK_S = 5

# The one real pillow whose alerts go to real phones (NOTIFY_PILLOW_IDS overrides)
DEFAULT_NOTIFY_PILLOW_IDS = ["mum"]

# The demo household's pillow (Margaret's); a fresh sign-up joins it as a plain contact on connect
DEMO_PILLOW_ID = "mum"
# The id the real boards' bridge posts as (sim/audio_bridge.py --pillow-id). "Connect pillow" on a
# login that looks after nobody creates it, for the person the login names (POST /api/me/pillows)
REAL_PILLOW_ID = "pillow-1"
# Quiet hours for a newly connected pillow: start == end means Night Watch watches all day, so a
# bed exit counts whenever it happens (the demo is judged mid-morning). The app can narrow them
NEW_PILLOW_QUIET_HOURS = {"quiet_start": "00:00", "quiet_end": "00:00"}
# Longest name the app may give the person a pillow is for
RESIDENT_NAME_MAX = 60
# Detail returned with a 409 when another login has already set the real pillow up
PILLOW_TAKEN = "This pillow is already set up by someone else"
# A fresh sign-up's name when their email gives none to borrow
NEW_HELPER_NAME = "Family helper"
# Detail returned with a 404 when the demo pillow (or its resident) is missing from the database
DEMO_PILLOW_MISSING = "The demo pillow is not set up"

# Detail returned with a 503 when CHECKIN_TOKEN is not set (POST /checkin fails closed)
CHECKIN_TOKEN_NOT_CONFIGURED = "CHECKIN_TOKEN is not configured on this server"

# Details returned when an app request has no valid Supabase login, or isn't the resident's owner
NOT_SIGNED_IN = "Sign in to the app first"
NOT_OWNER = "Only the owner can change these settings"
NOT_LINKED = "This login does not look after them"

# resident_contacts.role of the one login that may change a resident's settings
OWNER_ROLE = "owner"

# agent_log.agent for changes made from the family app, so the app's live log can say who did it
FAMILY_APP_AGENT = "family_app"
# agent_log.agent for the Fetch.ai family agents, which act with their own token (FAMILY_AGENT_TOKENS)
FAMILY_AGENT = "family_agent"
PILLOW_VOICE_AGENT = "pillow_voice"  # she asked the pillow herself (talk key), via the base laptop
RESIDENT_NOT_ALLOWED = "Acting as her (as=resident) only sets up reminders and reads her calendar"
AS_RESIDENT = "resident"  # ?as=resident: the agent token acting for her, not for a contact
# Details returned when the agent token changes a reminder without naming a contact of hers
AGENT_CONTACT_MISSING = "Say which contact the agent acts for: the contact_id query parameter"
AGENT_CONTACT_NOT_LINKED = "This contact does not look after them"
# Details returned when a family agent names someone other than its own contact, or uses the shared
# agent token once the family agents have their own
AGENT_CONTACT_MISMATCH = "This agent's token speaks for a different contact"
AGENT_OWN_TOKEN = "Family agents use their own token now (FAMILY_AGENT_TOKENS), not the shared one"
NOT_AN_AGENT = "Invalid agent token"
# agent_log.tool for a goodnight message, a settings change and an away date from a family member
GOODNIGHT_TOOL = "goodnight"
SETTINGS_TOOL = "settings"
AWAY_TOOL = "away"
# agent_log.tool for a reminder the family agent set up, changed or deleted
REMINDERS_TOOL = "reminders"
# agent_log.intent for a settings change made from the family app
SETTINGS_CHANGE_INTENT = "change settings"

# Settings > Alerts (GET/PATCH /api/me/alerts): the app's switch names -> the contacts columns.
# Night Watch's ladder skips a channel whose switch is off; texts keep the original consent column
ALERT_SWITCH_COLUMNS = {"app": "app_alerts", "sms": "sms_consent", "call": "call_alerts"}
# A mobile number in E.164 once spaces, dashes and brackets are gone ("00" counts as "+")
PHONE_PATTERN = r"\+[1-9]\d{7,14}"
PHONE_INVALID = "Use the full number with its country code, like +44 7700 900123"
PHONE_TAKEN = "Another person in the app already uses this number"
NO_ALERT_CONTACT = "Connect a pillow first, then choose how you're alerted"
KEEP_ONE_CHANNEL = "Keep at least one way to reach you on, so an alert always gets through"
# Settings > Alerts fields that are plain contacts columns, beside the three channel switches
ALERT_EXTRA_COLUMNS = {"restless": "restless_alerts", "on_call": "on_call",
                       "quiet_start": "quiet_start", "quiet_end": "quiet_end"}
LAST_ON_CALL = "Someone else has to be on call first, so an alert always tries someone straight away"
# The test buttons at the bottom of Settings: one per channel per person this often at most
ALERT_TEST_GAP_S = 30
ALERT_TEST_TOO_SOON = "A test just went out. Try again in half a minute"
ALERT_TEST_NO_PHONE = "Add your mobile number first"
ALERT_TEST_NOT_CONFIGURED = "Texts and calls aren't set up on this server"
ALERT_TEST_MESSAGES = {
    "sms": "Rest Easy test: alert texts reach this phone. Nothing is wrong.",
    "call": "This is a Rest Easy test call. Alerts will reach you on this number. Nothing is wrong.",
}

# Alert debug (test accounts only, contacts.is_test): a real alert through Night Watch, and its end
ALERT_DEBUG_NOT_TEST = "Only test accounts can start or stop alerts from the app"
# The debug alert runs as if she had said this to the pillow: a real distress alert, the call agent
# hearing her words like on any night
ALERT_DEBUG_REASON = "She said: \"I'm feeling dizzy.\""
# A one-off reminder due this minute, agreed already, so the pillow says it within a reminder tick
DEMO_REMINDER = {
    "label": "take your evening tablets",
    "kind": "meds",
    "confirm": False,
    "channels": ["voice"],
}

# Profile photos the API accepts, the same limits as the resident-photos bucket
PHOTO_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_WRONG_TYPE = "The photo must be a JPEG, PNG or WebP image"
PHOTO_EMPTY = "The photo file is empty"
PHOTO_TOO_LARGE = "The photo must be 5 MB or smaller"

# Reminders (the Routine agent). What an occurrence is for: say the reminder, or ask her consent
REMIND_PURPOSE = "remind"
CONSENT_PURPOSE = "consent"
# reminders.consent: nothing plays until she agrees, asked by the pillow itself
CONSENT_PENDING = "pending"
CONSENT_AGREED = "agreed"
CONSENT_DECLINED = "declined"
# Changing any of these asks her again: she agrees to what is said and when
CONSENT_RESET_FIELDS = frozenset({"label", "kind", "time_of_day", "days", "on_date"})
# When the pillow asks about a pending reminder, in her timezone: from 09:00 for 12 hours (never at
# night), held like any reminder until she is up for the day, again an hour after no answer
CONSENT_ASK_AT = time(9, 0)
CONSENT_ASK_WINDOW = timedelta(hours=12)
CONSENT_RETRY_AFTER = timedelta(hours=1)
# Who asks, when the family member who set the reminder up is unknown
FAMILY_FALLBACK_NAME = "Your family"
# Longest range GET /reminders/calendar expands, in days (two months)
CALENDAR_MAX_DAYS = 62
# Spoken names, independent of the server's locale (ISO weekday 1 = Monday)
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
